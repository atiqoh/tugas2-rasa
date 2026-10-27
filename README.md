# Tugas 2 – RASA Customization: Chatbot Admin OlshopKu

Chatbot **admin online shop** berbahasa Indonesia ("Mimin") berbasis **Rasa Pro**. Bot ini memakai **NLU eksternal IndoBERT** yang di-fine-tune di luar Rasa, dihubungkan lewat **NLUCommandAdapter** dan `endpoints.yml → nlu.url`. Data toko diambil dari **external service Node.js + MySQL (MAMP)**.

Yang dilayani bot: ketersediaan stok, harga & diskon, info produk (garansi, retur, pengiriman), katalog per kategori, status pesanan, serta data & riwayat transaksi pelanggan.
Yang **tidak** dilayani: pemesanan dan pembayaran. Pertanyaan seperti itu dikenali sebagai intent `transaction_out_of_scope` lalu dijawab dengan penolakan yang sopan.

```
 Pengguna ──▶ UI chat (http://localhost:4000)  atau  rasa inspect
                 │ POST /chat (proxy)
                 ▼
          ┌─────────────────────┐  POST /model/parse  ┌──────────────────────────────┐
          │  Rasa Pro  :5005    │ ──────────────────▶ │ NLU service (Flask) :3000    │
          │  rules/stories/forms│ ◀────────────────── │ IndoBERT intent + entity     │
          │  TED/Memo/RulePolicy│  intent, conf, ents │ (regex + gazetteer + fuzzy)  │
          └─────────┬───────────┘                     └──────────────────────────────┘
                    │ custom actions (HTTP GET)
                    ▼
          ┌─────────────────────┐   SQL    ┌──────────────────────────┐
          │ api-service (Node)  │ ───────▶ │ MySQL MAMP :8889         │
          │ Express :4000       │          │ olshop_db                │
          └─────────────────────┘          └──────────────────────────┘
```

## Isi folder

| Folder | Isi |
|---|---|
| `datasets/` | `build_datasets.py` (membangun semua data), `nlu_train.csv`, `nlu_dataset.xlsx`, `nlu_test_heldout.csv`, `bitext_id_translations.csv`, CSV produk/pelanggan/pesanan, `raw/` (data mentah + lisensi), `demo_cheatsheet.md` |
| `database/` | `olshop_db.sql`, berisi skema dan data untuk di-import ke phpMyAdmin MAMP |
| `nlu-service/` | `train_intent_model.py` (fine-tuning IndoBERT), `app.py` (Flask `/model/parse`), `entity_extractor.py`, `text_normalizer.py`, `baseline_tfidf.py`, unit test |
| `api-service/` | External service Node.js: `server.js`, `src/` (Express, mysql2, handler, SQL), `public/index.html` (UI chat), `test/` |
| `rasa-bot/` | `config.yml`, `domain.yml`, `endpoints.yml`, `credentials.yml`, `data/rules.yml`, `data/stories.yml`, `actions/actions.py`, `tests/` |
| `scripts/` | `setup_mac.sh`, `start_api.sh`, `start_nlu.sh`, `start_rasa.sh`, `smoke_test.sh`, `check_project.py` |
| `docs/` | Laporan Q1–Q4 (PDF & DOCX), diagram, naskah video |

## Menjalankan di macOS (Apple Silicon maupun Intel)

### 0. Prasyarat
- **MAMP** (gratis), dari https://www.mamp.info
- **Node.js ≥ 18** (disarankan 22 LTS) dari https://nodejs.org atau `brew install node`
- **License key Rasa Pro**, didapat lewat https://rasa.com/docs/learn/quickstart/pro (seperti di slide bab 5)
- Ruang disk sekitar 3 GB (PyTorch, Rasa, dan model IndoBERT sekitar 500 MB)

### 1. Database MAMP
1. Buka MAMP lalu klik **Start**. MySQL default MAMP: host `localhost`, **port `8889`**, user `root`, password `root`.
2. Buka phpMyAdmin (`http://localhost:8888/phpMyAdmin/` atau tombol *WebStart*), pilih tab **Import**, pilih `database/olshop_db.sql`, lalu klik **Go**. Database `olshop_db` beserta 5 tabel dan 1 view akan dibuat.
   *Alternatif lewat Terminal (path berbeda antar versi MAMP):*
   `/Applications/MAMP/Library/bin/mysql80/bin/mysql -h 127.0.0.1 -P 8889 -u root -proot < database/olshop_db.sql`

### 2. Instal dependensi (sekali saja)
```bash
cd tugas2-olshop-chatbot
./scripts/setup_mac.sh
```
Script ini membuat dua virtual environment Python 3.11 yang **terpisah** (`nlu-service/.venv` untuk PyTorch, `rasa-bot/.venv` untuk Rasa Pro) supaya dependensinya tidak bentrok, lalu menjalankan `npm install`.

