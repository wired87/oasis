from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class BlockChain:
    """Small blockchain integration wrapper with safe offline fallbacks."""

    def __init__(
        self,
        exchange: str | None = None,
        project_root: str | Path | None = None,
        kubernetes_os: str | None = None,
        request_fn: Any | None = None,
    ) -> None:
        self.exchange = (exchange or os.getenv("ISYS_EXCHANGE") or "binance").lower()
        self.project_root = Path(project_root or Path(__file__).resolve().parent)
        self.kubernetes_os = kubernetes_os or os.getenv("KUBERNETES_OS") or "local"
        self.request_fn = request_fn or urlopen
        self.coin_registry: dict[str, dict[str, Any]] = {}
        self.contract_registry: list[dict[str, Any]] = []

    def _http_json(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        req_headers = {"Content-Type": "application/json", **(headers or {})}
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(url, data=data, headers=req_headers, method=method)
        with self.request_fn(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body if isinstance(body, dict) else {}

    def _safe_http_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._http_json(*args, **kwargs)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return {}

    def register_isys_coin(self, symbol: str = "ISYSUSDT") -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "symbol": symbol,
            "exchange": self.exchange,
            "registered": False,
            "registered_at": datetime.now(UTC).isoformat(),
        }

        if self.exchange == "kraken":
            pair = symbol.replace("USDT", "USD")
            pair_data = self._safe_http_json(f"https://api.kraken.com/0/public/AssetPairs?pair={pair}")
            result = pair_data.get("result", {}) if isinstance(pair_data.get("result"), dict) else {}
            metadata.update(
                {
                    "registered": bool(result),
                    "raw": result,
                }
            )
        else:
            exchange_data = self._safe_http_json("https://api.binance.com/api/v3/exchangeInfo")
            symbols = exchange_data.get("symbols", []) if isinstance(exchange_data.get("symbols"), list) else []
            for row in symbols:
                if isinstance(row, dict) and row.get("symbol") == symbol:
                    metadata.update(
                        {
                            "registered": True,
                            "base_asset": row.get("baseAsset"),
                            "quote_asset": row.get("quoteAsset"),
                            "status": row.get("status"),
                            "raw": row,
                        }
                    )
                    break

        self.coin_registry[symbol] = metadata
        return metadata

    def _fetch_price(self, symbol: str) -> float:
        if self.exchange == "kraken":
            pair = symbol.replace("USDT", "USD")
            ticker = self._safe_http_json(f"https://api.kraken.com/0/public/Ticker?pair={pair}")
            result = ticker.get("result", {}) if isinstance(ticker.get("result"), dict) else {}
            if result:
                first_key = next(iter(result))
                ask = result.get(first_key, {}).get("a", ["0"])
                return float(ask[0]) if isinstance(ask, list) and ask else 0.0
            return 0.0

        ticker = self._safe_http_json(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
        return float(ticker.get("price", 0.0) or 0.0)

    def get_isys_coin_metadata(self, symbol: str = "ISYSUSDT") -> dict[str, Any]:
        registration = self.coin_registry.get(symbol) or self.register_isys_coin(symbol)
        amount = float(os.getenv("ISYS_COIN_AMOUNT", "0") or "0")
        price = self._fetch_price(symbol)
        metadata = {
            **registration,
            "amount": amount,
            "price": price,
            "value": round(amount * price, 8),
            "currency": "USDT",
        }
        self.coin_registry[symbol] = metadata
        return metadata

    def buy_isys_coin(self, quantity: float, symbol: str = "ISYSUSDT") -> dict[str, Any]:
        metadata = self.get_isys_coin_metadata(symbol)
        payment_master_id = os.getenv("PAYMENT_MASTER_ID")
        payment_master_secret = os.getenv("PAYMENT_MASTER_SECRET")
        order = {
            "symbol": symbol,
            "exchange": self.exchange,
            "quantity": float(quantity),
            "unit_price": metadata.get("price", 0.0),
            "total_price": round(float(quantity) * float(metadata.get("price", 0.0)), 8),
            "payment_master_id": payment_master_id,
            "ordered_at": datetime.now(UTC).isoformat(),
        }
        if payment_master_id and payment_master_secret:
            order["status"] = "completed"
            order["payment_method"] = "payment_master"
        else:
            order["status"] = "failed"
            order["reason"] = "missing_payment_master_credentials"
        return order

    def fetch_embeddings_from_pod(self, service_id: str) -> list[float]:
        pod_url = os.getenv("EMBEDDINGS_POD_URL", "http://localhost:8080/embeddings")
        query = urlencode({"service_id": service_id})
        response = self._safe_http_json(f"{pod_url}?{query}")
        embeddings = response.get("embeddings", []) if isinstance(response, dict) else []
        if isinstance(embeddings, list):
            return [float(x) for x in embeddings if isinstance(x, (float, int))]
        return []

    def register_contract(self, payload: dict[str, Any]) -> dict[str, Any]:
        service_id = str(payload.get("service_id") or "unknown_service")
        service_embeddings = payload.get("service_embeddings")
        if not isinstance(service_embeddings, list):
            service_embeddings = self.fetch_embeddings_from_pod(service_id)
        event_nodes = payload.get("event_nodes") if isinstance(payload.get("event_nodes"), list) else []

        contract = {
            "contract_id": f"contract:{service_id}",
            "service_id": service_id,
            "service_embeddings": service_embeddings,
            "event_nodes": event_nodes,
            "kubernetes_os": self.kubernetes_os,
            "smart_contract": {
                "version": "1.0",
                "type": "service_graph_contract",
                "created_at": datetime.now(UTC).isoformat(),
                "terms": {
                    "embedding_dimensions": len(service_embeddings),
                    "event_node_count": len(event_nodes),
                },
            },
        }

        endpoint = os.getenv("CONTRACT_REGISTRY_URL")
        if endpoint:
            body = self._safe_http_json(endpoint, method="POST", payload=contract)
            contract["status"] = "posted" if body else "post_failed"
            if body:
                contract["response"] = body
        else:
            contract["status"] = "stored_local"

        self.contract_registry.append(contract)
        return contract


def ingest_service_data(service_payload: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    blockchain = BlockChain()
    contracts: list[dict[str, Any]] = []
    for service_id, payload in service_payload.items():
        contracts.append(
            blockchain.register_contract(
                {
                    "service_id": service_id,
                    "service_embeddings": payload.get("service_embeddings", []),
                    "event_nodes": payload.get("event_nodes", []),
                }
            )
        )
    return contracts


def create_smart_contract(service_payload: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return ingest_service_data(service_payload)


def run(service_payload: dict[str, dict[str, Any]]) -> dict[str, Any]:
    blockchain = BlockChain()
    blockchain.register_isys_coin()
    metadata = blockchain.get_isys_coin_metadata()
    contracts = ingest_service_data(service_payload)
    return {"coin_metadata": metadata, "contracts": contracts}
