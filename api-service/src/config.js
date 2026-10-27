// Konfigurasi dari environment variable, default = setelan bawaan MAMP (macOS).
module.exports = {
  port: Number(process.env.PORT || 4000),
  db: {
    host: process.env.DB_HOST || '127.0.0.1',
    port: Number(process.env.DB_PORT || 8889), // port MySQL default MAMP
    user: process.env.DB_USER || 'root',
    password: process.env.DB_PASSWORD ?? 'root', // password default MAMP
    database: process.env.DB_NAME || 'olshop_db',
    socketPath: process.env.DB_SOCKET || undefined, // /Applications/MAMP/tmp/mysql/mysql.sock
  },
  rasaUrl: process.env.RASA_URL || 'http://localhost:5005',
  apiKey: process.env.API_KEY || '',
};
