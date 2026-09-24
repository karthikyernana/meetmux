"""
Seed fixture database with realistic tables, data, and indexing bottlenecks.
Generates pg_stat_statements workload observations for PlanGuard analysis.
"""
import argparse
import os
import random
import time
import psycopg

DEFAULT_DSN = "host=localhost port=5432 dbname=fixture_db user=fixture password=fixture"

def seed(conn_arg):
    print("Connecting to database...")
    connect_fn = (lambda: psycopg.connect(**conn_arg, autocommit=True)) if isinstance(conn_arg, dict) else (lambda: psycopg.connect(conn_arg, autocommit=True))
    with connect_fn() as conn:
        with conn.cursor() as cur:
            print("Enabling extensions (pg_stat_statements, hypopg)...")
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
                print("  ✓ pg_stat_statements enabled")
            except Exception as e:
                print(f"  ⚠ pg_stat_statements warning: {e}")

            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS hypopg;")
                print("  ✓ hypopg enabled")
            except Exception as e:
                print(f"  ⚠ hypopg warning: {e}")

            print("Creating schema tables...")
            cur.execute("""
                DROP TABLE IF EXISTS events CASCADE;
                DROP TABLE IF EXISTS payments CASCADE;
                DROP TABLE IF EXISTS order_items CASCADE;
                DROP TABLE IF EXISTS orders CASCADE;
                DROP TABLE IF EXISTS products CASCADE;
                DROP TABLE IF EXISTS users CASCADE;

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
            """)

            print("Inserting users...")
            cur.execute("""
                INSERT INTO users (email, name, role, created_at)
                SELECT
                    'user_' || i || '@example.com',
                    'User ' || i,
                    CASE WHEN i % 20 = 0 THEN 'admin' ELSE 'customer' END,
                    NOW() - (random() * interval '365 days')
                FROM generate_series(1, 5000) i;
            """)

            print("Inserting products...")
            categories = ['Electronics', 'Books', 'Clothing', 'Home', 'Toys']
            cur.execute("""
                INSERT INTO products (sku, name, category, price, stock, created_at)
                SELECT
                    'SKU-' || i,
                    'Product ' || i,
                    (ARRAY['Electronics', 'Books', 'Clothing', 'Home', 'Toys'])[1 + (i % 5)],
                    (random() * 500 + 5)::numeric(10, 2),
                    (random() * 500)::int,
                    NOW() - (random() * interval '180 days')
                FROM generate_series(1, 1500) i;
            """)

            print("Inserting orders...")
            cur.execute("""
                INSERT INTO orders (user_id, status, total_amount, shipping_city, created_at)
                SELECT
                    1 + (i % 5000),
                    (ARRAY['PENDING', 'PROCESSING', 'COMPLETED', 'CANCELLED', 'REFUNDED'])[1 + (i % 5)],
                    (random() * 1000 + 10)::numeric(10, 2),
                    (ARRAY['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'San Francisco'])[1 + (i % 6)],
                    NOW() - (random() * interval '90 days')
                FROM generate_series(1, 25000) i;
            """)

            print("Inserting order items...")
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                SELECT
                    1 + (i % 25000),
                    1 + (i % 1500),
                    1 + (i % 5),
                    (random() * 200 + 10)::numeric(10, 2)
                FROM generate_series(1, 50000) i;
            """)

            print("Inserting payments...")
            cur.execute("""
                INSERT INTO payments (order_id, status, payment_method, amount, processed_at)
                SELECT
                    i,
                    CASE WHEN i % 10 = 0 THEN 'FAILED' ELSE 'SUCCESS' END,
                    (ARRAY['CREDIT_CARD', 'PAYPAL', 'APPLE_PAY', 'STRIPE'])[1 + (i % 4)],
                    (random() * 1000 + 10)::numeric(10, 2),
                    NOW() - (random() * interval '90 days')
                FROM generate_series(1, 25000) i;
            """)

            print("Inserting events...")
            cur.execute("""
                INSERT INTO events (user_id, event_type, payload, created_at)
                SELECT
                    1 + (i % 5000),
                    (ARRAY['PAGE_VIEW', 'ADD_TO_CART', 'CHECKOUT', 'LOGIN', 'LOGOUT'])[1 + (i % 5)],
                    '{"page": "/item/' || (i % 100) || '"}',
                    NOW() - (random() * interval '30 days')
                FROM generate_series(1, 35000) i;
            """)

            print("Analyzing tables for optimizer statistics...")
            cur.execute("ANALYZE users;")
            cur.execute("ANALYZE products;")
            cur.execute("ANALYZE orders;")
            cur.execute("ANALYZE order_items;")
            cur.execute("ANALYZE payments;")
            cur.execute("ANALYZE events;")

            print("Executing slow workload queries to populate pg_stat_statements...")
            cur.execute("SELECT pg_stat_statements_reset();")

            # 1. Filter without supporting index on status + sort
            for _ in range(25):
                cur.execute("""
                    SELECT id, user_id, total_amount, shipping_city, created_at
                    FROM orders
                    WHERE status = 'PENDING'
                    ORDER BY created_at DESC
                    LIMIT 20;
                """)

            # 2. Equality filter on user_id + status
            for u in [10, 25, 42, 100, 250, 420]:
                for _ in range(15):
                    cur.execute(f"""
                        SELECT id, total_amount, status, created_at
                        FROM orders
                        WHERE user_id = {u} AND status = 'COMPLETED'
                        ORDER BY created_at DESC;
                    """)

            # 3. Join without supporting index on foreign key
            for city in ['Chicago', 'San Francisco', 'New York']:
                for _ in range(10):
                    cur.execute(f"""
                        SELECT o.id, o.user_id, o.total_amount, p.payment_method, p.status
                        FROM orders o
                        JOIN payments p ON o.id = p.order_id
                        WHERE o.shipping_city = '{city}' AND p.status = 'SUCCESS';
                    """)

            # 4. Large scan on events
            for _ in range(20):
                cur.execute("""
                    SELECT user_id, count(*)
                    FROM events
                    WHERE event_type = 'PAGE_VIEW'
                    GROUP BY user_id
                    HAVING count(*) > 5
                    ORDER BY count(*) DESC
                    LIMIT 50;
                """)

            # 5. Product scan with range and ordering
            for _ in range(15):
                cur.execute("""
                    SELECT id, sku, name, price, stock
                    FROM products
                    WHERE category = 'Electronics' AND price > 150
                    ORDER BY price ASC
                    LIMIT 25;
                """)

            print("Fixture dataset ready with real pg_stat_statements metrics!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed database for PlanGuard demo")
    parser.add_argument("--url", "-u", default=None,
                        help="PostgreSQL connection string")
    parser.add_argument("--host", default=None, help="Database host")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    parser.add_argument("--database", "--dbname", default="postgres", help="Database name")
    parser.add_argument("--user", default="postgres", help="Database username")
    parser.add_argument("--password", default=None, help="Database password")
    parser.add_argument("--sslmode", default="prefer", help="SSL mode (disable, prefer, require)")
    args = parser.parse_args()

    if args.host and args.password:
        conn_dict = {
            "host": args.host,
            "port": args.port,
            "dbname": args.database,
            "user": args.user,
            "password": args.password,
            "sslmode": args.sslmode,
        }
        seed(conn_dict)
    elif args.url:
        seed(args.url)
    else:
        seed(os.getenv("TARGET_DB_URL", DEFAULT_DSN))
