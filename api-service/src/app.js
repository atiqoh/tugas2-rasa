// Merakit aplikasi Express: middleware, rute REST API, proxy chat ke Rasa, error handling.
const path = require('path');
const express = require('express');
const { createHandlers, ApiError } = require('./handlers');
const { createChatHandler } = require('./chat');
const { wrap } = require('./http-utils');

const DB_DOWN_CODES = new Set(['ECONNREFUSED', 'ER_ACCESS_DENIED_ERROR', 'ER_BAD_DB_ERROR',
  'PROTOCOL_CONNECTION_LOST', 'ETIMEDOUT', 'ENOENT']);

function createApp({ db, config, fetchImpl }) {
  const app = express();
  const h = createHandlers(db);
  app.disable('x-powered-by');
  app.use(express.json({ limit: '10kb' }));

  app.use((req, res, next) => {
    const t0 = Date.now();
    res.on('finish', () => {
      console.log(`${new Date().toISOString()} ${req.method} ${req.originalUrl} -> ${res.statusCode} (${Date.now() - t0} ms)`);
    });
    next();
  });

  // Opsional: proteksi API key sederhana untuk komunikasi chatbot -> service.
  app.use('/api', (req, res, next) => {
    if (config.apiKey && req.get('x-api-key') !== config.apiKey) {
      return res.status(401).json({ success: false, error: { code: 'UNAUTHORIZED', message: 'API key salah/tidak ada' } });
    }
    return next();
  });

  app.get('/api/health', wrap(h.health));
  app.get('/api/products/search', wrap(h.searchProducts));
  app.get('/api/products/:id', wrap(h.getProduct));
  app.get('/api/products', wrap(h.listProducts));
  app.get('/api/categories', wrap(h.listCategories));
  app.get('/api/customers/lookup', wrap(h.lookupCustomer));
  app.get('/api/orders/:orderId', wrap(h.getOrder));

  app.post('/chat', wrap(createChatHandler(config.rasaUrl, fetchImpl)));
  app.use(express.static(path.join(__dirname, '..', 'public')));

  app.use((req, res) => {
    res.status(404).json({ success: false, error: { code: 'NOT_FOUND', message: `Rute ${req.method} ${req.path} tidak ada` } });
  });

  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    if (err instanceof ApiError) {
      return res.status(err.status).json({ success: false, error: { code: err.code, message: err.message } });
    }
    if (err.type === 'entity.parse.failed') {
      return res.status(400).json({ success: false, error: { code: 'BAD_JSON', message: 'Body bukan JSON valid' } });
    }
    if (DB_DOWN_CODES.has(err.code)) {
      console.error('[DB]', err.code, err.message);
      return res.status(503).json({ success: false, error: { code: 'DATABASE_UNAVAILABLE', message: 'Database tidak dapat dihubungi' } });
    }
    console.error('[ERROR]', err);
    // Detail error SQL tidak dikirim ke klien (mencegah kebocoran struktur database).
    return res.status(500).json({ success: false, error: { code: 'INTERNAL_ERROR', message: 'Terjadi kesalahan di server' } });
  });

  return app;
}

module.exports = { createApp };
