"""
Add 'ativo' column to 'clientes' with NOT NULL DEFAULT 1 (true).
Supports MySQL/MariaDB and SQLite using the app's SQLAlchemy engine
and DATABASE_URL from backend/app/core/config.py.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.db.session import engine, DATABASE_URL


def main():
    mysql = "ALTER TABLE clientes ADD COLUMN ativo TINYINT(1) NOT NULL DEFAULT 1"
    sqlite = "ALTER TABLE clientes ADD COLUMN ativo BOOLEAN DEFAULT 1"
    try:
        with engine.begin() as conn:
            if DATABASE_URL.startswith('sqlite'):
                conn.execute(text(sqlite))
            else:
                conn.execute(text(mysql))
        print('ALTER_OK')
    except Exception as e:
        print('ALTER_FAILED', e)


if __name__ == "__main__":
    main()
