"""
Template kalimat (Bahasa Indonesia) untuk dataset NLU chatbot admin OlshopKu.

Sumber dataset:
1. Bitext Customer Support Dataset (CDLA-Sharing-1.0) -> taksonomi intent & kalimat
   sumber berbahasa Inggris. Sampel yang dipakai diterjemahkan/dilokalkan secara manual
   ke gaya chat olshop di file `bitext_id_translations.csv` (kolom bitext_row menunjuk
   baris asli di CSV Bitext sehingga bisa ditelusuri).
2. Template di bawah ini ditulis manual untuk intent yang tidak ada padanannya di Bitext
   (cek stok, harga, info produk, kategori, data pelanggan, dll.). Placeholder <product>,
   <category>, <order_id>, <email> akan diisi/ditutup oleh entity extractor (lihat
   nlu-service/entity_extractor.py), mengikuti pola "modtext" pada modul kuliah bab 7.

Catatan metodologis: kalimat-kalimat di sini BUKAN log percakapan nyata. Karena itu
evaluasi model dilakukan pada `nlu_test_heldout.csv` yang ditulis terpisah dengan gaya
bahasa berbeda, supaya akurasi tidak terlalu optimistis.
"""

TEMPLATES = {
    "greet": [
        "halo", "hai", "hi", "hallo kak", "selamat pagi", "selamat siang", "selamat sore",
        "selamat malam", "pagi kak", "siang min", "permisi", "assalamualaikum", "halo admin",
        "hai min", "hello", "hey", "punten", "misi kak", "halo, ada orang?", "hai, mau tanya",
        "halo kak mau nanya", "selamat pagi admin", "met pagi", "met malam kak", "spada",
        "hai kak, lagi online?", "halo selamat siang", "hello admin", "hi there", "good evening",
    ],
    "goodbye": [
        "bye", "dadah", "sampai jumpa", "makasih, bye", "udah itu aja", "sudah cukup",
        "oke sampai nanti", "see you", "daah kak", "selamat tinggal", "nanti saya chat lagi",
        "saya pamit", "udahan dulu ya", "sampai ketemu lagi", "bye bye", "oke kak, nanti lagi",
        "cukup sekian", "pamit dulu kak", "nanti balik lagi", "goodbye", "see you later",
        "oke deh, sampai jumpa", "itu aja kak, bye",
    ],
    "affirm": [
        "ya", "iya", "iyaa", "betul", "benar", "oke", "ok", "boleh", "sip", "siap", "yup",
        "yoi", "mau", "iya kak", "boleh kak", "betul sekali", "tentu", "ya dong", "setuju",
        "lanjut", "gas", "ya ada", "ada", "masih ada pertanyaan", "yes", "of course",
        "iya benar", "oke boleh", "mau dong", "bener kak",
    ],
    "deny": [
        "tidak", "nggak", "gak", "ga", "enggak", "no", "bukan", "batal", "batalkan",
        "gak jadi", "nggak jadi deh", "cancel", "stop", "berhenti", "tidak usah", "ga usah",
        "lain kali aja", "nanti aja", "tidak ada", "udah gak ada", "engga kak", "jangan",
        "skip", "no thanks", "tidak jadi", "sudah tidak ada", "batal aja kak", "gak usah deh",
    ],
    "thank_you": [
        "terima kasih", "makasih", "makasih kak", "thanks", "thank you", "trims", "tengkyu",
        "makasih banyak", "terima kasih banyak min", "oke makasih infonya", "sip makasih",
        "mantap, makasih", "thx", "makasi ya", "terimakasih atas bantuannya", "hatur nuhun",
        "suwun", "makasih ya min", "terima kasih kak, membantu banget", "thanks a lot",
    ],
    "bot_challenge": [
        "kamu bot ya?", "ini bot atau manusia?", "saya ngobrol sama robot?", "kamu manusia?",
        "ini admin beneran atau bot?", "apakah kamu robot", "yang bales mesin ya?", "kamu AI?",
        "ini chatbot?", "kamu siapa?", "ini dibalas otomatis?", "admin asli bukan sih?",
        "am i talking to a bot?", "are you human?", "kamu program komputer ya",
        "ini balasan otomatis bukan",
    ],
    "check_stock": [
        "<product> ready?", "<product> ready kak?", "<product> masih ada?", "stok <product> ada?",
        "stok <product> masih ada gak?", "ada stok <product>?", "<product> ready stock?",
        "apakah <product> tersedia?", "<product> tersedia gak?", "<product> masih tersedia?",
        "<product> habis ya?", "<product> sudah habis?", "cek stok <product>",
        "tolong cek stok <product>", "sisa stok <product> berapa?", "<product> sisa berapa?",
        "stok <product> tinggal berapa?", "jual <product> gak?", "ada jual <product>?",
        "kak, <product> ready ga", "<product> restock kapan?", "barang <product> ada?",
        "<product> ada gak kak", "mau tanya ketersediaan <product>",
        "ketersediaan stok <product>", "<product>", "<product> ada?", "yang <product> ready?",
        "<product> kosong?", "is <product> in stock?", "<product> available?",
        "cek stok dong", "stoknya ada?", "masih ready?", "ready kak?", "ready stock?",
        "barangnya masih ada?", "mau cek ketersediaan barang", "stoknya tinggal berapa?",
        "apakah barang ini tersedia?", "ready ga?", "mau cek stok barang",
    ],
    "ask_price": [
        "berapa harga <product>?", "harga <product> berapa?", "<product> harganya berapa?",
        "brp harga <product>", "<product> berapaan?", "<product> harganya?", "harga <product>?",
        "cek harga <product>", "info harga <product> dong", "<product> dijual berapa?",
        "<product> berapa kak?", "kisaran harga <product>", "<product> ada diskon?",
        "diskon <product> berapa persen?", "<product> lagi promo gak?",
        "harga terbaru <product>", "mau tanya harga <product>", "<product> mahal gak?",
        "how much is <product>?", "price list <product>", "harganya berapa?", "berapaan kak?",
        "brp kak harganya?", "harga nya?", "ada diskon gak?", "lagi ada promo?",
        "mau tanya harga", "berapa harganya kak", "harga barang ini berapa",
    ],
    "ask_product_info": [
        "spesifikasi <product> apa aja?", "info lengkap <product> dong", "detail <product>",
        "<product> garansinya berapa lama?", "<product> ada garansi?", "<product> bisa retur?",
        "<product> mereknya apa?", "<product> brand apa?", "rating <product> berapa?",
        "<product> bagus gak?", "review <product> gimana?", "deskripsi <product>",
        "<product> itu apa?", "jelasin tentang <product>", "<product> pengirimannya berapa hari?",
        "kategori <product> apa?", "mau tahu lebih banyak tentang <product>",
        "<product> kualitasnya gimana?", "info produk <product>", "tell me about <product>",
        "kelebihan <product> apa", "spek <product> dong", "spesifikasinya apa?",
        "garansinya berapa lama?", "ada garansi gak?", "produk ini bagus gak?",
        "detail produknya dong", "info produknya kak", "mau lihat spesifikasi produk",
    ],
    "browse_category": [
        "ada <category> apa aja?", "jual <category> gak?", "lihat daftar <category>",
        "<category> yang ready apa aja?", "list <category> dong", "mau lihat koleksi <category>",
        "ada <category>?", "produk <category> apa saja", "tampilkan <category>",
        "rekomendasi <category> dong", "pilihan <category> nya apa aja", "katalog <category>",
        "show me <category>", "mau cari <category>", "<category> nya ada apa aja kak",
        "kategori produk apa aja?", "jual apa aja kak?", "toko ini jual apa saja?",
        "lihat katalog", "ada kategori apa?", "produk apa saja yang dijual?",
        "mau lihat semua produk", "daftar kategori dong", "barang apa aja yang ada?",
        "menu produknya apa aja", "what do you sell?",
    ],
    "check_order_status": [
        "pesanan saya sudah sampai mana?", "paket saya di mana?", "cek status pesanan",
        "status order saya gimana?", "pesanan <order_id> sudah dikirim?",
        "order <order_id> statusnya apa?", "cek resi pesanan <order_id>",
        "nomor resi pesanan saya berapa?", "pesanan saya kok belum datang?",
        "kapan pesanan saya dikirim?", "barang yang saya pesan sudah dikemas?",
        "tracking pesanan <order_id>", "lacak paket saya", "pesanan <order_id> kapan sampai?",
        "status pengiriman order <order_id>", "orderan saya udah diproses belum?",
        "kak pesanan saya belum sampai", "cek orderan dong", "what is the status of my order",
        "where is my order <order_id>?", "track my order", "status pesanan <order_id>",
        "pesanan saya sudah diproses?", "paketnya udah jalan belum?",
    ],
    "check_customer_data": [
        "cek data akun saya", "lihat profil saya", "data pelanggan saya apa aja?",
        "tampilkan info akun", "email saya terdaftar gak?", "akun saya atas nama siapa?",
        "cek data customer saya", "riwayat belanja saya", "riwayat pesanan saya apa aja",
        "histori order saya", "saya sudah pernah order apa aja?",
        "data diri saya yang tersimpan apa?", "kota saya yang terdaftar apa?",
        "nomor hp saya yang terdaftar", "cek akun dengan email <email>", "data akun <email>",
        "lihat detail akun saya", "my account details", "show my customer data",
        "riwayat transaksi saya", "berapa kali saya sudah belanja?", "info member saya",
        "profil akun <email> dong", "transaksi saya apa saja",
    ],
    "provide_order_id": [
        "<order_id>", "nomor pesanannya <order_id>", "order id saya <order_id>",
        "ini nomornya <order_id>", "no pesanan <order_id>", "pesanan nomor <order_id>",
        "id order <order_id>", "kode pesanan <order_id>", "itu <order_id> kak", "<order_id> kak",
        "nomor order <order_id>", "my order number is <order_id>", "no order <order_id> ya",
        "pesanannya yang <order_id>",
    ],
    "provide_email": [
        "<email>", "email saya <email>", "emailnya <email>", "ini email saya <email>",
        "pakai email <email>", "email terdaftar <email>", "<email> kak",
        "alamat email saya <email>", "saya daftar pakai <email>", "my email is <email>",
        "email aku <email>", "pake email <email>", "<email> ya min", "terdaftar pakai <email>",
    ],
    "ask_delivery_info": [
        "ongkirnya berapa?", "kirim pakai kurir apa?", "bisa kirim ke luar pulau?",
        "bisa same day?", "ada instant delivery?", "pengiriman dari kota mana?",
        "ekspedisi apa yang dipakai?", "bisa pakai JNE?", "kirim pakai J&T bisa?",
        "estimasi pengiriman ke surabaya berapa hari?", "berapa lama pengiriman ke jakarta?",
        "pengiriman hari minggu ada?", "jam berapa batas pengiriman hari ini?",
        "paket dikirim jam berapa?", "ongkir ke makassar berapa", "bisa kirim pakai gosend?",
        "shipping nya berapa lama?", "what couriers do you use?",
    ],
    "ask_return_policy": [
        "bisa retur barang?", "kebijakan retur gimana?", "barang rusak bisa ditukar?",
        "kalau salah ukuran bisa tukar?", "cara pengembalian barang gimana?",
        "syarat retur apa aja?", "bisa refund?", "barang cacat gimana?",
        "mau komplain barang rusak", "tukar barang bisa?", "return policy nya apa?",
        "barang tidak sesuai bisa dikembalikan?", "berapa hari batas retur?",
    ],
    "contact_admin": [
        "mau ngomong sama admin", "hubungkan ke CS", "nomor WA admin berapa?",
        "minta kontak admin", "bisa telepon toko?", "email toko apa?",
        "saya mau komplain ke admin langsung", "panggil admin dong", "mau bicara sama manusia",
        "alamat toko di mana?", "contact customer service", "talk to a human agent",
        "admin manusianya ada?", "jam operasional toko jam berapa",
    ],
    "transaction_out_of_scope": [
        "saya mau checkout", "cara bayarnya gimana?", "bisa bayar pakai QRIS?",
        "transfer ke rekening mana?", "bisa COD?", "minta nomor rekening", "mau bayar sekarang",
        "konfirmasi pembayaran dong", "saya mau beli <product>", "tolong pesankan <product>",
        "masukin <product> ke keranjang", "mau order <product> 2", "bisa cicilan?",
        "bisa paylater?", "pakai kartu kredit bisa?", "mau batalin pembayaran",
        "minta invoice pembayaran", "kode voucher saya gak bisa dipakai",
        "i want to pay now", "beliin <product> satu ya",
    ],
    "out_of_scope": [
        "cuaca hari ini gimana", "siapa presiden indonesia", "ceritakan lelucon",
        "rekomendasi film bagus", "resep nasi goreng", "jam berapa sekarang",
        "kamu suka makan apa", "berapa 25 dikali 4", "terjemahkan ke bahasa inggris",
        "hasil pertandingan bola semalam", "lagu yang lagi viral apa", "ibukota jepang apa",
        "tolong buatkan puisi", "kamu tinggal di mana", "bagaimana cara masak rendang",
        "info lowongan kerja", "jadwal kereta ke bandung", "berita terbaru hari ini",
        "what's the weather like", "tell me a joke", "carikan tiket pesawat",
        "kapan libur nasional berikutnya", "ajarin aku coding python", "harga emas hari ini",
    ],
}

