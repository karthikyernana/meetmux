-- =============================================================================
-- PlanGuard Local Seed Database Script (seed_ecommerce_local.sql)
--
-- This script sets up a realistic e-commerce database schema and workload:
-- 1. Installs extensions: pg_stat_statements (workload tracking) and hypopg (simulation)
-- 2. Creates 6 core tables: users, products, orders, order_items, payments, events
-- 3. Generates 115,000+ realistic rows with foreign keys and realistic distributions
-- 4. Runs ANALYZE to update PostgreSQL optimizer planner statistics
-- 5. Resets pg_stat_statements to clear DDL noise
-- 6. Executes unindexed workload queries that reveal real optimization candidates
-- =============================================================================

-- Step 1: Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS hypopg;

-- Step 2: Drop existing demo tables
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Step 3: Create schema
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
    status VARCHAR(50) NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    event_type VARCHAR(100) NOT NULL,
    payload TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Step 4: Populate realistic seed rows
-- 5,000 Users
INSERT INTO users (email, name, role, created_at)
SELECT
    'user_' || i || '@example.com',
    'Customer ' || i,
    CASE WHEN i % 25 = 0 THEN 'admin' ELSE 'customer' END,
    NOW() - (random() * interval '365 days')
FROM generate_series(1, 5000) i;

-- 1,500 Products
INSERT INTO products (sku, name, category, price, stock, created_at)
SELECT
    'SKU-' || i,
    'Product ' || i,
    (ARRAY['Electronics', 'Books', 'Clothing', 'Home & Kitchen', 'Sports'])[1 + (i % 5)],
    (random() * 500 + 5)::numeric(10, 2),
    (random() * 500)::int,
    NOW() - (random() * interval '180 days')
FROM generate_series(1, 1500) i;

-- 25,000 Orders
INSERT INTO orders (user_id, status, total_amount, shipping_city, created_at)
SELECT
    1 + (i % 5000),
    (ARRAY['PENDING', 'PROCESSING', 'COMPLETED', 'CANCELLED', 'REFUNDED'])[1 + (i % 5)],
    (random() * 1000 + 10)::numeric(10, 2),
    (ARRAY['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'San Francisco', 'Seattle', 'Austin'])[1 + (i % 8)],
    NOW() - (random() * interval '90 days')
FROM generate_series(1, 25000) i;

-- 50,000 Order Items
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT
    1 + (i % 25000),
    1 + (i % 1500),
    1 + (i % 5),
    (random() * 200 + 10)::numeric(10, 2)
FROM generate_series(1, 50000) i;

-- 25,000 Payments
INSERT INTO payments (order_id, status, payment_method, amount, processed_at)
SELECT
    i,
    CASE WHEN i % 10 = 0 THEN 'FAILED' ELSE 'SUCCESS' END,
    (ARRAY['CREDIT_CARD', 'PAYPAL', 'APPLE_PAY', 'STRIPE'])[1 + (i % 4)],
    (random() * 1000 + 10)::numeric(10, 2),
    NOW() - (random() * interval '90 days')
FROM generate_series(1, 25000) i;

-- 35,000 Tracking Events
INSERT INTO events (user_id, event_type, payload, created_at)
SELECT
    1 + (i % 5000),
    (ARRAY['PAGE_VIEW', 'ADD_TO_CART', 'CHECKOUT', 'LOGIN', 'LOGOUT'])[1 + (i % 5)],
    '{"page": "/item/' || (i % 100) || '"}',
    NOW() - (random() * interval '30 days')
FROM generate_series(1, 35000) i;

-- Step 5: Refresh PostgreSQL statistics
ANALYZE users;
ANALYZE products;
ANALYZE orders;
ANALYZE order_items;
ANALYZE payments;
ANALYZE events;

-- Step 6: Clear previous DDL noise from pg_stat_statements
SELECT pg_stat_statements_reset();

-- Step 7: Execute representative application workload to simulate production traffic
-- Workload Pattern 1: Pending orders by date (High impact, Sequential scan on orders)
DO $$
BEGIN
    FOR i IN 1..30 LOOP
        PERFORM id, user_id, total_amount, shipping_city, created_at
        FROM orders
        WHERE status = 'PENDING'
        ORDER BY created_at DESC
        LIMIT 20;
    END LOOP;
END $$;

-- Workload Pattern 2: Customer order lookup (Unindexed foreign key + status)
DO $$
DECLARE
    uid INT;
BEGIN
    FOR uid IN 1..25 LOOP
        PERFORM id, total_amount, status, created_at
        FROM orders
        WHERE user_id = uid AND status = 'COMPLETED'
        ORDER BY created_at DESC;
    END LOOP;
END $$;

-- Workload Pattern 3: City payment joins (Join between unindexed foreign keys)
DO $$
DECLARE
    c TEXT;
BEGIN
    FOREACH c IN ARRAY ARRAY['San Francisco', 'New York', 'Chicago', 'Seattle'] LOOP
        FOR i IN 1..10 LOOP
            PERFORM o.id, o.user_id, o.total_amount, p.payment_method, p.status
            FROM orders o
            JOIN payments p ON o.id = p.order_id
            WHERE o.shipping_city = c AND p.status = 'SUCCESS';
        END LOOP;
    END LOOP;
END $$;

-- Workload Pattern 4: High volume user event aggregation
DO $$
BEGIN
    FOR i IN 1..20 LOOP
        PERFORM user_id, count(*)
        FROM events
        WHERE event_type = 'PAGE_VIEW'
        GROUP BY user_id
        HAVING count(*) > 5
        ORDER BY count(*) DESC
        LIMIT 50;
    END LOOP;
END $$;

-- Workload Pattern 5: Product category pricing filter
DO $$
BEGIN
    FOR i IN 1..15 LOOP
        PERFORM id, sku, name, price, stock
        FROM products
        WHERE category = 'Electronics' AND price > 150
        ORDER BY price ASC
        LIMIT 25;
    END LOOP;
END $$;
