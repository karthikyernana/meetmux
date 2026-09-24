-- ==============================================================================
-- PlanGuard Supabase Demo Seed Script
-- Paste this entire file into the Supabase SQL Editor and click "Run".
-- ==============================================================================

-- 1. Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS hypopg;

-- 2. Drop existing demo tables if any
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- 3. Create schema
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'customer',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    stock INT NOT NULL DEFAULT 100,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    status VARCHAR(50) NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL,
    shipping_city VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id),
    product_id INT NOT NULL REFERENCES products(id),
    quantity INT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id),
    payment_method VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    transaction_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    event_type VARCHAR(100) NOT NULL,
    url VARCHAR(500),
    payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Fast Generation of Realistic Data (using generate_series)
-- Users (3,000)
INSERT INTO users (email, name, role, created_at)
SELECT
    'user_' || i || '@example.com',
    'Customer ' || i,
    CASE WHEN i % 10 = 0 THEN 'admin' ELSE 'customer' END,
    NOW() - (random() * interval '90 days')
FROM generate_series(1, 3000) AS i;

-- Products (1,000)
INSERT INTO products (sku, name, category, price, stock, created_at)
SELECT
    'SKU-' || lpad(i::text, 6, '0'),
    'Product ' || i,
    (ARRAY['Electronics', 'Apparel', 'Home', 'Books', 'Toys', 'Garden'])[1 + (i % 6)],
    ROUND((10 + random() * 490)::numeric, 2),
    (5 + (random() * 200)::int),
    NOW() - (random() * interval '120 days')
FROM generate_series(1, 1000) AS i;

-- Orders (15,000)
INSERT INTO orders (user_id, status, total_amount, shipping_city, created_at)
SELECT
    1 + (random() * 2999)::int,
    (ARRAY['completed', 'pending', 'cancelled', 'processing'])[1 + (i % 4)],
    ROUND((20 + random() * 600)::numeric, 2),
    (ARRAY['New York', 'Chicago', 'San Francisco', 'Austin', 'Seattle', 'Boston', 'Miami'])[1 + (i % 7)],
    NOW() - (random() * interval '60 days')
FROM generate_series(1, 15000) AS i;

-- Payments (15,000)
INSERT INTO payments (order_id, payment_method, status, amount, transaction_id, created_at)
SELECT
    i,
    (ARRAY['credit_card', 'paypal', 'apple_pay', 'crypto'])[1 + (i % 4)],
    (ARRAY['completed', 'refunded', 'failed'])[CASE WHEN i % 10 = 0 THEN 2 WHEN i % 25 = 0 THEN 3 ELSE 1 END],
    ROUND((20 + random() * 600)::numeric, 2),
    'TXN-' || md5(i::text),
    NOW() - (random() * interval '60 days')
FROM generate_series(1, 15000) AS i;

-- Events (20,000)
INSERT INTO events (user_id, event_type, url, payload, created_at)
SELECT
    1 + (random() * 2999)::int,
    (ARRAY['PAGE_VIEW', 'SEARCH', 'ADD_TO_CART', 'CHECKOUT', 'LOGOUT'])[1 + (i % 5)],
    '/products/' || (1 + (i % 1000)),
    jsonb_build_object('session_id', md5(i::text), 'source', 'web'),
    NOW() - (random() * interval '30 days')
FROM generate_series(1, 20000) AS i;

-- 5. Refresh table statistics so planner has accurate cardinalities
ANALYZE users;
ANALYZE products;
ANALYZE orders;
ANALYZE payments;
ANALYZE events;

-- 6. Trigger representative production queries to populate pg_stat_statements
-- Query 1: Join with filters on unindexed columns (triggers Seq Scan bottleneck on payments/orders)
SELECT o.id, o.user_id, o.total_amount, p.payment_method, p.status
FROM orders o
JOIN payments p ON o.id = p.order_id
WHERE o.shipping_city = 'Chicago' AND p.status = 'completed'
LIMIT 50;

SELECT o.id, o.user_id, o.total_amount, p.payment_method, p.status
FROM orders o
JOIN payments p ON o.id = p.order_id
WHERE o.shipping_city = 'San Francisco' AND p.status = 'completed'
LIMIT 50;

SELECT o.id, o.user_id, o.total_amount, p.payment_method, p.status
FROM orders o
JOIN payments p ON o.id = p.order_id
WHERE o.shipping_city = 'New York' AND p.status = 'completed'
LIMIT 50;

-- Query 2: Range query on orders with sorting (Seq Scan bottleneck)
SELECT id, user_id, total_amount, shipping_city, created_at
FROM orders
WHERE shipping_city = 'Austin' AND total_amount > 250.00
ORDER BY created_at DESC
LIMIT 50;

SELECT id, user_id, total_amount, shipping_city, created_at
FROM orders
WHERE shipping_city = 'Seattle' AND total_amount > 150.00
ORDER BY created_at DESC
LIMIT 50;

-- Query 3: Aggregation on events (large table scan)
SELECT user_id, count(*)
FROM events
WHERE event_type = 'PAGE_VIEW'
GROUP BY user_id
HAVING count(*) > 5
ORDER BY count(*) DESC
LIMIT 50;

SELECT user_id, count(*)
FROM events
WHERE event_type = 'ADD_TO_CART'
GROUP BY user_id
HAVING count(*) > 2
ORDER BY count(*) DESC
LIMIT 50;

-- Query 4: Products category filter and sort
SELECT id, sku, name, price, stock
FROM products
WHERE category = 'Electronics' AND price > 150.00
ORDER BY price ASC
LIMIT 50;

SELECT id, sku, name, price, stock
FROM products
WHERE category = 'Apparel' AND price > 50.00
ORDER BY price ASC
LIMIT 50;
