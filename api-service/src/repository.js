// Semua query SQL berada di sini (pemisahan data-access dari HTTP handler).
// SQL sengaja ditulis portabel (MySQL & SQLite) agar bisa diuji otomatis tanpa MySQL.

const PRODUCT_COLS = `p.product_id, p.title, p.brand, p.category_slug, c.category_name,
  p.price_idr, p.discount_percent, p.stock, p.rating, p.warranty_info, p.shipping_info,
  p.return_policy, p.description`;

// Escape wildcard LIKE (% dan _) dari input pengguna. Karakter escape "!" dipilih karena
// valid di MySQL maupun SQLite (backslash berbeda perlakuannya di kedua DBMS).
const likeEscape = (s) => s.replace(/[!%_]/g, (m) => `!${m}`);

async function searchProducts(db, q, limit) {
  const query = q.toLowerCase();
  const tokens = query.split(/\s+/).filter(Boolean).slice(0, 6);
  const where = tokens
    .map(() => "(LOWER(p.title) LIKE ? ESCAPE '!' OR LOWER(COALESCE(p.brand, '')) LIKE ? ESCAPE '!')")
    .join(' AND ');
  const params = tokens.flatMap((t) => [`%${likeEscape(t)}%`, `%${likeEscape(t)}%`]);
  const sql = `SELECT ${PRODUCT_COLS}
    FROM products p JOIN categories c ON c.category_slug = p.category_slug
    WHERE ${where}
    ORDER BY CASE WHEN LOWER(p.title) = ? THEN 0
                  WHEN LOWER(p.title) LIKE ? ESCAPE '!' THEN 1
                  ELSE 2 END, p.title
    LIMIT ?`;
  return db.query(sql, [...params, query, `${likeEscape(query)}%`, limit]);
}

async function getProductById(db, id) {
  const rows = await db.query(
    `SELECT ${PRODUCT_COLS} FROM products p
     JOIN categories c ON c.category_slug = p.category_slug WHERE p.product_id = ?`,
    [id],
  );
  return rows[0] || null;
}

async function listCategories(db) {
  return db.query(
    `SELECT c.category_slug, c.category_name, COUNT(p.product_id) AS product_count,
            SUM(CASE WHEN p.stock > 0 THEN 1 ELSE 0 END) AS in_stock_count
     FROM categories c LEFT JOIN products p ON p.category_slug = c.category_slug
     GROUP BY c.category_slug, c.category_name
     ORDER BY c.category_name`,
  );
}

async function listProductsByCategories(db, slugs, limit) {
  const marks = slugs.map(() => '?').join(', ');
  return db.query(
    `SELECT ${PRODUCT_COLS} FROM products p
     JOIN categories c ON c.category_slug = p.category_slug
     WHERE p.category_slug IN (${marks})
     ORDER BY CASE WHEN p.stock > 0 THEN 0 ELSE 1 END, p.rating DESC, p.title
     LIMIT ?`,
    [...slugs, limit],
  );
}

async function findCustomerByEmail(db, email) {
  const rows = await db.query(
    `SELECT customer_id, customer_name, email, phone, city, created_at
     FROM customers WHERE LOWER(email) = LOWER(?)`,
    [email],
  );
  return rows[0] || null;
}

async function customerOrderSummary(db, customerId) {
  const rows = await db.query(
    `SELECT COUNT(*) AS total_orders,
            SUM(CASE WHEN order_status <> 'cancelled' THEN total_amount_idr ELSE 0 END)
              AS total_spent_idr,
            MAX(order_date) AS last_order_date
     FROM orders WHERE customer_id = ?`,
    [customerId],
  );
  return rows[0];
}

async function customerOrders(db, customerId, limit) {
  return db.query(
    `SELECT order_id, order_date, order_status, total_items, total_amount_idr
     FROM orders WHERE customer_id = ? ORDER BY order_date DESC LIMIT ?`,
    [customerId, limit],
  );
}

async function getOrderWithOwner(db, orderId) {
  const rows = await db.query(
    `SELECT o.order_id, o.order_date, o.order_status, o.courier, o.tracking_number,
            o.estimated_delivery, o.total_items, o.total_amount_idr,
            c.customer_id, c.customer_name, c.email
     FROM orders o JOIN customers c ON c.customer_id = o.customer_id
     WHERE o.order_id = ?`,
    [orderId],
  );
  return rows[0] || null;
}

async function getOrderItems(db, orderId) {
  return db.query(
    `SELECT oi.product_id, p.title, oi.quantity, oi.unit_price_idr
     FROM order_items oi JOIN products p ON p.product_id = oi.product_id
     WHERE oi.order_id = ? ORDER BY oi.order_item_id`,
    [orderId],
  );
}

module.exports = {
  searchProducts,
  getProductById,
  listCategories,
  listProductsByCategories,
  findCustomerByEmail,
  customerOrderSummary,
  customerOrders,
  getOrderWithOwner,
  getOrderItems,
};
