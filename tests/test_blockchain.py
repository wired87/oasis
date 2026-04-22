import os
import unittest
from unittest.mock import patch

from blockchain import (
    BlockChain,
    create_smart_contract,
    create_smart_contracts,
    ingest_service_data,
    run,
    setup_coin_and_contracts,
)


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
            with patch.dict("os.environ", {"PAYMENT_MASTER_ID": "pm_1", "PAYMENT_MASTER_SECRET": "secret"}):
                order = chain.buy_isys_coin(quantity=4)

        self.assertEqual(order["status"], "completed")
        self.assertEqual(order["total_price"], 5.0)
        self.assertEqual(order["payment_method"], "payment_master")

    def test_buy_isys_coin_fails_without_payment_master_env(self):
        chain = BlockChain(exchange="binance")
        with patch.object(chain, "get_isys_coin_metadata", return_value={"price": 1.25}):
            with patch.dict("os.environ", {}, clear=True):
                order = chain.buy_isys_coin(quantity=1)

        self.assertEqual(order["status"], "failed")
        self.assertEqual(order["reason"], "missing_payment_master_credentials")

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

    def test_register_isys_coin_and_fetch_price_for_kraken(self):
        chain = BlockChain(exchange="kraken")
        with patch.object(
            chain,
            "_safe_http_json",
            side_effect=[
                {"result": {"ISYSUSD": {"wsname": "ISYS/USD"}}},
                {"result": {"ISYSUSD": {"a": ["3.4"]}}},
            ],
        ):
            registration = chain.register_isys_coin("ISYSUSDT")
            price = chain._fetch_price("ISYSUSDT")

        self.assertTrue(registration["registered"])
        self.assertEqual(price, 3.4)

    def test_fetch_embeddings_from_pod(self):
        chain = BlockChain()
        with patch.dict("os.environ", {"EMBEDDINGS_POD_URL": "https://embeddings.local/pod"}):
            with patch.object(chain, "_safe_http_json", return_value={"embeddings": [0.1, 1, "x"]}) as mocked:
                embeddings = chain.fetch_embeddings_from_pod("service:maps")

        self.assertEqual(embeddings, [0.1, 1.0])
        self.assertIn("service_id=service%3Amaps", mocked.call_args[0][0])
        with patch.dict("os.environ", {"EMBEDDINGS_POD_URL": "https://embeddings.local/pod"}):
            with patch.object(chain, "_safe_http_json", return_value={"embeddings": "bad"}):
                self.assertEqual(chain.fetch_embeddings_from_pod("service:maps"), [])
            with patch.object(chain, "_safe_http_json", return_value={}):
                self.assertEqual(chain.fetch_embeddings_from_pod("service:maps"), [])
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(chain.fetch_embeddings_from_pod("service:maps"), [])

    def test_register_contract_requires_service_id(self):
        chain = BlockChain()
        with self.assertRaises(ValueError):
            chain.register_contract({"event_nodes": []})

    def test_wrapper_entrypoints_delegate(self):
        payload = {"service:maps": {"service_embeddings": [0.1], "event_nodes": []}}
        with patch("blockchain.ingest_service_data", return_value=[{"service_id": "service:maps"}]) as mocked_ingest:
            self.assertEqual(create_smart_contracts(payload), [{"service_id": "service:maps"}])
            self.assertEqual(create_smart_contract(payload), {"service_id": "service:maps"})
            mocked_ingest.assert_called_with(payload)

        with patch("blockchain.BlockChain.register_isys_coin"), patch(
            "blockchain.BlockChain.get_isys_coin_metadata", return_value={"symbol": "ISYSUSDT"}
        ), patch("blockchain.create_smart_contracts", return_value=[{"service_id": "service:maps"}]):
            setup_result = setup_coin_and_contracts(payload)
            run_result = run(payload)
        self.assertEqual(setup_result["coin_metadata"]["symbol"], "ISYSUSDT")
        self.assertEqual(run_result["contracts"][0]["service_id"], "service:maps")


if __name__ == "__main__":
    unittest.main()