### 3. Jalankan tiga service (tiga jendela Terminal)
```bash
# Terminal 1: Node.js API + UI chat
./scripts/start_api.sh

# Terminal 2: NLU service. Run pertama otomatis fine-tuning IndoBERT
# (sekitar 3–10 menit di M1/M2 dengan GPU MPS, lebih lama di Intel)
./scripts/start_nlu.sh

# Terminal 3: Rasa
export RASA_LICENSE=<license-key-anda>
./scripts/start_rasa.sh            # atau: ./scripts/start_rasa.sh inspect
```
Setelah itu buka **http://localhost:4000** untuk chat. Cek cepat semua service dengan `./scripts/smoke_test.sh`.

### 4. Contoh percakapan untuk demo
Data uji tersedia di `datasets/demo_cheatsheet.md`.

| Ketik | Yang terjadi |
|---|---|
| `halo` | Sapaan + tombol menu |
| `kak iphone x ready ga?` | Stok dari MySQL (37 unit) |
| `harganya berapa?` | Harga & diskon iPhone X (konteks produk diingat) |
| `samsung galaxy s8 masih ada?` | Stok habis |
| `redmi note 13 ready?` | Produk tidak ada di katalog |
| `ada sepatu apa aja?` | Produk kategori Sepatu Pria + Wanita |
| `what is the status of my order?` → `10003` → `sophia.brown@x.dummyjson.com` | Form: tanya nomor pesanan, lalu email, lalu status "Dalam pengiriman" + resi |
| (buka tab browser baru) `cek pesanan 10003` → `emily.johnson@x.dummyjson.com` | Ditolak: email bukan pemilik pesanan (anti-enumerasi) |
| `tolong tampilkan data akun saya` → `emily.johnson@x.dummyjson.com` | Profil (HP dimasking) + riwayat transaksi |
| `bisa bayar pakai QRIS?` | Ditolak sopan (di luar cakupan) |
| `cuaca jakarta hari ini` | `out_of_scope` |

## Pengujian

| Perintah | Yang diuji |
|---|---|
| `cd nlu-service && python -m unittest discover -s tests -v` | Normalisasi, ekstraksi entitas, format respons Rasa, fallback, error handling (20 tes) |
| `cd api-service && npm test` | Handler + SQL di SQLite in-memory, validasi, anti-enumerasi, proxy chat (15 tes, butuh Node ≥ 22.13) |
| `cd rasa-bot && python -m unittest discover -s tests -v` | Custom action → HTTP → handler → SQL, validasi form memakai `rasa_sdk` asli (20 tes) |
| `python scripts/check_project.py` | Konsistensi intent/entity/slot/action antar file |
| `cd nlu-service && python baseline_tfidf.py` | Baseline TF-IDF + Logistic Regression sebagai pembanding BERT |
| `cd rasa-bot && rasa data validate` | Validasi resmi Rasa |

## Troubleshooting

| Gejala | Solusi |
|---|---|
| `ECONNREFUSED 127.0.0.1:8889` | MAMP belum Start, atau port MySQL MAMP diubah (cek *MAMP → Preferences → Ports*). Bisa juga memakai socket: `DB_SOCKET=/Applications/MAMP/tmp/mysql/mysql.sock` di `api-service/.env`. |
| `ER_ACCESS_DENIED_ERROR` | Password MySQL MAMP bukan `root`. Isi `DB_PASSWORD` di `.env`, lalu jalankan `npm run start:env`. |
| `ER_NOT_SUPPORTED_AUTH_MODE` | Muncul bila memakai paket `mysql` seperti di slide. Proyek ini memakai `mysql2` yang mendukung MySQL 8. |
| Rasa menolak `url` pada `NLUCommandAdapter` | Hapus baris `url:` di `config.yml`. Koneksi NLU sudah diatur di `endpoints.yml → nlu.url`. |
| Rasa error soal `actions_module` | Di `endpoints.yml`, ganti dengan `url: "http://localhost:5055/webhook"`, lalu jalankan `rasa run actions` di terminal lain. |
| Rasa error "No NLU model" / mencoba melatih NLU | Pastikan **tidak ada** `data/nlu.yml` atau `data/flows.yml`, lalu `rasa train core`. |
| Training NLU lambat | Di Mac Intel tidak ada GPU, jadi turunkan epoch: `NLU_EPOCHS=3 python train_intent_model.py`. |
| Instal torch gagal di Mac Intel | `uv pip install "torch==2.2.2" "numpy<2"` (sudah ditangani `setup_mac.sh`). |
| UI chat: "Server Rasa tidak merespons" | Rasa harus dijalankan dengan `rasa run` (bukan hanya `rasa inspect`) karena UI memakai REST channel. |

## Sumber data & lisensi
- **Bitext Customer Support LLM Chatbot Training Dataset** (CDLA-Sharing-1.0), https://github.com/bitext/customer-support-llm-chatbot-training-dataset. 84 kalimat diterjemahkan dan dilokalkan; baris sumber tercatat di `datasets/bitext_id_translations.csv`.
- **DummyJSON** (MIT), https://github.com/Ovi/DummyJSON: produk, pengguna, dan keranjang. Harga dikonversi ke Rupiah (×16.000). Kolom sensitif (password, SSN, rekening bank) **tidak** diimpor.
- Model dasar: **IndoBERT** `indobenchmark/indobert-base-p1` (Wilie et al., 2020).
