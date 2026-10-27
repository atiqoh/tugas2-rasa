"""
Unit test NLU service (tanpa model BERT: classifier diganti FakeClassifier sehingga
logika ekstraksi entitas, format respons Rasa, fallback, dan error handling bisa diuji
cepat).  Jalankan dari folder nlu-service:  python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, parse_shortcut              # noqa: E402
from entity_extractor import EntityExtractor            # noqa: E402
from text_normalizer import normalize_for_model         # noqa: E402


class FakeClassifier:
    """Mengembalikan intent berdasar kata kunci sederhana pada teks yang sudah dimasking."""
    labels = ["check_stock", "greet", "check_order_status", "out_of_scope"]
    meta = {"base_model": "fake"}

    def predict(self, text, top_k=5):
        if "<product>" in text:
            return [("check_stock", 0.93), ("ask_price", 0.04)]
        if "<order_id>" in text or "pesanan" in text:
            return [("check_order_status", 0.88), ("provide_order_id", 0.1)]
        if "halo" in text:
            return [("greet", 0.97)]
        if "ready" in text:
            return [("check_stock", 0.9), ("ask_price", 0.05)]
        return [("out_of_scope", 0.31), ("greet", 0.2)]


class TestNormalizer(unittest.TestCase):
    def test_slang_and_placeholders(self):
        self.assertEqual(normalize_for_model("Brp hrg <product> kak??"),
                         "berapa harga <product> kak ? ?")
        self.assertEqual(normalize_for_model("udh nyampe blm"), "sudah sampai belum")
        self.assertEqual(normalize_for_model("halooooo"), "haloo")


class TestEntityExtractor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = EntityExtractor.from_resources()

    def ents(self, text):
        return {(e["entity"], e["value"]) for e in self.ex.extract(text)[1]}

    def test_product_exact_and_alias(self):
        self.assertIn(("product", "iPhone X"), self.ents("kak iphone x ready?"))
        self.assertIn(("product", "Lenovo Yoga 920"), self.ents("lenovo yoga 920 ready"))
        self.assertIn(("product", "Apple"), self.ents("harga apel berapa"))

    def test_product_fuzzy_typo(self):
        e = self.ex.extract("iphon x ready?")[1]
        self.assertEqual(e[0]["value"], "iPhone X")
        self.assertEqual(e[0]["extractor"], "FuzzyGazetteerEntityExtractor")

    def test_ambiguous_hp_is_category_not_product(self):
        self.assertEqual(self.ents("ada hp apa aja"), {("category", "smartphones")})

    def test_category_group(self):
        self.assertIn(("category", "mens-shoes,womens-shoes"), self.ents("ada sepatu apa aja"))

    def test_order_id_formats(self):
        for t in ["cek ORD-10101", "resi #10101", "pesanan 10101", "ord10101 dong"]:
            self.assertIn(("order_id", "10101"), self.ents(t), t)
        self.assertNotIn("order_id", {e for e, _ in self.ents("stok 123456 unit")})

    def test_order_word_kept_for_classifier(self):
        masked, _ = self.ex.extract("order 10120 ya")
        self.assertEqual(masked, "order <order_id> ya")

    def test_email_and_offsets(self):
        text = "Email Saya Emily.Johnson@x.dummyjson.com ya"
        masked, ents = self.ex.extract(text)
        self.assertEqual(masked, "Email Saya <email> ya")
        e = ents[0]
        self.assertEqual(e["value"], "emily.johnson@x.dummyjson.com")
        self.assertEqual(text[e["start"]:e["end"]].lower(), e["value"])

    def test_unknown_product_not_masked(self):
        masked, ents = self.ex.extract("redmi note 13 ready gak")
        self.assertEqual(ents, [])
        self.assertEqual(masked, "redmi note 13 ready gak")

    def test_no_false_positive_on_common_chat(self):
        for t in ["pesanan saya kok belum datang?", "terima kasih banyak kak",
                  "cara bayarnya gimana?", "halo admin selamat pagi"]:
            self.assertEqual(self.ex.extract(t)[1], [], t)


class TestTrainingDataMasking(unittest.TestCase):
    """Semua nama produk katalog di data latih harus berhasil dimasking oleh extractor
    (kecuali yang sengaja diberi salah ketik oleh augmentasi)."""

    def test_known_products_masked(self):
        import json
        import pandas as pd
        ex = EntityExtractor.from_resources()
        df = pd.read_csv(Path(__file__).resolve().parents[2] / "datasets" / "nlu_train.csv")
        df = df[df.entities.fillna("").str.contains('"entity": "product"')]
        masked = [("<product>" in ex.prepare(t)[0]) for t in df.text]
        rate = sum(masked) / len(masked)
        self.assertGreater(rate, 0.93, f"hanya {rate:.1%} produk ter-masking")


class TestFlaskApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app(classifier=FakeClassifier(), threshold=0.5).test_client()

    def test_parse_rasa_format(self):
        r = self.client.post("/model/parse", json={"text": "iPhone X ready kak?",
                                                    "message_id": "u1", "token": None})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["text"], "iPhone X ready kak?")
        self.assertEqual(d["intent"]["name"], "check_stock")
        self.assertIsInstance(d["intent"]["confidence"], float)
        self.assertEqual(d["entities"][0]["entity"], "product")
        self.assertEqual(d["entities"][0]["value"], "iPhone X")
        self.assertEqual(d["entities"][0]["start"], 0)
        self.assertEqual(d["entities"][0]["end"], 8)
        self.assertEqual(d["intent_ranking"][0]["name"], "check_stock")

    def test_low_confidence_becomes_nlu_fallback(self):
        d = self.client.post("/model/parse", json={"text": "cuaca hari ini"}).get_json()
        self.assertEqual(d["intent"]["name"], "nlu_fallback")
        self.assertEqual(d["intent_ranking"][1]["name"], "out_of_scope")

    def test_shortcut_payload(self):
        d = self.client.post("/model/parse", json={"text": "/session_start"}).get_json()
        self.assertEqual(d["intent"], {"name": "session_start", "confidence": 1.0})
        d = self.client.post("/model/parse",
                             json={"text": '/check_stock{"product": "iPhone X"}'}).get_json()
        self.assertEqual(d["intent"]["name"], "check_stock")
        self.assertEqual(d["entities"][0]["value"], "iPhone X")

    def test_bad_requests(self):
        self.assertEqual(self.client.post("/model/parse", data="xx").status_code, 400)
        self.assertEqual(self.client.post("/model/parse", json={"txt": 1}).status_code, 400)
        self.assertEqual(self.client.post("/model/parse", json={"text": 5}).status_code, 400)
        self.assertEqual(self.client.get("/model/parse").status_code, 405)
        self.assertEqual(self.client.get("/model/parse").get_json()["error"][:6], "The me")

    def test_unknown_product_candidate_for_product_intent(self):
        d = self.client.post("/model/parse", json={"text": "redmi note 13 ready gak kak"}).get_json()
        self.assertEqual(d["intent"]["name"], "check_stock")
        self.assertEqual(d["entities"], [{"entity": "product", "value": "redmi note 13",
                                          "start": 0, "end": 13, "confidence_entity": 0.5,
                                          "extractor": "ProductCandidateHeuristic"}])

    def test_no_candidate_for_generic_question(self):
        d = self.client.post("/model/parse", json={"text": "stoknya masih ready kak?"}).get_json()
        self.assertEqual(d["intent"]["name"], "check_stock")
        self.assertEqual(d["entities"], [])

    def test_empty_text_falls_back(self):
        d = self.client.post("/model/parse", json={"text": "   "}).get_json()
        self.assertEqual(d["intent"]["name"], "nlu_fallback")

    def test_health(self):
        self.assertEqual(self.client.get("/health").get_json()["status"], "ok")


class TestShortcutParser(unittest.TestCase):
    def test_not_a_shortcut(self):
        self.assertIsNone(parse_shortcut("/ halo"))
        self.assertIsNone(parse_shortcut("halo"))


if __name__ == "__main__":
    unittest.main()
