// Database SQLite in-memory berisi data yang sama dengan olshop_db.sql (dari CSV dataset).
// HANYA untuk pengujian otomatis tanpa MySQL. Butuh Node >= 22.13 (modul node:sqlite).
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

const DS = path.join(__dirname, '..', '..', 'datasets');

function parseCsv(text) {
  const rows = [];
  let row = [], field = '', inQ = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inQ) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i += 1; }
      else if (ch === '"') inQ = false;
      else field += ch;
    } else if (ch === '"') inQ = true;
    else if (ch === ',') { row.push(field); field = ''; }
    else if (ch === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (ch !== '\r') field += ch;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [head, ...body] = rows;
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] === '' ? null : r[i]])));
}

function buildSqlite() {
  const db = new DatabaseSync(':memory:');
  db.exec(`
    CREATE TABLE categories (category_slug TEXT PRIMARY KEY, category_name TEXT);
    CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, customer_name TEXT, email TEXT,
      phone TEXT, city TEXT, created_at TEXT);
    CREATE TABLE products (product_id INTEGER PRIMARY KEY, sku TEXT, title TEXT, brand TEXT,
      category_slug TEXT, description TEXT, price_idr INTEGER, discount_percent REAL,
      stock INTEGER, rating REAL, warranty_info TEXT, shipping_info TEXT, return_policy TEXT);
    CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT,
      order_status TEXT, courier TEXT, tracking_number TEXT, estimated_delivery TEXT,
      total_items INTEGER, total_amount_idr INTEGER);
    CREATE TABLE order_items (order_item_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER,
      product_id INTEGER, quantity INTEGER, unit_price_idr INTEGER);`);
  const numeric = new Set(['customer_id', 'product_id', 'price_idr', 'discount_percent', 'stock',
    'rating', 'order_id', 'total_items', 'total_amount_idr', 'quantity', 'unit_price_idr']);
  for (const t of ['categories', 'customers', 'products', 'orders', 'order_items']) {
    const rows = parseCsv(fs.readFileSync(path.join(DS, `${t}.csv`), 'utf8'));
    const cols = Object.keys(rows[0]);
    const stmt = db.prepare(`INSERT INTO ${t} (${cols.join(',')}) VALUES (${cols.map(() => '?').join(',')})`);
    for (const r of rows) stmt.run(...cols.map((c) => (numeric.has(c) && r[c] !== null ? Number(r[c]) : r[c])));
  }
  return {
    async query(sql, params = []) { return db.prepare(sql).all(...params).map((r) => ({ ...r })); },
    async ping() {},
  };
}

module.exports = { buildSqlite, parseCsv };
