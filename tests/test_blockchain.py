import os
import unittest
from unittest.mock import patch

from blockchain import BlockChain, ingest_service_data


class TestBlockChain(unittest.TestCase):
    def test_get_isys_coin_metadata_merges_registration_and_value(self):
        chain = BlockChain(exchange="binance")
        with patch.object(
            chain,
            "_safe_http_json",
            side_effect=[
                {
                    "symbols": [
                        {
                            "symbol": "ISYSUSDT",
                            "baseAsset": "ISYS",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                        }
                    ]
                },
                {"price": "2.5"},
            ],
        ):
            with patch.dict(os.environ, {"ISYS_COIN_AMOUNT": "3"}, clear=False):
                meta = chain.get_isys_coin_metadata("ISYSUSDT")

        self.assertTrue(meta["registered"])
        self.assertEqual(meta["base_asset"], "ISYS")
        self.assertEqual(meta["amount"], 3.0)
        self.assertEqual(meta["price"], 2.5)
        self.assertEqual(meta["value"], 7.5)

    def test_buy_isys_coin_uses_payment_master_env(self):
        chain = BlockChain(exchange="binance")
        with patch.object(chain, "get_isys_coin_metadata", return_value={"price": 1.25}):
            with patch.dict(
                os.environ,
                {"PAYMENT_MASTER_ID": "pm_1", "PAYMENT_MASTER_SECRET": "secret"},
                clear=False,
            ):
                order = chain.buy_isys_coin(quantity=4)

        self.assertEqual(order["status"], "completed")
        self.assertEqual(order["total_price"], 5.0)
        self.assertEqual(order["payment_method"], "payment_master")

    def test_register_contract_local_fallback_and_ingest(self):
        chain = BlockChain(kubernetes_os="local")
        contract = chain.register_contract(
            {
                "service_id": "service:maps",
                "service_embeddings": [0.1, 0.2],
                "event_nodes": [{"event_id": "evt_1"}],
            }
        )

        self.assertEqual(contract["status"], "stored_local")
        self.assertEqual(contract["kubernetes_os"], "local")
        self.assertEqual(contract["smart_contract"]["terms"]["embedding_dimensions"], 2)

        contracts = ingest_service_data(
            {
                "service:maps": {
                    "service_embeddings": [0.1, 0.2],
                    "event_nodes": [{"event_id": "evt_1"}],
                }
            }
        )
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0]["service_id"], "service:maps")


if __name__ == "__main__":
    unittest.main()
