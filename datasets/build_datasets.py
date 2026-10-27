"""
build_datasets.py
=================
Membangun SEMUA data untuk Tugas 2 dari dataset gratis di internet:

  A. DummyJSON (MIT License, https://github.com/Ovi/DummyJSON)
     - products.json  -> tabel products & categories (stok, harga, garansi, dll.)
     - users.json     -> tabel customers (hanya kolom non-sensitif, lihat users_minimal.json)
     - carts.json     -> tabel orders & order_items (1 cart = 1 pesanan)
  B. Bitext Customer Support LLM Chatbot Training Dataset (CDLA-Sharing-1.0,
     https://github.com/bitext/customer-support-llm-chatbot-training-dataset)
     - sampel kalimat diterjemahkan ke Bahasa Indonesia -> bitext_id_translations.csv
  C. Template manual -> nlu_templates.py

Output:
  datasets/products.csv, categories.csv, customers.csv, orders.csv, order_items.csv
  datasets/nlu_train.csv, datasets/nlu_dataset.xlsx
  datasets/demo_cheatsheet.md
  database/olshop_db.sql                       (import ke MAMP via phpMyAdmin)
  nlu-service/resources/products_gazetteer.json
  nlu-service/resources/category_synonyms.json

Jalankan:  python datasets/build_datasets.py   (dari root proyek)
Deterministik: seed tetap, hasil selalu sama.
"""
from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from nlu_templates import (TEMPLATES, UNKNOWN_PRODUCTS, UNKNOWN_CATEGORIES,
                           PREFIXES_QUESTION, SUFFIXES_QUESTION, PREFIXES_SHORT,
                           SUFFIXES_SHORT, SHORT_INTENTS)

ROOT = Path(__file__).resolve().parent.parent
DS = ROOT / "datasets"
RAW = DS / "raw"
NLU_RES = ROOT / "nlu-service" / "resources"
DB_DIR = ROOT / "database"

SEED = 42
USD_TO_IDR = 16_000          # kurs asumsi untuk konversi harga DummyJSON (USD) -> Rupiah
REFERENCE_DATE = date(2026, 10, 14)   # "hari ini" saat data pesanan dibangkitkan
TARGET_PER_INTENT = 160

# ----------------------------------------------------------------------------------
# 1. Kategori: slug DummyJSON -> nama Indonesia + sinonim yang dipakai pembeli
# ----------------------------------------------------------------------------------
CATEGORY_ID = {
    "beauty": "Kosmetik & Kecantikan", "fragrances": "Parfum", "furniture": "Furnitur",
    "groceries": "Bahan Makanan", "home-decoration": "Dekorasi Rumah",
    "kitchen-accessories": "Peralatan Dapur", "laptops": "Laptop",
    "mens-shirts": "Kemeja Pria", "mens-shoes": "Sepatu Pria", "mens-watches": "Jam Tangan Pria",
    "mobile-accessories": "Aksesoris HP", "motorcycle": "Motor", "skin-care": "Perawatan Kulit",
    "smartphones": "Smartphone", "sports-accessories": "Alat Olahraga", "sunglasses": "Kacamata",
    "tablets": "Tablet", "tops": "Atasan Wanita", "vehicle": "Mobil", "womens-bags": "Tas Wanita",
    "womens-dresses": "Dress Wanita", "womens-jewellery": "Perhiasan Wanita",
    "womens-shoes": "Sepatu Wanita", "womens-watches": "Jam Tangan Wanita",
}

