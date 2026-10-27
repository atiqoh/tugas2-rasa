"""
Entity extractor hibrida (slide bab 3 "Hybrid Approach" + bab 7 "modtext"):

  1. Regex      -> email, order_id (5 digit, boleh diawali "#" atau "ORD-")
  2. Gazetteer  -> product (judul/alias produk dari database), category (sinonim Indonesia)
  3. Fuzzy      -> product dengan salah ketik ringan ("iphon x" -> "iPhone X"),
                   memakai difflib (tanpa dependensi tambahan)

Setelah entitas ditemukan, span-nya diganti placeholder (<email>, <order_id>, <product>,
<category>) sehingga classifier intent hanya melihat POLA kalimat, bukan nilai spesifik.
Ini persis teknik `modtext` pada myInterpreter.py di modul bab 7.

Format entitas mengikuti format Rasa:
  {"entity": "product", "value": "iPhone X", "start": 4, "end": 12,
   "confidence_entity": 1.0, "extractor": "GazetteerEntityExtractor"}
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from text_normalizer import basic_clean, normalize_for_model

RES_DIR = Path(__file__).resolve().parent / "resources"

EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
# alt-1: "ord10023" / "ORD-10023" / "ord 10023";  alt-2: "#10023" / "10023"
ORDER_RE = re.compile(r"\bord[-\s]?(\d{5})(?!\d)|#?(?<![\w])(\d{5})(?!\d)")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:['\-][a-z0-9]+)*|&")

# Kata umum chat yang tidak boleh dicocokkan secara fuzzy ke nama produk.
COMMON_WORDS = set("""
ada apa aja saja apakah atau bagaimana bantu barang beli belum berapa berapaan bisa boleh
buat cek coba dong dari dengan di dia diskon gak gan ganti garansi gimana halo harga hari
ini itu iya jual juga kak kakak kalau kami kamu kapan katalog kategori kenapa kirim kok
lagi lihat masih mau min minta mohon nanya nih order paket pakai pesan pesanan produk promo
ready retur saya sama sampai sih sis spesifikasi stok sudah tanya terima tidak tolong toko
tersedia untuk yang ya admin habis info kasih makasih status email nomor kurir ongkir
pengiriman tahu thanks thank please stock price available pembayaran bayar akun data
""".split())

# Kata yang dibuang saat menebak "kandidat nama produk" yang tidak ada di gazetteer.
CANDIDATE_STOPWORDS = COMMON_WORDS | set("""
stoknya harganya barangnya produknya readystock restock sisa tinggal unit pcs biji brp hrg
gk ga gak nggak ngga enggak tdk udh udah sdh blm yg dgn utk aja dah kah kak kk min gan sis
the is in of a an how much does have stock still cek dicek berapaan dijual mahal murah bagus
info detail spek garansinya kualitas review rating jelasin tentang tell me about apakah
kosong ketersediaan masih tolong dong deh ya yah nih sih kan pun lho lama baru sekarang
mana dimana kapan minggu bulan tahun kira kira-kira bener benar emang memang punya dapat
""".split())
PRODUCT_INTENTS = {"check_stock", "ask_price", "ask_product_info"}

# Kata yang terlalu umum/ambigu untuk dianggap nama produk walau cocok persis
# (contoh ambiguitas leksikal: "hp" = handphone, bukan merek laptop HP).
BLOCKED_PRODUCT_ALIASES = {"hp", "air", "set", "box", "date", "master", "ultra", "wash"}


def tokenize_with_offsets(text: str):
    return [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


@dataclass
class Span:
    start: int
    end: int
    entity: str
    value: str
    confidence: float
    extractor: str

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end


class EntityExtractor:
    def __init__(self, products_gazetteer: dict[str, str], category_synonyms: dict[str, list],
                 fuzzy_threshold: float = 0.86):
        self.fuzzy_threshold = fuzzy_threshold
        self.products: dict[tuple, str] = {}
        for alias, value in products_gazetteer.items():
            key = tuple(t for t, _, _ in tokenize_with_offsets(alias.lower()))
            if key and " ".join(key) not in BLOCKED_PRODUCT_ALIASES:
                self.products[key] = value
        self.categories: dict[tuple, str] = {}
        for phrase, slugs in category_synonyms.items():
            key = tuple(t for t, _, _ in tokenize_with_offsets(phrase.lower()))
            if key:
                self.categories[key] = ",".join(slugs)
        self.max_n = max(len(k) for k in list(self.products) + list(self.categories))
        # kunci untuk fuzzy: hanya alias cukup panjang
        self._fuzzy_keys = [(" ".join(k), v) for k, v in self.products.items()
                            if len(" ".join(k)) >= 5]

    # ------------------------------------------------------------------
    @classmethod
    def from_resources(cls, res_dir: Path = RES_DIR, **kw) -> "EntityExtractor":
        gaz = json.loads((res_dir / "products_gazetteer.json").read_text(encoding="utf-8"))
        cats = json.loads((res_dir / "category_synonyms.json").read_text(encoding="utf-8"))
        return cls(gaz, cats, **kw)

    # ------------------------------------------------------------------
    def _regex_spans(self, low: str) -> list[Span]:
        spans: list[Span] = []
        for m in EMAIL_RE.finditer(low):
            spans.append(Span(m.start(), m.end(), "email", m.group(0), 1.0,
                              "RegexEntityExtractor"))
        for m in ORDER_RE.finditer(low):
            s = Span(m.start(), m.end(), "order_id", m.group(1) or m.group(2), 1.0,
                     "RegexEntityExtractor")
            if not any(s.overlaps(x) for x in spans):
                spans.append(s)
        return spans

    def _gazetteer_spans(self, low: str, taken: list[Span]) -> list[Span]:
        toks = tokenize_with_offsets(low)
        cands: list[tuple[int, Span]] = []
        for i in range(len(toks)):
            for n in range(min(self.max_n, len(toks) - i), 0, -1):
                key = tuple(t for t, _, _ in toks[i:i + n])
                start, end = toks[i][1], toks[i + n - 1][2]
                if key in self.products:
                    cands.append((n, Span(start, end, "product", self.products[key], 1.0,
                                          "GazetteerEntityExtractor")))
                if key in self.categories:
                    cands.append((n, Span(start, end, "category", self.categories[key], 1.0,
                                          "GazetteerEntityExtractor")))
        # pilih span terpanjang dulu, tidak boleh tumpang tindih
        cands.sort(key=lambda c: (-c[0], c[1].start, c[1].entity != "category"))
        chosen: list[Span] = []
        for _, sp in cands:
            if not any(sp.overlaps(x) for x in taken + chosen):
                chosen.append(sp)
        return chosen

    def _fuzzy_product(self, low: str, taken: list[Span]) -> Span | None:
        toks = [t for t in tokenize_with_offsets(low)
                if not any(Span(t[1], t[2], "", "", 0, "").overlaps(x) for x in taken)]
        best: tuple[float, int, Span] | None = None
        for i in range(len(toks)):
            for n in (3, 2, 1):
                if i + n > len(toks):
                    continue
                window = toks[i:i + n]
                # token harus bersebelahan di teks asli
                if any(window[k + 1][1] - window[k][2] > 1 for k in range(n - 1)):
                    continue
                words = [w for w, _, _ in window]
                if all(w in COMMON_WORDS or w.isdigit() for w in words):
                    continue
                if words[0] in COMMON_WORDS or words[-1] in COMMON_WORDS:
                    continue
                phrase = " ".join(words)
                if len(phrase) < 5:
                    continue
                for key, value in self._fuzzy_keys:
                    if abs(len(key) - len(phrase)) > 2:
                        continue
                    r = difflib.SequenceMatcher(None, phrase, key).ratio()
                    if r >= self.fuzzy_threshold and (best is None or (r, n) > best[:2]):
                        best = (r, n, Span(window[0][1], window[-1][2], "product", value,
                                           round(r, 3), "FuzzyGazetteerEntityExtractor"))
        return best[2] if best else None

    # ------------------------------------------------------------------
    def extract(self, text: str) -> tuple[str, list[dict]]:
        """Kembalikan (masked_text, entities). Posisi start/end mengacu ke teks asli."""
        text = basic_clean(text)
        low = text.lower()
        if len(low) != len(text):          # jaga-jaga karakter unicode yang berubah panjang
            low = "".join(c.lower() if len(c.lower()) == 1 else c for c in text)
        spans = self._regex_spans(low)
        spans += self._gazetteer_spans(low, spans)
        if not any(s.entity == "product" for s in spans):
            fz = self._fuzzy_product(low, spans)
            if fz:
                spans.append(fz)
        spans.sort(key=lambda s: s.start)
        masked = text
        for s in sorted(spans, key=lambda s: s.start, reverse=True):
            masked = masked[:s.start] + f"<{s.entity}>" + masked[s.end:]
        entities = [{"entity": s.entity, "value": s.value, "start": s.start, "end": s.end,
                     "confidence_entity": s.confidence, "extractor": s.extractor}
                    for s in spans]
        return masked, entities

    def guess_product_candidate(self, text: str, entities: list[dict]) -> dict | None:
        """Untuk intent produk tanpa entitas product (mis. "redmi note 13 ready?"), ambil
        rangkaian kata terpanjang yang bukan kata umum sebagai KANDIDAT nama produk.
        Kandidat ini divalidasi ke database oleh custom action; jika tidak ada, bot
        menjawab "produk tidak ditemukan" alih-alih bertanya ulang nama produknya."""
        low = basic_clean(text).lower()
        spans = [Span(e["start"], e["end"], "", "", 0, "") for e in entities]
        runs, cur = [], []
        for tok, s, e in tokenize_with_offsets(low):
            inside = any(Span(s, e, "", "", 0, "").overlaps(x) for x in spans)
            base = tok[:-3] if tok.endswith("nya") and len(tok) > 5 else tok
            if inside or tok in CANDIDATE_STOPWORDS or base in CANDIDATE_STOPWORDS:
                if cur:
                    runs.append(cur)
                cur = []
            else:
                cur.append((tok, s, e))
        if cur:
            runs.append(cur)
        runs = [r for r in runs if len(" ".join(t for t, _, _ in r)) >= 3
                and not all(t.isdigit() for t, _, _ in r)]
        if not runs:
            return None
        best = max(runs, key=lambda r: (len(r), -r[0][1]))[:5]
        return {"entity": "product", "value": text[best[0][1]:best[-1][2]].strip(),
                "start": best[0][1], "end": best[-1][2], "confidence_entity": 0.5,
                "extractor": "ProductCandidateHeuristic"}

    def prepare(self, text: str) -> tuple[str, list[dict]]:
        """Teks siap-classifier (masked + dinormalisasi) beserta entitasnya."""
        masked, entities = self.extract(text)
        return normalize_for_model(masked), entities
