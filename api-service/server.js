// Titik masuk external service. Jalankan:  npm start   (atau npm run start:env)
const config = require('./src/config');
const { createDb } = require('./src/db');
const { createApp } = require('./src/app');

const db = createDb(config.db);
const app = createApp({ db, config });

const server = app.listen(config.port, async () => {
  console.log(`OlshopKu API berjalan di http://localhost:${config.port}`);
  console.log(`Chat UI: http://localhost:${config.port}/   |   Health: /api/health`);
  try {
    await db.ping();
    const where = config.db.socketPath || `${config.db.host}:${config.db.port}`;
    console.log(`MySQL (MAMP) terhubung -> ${where}/${config.db.database}`);
  } catch (e) {
    console.error(`PERINGATAN: gagal konek MySQL (${e.code || e.message}). ` +
      'Pastikan MAMP sudah Start dan olshop_db.sql sudah di-import.');
  }
});

const shutdown = () => server.close(() => db.close().finally(() => process.exit(0)));
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