# Produk yang TIDAK ada di katalog -> dipakai sebagai variasi "nama mentah" agar model
# tetap mengenali konteks kalimat ketika gazetteer gagal mengenali nama produk.
UNKNOWN_PRODUCTS = [
    "xiaomi redmi note 12", "infinix hot 30", "poco x5", "asus rog phone 6", "sepatu ventela",
    "kaos polos hitam", "tumbler stainless", "serum somethinc", "lampu tidur led",
    "headset gaming", "powerbank 20000mah", "kemeja flanel", "hijab segi empat",
    "celana jeans", "botol minum", "keyboard mekanikal", "mouse wireless", "rak sepatu",
    "sprei katun", "kipas angin mini",
]

UNKNOWN_CATEGORIES = ["mainan anak", "buku", "alat tulis", "perlengkapan bayi", "obat"]

# Variasi sapaan/partikel khas chat olshop (augmentasi ringan).
PREFIXES_QUESTION = ["", "", "", "kak ", "min ", "halo kak, ", "permisi, ", "gan ", "sis ",
                     "mau tanya, ", "kak mau nanya, "]
SUFFIXES_QUESTION = ["", "", "", " dong", " ya", " kak", " nih", "?", " ya kak", " min",
                     " gan", " kak?"]
PREFIXES_SHORT = ["", "", "oh ", "oke "]
SUFFIXES_SHORT = ["", "", " kak", " min", "!", " ya"]

SHORT_INTENTS = {"greet", "goodbye", "affirm", "deny", "thank_you", "provide_order_id",
                 "provide_email", "bot_challenge"}
