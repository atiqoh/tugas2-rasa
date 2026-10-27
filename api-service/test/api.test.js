// Uji otomatis handler + SQL repository TANPA MySQL: database diganti SQLite in-memory
// (node:sqlite, Node >= 22.13) yang diisi dari CSV yang sama dengan olshop_db.sql.
// Jalankan: npm test
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildSqlite } = require('../tools/sqlite-db');
const { createHandlers, ApiError, maskPhone } = require('../src/handlers');
const { createChatHandler } = require('../src/chat');
const { wrap } = require('../src/http-utils');

const db = buildSqlite();
const h = createHandlers(db);

function mockRes() {
  return {
    statusCode: 200,
    body: null,
    status(c) { this.statusCode = c; return this; },
    json(b) { this.body = b; return this; },
  };
}
async function call(fn, req) {
  const res = mockRes();
  try {
    await fn({ query: {}, params: {}, body: {}, ...req }, res);
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    res.status(e.status).json({ success: false, error: { code: e.code, message: e.message } });
  }
  return res;
}

test('cari produk: kecocokan persis berada di urutan pertama', async () => {
  const r = await call(h.searchProducts, { query: { q: 'iphone x' } });
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.data.products[0].title, 'iPhone X');
  assert.equal(r.body.data.products[0].availability, 'in_stock');
});

test('cari produk: pencarian per kata (samsung s8) & stok habis', async () => {
  const r = await call(h.searchProducts, { query: { q: 'samsung s8' } });
  const p = r.body.data.products.find((x) => x.title === 'Samsung Galaxy S8');
  assert.ok(p);
  assert.equal(p.stock, 0);
  assert.equal(p.availability_label, 'Stok habis');
});

test('cari produk: harga final setelah diskon dibulatkan ke ratusan', async () => {
  const r = await call(h.searchProducts, { query: { q: 'iPhone X' } });
  const p = r.body.data.products[0];
  assert.equal(p.final_price_idr % 100, 0);
  assert.ok(p.final_price_idr < p.price_idr);
});

test('cari produk: wildcard SQL dari user tidak dieksekusi sebagai wildcard', async () => {
  const r = await call(h.searchProducts, { query: { q: '%%' } });
  assert.equal(r.body.data.count, 0);
});

test('cari produk: validasi q', async () => {
  assert.equal((await call(h.searchProducts, { query: { q: 'a' } })).statusCode, 400);
  assert.equal((await call(h.searchProducts, {})).statusCode, 400);
});

test('produk by id', async () => {
  assert.equal((await call(h.getProduct, { params: { id: '124' } })).body.data.title, 'iPhone X');
  assert.equal((await call(h.getProduct, { params: { id: '9999' } })).statusCode, 404);
  assert.equal((await call(h.getProduct, { params: { id: '12abc' } })).statusCode, 400);
});

test('kategori & produk per kategori (multi-kategori)', async () => {
  const c = await call(h.listCategories, {});
  assert.equal(c.body.data.count, 24);
  const r = await call(h.listProducts, { query: { category: 'mens-shoes,womens-shoes', limit: '30' } });
  assert.equal(r.body.data.count, 10);
  const stocks = r.body.data.products.map((p) => p.stock > 0);
  assert.deepEqual(stocks, [...stocks].sort((a, b) => b - a)); // yang ada stok di depan
  assert.equal((await call(h.listProducts, { query: { category: "x'; DROP" } })).statusCode, 400);
});

test('data pelanggan: profil, ringkasan, riwayat, nomor HP dimasking', async () => {
  const r = await call(h.lookupCustomer, { query: { email: 'Emily.Johnson@x.dummyjson.com' } });
  assert.equal(r.statusCode, 200);
  const d = r.body.data;
  assert.equal(d.customer.customer_name, 'Emily Johnson');
  assert.match(d.customer.phone_masked, /^\*+\d{4}$/);
  assert.equal(d.summary.total_orders, 1);
  assert.equal(d.recent_orders[0].order_id, 10001);
  assert.ok(d.recent_orders[0].status_label);
});

test('data pelanggan: email tidak valid / tidak terdaftar', async () => {
  assert.equal((await call(h.lookupCustomer, { query: { email: 'bukan-email' } })).statusCode, 400);
  const r = await call(h.lookupCustomer, { query: { email: 'nobody@example.com' } });
  assert.equal(r.statusCode, 404);
  assert.equal(r.body.error.code, 'CUSTOMER_NOT_FOUND');
});

test('status pesanan: pemilik benar -> detail + item', async () => {
  const r = await call(h.getOrder, { params: { orderId: 'ORD-10001' }, query: { email: 'emily.johnson@x.dummyjson.com' } });
  assert.equal(r.statusCode, 200);
  assert.equal(r.body.data.order_id, 10001);
  assert.ok(r.body.data.items.length >= 2);
  assert.ok(r.body.data.status_label);
});

test('status pesanan: email bukan pemilik -> 404 dengan pesan yang sama (anti-enumerasi)', async () => {
  const wrong = await call(h.getOrder, { params: { orderId: '10001' }, query: { email: 'michael.williams@x.dummyjson.com' } });
  const missing = await call(h.getOrder, { params: { orderId: '99999' }, query: { email: 'michael.williams@x.dummyjson.com' } });
  assert.equal(wrong.statusCode, 404);
  assert.deepEqual(wrong.body, missing.body);
});

test('status pesanan: validasi format', async () => {
  assert.equal((await call(h.getOrder, { params: { orderId: '123' }, query: { email: 'a@b.co' } })).statusCode, 400);
  assert.equal((await call(h.getOrder, { params: { orderId: '10001' }, query: {} })).statusCode, 400);
});

test('maskPhone', () => {
  assert.equal(maskPhone('+81 965-431-3024'), '********3024');
  assert.equal(maskPhone(null), null);
});

test('proxy chat ke Rasa: sukses, validasi, dan Rasa mati', async () => {
  const fakeOk = async (url, opts) => {
    assert.equal(url, 'http://rasa:5005/webhooks/rest/webhook');
    assert.equal(JSON.parse(opts.body).message, 'halo');
    return { ok: true, json: async () => [{ recipient_id: 'u', text: 'Halo kak!' }] };
  };
  const r1 = await call(createChatHandler('http://rasa:5005', fakeOk), { body: { sender: 'u', message: 'halo' } });
  assert.equal(r1.body.data[0].text, 'Halo kak!');
  const r2 = await call(createChatHandler('http://rasa:5005', fakeOk), { body: { message: '' } });
  assert.equal(r2.statusCode, 400);
  const down = async () => { throw new Error('ECONNREFUSED'); };
  const r3 = await call(createChatHandler('http://rasa:5005', down), { body: { message: 'halo' } });
  assert.equal(r3.statusCode, 502);
});

test('wrap meneruskan error async ke next()', async () => {
  let got;
  await wrap(async () => { throw new Error('boom'); })({}, {}, (e) => { got = e; });
  assert.equal(got.message, 'boom');
});
