import sqlite3

DB_NAME = "laundry.db"

def table_exists(cursor, table):
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
    """, (table,))
    return cursor.fetchone() is not None

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]

def migrate():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # =========================
    # PROVIDERS
    # =========================
    if not table_exists(cursor, "providers"):
        cursor.execute("""
        CREATE TABLE providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            country_code TEXT NOT NULL DEFAULT '+254',
            area TEXT NOT NULL,
            price_per_kg REAL NOT NULL DEFAULT 0,
            delivery_fee REAL NOT NULL DEFAULT 0,
            services TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            description TEXT,
            profile_pic TEXT DEFAULT 'profile_placeholder.png',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
    else:
        if not column_exists(cursor, "providers", "country_code"):
            cursor.execute("ALTER TABLE providers ADD COLUMN country_code TEXT DEFAULT '+254'")
        if not column_exists(cursor, "providers", "price_per_kg"):
            cursor.execute("ALTER TABLE providers ADD COLUMN price_per_kg REAL DEFAULT 0")
        if not column_exists(cursor, "providers", "delivery_fee"):
            cursor.execute("ALTER TABLE providers ADD COLUMN delivery_fee REAL DEFAULT 0")
        if not column_exists(cursor, "providers", "description"):
            cursor.execute("ALTER TABLE providers ADD COLUMN description TEXT")
        if not column_exists(cursor, "providers", "profile_pic"):
            cursor.execute("ALTER TABLE providers ADD COLUMN profile_pic TEXT")

    # =========================
    # RATINGS (REVIEWS)
    # =========================
    if not table_exists(cursor, "ratings"):
        cursor.execute("""
        CREATE TABLE ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            customer_name TEXT,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers(id)
        )
        """)

    # =========================
    # REVIEW TOKENS
    # =========================
    if not table_exists(cursor, "review_tokens"):
        cursor.execute("""
        CREATE TABLE review_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers(id)
        )
        """)

    # =========================
    # PASSWORD RESETS
    # =========================
    if not table_exists(cursor, "password_resets"):
        cursor.execute("""
        CREATE TABLE password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers(id)
        )
        """)

    conn.commit()
    conn.close()
    print("Database migrated successfully")

if __name__ == "__main__":
    migrate()