# frasa -> daftar slug (satu frasa bisa menunjuk >1 kategori, mis. "sepatu")
CATEGORY_SYNONYMS = {
    "smartphones": ["hp", "handphone", "smartphone", "smartphones", "ponsel", "hape",
                    "telepon genggam"],
    "laptops": ["laptop", "laptops", "notebook"],
    "tablets": ["tablet", "tablets"],
    "mobile-accessories": ["aksesoris hp", "aksesoris handphone", "aksesoris gadget",
                           "mobile accessories"],
    "fragrances": ["parfum", "parfume", "minyak wangi", "wewangian", "fragrance", "fragrances"],
    "beauty": ["kosmetik", "makeup", "make up", "alat kecantikan", "produk kecantikan", "beauty"],
    "skin-care": ["skincare", "skin care", "perawatan kulit"],
    "furniture": ["furnitur", "furniture", "mebel", "perabot"],
    "groceries": ["sembako", "bahan makanan", "groceries", "buah", "sayur", "bahan dapur"],
    "home-decoration": ["dekorasi rumah", "hiasan rumah", "dekorasi", "pajangan"],
    "kitchen-accessories": ["peralatan dapur", "alat dapur", "perlengkapan dapur", "alat masak"],
    "mens-shirts": ["kemeja pria", "baju pria", "kaos pria", "kemeja cowok", "baju cowok"],
    "mens-shoes": ["sepatu pria", "sepatu cowok", "sneakers pria"],
    "mens-watches": ["jam tangan pria", "jam pria", "jam cowok"],
    "motorcycle": ["motor", "sepeda motor", "motorcycle"],
    "sports-accessories": ["alat olahraga", "perlengkapan olahraga", "peralatan olahraga"],
    "sunglasses": ["kacamata", "kacamata hitam", "sunglasses"],
    "tops": ["atasan", "atasan wanita", "baju wanita", "blouse"],
    "vehicle": ["mobil", "kendaraan"],
    "womens-bags": ["tas", "tas wanita", "handbag", "tas cewek"],
    "womens-dresses": ["dress", "gaun", "baju pesta", "dress wanita"],
    "womens-jewellery": ["perhiasan", "anting", "perhiasan wanita"],
    "womens-shoes": ["sepatu wanita", "sepatu cewek", "heels", "high heels"],
    "womens-watches": ["jam tangan wanita", "jam wanita", "jam cewek"],
}
CATEGORY_GROUPS = {   # frasa umum -> beberapa kategori sekaligus
    "sepatu": ["mens-shoes", "womens-shoes"],
    "jam tangan": ["mens-watches", "womens-watches"],
    "baju": ["mens-shirts", "tops", "womens-dresses"],
    "aksesoris": ["mobile-accessories", "womens-jewellery"],
}

# Alias berbahasa Indonesia untuk produk katalog (nilai = judul kanonik / kata kunci).
ID_PRODUCT_ALIASES = {
    "apel": "Apple", "telur": "Eggs", "beras": "Rice", "susu": "Milk",
    "air mineral": "Water", "jus": "Juice", "madu": "Honey Jar", "es krim": "Ice Cream",
    "daging sapi": "Beef Steak", "daging ayam": "Chicken Meat", "minyak goreng": "Cooking Oil",
    "timun": "Cucumber", "kentang": "Potatoes", "bawang merah": "Red Onions",
    "stroberi": "Strawberry", "makanan kucing": "Cat Food", "makanan anjing": "Dog Food",
    "tisu": "Tissue Paper Box", "minuman soda": "Soft Drinks", "cabai hijau": "Green Chili Pepper",
    "paprika hijau": "Green Bell Pepper", "ikan": "Fish Steak", "pisau": "Knife",
    "garpu": "Fork", "sendok": "Spoon", "piring": "Plate", "gelas": "Glass", "wajan": "Pan",
    "talenan": "Chopping Board", "kotak bekal": "Lunch Box", "kompor listrik": "Electric Stove",
    "lampu meja": "Table Lamp", "pot tanaman": "Plant Pot", "bola basket": "Basketball",
    "bola voli": "Volleyball", "bola sepak": "Football", "raket tenis": "Tennis Racket",
    "bola golf": "Golf Ball", "bola tenis": "Tennis Ball", "lipstik merah": "Red Lipstick",
    "kutek merah": "Red Nail Polish", "maskara": "Essence Mascara Lash Princess",
    "sepatu merah": "Red Shoes", "sabun cuci tangan": "Attitude Super Leaves Hand Soap",
    "kopi nescafe": "Nescafe Coffee", "nescafe": "Nescafe Coffee", "blender": "blender",
}

STOP_ALIAS = {"with", "and", "for", "&", "the", "of", "de", "eau", "new"}
COLORS = {"black", "red", "white", "blue", "green", "gray", "grey", "gold", "golden", "silver",
          "brown", "yellow", "plum", "starlight", "pink"}
