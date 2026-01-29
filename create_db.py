import psycopg2
import psycopg2.extras
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")
# =========================
# ENVIRONMENT CHECK
# =========================
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable not set!")

# =========================
# DATABASE CONNECTION
# =========================
def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
    except Exception as e:
        print("Failed to connect to PostgreSQL:", e)
        raise

def table_exists(cursor, table):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, (table,))
    return cursor.fetchone()[0]

# =========================
# MIGRATION
# =========================
def migrate():
    conn = get_conn()
    cur = conn.cursor()

    # =========================
    # PROVIDERS
    # =========================
    if not table_exists(cur, "providers"):
        cur.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            country_code VARCHAR(10) NOT NULL DEFAULT '+254',
            area TEXT NOT NULL,
            price_per_kg NUMERIC(10,2) NOT NULL DEFAULT 0,
            delivery_fee NUMERIC(10,2) NOT NULL DEFAULT 0,
            services TEXT NOT NULL,
            phone VARCHAR(20) UNIQUE NOT NULL,
            password TEXT NOT NULL,
            description TEXT,
            profile_pic TEXT DEFAULT 'profile_placeholder.png',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

    # =========================
    # RATINGS (REVIEWS)
    # =========================
    if not table_exists(cur, "ratings"):
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            customer_name TEXT DEFAULT 'Anonymous',
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

    # =========================
    # REVIEW TOKENS
    # =========================
    if not table_exists(cur, "review_tokens"):
        cur.execute("""
        CREATE TABLE IF NOT EXISTS review_tokens (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            token UUID UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

    # =========================
    # PASSWORD RESETS
    # =========================
    if not table_exists(cur, "password_resets"):
        cur.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

    conn.commit()
    cur.close()
    conn.close()
    print("PostgreSQL database migrated successfully!")

# =========================
# RUN MIGRATION
# =========================
if __name__ == "__main__":
    migrate()
