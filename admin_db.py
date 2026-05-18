import sqlite3
import os
import uuid
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "admin.db")

class AdminDB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    license_key TEXT UNIQUE NOT NULL,
                    customer_email TEXT,
                    plan TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at REAL NOT NULL,
                    expires_at REAL
                )
            """)

    def create_license(self, email: str, plan: str, duration_days: int = 30) -> str:
        key = "QRV-" + str(uuid.uuid4()).upper()[:12]
        created_at = time.time()
        expires_at = created_at + (duration_days * 86400)
        
        with self.conn:
            self.conn.execute(
                "INSERT INTO licenses (license_key, customer_email, plan, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (key, email, plan, 'active', created_at, expires_at)
            )
        return key

    def get_all_licenses(self) -> list[dict]:
        with self.conn:
            rows = self.conn.execute("SELECT * FROM licenses ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def revoke_license(self, license_key: str):
        with self.conn:
            self.conn.execute("UPDATE licenses SET status='revoked' WHERE license_key=?", (license_key,))

    def activate_license(self, license_key: str):
        with self.conn:
            self.conn.execute("UPDATE licenses SET status='active' WHERE license_key=?", (license_key,))
            
    def validate_license(self, license_key: str) -> dict:
        """Returns the license data if valid and active, else None"""
        with self.conn:
            row = self.conn.execute("SELECT * FROM licenses WHERE license_key=?", (license_key,)).fetchone()
            if row:
                data = dict(row)
                if data["status"] == "active" and (not data["expires_at"] or data["expires_at"] > time.time()):
                    return data
            return None

# Singleton instance
ADMIN_DB = AdminDB()