GENERIC_SINGLE = {"pro", "plus", "max", "mini", "men", "man", "women", "woman", "women's",
                  "girl", "inch", "series", "collection", "with", "set", "box", "x", "dual",
                  "screen", "space"}

SHIP_ID = {
    "Ships overnight": "Dikirim keesokan hari (overnight)",
    "Ships in 1-2 business days": "Dikirim dalam 1-2 hari kerja",
    "Ships in 3-5 business days": "Dikirim dalam 3-5 hari kerja",
    "Ships in 1 week": "Dikirim dalam 1 minggu",
    "Ships in 2 weeks": "Dikirim dalam 2 minggu",
    "Ships in 1 month": "Dikirim dalam 1 bulan",
}


def warranty_id(s: str) -> str:
    if s == "No warranty":
        return "Tanpa garansi"
    if s == "Lifetime warranty":
        return "Garansi seumur hidup"
    m = re.match(r"(\d+) (week|month|year)s? warranty", s)
    unit = {"week": "minggu", "month": "bulan", "year": "tahun"}[m.group(2)]
    return f"Garansi {m.group(1)} {unit}"


def return_id(s: str) -> str:
    if s == "No return policy":
        return "Tidak bisa retur"
    m = re.match(r"(\d+) days return policy", s)
    return f"Bisa retur maksimal {m.group(1)} hari"


def to_idr(usd: float) -> int:
    return int(round(usd * USD_TO_IDR, -2))


