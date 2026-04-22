from __future__ import annotations

import hashlib
import os
from pathlib import Path
from threading import Lock
from typing import Any

from blockchain import BlockChain

try:
    import duckdb
except Exception:  # pragma: no cover - optional dependency
    duckdb = None


class Ledger:
    """User ledger with local account state and blockchain payout integration."""

    # Fixed transfer fee (2% of transfer amount).
    FEE_RATE = 0.02
    _accounts: dict[str, float] = {}
    _reserved: dict[str, float] = {}
    _account_lock = Lock()

    def __init__(
        self,
        uid: str,
        db_path: str | Path | None = None,
        blockchain: BlockChain | None = None,
        project_root: str | Path | None = None,
    ) -> None:
        self.uid = str(uid)
        self.project_root = Path(project_root or Path(__file__).resolve().parent)
        self.db_path = Path(db_path or self.project_root / "oasis.duckdb")
        self.blockchain = blockchain or BlockChain(project_root=self.project_root)
        self.user_info: dict[str, Any] = {}
        self.deposit_address = self._generate_deposit_address()
        self.setup()

    def setup(self) -> dict[str, Any]:
        self.user_info = self._load_user_from_duckdb()
        self.check_create_isys_ledger()
        return self.user_info

    def _load_user_from_duckdb(self) -> dict[str, Any]:
        fallback = {"uid": self.uid}
        if duckdb is None or not self.db_path.exists():
            return fallback

        conn = duckdb.connect(str(self.db_path))
        try:
            rows = conn.execute("SELECT * FROM users WHERE uid = ?", [self.uid]).fetchall()
            if not rows:
                return fallback
            columns = [desc[0] for desc in conn.description]
            user_info = dict(zip(columns, rows[0]))
            if "uid" not in user_info:
                user_info["uid"] = self.uid
            return user_info
        except Exception:
            return fallback
        finally:
            conn.close()

    def _generate_deposit_address(self) -> str:
        digest = hashlib.sha256(self.uid.encode("utf-8")).hexdigest()
        return f"isys_{digest}"

    @classmethod
    def reset_accounts(cls) -> None:
        with cls._account_lock:
            cls._accounts.clear()
            cls._reserved.clear()

    def check_create_isys_ledger(self) -> dict[str, Any]:
        starting_balance_value = self.user_info.get("balance", 0.0)
        starting_balance = float(starting_balance_value) if starting_balance_value is not None else 0.0
        with self._account_lock:
            self._accounts.setdefault(self.uid, starting_balance)
        return {
            "uid": self.uid,
            "exists": True,
            "deposit_address": self.deposit_address,
            "balance": self._accounts[self.uid],
        }

    def deposit(self, amount: float) -> dict[str, Any]:
        amount_f = self._validate_positive_amount(amount)
        with self._account_lock:
            self._accounts[self.uid] = round(self._accounts[self.uid] + amount_f, 8)
            balance = self._accounts[self.uid]
        return {"uid": self.uid, "amount": amount_f, "deposit_address": self.deposit_address, "balance": balance}

    def get_metadata(self) -> dict[str, Any]:
        with self._account_lock:
            balance = self._accounts.get(self.uid, 0.0)
        return {
            "uid": self.uid,
            "user_info": dict(self.user_info),
            "deposit_address": self.deposit_address,
            "balance": balance,
            "fee_percent": self.FEE_RATE * 100,
            "coin_symbol": "ISYSUSDT",
        }

    def transaction(self, receiver_id: str, amount: float) -> dict[str, Any]:
        receiver = str(receiver_id)
        amount_f = self._validate_positive_amount(amount)
        fee = round(amount_f * self.FEE_RATE, 8)
        total_debit = round(amount_f + fee, 8)

        with self._account_lock:
            sender_balance = self._accounts.get(self.uid, 0.0)
            if sender_balance < total_debit:
                raise ValueError("insufficient funds")
            self._accounts.setdefault(receiver, 0.0)
            self._accounts[self.uid] = round(sender_balance - total_debit, 8)
            self._accounts[receiver] = round(self._accounts[receiver] + amount_f, 8)
            updated_sender = self._accounts[self.uid]
            updated_receiver = self._accounts[receiver]

        return {
            "from": self.uid,
            "to": receiver,
            "amount": amount_f,
            "fee": fee,
            "total_debit": total_debit,
            "sender_balance": updated_sender,
            "receiver_balance": updated_receiver,
        }

    def payout(self, amount: float) -> dict[str, Any]:
        amount_f = self._validate_positive_amount(amount)
        cashout_address = os.environ.get("CASHOUT_ADDRESS")
        if not cashout_address:
            raise ValueError("CASHOUT_ADDRESS is required")

        with self._account_lock:
            balance = self._accounts.get(self.uid, 0.0)
            if balance < amount_f:
                raise ValueError("insufficient funds")
            self._accounts[self.uid] = round(balance - amount_f, 8)
            self._reserved[self.uid] = round(self._reserved.get(self.uid, 0.0) + amount_f, 8)

        try:
            order = self.blockchain.buy_isys_coin(quantity=amount_f)
        except Exception:
            with self._account_lock:
                self._reserved[self.uid] = round(max(self._reserved.get(self.uid, 0.0) - amount_f, 0.0), 8)
                self._accounts[self.uid] = round(self._accounts[self.uid] + amount_f, 8)
            raise

        order_status = order.get("status")
        status = str(order_status) if order_status is not None else "unknown"
        with self._account_lock:
            self._reserved[self.uid] = round(max(self._reserved.get(self.uid, 0.0) - amount_f, 0.0), 8)
            if status != "completed":
                self._accounts[self.uid] = round(self._accounts[self.uid] + amount_f, 8)
            balance = self._accounts.get(self.uid, 0.0)

        return {
            "uid": self.uid,
            "cashout_address": cashout_address,
            "amount": amount_f,
            "balance": balance,
            "status": status,
            "order": order,
        }

    @staticmethod
    def _validate_positive_amount(amount: float) -> float:
        amount_f = float(amount)
        if amount_f <= 0:
            raise ValueError("amount must be greater than zero")
        return amount_f
