// Server uji TANPA Express & TANPA MySQL: rute yang sama dengan src/app.js, tetapi memakai
// node:http + SQLite in-memory. Dipakai oleh tes integrasi Python (rasa-bot/tests) agar
// custom action benar-benar memanggil HTTP -> handler -> SQL.  Bukan untuk produksi.
//   node tools/sqlite-dev-server.js 4100
const http = require('node:http');
const { buildSqlite } = require('./sqlite-db');
const { createHandlers, ApiError } = require('../src/handlers');

const h = createHandlers(buildSqlite());
const routes = [
  [/^\/api\/health$/, h.health, []],
  [/^\/api\/products\/search$/, h.searchProducts, []],
  [/^\/api\/products\/([^/]+)$/, h.getProduct, ['id']],
  [/^\/api\/products$/, h.listProducts, []],
  [/^\/api\/categories$/, h.listCategories, []],
  [/^\/api\/customers\/lookup$/, h.lookupCustomer, []],
  [/^\/api\/orders\/([^/]+)$/, h.getOrder, ['orderId']],
];

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const out = {
    statusCode: 200,
    status(c) { this.statusCode = c; return this; },
    json(body) {
      res.writeHead(this.statusCode, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(body));
      return this;
    },
  };
  const hit = routes.find(([re]) => re.test(url.pathname));
  if (!hit || req.method !== 'GET') return out.status(404).json({ success: false, error: { code: 'NOT_FOUND' } });
  const [re, fn, names] = hit;
  const m = re.exec(url.pathname);
  const params = Object.fromEntries(names.map((n, i) => [n, decodeURIComponent(m[i + 1])]));
  try {
    await fn({ query: Object.fromEntries(url.searchParams), params }, out);
  } catch (e) {
    if (e instanceof ApiError) return out.status(e.status).json({ success: false, error: { code: e.code, message: e.message } });
    console.error(e);
    return out.status(500).json({ success: false, error: { code: 'INTERNAL_ERROR' } });
  }
  return undefined;
});

const port = Number(process.argv[2] || 4100);
server.listen(port, () => console.log(`sqlite dev server on ${port}`));