def sql_str(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9'.\-]*|&", s.lower())


# ----------------------------------------------------------------------------------
# 2. Data toko (produk, pelanggan, pesanan)
# ----------------------------------------------------------------------------------
def build_store_data():
    products_raw = json.loads((RAW / "dummyjson" / "products.json").read_text())
    users = json.loads((RAW / "dummyjson" / "users_minimal.json").read_text())
    carts = json.loads((RAW / "dummyjson" / "carts.json").read_text())

    categories = [{"category_slug": k, "category_name": v} for k, v in CATEGORY_ID.items()]

    products = []
    for p in products_raw:
        products.append({
            "product_id": p["id"], "sku": p["sku"], "title": p["title"],
            "brand": p.get("brand"), "category_slug": p["category"],
            "description": p["description"], "price_idr": to_idr(p["price"]),
            "discount_percent": round(p["discountPercentage"], 2), "stock": p["stock"],
            "rating": round(p["rating"], 2),
            "warranty_info": warranty_id(p["warrantyInformation"]),
            "shipping_info": SHIP_ID[p["shippingInformation"]],
            "return_policy": return_id(p["returnPolicy"]),
        })

    rng = random.Random(SEED)
    customers = []
    for u in users:
        joined = date(2024, 1, 1) + timedelta(days=rng.randint(0, 900))
        customers.append({
            "customer_id": u["id"], "customer_name": f"{u['firstName']} {u['lastName']}",
            "email": u["email"].lower(), "phone": u["phone"], "city": u["city"],
            "created_at": f"{joined.isoformat()} 10:00:00",
        })

    couriers = ["JNE", "J&T Express", "SiCepat", "AnterAja", "Pos Indonesia"]
    orders, items = [], []
    for c in carts:
        r = random.Random(SEED * 1000 + c["id"])
        days_ago = r.randint(0, 75)
        odate = datetime.combine(REFERENCE_DATE - timedelta(days=days_ago),
                                 datetime.min.time()) + timedelta(hours=r.randint(7, 22),
                                                                  minutes=r.randint(0, 59))
        if r.random() < 0.08:
            status = "cancelled"
        elif days_ago <= 1:
            status = "pending"
        elif days_ago <= 3:
            status = "processing"
        elif days_ago <= 7:
            status = r.choice(["shipped", "shipped", "processing"])
        else:
            status = "delivered" if r.random() < 0.9 else "shipped"
        courier = r.choice(couriers) if status != "cancelled" else None
        tracking = (f"{courier.split()[0].upper()[:3]}{r.randint(10**9, 10**10 - 1)}"
                    if status in ("shipped", "delivered") else None)
        eta = (odate.date() + timedelta(days=r.randint(2, 6))).isoformat() \
            if status != "cancelled" else None
        order_id = 10000 + c["id"]
        total = 0
        for it in c["products"]:
            unit = to_idr(it["price"])
            total += unit * it["quantity"]
            items.append({"order_id": order_id, "product_id": it["id"],
                          "quantity": it["quantity"], "unit_price_idr": unit})
        orders.append({
            "order_id": order_id, "customer_id": c["userId"],
            "order_date": odate.strftime("%Y-%m-%d %H:%M:%S"), "order_status": status,
            "courier": courier, "tracking_number": tracking, "estimated_delivery": eta,
            "total_items": c["totalQuantity"], "total_amount_idr": total,
        })
    return categories, products, customers, orders, items


def write_sql(categories, products, customers, orders, items):
    L = []
    L.append("-- =====================================================================")
    L.append("-- olshop_db.sql  -  Database chatbot admin OlshopKu (Tugas 2 RASA)")
    L.append("-- Dibangkitkan otomatis oleh datasets/build_datasets.py (JANGAN edit manual)")
    L.append("-- Sumber data: DummyJSON (MIT). Harga dikonversi USD -> IDR (x16.000).")
    L.append("-- Kompatibel MySQL 5.7 / 8.x (MAMP). Import via phpMyAdmin -> tab Import.")
    L.append("-- =====================================================================")
    L.append("SET NAMES utf8mb4;")
    L.append("CREATE DATABASE IF NOT EXISTS olshop_db CHARACTER SET utf8mb4 "
             "COLLATE utf8mb4_unicode_ci;")
    L.append("USE olshop_db;")
    L.append("SET FOREIGN_KEY_CHECKS = 0;")
    for t in ("order_items", "orders", "products", "categories", "customers"):
        L.append(f"DROP TABLE IF EXISTS {t};")
    L.append("DROP VIEW IF EXISTS v_customer_order_status;")
    L.append("SET FOREIGN_KEY_CHECKS = 1;")
    L.append("""
CREATE TABLE customers (
  customer_id    INT UNSIGNED  NOT NULL PRIMARY KEY,
  customer_name  VARCHAR(100)  NOT NULL,
  email          VARCHAR(150)  NOT NULL,
  phone          VARCHAR(30)   NULL,
  city           VARCHAR(80)   NULL,
  created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE categories (
  category_slug  VARCHAR(50)   NOT NULL PRIMARY KEY,
  category_name  VARCHAR(80)   NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE products (
  product_id       INT UNSIGNED  NOT NULL PRIMARY KEY,
  sku              VARCHAR(40)   NOT NULL,
  title            VARCHAR(150)  NOT NULL,
  brand            VARCHAR(80)   NULL,
  category_slug    VARCHAR(50)   NOT NULL,
  description      TEXT          NULL,
  price_idr        INT UNSIGNED  NOT NULL,
  discount_percent DECIMAL(5,2)  NOT NULL DEFAULT 0,
  stock            INT UNSIGNED  NOT NULL DEFAULT 0,
  rating           DECIMAL(3,2)  NULL,
  warranty_info    VARCHAR(80)   NULL,
  shipping_info    VARCHAR(80)   NULL,
  return_policy    VARCHAR(80)   NULL,
  updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_products_sku (sku),
  KEY idx_products_title (title),
  KEY idx_products_category (category_slug),
  CONSTRAINT fk_products_category FOREIGN KEY (category_slug)
    REFERENCES categories (category_slug) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE orders (
  order_id           INT UNSIGNED  NOT NULL PRIMARY KEY,
  customer_id        INT UNSIGNED  NOT NULL,
  order_date         DATETIME      NOT NULL,
  order_status       ENUM('pending','processing','shipped','delivered','cancelled') NOT NULL,
  courier            VARCHAR(30)   NULL,
  tracking_number    VARCHAR(40)   NULL,
  estimated_delivery DATE          NULL,
  total_items        INT UNSIGNED  NOT NULL,
  total_amount_idr   BIGINT UNSIGNED NOT NULL,
  updated_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_orders_customer (customer_id),
  CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id)
    REFERENCES customers (customer_id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE order_items (
  order_item_id   INT UNSIGNED  NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id        INT UNSIGNED  NOT NULL,
  product_id      INT UNSIGNED  NOT NULL,
  quantity        INT UNSIGNED  NOT NULL,
  unit_price_idr  INT UNSIGNED  NOT NULL,
  KEY idx_items_order (order_id),
  CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders (order_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- View yang memenuhi skema minimal soal (customer_id, customer_name, email, order_status)
-- tanpa melanggar normalisasi: satu pelanggan dapat memiliki banyak pesanan.
CREATE VIEW v_customer_order_status AS
SELECT c.customer_id, c.customer_name, c.email, o.order_id, o.order_status, o.order_date
FROM customers c JOIN orders o ON o.customer_id = c.customer_id;
""")

    def bulk(table, cols, rows, chunk=100):
        for i in range(0, len(rows), chunk):
            vals = ",\n".join("(" + ", ".join(sql_str(r[c]) for c in cols) + ")"
                              for r in rows[i:i + chunk])
            L.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{vals};")

    bulk("categories", ["category_slug", "category_name"], categories)
    bulk("customers", ["customer_id", "customer_name", "email", "phone", "city", "created_at"],
         customers)
    bulk("products", ["product_id", "sku", "title", "brand", "category_slug", "description",
                      "price_idr", "discount_percent", "stock", "rating", "warranty_info",
                      "shipping_info", "return_policy"], products)
    bulk("orders", ["order_id", "customer_id", "order_date", "order_status", "courier",
                    "tracking_number", "estimated_delivery", "total_items", "total_amount_idr"],
         orders)
    bulk("order_items", ["order_id", "product_id", "quantity", "unit_price_idr"], items)
    DB_DIR.mkdir(exist_ok=True)
    (DB_DIR / "olshop_db.sql").write_text("\n".join(L) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------
# 3. Gazetteer produk & kategori untuk entity extractor (pola "Dictionary/Gazetteer
#    Lookup" pada slide bab 3)
# ----------------------------------------------------------------------------------
def build_gazetteer(products):
    titles = {p["product_id"]: p["title"] for p in products}
    brands = {p["brand"].lower() for p in products if p.get("brand")}
    token_freq = Counter()
    for t in titles.values():
        token_freq.update(set(tokenize(t)))
    category_words = {w for syns in CATEGORY_SYNONYMS.values() for s in syns for w in [s]}
    category_words |= set(CATEGORY_GROUPS)

    alias_to_ids: dict[str, set[int]] = defaultdict(set)
    for pid, title in titles.items():
        toks = tokenize(title)
        p = next(x for x in products if x["product_id"] == pid)
        brand_toks = tokenize(p["brand"]) if p.get("brand") else []
        variants = [toks]
        if brand_toks and toks[:len(brand_toks)] == brand_toks and len(toks) > len(brand_toks):
            variants.append(toks[len(brand_toks):])
        for v in variants:
            for n in range(1, len(v) + 1):
                for i in range(0, len(v) - n + 1):
                    gram = v[i:i + n]
                    phrase = " ".join(gram)
                    if n == 1:
                        w = gram[0]
                        ok = (len(toks) == 1) or (
                            w in brands) or (
                            token_freq[w] <= 2 and len(w) >= 4 and not w.isdigit()
                            and w not in COLORS and w not in GENERIC_SINGLE
                            and w not in STOP_ALIAS)
                    else:
                        ok = (gram[0] not in STOP_ALIAS and gram[-1] not in STOP_ALIAS
                              and any(g not in COLORS and g not in STOP_ALIAS
                                      and g not in GENERIC_SINGLE and not g.isdigit()
                                      for g in gram))
                    if ok and phrase not in category_words:
                        alias_to_ids[phrase].add(pid)
        if p.get("brand"):     # brand sebagai alias, mis. "calvin klein", "rolex"
            alias_to_ids[p["brand"].lower()].add(pid)

    gaz = {}
    for alias, ids in alias_to_ids.items():
        if alias in category_words:
            continue
        # Merek selalu dijadikan kata kunci pencarian (bukan judul tunggal): "asus rog
        # phone" tidak boleh dijawab dengan stok "Asus Zenbook" seolah-olah produk yang sama.
        if alias in brands or len(ids) > 1:
            gaz[alias] = alias
        else:
            gaz[alias] = titles[next(iter(ids))]
    for alias, value in ID_PRODUCT_ALIASES.items():
        gaz[alias] = value

    NLU_RES.mkdir(parents=True, exist_ok=True)
    (NLU_RES / "products_gazetteer.json").write_text(
        json.dumps(dict(sorted(gaz.items())), indent=1, ensure_ascii=False), encoding="utf-8")
    cat_syn = {}
    for slug, syns in CATEGORY_SYNONYMS.items():
        for s in syns:
            cat_syn[s] = [slug]
    for phrase, slugs in CATEGORY_GROUPS.items():
        cat_syn[phrase] = slugs
    (NLU_RES / "category_synonyms.json").write_text(
        json.dumps(dict(sorted(cat_syn.items())), indent=1, ensure_ascii=False),
        encoding="utf-8")
    return gaz, cat_syn


# ----------------------------------------------------------------------------------
# 4. Dataset NLU (Bahasa Indonesia)
# ----------------------------------------------------------------------------------
def product_surface_forms(gaz, products, rng):
    """Bentuk penyebutan produk yang realistis: judul penuh, alias pendek, alias Indonesia."""
    unique_aliases = [a for a, v in gaz.items() if v in {p["title"] for p in products}
                      and len(a) >= 4]
    titles = [p["title"] for p in products]
    forms = set(rng.sample(unique_aliases, min(220, len(unique_aliases))))
    forms |= {t.lower() for t in rng.sample(titles, 60)}
    forms |= set(rng.sample(titles, 40))           # kapitalisasi asli
    forms |= set(ID_PRODUCT_ALIASES)
    return sorted(forms)


def fill(template, rng, product_forms, emails, cat_forms):
    ents = []
    text = template
    if "<product>" in text:
        if rng.random() < 0.25:
            val, kind = rng.choice(UNKNOWN_PRODUCTS), "unknown_product"
        else:
            val, kind = rng.choice(product_forms), "product"
        text = text.replace("<product>", val, 1)
        ents.append({"entity": kind, "value": val})
    if "<category>" in text:
        if rng.random() < 0.1:
            val, kind = rng.choice(UNKNOWN_CATEGORIES), "unknown_category"
        else:
            val, kind = rng.choice(cat_forms), "category"
        text = text.replace("<category>", val, 1)
        ents.append({"entity": kind, "value": val})
    if "<order_id>" in text:
        oid = rng.randint(10001, 10208)
        val = rng.choice([str(oid), str(oid), f"#{oid}", f"ORD-{oid}", f"ord{oid}"])
        text = text.replace("<order_id>", val, 1)
        ents.append({"entity": "order_id", "value": str(oid)})
    if "<email>" in text:
        val = rng.choice(emails)
        text = text.replace("<email>", val, 1)
        ents.append({"entity": "email", "value": val})
    return text, ents


def typo(text, rng):
    words = text.split()
    cand = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
    if not cand:
        return text
    i = rng.choice(cand)
    w = words[i]
    j = rng.randint(1, len(w) - 2)
    words[i] = w[:j] + w[j + 1:]
    return " ".join(words)


def build_nlu(gaz, cat_syn, products, customers):
    rng = random.Random(SEED)
    product_forms = product_surface_forms(gaz, products, rng)
    emails = [c["email"] for c in customers]
    cat_forms = sorted(cat_syn)

    trans = pd.read_csv(DS / "bitext_id_translations.csv")
    base = defaultdict(list)       # intent -> list of (template, source, bitext_row)
    for _, r in trans.iterrows():
        base[r.target_intent].append((r.text_id, "bitext_translated", int(r.bitext_row)))
    for intent, temps in TEMPLATES.items():
        for t in temps:
            base[intent].append((t, "template_manual", None))

    rows, seen = [], set()
    for intent in sorted(base):
        items = base[intent]
        short = intent in SHORT_INTENTS
        pre = PREFIXES_SHORT if short else PREFIXES_QUESTION
        suf = SUFFIXES_SHORT if short else SUFFIXES_QUESTION
        # 1) setiap kalimat dasar minimal sekali (tanpa augmentasi)
        queue = [(t, s, b, "", "") for t, s, b in items]
        # 2) variasi augmentasi hingga target
        attempts = 0
        while len(queue) < TARGET_PER_INTENT * 3 and attempts < 5000:
            t, s, b = rng.choice(items)
            queue.append((t, s, b, rng.choice(pre), rng.choice(suf)))
            attempts += 1
        count = 0
        for t, s, b, p, sf in queue:
            if count >= TARGET_PER_INTENT:
                break
            text, ents = fill(t, rng, product_forms, emails, cat_forms)
            if intent in ("provide_order_id", "provide_email") and p.strip() in ("oh", "oke"):
                p = ""
            text = (p + text + sf).strip()
            text = re.sub(r"\?+", "?", text.replace("??", "?"))
            if rng.random() < 0.08:
                text = typo(text, rng)
            key = (text.lower(), intent)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"text": text, "intent": intent, "source": s,
                         "bitext_row": b if b is not None else "",
                         "entities": json.dumps(ents, ensure_ascii=False) if ents else ""})
            count += 1
    df = pd.DataFrame(rows)
    df.to_csv(DS / "nlu_train.csv", index=False, quoting=csv.QUOTE_MINIMAL)

    held = pd.read_csv(DS / "nlu_test_heldout.csv")
    summary = (df.groupby("intent").agg(n_train=("text", "size"),
                                         n_bitext=("source",
                                                   lambda s: (s == "bitext_translated").sum()))
               .join(held.groupby("intent").size().rename("n_heldout_test")).reset_index())
    with pd.ExcelWriter(DS / "nlu_dataset.xlsx") as xw:
        df.to_excel(xw, sheet_name="train", index=False)
        held.to_excel(xw, sheet_name="heldout_test", index=False)
        trans.to_excel(xw, sheet_name="bitext_translations", index=False)
        summary.to_excel(xw, sheet_name="intent_summary", index=False)
    return df, held, summary


