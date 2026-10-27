"""
Tes integrasi custom actions: action Rasa -> HTTP -> handler api-service -> SQL.
Agar bisa berjalan tanpa MySQL/Express, tes ini menyalakan api-service/tools/
sqlite-dev-server.js (node:http + SQLite berisi data yang sama dengan olshop_db.sql).

Jalankan dari folder rasa-bot (venv Rasa aktif, Node >= 22.13 terpasang):
    python -m unittest discover -s tests -v
"""
import os
import socket
import subprocess
import sys
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORT = 4100
os.environ["OLSHOP_API_URL"] = f"http://127.0.0.1:{PORT}"
sys.path.insert(0, str(ROOT / "rasa-bot"))


def _import_rasa_sdk():
    """Pakai rasa_sdk asli. Bila dependensi server-nya (sanic, ruamel) tidak terpasang
    (mis. di sandbox CI), stub HANYA modul yang tidak dipakai oleh action."""
    try:
        import rasa_sdk  # noqa: F401
        return
    except ImportError:
        for mod in [m for m in sys.modules if m.startswith("rasa_sdk")]:
            del sys.modules[mod]
    for name in ("rasa_sdk.cli", "rasa_sdk.plugin"):
        sys.modules[name] = types.ModuleType(name)
    ruamel = types.ModuleType("ruamel")
    ry = types.ModuleType("ruamel.yaml")
    ry.YAMLError = Exception
    rc = types.ModuleType("ruamel.yaml.constructor")
    rc.DuplicateKeyError = Exception
    re_ = types.ModuleType("ruamel.yaml.error")
    re_.MarkedYAMLError = re_.MarkedYAMLWarning = re_.MarkedYAMLFutureWarning = Exception
    ry.__path__ = []
    ruamel.yaml = ry
    sys.modules.update({"ruamel": ruamel, "ruamel.yaml": ry, "ruamel.yaml.constructor": rc,
                        "ruamel.yaml.error": re_})
    import rasa_sdk  # noqa: F401


_import_rasa_sdk()
from rasa_sdk import Tracker                                   # noqa: E402
from rasa_sdk.executor import CollectingDispatcher             # noqa: E402
from actions import actions as A                               # noqa: E402

DOMAIN = {"slots": {}, "forms": {}}


def make_tracker(slots=None, text="", intent="", entities=None, events=None,
                 active_loop=None):
    return Tracker(
        sender_id="test",
        slots=slots or {},
        latest_message={"text": text, "intent": {"name": intent, "confidence": 1.0},
                        "entities": entities or []},
        events=events or [],
        paused=False,
        followup_action=None,
        active_loop={"name": active_loop} if active_loop else {},
        latest_action_name="action_listen",
    )


def run(action, tracker):
    d = CollectingDispatcher()
    events = action.run(d, tracker, DOMAIN)
    return [m.get("text") or m.get("response") for m in d.messages], events


def slot_events(events):
    return {e["name"]: e["value"] for e in events if e.get("event") == "slot"}


class ActionIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen(
            ["node", str(ROOT / "api-service" / "tools" / "sqlite-dev-server.js"), str(PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("sqlite-dev-server gagal start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)

    # ------------------------------------------------------------- produk
    def test_stock_single_product(self):
        msgs, ev = run(A.ActionProductLookup(),
                       make_tracker({"product": "iPhone X", "product_query_type": "stock"}))
        self.assertIn("iPhone X ready kak, stok 37 unit", msgs[0])
        self.assertEqual(slot_events(ev)["product"], "iPhone X")

    def test_stock_out_of_stock(self):
        msgs, _ = run(A.ActionProductLookup(),
                      make_tracker({"product": "Samsung Galaxy S8", "product_query_type": "stock"}))
        self.assertIn("sedang habis", msgs[0])
        self.assertIn("Smartphone", msgs[0])

    def test_price_with_discount(self):
        msgs, _ = run(A.ActionProductLookup(),
                      make_tracker({"product": "iPhone X", "product_query_type": "price"}))
        self.assertIn("Harga iPhone X: Rp11.578.900 (diskon 20% dari Rp14.399.800)", msgs[0])

    def test_info_product(self):
        msgs, _ = run(A.ActionProductLookup(),
                      make_tracker({"product": "Lenovo Yoga 920", "product_query_type": "info"}))
        self.assertIn("Merek: Lenovo", msgs[0])
        self.assertIn("Garansi 6 bulan", msgs[0])

    def test_brand_keyword_gives_list(self):
        msgs, _ = run(A.ActionProductLookup(),
                      make_tracker({"product": "rolex", "product_query_type": "stock"}))
        self.assertTrue(msgs[0].startswith("Ada 5 produk yang cocok"))

    def test_unknown_product(self):
        msgs, ev = run(A.ActionProductLookup(),
                       make_tracker({"product": "redmi note 13", "product_query_type": "stock"}))
        self.assertIn("tidak ditemukan", msgs[0])
        self.assertIsNone(slot_events(ev)["product"])

    # ----------------------------------------------------------- kategori
    def test_browse_all_categories(self):
        msgs, _ = run(A.ActionBrowseCategory(), make_tracker(text="kategori apa aja"))
        self.assertIn("Kategori produk di OlshopKu", msgs[0])
        self.assertEqual(msgs[0].count("•"), 24)

    def test_browse_one_category_group(self):
        t = make_tracker(text="ada sepatu apa aja", entities=[
            {"entity": "category", "value": "mens-shoes,womens-shoes"}])
        msgs, _ = run(A.ActionBrowseCategory(), t)
        self.assertIn("Sepatu Pria & Sepatu Wanita", msgs[0])

    # ----------------------------------------------------- status pesanan
    def test_order_status_owner_ok(self):
        msgs, ev = run(A.ActionCheckOrderStatus(), make_tracker(
            {"order_id": "10003", "customer_email": "sophia.brown@x.dummyjson.com"}))
        self.assertIn("Pesanan #10003 a.n. Sophia Brown", msgs[0])
        self.assertIn("Status: Dalam pengiriman", msgs[0])
        self.assertIn("Resi:", msgs[0])
        self.assertEqual(slot_events(ev), {"order_id": None})

    def test_order_status_wrong_owner(self):
        msgs, ev = run(A.ActionCheckOrderStatus(), make_tracker(
            {"order_id": "10003", "customer_email": "emily.johnson@x.dummyjson.com"}))
        self.assertIn("tidak ditemukan atau email-nya tidak cocok", msgs[0])
        self.assertEqual(slot_events(ev), {"order_id": None, "customer_email": None})

    # ---------------------------------------------------- data pelanggan
    def test_customer_data(self):
        msgs, _ = run(A.ActionCheckCustomerData(),
                      make_tracker({"customer_email": "emily.johnson@x.dummyjson.com"}))
        self.assertIn("Nama: Emily Johnson", msgs[0])
        self.assertIn("No. HP: ********3024", msgs[0])
        self.assertIn("#10001", msgs[0])

    def test_customer_not_found(self):
        msgs, ev = run(A.ActionCheckCustomerData(),
                       make_tracker({"customer_email": "nobody@example.com"}))
        self.assertIn("belum terdaftar", msgs[0])
        self.assertIsNone(slot_events(ev)["customer_email"])

    # ------------------------------------------------- service mati
    def test_api_down(self):
        down = A.OlshopApi(base_url="http://127.0.0.1:9")
        old, A.api = A.api, down
        try:
            msgs, _ = run(A.ActionCheckCustomerData(),
                          make_tracker({"customer_email": "emily.johnson@x.dummyjson.com"}))
            self.assertEqual(msgs, ["utter_api_error"])
        finally:
            A.api = old


class FormValidationTest(unittest.TestCase):
    """Validasi slot memakai FormValidationAction.run asli dari rasa_sdk."""

    @classmethod
    def setUpClass(cls):
        ActionIntegrationTest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        ActionIntegrationTest.tearDownClass.__func__(cls)

    def _validate(self, action, slot, value, text="", entities=None, form="x"):
        events = [{"event": "user", "text": text},
                  {"event": "slot", "name": slot, "value": value}]
        t = make_tracker({slot: value}, text=text, entities=entities, events=events,
                         active_loop=form)
        d = CollectingDispatcher()
        import asyncio
        domain = {"forms": {form: {"required_slots": [slot]}}, "slots": {slot: {}}}
        out = asyncio.run(action.run(d, t, domain))
        return slot_events(out)[slot], d.messages

    def test_order_id_extracted_from_text(self):
        v, _ = self._validate(A.ValidateOrderStatusForm(), "order_id", "nomornya #10023 kak",
                              form="order_status_form")
        self.assertEqual(v, "10023")

    def test_order_id_invalid(self):
        v, msgs = self._validate(A.ValidateOrderStatusForm(), "order_id", "123",
                                 form="order_status_form")
        self.assertIsNone(v)
        self.assertEqual(msgs[0]["response"], "utter_invalid_order_id")

    def test_email_valid_and_invalid(self):
        v, _ = self._validate(A.ValidateCustomerDataForm(), "customer_email",
                              "Emily.Johnson@x.dummyjson.com", form="customer_data_form")
        self.assertEqual(v, "emily.johnson@x.dummyjson.com")
        v, msgs = self._validate(A.ValidateCustomerDataForm(), "customer_email",
                                 "emily@gmail", form="customer_data_form")
        self.assertIsNone(v)
        self.assertEqual(msgs[0]["response"], "utter_invalid_email")

    def test_product_free_text_cleaned_and_checked(self):
        v, _ = self._validate(A.ValidateProductForm(), "product", "yang lenovo yoga 920 kak",
                              text="yang lenovo yoga 920 kak", form="product_form")
        self.assertEqual(v, "lenovo yoga 920")

    def test_product_entity_preferred(self):
        v, _ = self._validate(A.ValidateProductForm(), "product", "itu iphon x dong",
                              text="itu iphon x dong", form="product_form",
                              entities=[{"entity": "product", "value": "iPhone X"}])
        self.assertEqual(v, "iPhone X")

    def test_product_not_in_catalog(self):
        v, msgs = self._validate(A.ValidateProductForm(), "product", "poco x5",
                                 text="poco x5", form="product_form")
        self.assertIsNone(v)
        self.assertIn("tidak ada di katalog", msgs[0]["text"])


class HelperTest(unittest.TestCase):
    def test_rupiah_and_tanggal(self):
        self.assertEqual(A.rupiah(14399800), "Rp14.399.800")
        self.assertEqual(A.tanggal("2026-10-12 14:22:00", with_time=True), "12 Okt 2026 14:22")


if __name__ == "__main__":
    unittest.main()
