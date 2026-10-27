// Proxy chat: UI web -> Node -> Rasa REST channel (/webhooks/rest/webhook).
const { ApiError } = require('./handlers');

function createChatHandler(rasaUrl, fetchImpl = globalThis.fetch) {
  return async (req, res) => {
    const { sender, message } = req.body || {};
    if (typeof message !== 'string' || !message.trim() || message.length > 500) {
      throw new ApiError(400, 'VALIDATION_ERROR', 'Field message wajib (1-500 karakter)');
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const r = await fetchImpl(`${rasaUrl}/webhooks/rest/webhook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender: String(sender || 'web-user').slice(0, 64), message }),
        signal: controller.signal,
      });
      if (!r.ok) throw new Error(`Rasa HTTP ${r.status}`);
      return res.json({ success: true, data: await r.json() });
    } catch (e) {
      return res.status(502).json({
        success: false,
        error: { code: 'RASA_UNAVAILABLE', message: 'Server Rasa tidak merespons. Sudah dijalankan dengan `rasa run`?' },
      });
    } finally {
      clearTimeout(timer);
    }
  };
}

module.exports = { createChatHandler };