def write_csvs(categories, products, customers, orders, items):
    for name, rows in [("categories", categories), ("products", products),
                       ("customers", customers), ("orders", orders), ("order_items", items)]:
        pd.DataFrame(rows).to_csv(DS / f"{name}.csv", index=False)


def write_cheatsheet(products, customers, orders):
    cust = {c["customer_id"]: c for c in customers}
    L = ["# Demo cheat-sheet (data uji untuk video demo)", "",
         f"Tanggal referensi data pesanan: {REFERENCE_DATE.isoformat()}", "",
         "## Contoh pesanan per status", "",
         "| order_id | status | email pemilik | nama |", "|---|---|---|---|"]
    by_status = defaultdict(list)
    for o in orders:
        by_status[o["order_status"]].append(o)
    for st in ["pending", "processing", "shipped", "delivered", "cancelled"]:
        for o in by_status[st][:2]:
            c = cust[o["customer_id"]]
            L.append(f"| {o['order_id']} | {st} | {c['email']} | {c['customer_name']} |")
    L += ["", "## Produk menarik untuk demo stok", "", "| produk | stok |", "|---|---|"]
    for p in sorted(products, key=lambda x: x["stock"])[:8]:
        L.append(f"| {p['title']} | {p['stock']} |")
    for t in ["iPhone X", "Samsung Galaxy S10", "Rolex Submariner Watch", "Lenovo Yoga 920"]:
        p = next(x for x in products if x["title"] == t)
        L.append(f"| {p['title']} | {p['stock']} |")
    (DS / "demo_cheatsheet.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    categories, products, customers, orders, items = build_store_data()
    write_csvs(categories, products, customers, orders, items)
    write_sql(categories, products, customers, orders, items)
    gaz, cat_syn = build_gazetteer(products)
    df, held, summary = build_nlu(gaz, cat_syn, products, customers)
    write_cheatsheet(products, customers, orders)
    print(f"products={len(products)} customers={len(customers)} orders={len(orders)} "
          f"order_items={len(items)}")
    print(f"gazetteer aliases={len(gaz)} category phrases={len(cat_syn)}")
    print(f"NLU train rows={len(df)} intents={df.intent.nunique()} heldout={len(held)}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
