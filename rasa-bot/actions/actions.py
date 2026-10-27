"""
actions.py - Custom actions chatbot admin OlshopKu
==================================================
Custom action = kode Python yang dijalankan Rasa ketika bot perlu melakukan sesuatu di
luar respons statis (slide bab 5 & 7). Di sini semua data toko diambil dari EXTERNAL
SERVICE Node.js (api-service) yang terhubung ke MySQL MAMP, bukan langsung ke database.

  Rasa ──HTTP GET──▶ api-service (Express, port 4000) ──SQL──▶ MySQL MAMP (port 8889)

Konfigurasi lewat environment variable:
  OLSHOP_API_URL  (default http://localhost:4000)
  OLSHOP_API_KEY  (opsional, harus sama dengan API_KEY di api-service)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Text, Tuple

import requests
from rasa_sdk import Action, FormValidationAction, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict

logger = logging.getLogger(__name__)

API_URL = os.getenv("OLSHOP_API_URL", "http://localhost:4000").rstrip("/")
API_KEY = os.getenv("OLSHOP_API_KEY", "")
TIMEOUT = (3, 8)          # (connect, read) detik

EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
ORDER_ID_RE = re.compile(r"(?<!\d)(\d{5})(?!\d)")
FILLER_WORDS = {"kak", "kakak", "min", "gan", "sis", "dong", "ya", "yang", "yg", "itu", "ini",
                "nih", "deh", "aja", "saja", "mau", "cek", "stok", "harga", "info", "produk",
                "barang", "ada", "ready", "berapa", "apa", "tolong", "please", "the"}

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
STATUS_EMOJI = {"pending": "🕒", "processing": "📦", "shipped": "🚚", "delivered": "✅",
                "cancelled": "❌"}
STATUS_NOTE = {
    "pending": "Pesanan sudah masuk dan menunggu konfirmasi penjual.",
    "processing": "Pesanan sedang dikemas oleh tim gudang.",
    "shipped": "Paket sudah diserahkan ke kurir, resi bisa dilacak di website kurir.",
    "delivered": "Paket sudah diterima. Terima kasih sudah belanja!",
    "cancelled": "Pesanan ini dibatalkan. Hubungi admin bila ada pertanyaan.",
}


# ---------------------------------------------------------------------------- helpers
def rupiah(n: Any) -> str:
    try:
        return "Rp" + f"{int(round(float(n))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def tanggal(s: Optional[str], with_time: bool = False) -> str:
    """'2026-10-12 14:22:00' -> '12 Okt 2026 14:22'"""
    if not s:
        return "-"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?", str(s))
    if not m:
        return str(s)
    y, mo, d, hh, mm = m.groups()
    out = f"{int(d)} {BULAN[int(mo) - 1]} {y}"
    return f"{out} {hh}:{mm}" if with_time and hh else out


def clean_product_text(text: str) -> str:
    words = re.findall(r"[\w'&.-]+", text or "")
    kept = [w for w in words if w.lower() not in FILLER_WORDS]
    return " ".join(kept).strip(" .-")


class OlshopApi:
    """Klien kecil untuk external service. Mengembalikan (status_code, body). Kode 0 berarti
    service tidak dapat dihubungi (timeout / connection refused)."""

    def __init__(self, base_url: str = API_URL, api_key: str = API_KEY, session=None):
        self.base_url = base_url
        self.session = session or requests.Session()
        self.headers = {"x-api-key": api_key} if api_key else {}

    def get(self, path: str, params: Optional[dict] = None) -> Tuple[int, Optional[dict]]:
        try:
            r = self.session.get(f"{self.base_url}{path}", params=params,
                                 headers=self.headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            logger.error("API tidak dapat dihubungi: %s", e)
            return 0, None
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, None


api = OlshopApi()


# ------------------------------------------------------------------ format jawaban
def _stock_line(p: dict) -> str:
    if p["availability"] == "out_of_stock":
        return f"😔 Maaf kak, {p['title']} sedang habis (stok 0)."
    if p["availability"] == "low_stock":
        return f"⚠️ {p['title']} stoknya tinggal {p['stock']} unit, buruan sebelum kehabisan ya kak."
    return f"✅ {p['title']} ready kak, stok {p['stock']} unit."


def _price_text(p: dict) -> str:
    if p.get("discount_percent", 0) >= 1:
        return (f"{rupiah(p['final_price_idr'])} (diskon {p['discount_percent']:.0f}% dari "
                f"{rupiah(p['price_idr'])})")
    return rupiah(p["price_idr"])


def format_single(p: dict, qtype: str) -> str:
    if qtype == "price":
        return f"💰 Harga {p['title']}: {_price_text(p)}.\n{_stock_line(p)}"
    if qtype == "info":
        desc = p.get("description") or ""
        if len(desc) > 160:
            desc = desc[:157].rsplit(" ", 1)[0] + "…"
        return "\n".join([
            f"📦 {p['title']}",
            f"Merek: {p.get('brand') or '-'} · Kategori: {p['category_name']}",
            f"Harga: {_price_text(p)}",
            f"Stok: {p['stock']} ({p['availability_label']}) · Rating: {p['rating']}/5",
            f"{p['warranty_info']} · {p['return_policy']}",
            f"Pengiriman: {p['shipping_info']}",
            f"Deskripsi: {desc}",
        ])
    msg = _stock_line(p)
    if p["availability"] == "out_of_stock":
        msg += f" Coba lihat alternatif di kategori {p['category_name']} ya."
    return msg


def format_list(products: List[dict], query: str, qtype: str) -> str:
    lines = [f"Ada {len(products)} produk yang cocok dengan \"{query}\":"]
    for p in products:
        if qtype == "price":
            lines.append(f"• {p['title']} — {rupiah(p['final_price_idr'])}")
        else:
            lines.append(f"• {p['title']} — stok {p['stock']} ({p['availability_label']})")
    lines.append("Sebutkan nama lengkapnya kalau mau detail salah satunya ya kak.")
    return "\n".join(lines)


# ======================================================================== ACTIONS
class ActionProductLookup(Action):
    """Menjawab cek stok / harga / info produk setelah product_form selesai."""

    def name(self) -> Text:
        return "action_product_lookup"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        product = tracker.get_slot("product")
        qtype = tracker.get_slot("product_query_type") or "stock"
        if not product:
            dispatcher.utter_message(response="utter_ask_product")
            return []
        status, body = api.get("/api/products/search", {"q": product, "limit": 5})
        if status != 200 or not body:
            dispatcher.utter_message(response="utter_api_error")
            return []
        products = body["data"]["products"]
        if not products:
            dispatcher.utter_message(
                text=f"Maaf kak, produk \"{product}\" tidak ditemukan di katalog OlshopKu 🙏")
            return [SlotSet("product", None)]
        # Satu hasil, atau judul persis sama (case-sensitive: "apple" = kata kunci merek,
        # "Apple" = judul produk buah) -> jawaban tunggal; selain itu tampilkan daftar.
        if len(products) == 1 or products[0]["title"] == product:
            dispatcher.utter_message(text=format_single(products[0], qtype))
            # simpan nama kanonik agar pertanyaan lanjutan ("harganya?") merujuk ke produk ini
            return [SlotSet("product", products[0]["title"])]
        dispatcher.utter_message(text=format_list(products, product, qtype))
        return []


class ActionBrowseCategory(Action):
    """Menampilkan daftar kategori, atau produk dalam kategori tertentu."""

    def name(self) -> Text:
        return "action_browse_category"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        # Pakai entitas dari pesan TERAKHIR saja (bukan slot lama) supaya "ada kategori
        # apa aja?" tidak menampilkan kategori yang ditanyakan sebelumnya.
        category = next(tracker.get_latest_entity_values("category"), None)
        if not category:
            status, body = api.get("/api/categories")
            if status != 200 or not body:
                dispatcher.utter_message(response="utter_api_error")
                return []
            lines = ["Kategori produk di OlshopKu:"]
            for c in body["data"]["categories"]:
                lines.append(f"• {c['category_name']} ({c['in_stock_count']}/"
                             f"{c['product_count']} produk ready)")
            lines.append("Ketik misalnya \"ada laptop apa aja?\" untuk melihat isinya.")
            dispatcher.utter_message(text="\n".join(lines))
            return [SlotSet("category", None)]

        status, body = api.get("/api/products", {"category": category, "limit": 8})
        if status != 200 or not body:
            dispatcher.utter_message(response="utter_api_error")
            return [SlotSet("category", None)]
        products = body["data"]["products"]
        if not products:
            dispatcher.utter_message(text="Belum ada produk di kategori itu, kak.")
            return [SlotSet("category", None)]
        names = sorted({p["category_name"] for p in products})
        lines = [f"Pilihan {' & '.join(names)} di OlshopKu:"]
        for p in products:
            lines.append(f"• {p['title']} — {rupiah(p['final_price_idr'])} · "
                         f"stok {p['stock']}")
        lines.append("Mau cek detail salah satunya? Sebutkan namanya ya kak.")
        dispatcher.utter_message(text="\n".join(lines))
        return [SlotSet("category", None)]


class ActionCheckOrderStatus(Action):
    """Pseudocode Q4b diimplementasikan: ambil identitas -> request ke server -> balas."""

    def name(self) -> Text:
        return "action_check_order_status"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        order_id = tracker.get_slot("order_id")
        email = tracker.get_slot("customer_email")
        if not order_id or not email:
            dispatcher.utter_message(response="utter_ask_order_id")
            return []
        status, body = api.get(f"/api/orders/{order_id}", {"email": email})
        if status == 200 and body:
            o = body["data"]
            lines = [
                f"{STATUS_EMOJI.get(o['order_status'], '📦')} Pesanan #{o['order_id']} "
                f"a.n. {o['customer_name']}",
                f"Status: {o['status_label']}",
                f"Tanggal pesan: {tanggal(o['order_date'], with_time=True)}",
            ]
            if o.get("courier"):
                resi = f" · Resi: {o['tracking_number']}" if o.get("tracking_number") else ""
                lines.append(f"Kurir: {o['courier']}{resi}")
            if o.get("estimated_delivery") and o["order_status"] not in ("cancelled",):
                label = "Tiba" if o["order_status"] == "delivered" else "Estimasi tiba"
                lines.append(f"{label}: {tanggal(o['estimated_delivery'])}")
            lines.append("Isi pesanan:")
            for it in o["items"][:5]:
                lines.append(f"• {it['title']} × {it['quantity']}")
            if len(o["items"]) > 5:
                lines.append(f"• …dan {len(o['items']) - 5} produk lain")
            lines.append(f"Total: {rupiah(o['total_amount_idr'])}")
            lines.append(STATUS_NOTE.get(o["order_status"], ""))
            dispatcher.utter_message(text="\n".join(l for l in lines if l))
            # order_id dikosongkan agar pertanyaan berikutnya menanyakan nomor baru,
            # email tetap disimpan (pengguna sudah terverifikasi di sesi ini).
            return [SlotSet("order_id", None)]
        if status == 404:
            dispatcher.utter_message(
                text=f"Maaf kak, pesanan #{order_id} tidak ditemukan atau email-nya tidak "
                     f"cocok dengan pemilik pesanan. Silakan cek kembali ya 🙏")
            return [SlotSet("order_id", None), SlotSet("customer_email", None)]
        if status == 400:
            dispatcher.utter_message(text="Nomor pesanan atau email tidak valid, kak.")
            return [SlotSet("order_id", None), SlotSet("customer_email", None)]
        dispatcher.utter_message(response="utter_api_error")
        return [SlotSet("order_id", None)]


class ActionCheckCustomerData(Action):
    """action_check_customer_data (Q4b): identitas = email -> external service -> profil."""

    def name(self) -> Text:
        return "action_check_customer_data"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        email = tracker.get_slot("customer_email")
        if not email:
            dispatcher.utter_message(response="utter_ask_customer_email")
            return []
        status, body = api.get("/api/customers/lookup", {"email": email})
        if status == 200 and body:
            d = body["data"]
            c, s = d["customer"], d["summary"]
            lines = [
                "👤 Data akun kakak:",
                f"Nama: {c['customer_name']}",
                f"Email: {c['email']}",
                f"No. HP: {c['phone_masked'] or '-'}",
                f"Kota: {c['city'] or '-'}",
                f"Member sejak: {tanggal(c['member_since'])}",
                f"Total pesanan: {s['total_orders']} (belanja {rupiah(s['total_spent_idr'])})",
            ]
            if d["recent_orders"]:
                lines.append("Riwayat pesanan terakhir:")
                for o in d["recent_orders"]:
                    lines.append(f"• #{o['order_id']} · {tanggal(o['order_date'])} · "
                                 f"{o['status_label']} · {rupiah(o['total_amount_idr'])}")
            dispatcher.utter_message(text="\n".join(lines))
            return []
        if status == 404:
            dispatcher.utter_message(
                text=f"Email {email} belum terdaftar sebagai pelanggan OlshopKu, kak.")
            return [SlotSet("customer_email", None)]
        dispatcher.utter_message(response="utter_api_error")
        return []


# ================================================================ FORM VALIDATION
def _validate_email(value: Any, dispatcher: CollectingDispatcher) -> Dict[Text, Any]:
    email = str(value or "").strip().lower()
    m = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", email)
    if m and EMAIL_RE.match(m.group(0)):
        return {"customer_email": m.group(0)}
    dispatcher.utter_message(response="utter_invalid_email", customer_email=value)
    return {"customer_email": None}


class ValidateProductForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_product_form"

    def validate_product(self, slot_value: Any, dispatcher: CollectingDispatcher,
                         tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        # Utamakan entitas dari NLU; jika slot berasal dari teks bebas, buang kata pengisi.
        entity = next(tracker.get_latest_entity_values("product"), None)
        query = (entity or clean_product_text(str(slot_value or ""))).strip()
        if len(query) < 2:
            dispatcher.utter_message(response="utter_ask_product")
            return {"product": None}
        status, body = api.get("/api/products/search", {"q": query, "limit": 1})
        if status != 200 or not body:
            # Service mati: terima nilai apa adanya, action lookup yang melaporkan gangguan
            # (mencegah form bertanya berulang-ulang tanpa akhir).
            return {"product": query}
        if body["data"]["count"] == 0:
            dispatcher.utter_message(
                text=f"Maaf kak, produk \"{query}\" tidak ada di katalog OlshopKu. Coba nama "
                     f"lain, atau ketik \"batal\".")
            return {"product": None}
        return {"product": query}


class ValidateOrderStatusForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_order_status_form"

    def validate_order_id(self, slot_value: Any, dispatcher: CollectingDispatcher,
                          tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        m = ORDER_ID_RE.search(str(slot_value or ""))
        if m:
            return {"order_id": m.group(1)}
        dispatcher.utter_message(response="utter_invalid_order_id", order_id=slot_value)
        return {"order_id": None}

    def validate_customer_email(self, slot_value: Any, dispatcher: CollectingDispatcher,
                                tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return _validate_email(slot_value, dispatcher)


class ValidateCustomerDataForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_customer_data_form"

    def validate_customer_email(self, slot_value: Any, dispatcher: CollectingDispatcher,
                                tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return _validate_email(slot_value, dispatcher)
