import sqlite3
import json
import os

# -------------------------
# CONFIG
# -------------------------
DB_NAME = "laundry.db"
BACKUP_FILE = "laundry_backup.json"

# -------------------------
# EXPORT FUNCTION
# -------------------------
def export_to_json():
    # Ensure the DB file exists
    if not os.path.exists(DB_NAME):
        print(f"❌ Database file '{DB_NAME}' not found.")
        return

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # allows dict conversion
    cursor = conn.cursor()

    data = {}

    # List of tables to export
    tables = ["providers", "ratings", "review_tokens"]

    for table in tables:
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        data[table] = [dict(row) for row in rows]  # convert each row to dict

    conn.close()

    # Write JSON file
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"✔ Database exported successfully to '{BACKUP_FILE}'!")

# -------------------------
# RUN EXPORT
# -------------------------
if __name__ == "__main__":
    export_to_json()
