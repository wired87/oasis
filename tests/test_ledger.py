import os
import unittest
from unittest.mock import Mock, patch

from ledger import Ledger


class TestLedger(unittest.TestCase):
    def setUp(self):
        Ledger.reset_accounts()

    def test_setup_loads_user_from_duckdb_when_available(self):
        fake_conn = Mock()
        fake_conn.execute.return_value = fake_conn
        fake_conn.fetchall.return_value = [("u-1", "alice", 12.5)]
        fake_conn.description = [("uid",), ("name",), ("balance",)]
        with patch("ledger.duckdb", Mock(connect=Mock(return_value=fake_conn))), patch(
            "ledger.Path.exists", return_value=True
        ):
            ledger = Ledger(uid="u-1")
        self.assertEqual(ledger.user_info["name"], "alice")
        self.assertEqual(ledger.get_metadata()["balance"], 12.5)

    def test_deposit_and_transaction_apply_two_percent_fee(self):
        sender = Ledger(uid="sender")
        sender.deposit(100)

        tx = sender.transaction(receiver_id="receiver", amount=50)
        self.assertEqual(tx["fee"], 1.0)
        self.assertEqual(tx["total_debit"], 51.0)
        self.assertEqual(tx["sender_balance"], 49.0)

        receiver = Ledger(uid="receiver")
        self.assertEqual(receiver.get_metadata()["balance"], 50.0)

    def test_payout_uses_cashout_address_and_blockchain_workflow(self):
        blockchain = Mock()
        blockchain.buy_isys_coin.return_value = {"status": "completed", "symbol": "ISYSUSDT"}
        ledger = Ledger(uid="u-2", blockchain=blockchain)
        ledger.deposit(20)

        with patch.dict(os.environ, {"CASHOUT_ADDRESS": "isys_cashout_wallet"}, clear=False):
            result = ledger.payout(10)

        blockchain.buy_isys_coin.assert_called_once_with(quantity=10.0)
        self.assertEqual(result["cashout_address"], "isys_cashout_wallet")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["balance"], 10.0)

    def test_payout_requires_cashout_address(self):
        ledger = Ledger(uid="u-3")
        ledger.deposit(5)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                ledger.payout(1)

    def test_failed_payout_refunds_balance(self):
        blockchain = Mock()
        blockchain.buy_isys_coin.return_value = {"status": "failed", "reason": "payment_error"}
        ledger = Ledger(uid="u-4", blockchain=blockchain)
        ledger.deposit(9)
        with patch.dict(os.environ, {"CASHOUT_ADDRESS": "isys_cashout_wallet"}, clear=False):
            result = ledger.payout(4)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["balance"], 9.0)


if __name__ == "__main__":
    unittest.main()
