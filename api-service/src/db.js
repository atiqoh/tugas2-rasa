// Koneksi MySQL (MAMP) memakai mysql2/promise.
// Catatan: modul kuliah memakai paket `mysql`, tetapi paket itu tidak mendukung autentikasi
// default MySQL 8 (caching_sha2_password) yang dipakai MAMP versi baru -> error
// ER_NOT_SUPPORTED_AUTH_MODE. mysql2 mendukungnya dan menyediakan API Promise.
const mysql = require('mysql2/promise');

function createDb(dbConfig) {
  const options = {
    user: dbConfig.user,
    password: dbConfig.password,
    database: dbConfig.database,
    waitForConnections: true,
    connectionLimit: 10,
    charset: 'utf8mb4',
    decimalNumbers: true, // DECIMAL -> number (bukan string)
    dateStrings: true, // DATETIME dikembalikan apa adanya, tanpa geser zona waktu
  };
  if (dbConfig.socketPath) options.socketPath = dbConfig.socketPath;
  else Object.assign(options, { host: dbConfig.host, port: dbConfig.port });

  const pool = mysql.createPool(options);
  return {
    // pool.query (bukan execute): placeholder "?" di-escape di sisi klien, sehingga
    // "LIMIT ?" aman dipakai (execute/prepared statement bermasalah dengan LIMIT di MySQL 8).
    async query(sql, params = []) {
      const [rows] = await pool.query(sql, params);
      return rows;
    },
    async ping() {
      await pool.query('SELECT 1');
    },
    async close() {
      await pool.end();
    },
  };
}

module.exports = { createDb };
