// HTTP handler (validasi input -> repository -> format JSON).
// Format respons seragam:
//   sukses : { "success": true,  "data": {...} }
//   gagal  : { "success": false, "error": { "code": "...", "message": "..." } }
const repo = require('./repository');

const EMAIL_RE = /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i;
const ORDER_ID_RE = /^(?:ord-?|#)?(\d{5})$/i;
const SLUG_RE = /^[a-z][a-z-]{1,40}$/;

const STATUS_LABEL = {
  pending: 'Menunggu konfirmasi penjual',
  processing: 'Sedang dikemas',
  shipped: 'Dalam pengiriman',
  delivered: 'Sudah diterima',
  cancelled: 'Dibatalkan',
};

class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const ok = (res, data) => res.status(200).json({ success: true, data });
const clampInt = (v, def, min, max) => {
  const n = Number.parseInt(v, 10);
  return Number.isNaN(n) ? def : Math.min(Math.max(n, min), max);
};

function availability(stock) {
  if (stock <= 0) return { code: 'out_of_stock', label: 'Stok habis' };
  if (stock <= 10) return { code: 'low_stock', label: 'Stok terbatas' };
  return { code: 'in_stock', label: 'Tersedia' };
}

// Status ketersediaan DIHITUNG dari angka stok (satu sumber kebenaran). Data mentah
// DummyJSON menyimpan availabilityStatus terpisah dan terbukti tidak konsisten
// (mis. stok 8 berlabel "In Stock", stok 7 berlabel "Low Stock").
function formatProduct(p) {
  const av = availability(p.stock);
  const finalPrice = Math.round((p.price_idr * (1 - p.discount_percent / 100)) / 100) * 100;
  return {
    product_id: p.product_id,
    title: p.title,
    brand: p.brand,
    category_slug: p.category_slug,
    category_name: p.category_name,
    price_idr: p.price_idr,
    discount_percent: p.discount_percent,
    final_price_idr: finalPrice,
    stock: p.stock,
    availability: av.code,
    availability_label: av.label,
    rating: p.rating,
    warranty_info: p.warranty_info,
    shipping_info: p.shipping_info,
    return_policy: p.return_policy,
    description: p.description,
  };
}

function maskPhone(phone) {
  if (!phone) return null;
  const digits = phone.replace(/\D/g, '');
  return `${'*'.repeat(Math.max(digits.length - 4, 0))}${digits.slice(-4)}`;
}

function requireEmail(raw) {
  const email = String(raw || '').trim().toLowerCase();
  if (!EMAIL_RE.test(email) || email.length > 150) {
    throw new ApiError(400, 'VALIDATION_ERROR', 'Parameter email tidak valid');
  }
  return email;
}

function createHandlers(db) {
  return {
    async health(req, res) {
      try {
        await db.ping();
        return ok(res, { status: 'ok', database: 'connected' });
      } catch (e) {
        return res.status(503).json({
          success: false,
          error: { code: 'DATABASE_UNAVAILABLE', message: 'Database tidak dapat dihubungi' },
        });
      }
    },

    async searchProducts(req, res) {
      const q = String(req.query.q || '').trim();
      if (q.length < 2 || q.length > 100) {
        throw new ApiError(400, 'VALIDATION_ERROR', 'Parameter q wajib 2-100 karakter');
      }
      const limit = clampInt(req.query.limit, 5, 1, 20);
      const rows = await repo.searchProducts(db, q, limit);
      return ok(res, { query: q, count: rows.length, products: rows.map(formatProduct) });
    },

    async getProduct(req, res) {
      const id = Number.parseInt(req.params.id, 10);
      if (!Number.isInteger(id) || id <= 0 || String(id) !== String(req.params.id)) {
        throw new ApiError(400, 'VALIDATION_ERROR', 'ID produk harus bilangan bulat positif');
      }
      const p = await repo.getProductById(db, id);
      if (!p) throw new ApiError(404, 'PRODUCT_NOT_FOUND', 'Produk tidak ditemukan');
      return ok(res, formatProduct(p));
    },

    async listCategories(req, res) {
      const rows = await repo.listCategories(db);
      return ok(res, { count: rows.length, categories: rows });
    },

    async listProducts(req, res) {
      const slugs = String(req.query.category || '')
        .split(',')
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
      if (slugs.length === 0 || slugs.length > 5 || !slugs.every((s) => SLUG_RE.test(s))) {
        throw new ApiError(400, 'VALIDATION_ERROR',
          'Parameter category wajib, contoh: ?category=smartphones atau ?category=a,b');
      }
      const limit = clampInt(req.query.limit, 8, 1, 30);
      const rows = await repo.listProductsByCategories(db, slugs, limit);
      return ok(res, { categories: slugs, count: rows.length, products: rows.map(formatProduct) });
    },

    async lookupCustomer(req, res) {
      const email = requireEmail(req.query.email);
      const c = await repo.findCustomerByEmail(db, email);
      if (!c) {
        throw new ApiError(404, 'CUSTOMER_NOT_FOUND', 'Pelanggan dengan email tersebut tidak ditemukan');
      }
      const summary = await repo.customerOrderSummary(db, c.customer_id);
      const recent = await repo.customerOrders(db, c.customer_id, clampInt(req.query.limit, 5, 1, 20));
      return ok(res, {
        customer: {
          customer_id: c.customer_id,
          customer_name: c.customer_name,
          email: c.email,
          phone_masked: maskPhone(c.phone), // data minimization: nomor lengkap tidak dikirim
          city: c.city,
          member_since: String(c.created_at).slice(0, 10),
        },
        summary: {
          total_orders: Number(summary.total_orders || 0),
          total_spent_idr: Number(summary.total_spent_idr || 0),
          last_order_date: summary.last_order_date,
        },
        recent_orders: recent.map((o) => ({ ...o, status_label: STATUS_LABEL[o.order_status] })),
      });
    },

    async getOrder(req, res) {
      const m = ORDER_ID_RE.exec(String(req.params.orderId || '').trim());
      if (!m) {
        throw new ApiError(400, 'VALIDATION_ERROR', 'Nomor pesanan harus 5 digit, contoh 10023');
      }
      const email = requireEmail(req.query.email);
      const order = await repo.getOrderWithOwner(db, Number(m[1]));
      // Pesan sengaja SAMA untuk "tidak ada" dan "email tidak cocok" agar orang lain tidak
      // bisa menebak-nebak nomor pesanan milik pelanggan lain (enumeration).
      if (!order || order.email.toLowerCase() !== email) {
        throw new ApiError(404, 'ORDER_NOT_FOUND',
          'Pesanan tidak ditemukan atau email tidak cocok dengan pemilik pesanan');
      }
      const items = await repo.getOrderItems(db, order.order_id);
      return ok(res, {
        order_id: order.order_id,
        order_date: order.order_date,
        order_status: order.order_status,
        status_label: STATUS_LABEL[order.order_status],
        courier: order.courier,
        tracking_number: order.tracking_number,
        estimated_delivery: order.estimated_delivery,
        total_items: order.total_items,
        total_amount_idr: Number(order.total_amount_idr),
        customer_name: order.customer_name,
        items,
      });
    },
  };
}

module.exports = { createHandlers, ApiError, formatProduct, maskPhone, STATUS_LABEL };
