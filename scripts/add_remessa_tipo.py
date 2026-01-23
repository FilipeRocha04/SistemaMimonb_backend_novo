"""
Add 'tipo' column to 'pedido_remessas' with NOT NULL DEFAULT 'local'.

Supports MySQL/MariaDB and SQLite using the app's SQLAlchemy engine
and DATABASE_URL from backend/app/core/config.py.
"""

import sys
from pathlib import Path
# Ensure the backend folder (which contains the 'app' package) is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.db.session import engine, DATABASE_URL

def main():
    ddl = "ALTER TABLE pedido_remessas ADD COLUMN tipo VARCHAR(20) NOT NULL DEFAULT 'local'"
    # SQLite uses type TEXT and cannot enforce NOT NULL DEFAULT reliably for existing rows
    sqlite_ddl = "ALTER TABLE pedido_remessas ADD COLUMN tipo TEXT DEFAULT 'local'"
    try:
        with engine.begin() as conn:
            if DATABASE_URL.startswith('sqlite'):
                conn.execute(text(sqlite_ddl))
            else:
                conn.execute(text(ddl))
        print('ALTER_OK')
    except Exception as e:
        print('ALTER_FAILED', e)

if __name__ == "__main__":
    main()
