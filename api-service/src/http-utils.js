// Utilitas HTTP tanpa dependensi Express (agar mudah diuji).
// Express 4 tidak menangkap error dari fungsi async -> bungkus agar diteruskan ke next().
const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);

module.exports = { wrap };
