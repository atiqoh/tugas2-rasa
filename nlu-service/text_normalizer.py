"""
Normalisasi teks (pre-processing NLU, slide bab 2-1): lowercasing, normalisasi spasi &
tanda baca, penanganan kata tidak baku/singkatan chat (slide bab 2-2: non-standard
language & typo), dan pemendekan huruf berulang ("kakkk" -> "kakk").

Fungsi yang SAMA dipakai saat training dan saat inference agar tidak terjadi
training-serving skew.
"""
import re
import unicodedata

PLACEHOLDER_RE = re.compile(r"^<(product|category|order_id|email)>$")

# Kamus kata tidak baku -> baku (sengaja kecil & eksplisit agar mudah dijelaskan).
SLANG = {
    "gak": "tidak", "ga": "tidak", "nggak": "tidak", "ngga": "tidak", "enggak": "tidak",
    "engga": "tidak", "gk": "tidak", "tdk": "tidak", "kagak": "tidak",
    "brp": "berapa", "hrg": "harga", "sy": "saya", "aku": "saya", "gue": "saya",
    "udh": "sudah", "udah": "sudah", "sdh": "sudah", "dah": "sudah", "blm": "belum",
    "yg": "yang", "dgn": "dengan", "utk": "untuk", "bs": "bisa", "bsa": "bisa",
    "gmn": "bagaimana", "gimana": "bagaimana", "knp": "kenapa", "dmn": "dimana", "tau": "tahu",
    "liat": "lihat", "nyampe": "sampai", "sampe": "sampai", "pake": "pakai",
    "makasih": "terima kasih", "makasi": "terima kasih", "mksh": "terima kasih",
    "trims": "terima kasih", "terimakasih": "terima kasih", "thx": "thanks",
    "pesenan": "pesanan", "stock": "stok", "aja": "saja", "aj": "saja", "dlm": "dalam",
    "krn": "karena", "jg": "juga", "lg": "lagi", "msh": "masih", "bgt": "banget",
    "tp": "tapi", "kalo": "kalau", "klo": "kalau", "pengen": "ingin", "pgn": "ingin",
    "sm": "sama", "bkn": "bukan", "ok": "oke", "okay": "oke", "okey": "oke", "kk": "kak",
    "kakak": "kak", "mimin": "admin",
}

_PUNCT_RE = re.compile(r"([?!.,;:()\"])")
_REPEAT_RE = re.compile(r"([a-z])\1{2,}")


def basic_clean(text: str) -> str:
    """Normalisasi ringan yang TIDAK mengubah panjang/posisi karakter secara berarti:
    unicode NFKC + kutip pintar -> kutip biasa. Dipakai sebelum ekstraksi entitas."""
    text = unicodedata.normalize("NFKC", text or "")
    return text.replace("’", "'").replace("‘", "'")


def normalize_for_model(masked_text: str) -> str:
    """Normalisasi penuh untuk input classifier (dipanggil SETELAH entitas ditutup
    placeholder, sehingga email/nomor pesanan tidak ikut rusak)."""
    t = masked_text.lower()
    t = _PUNCT_RE.sub(r" \1 ", t)
    out = []
    for tok in t.split():
        if PLACEHOLDER_RE.match(tok):
            out.append(tok)
            continue
        tok = _REPEAT_RE.sub(r"\1\1", tok)
        out.append(SLANG.get(tok, tok))
    return " ".join(out).strip()
