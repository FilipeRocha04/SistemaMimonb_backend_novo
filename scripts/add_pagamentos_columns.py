"""Add missing timestamp columns to the `pagamentos` table if they don't exist.

Run this from the repository root or the `backend` folder. It will import the
application settings to get the DATABASE_URL and execute safe ALTER TABLE
statements only when columns are missing.

Usage (from repo root):
  python backend/scripts/add_pagamentos_columns.py

The script prints what it does. It is idempotent: running it twice does nothing
the second time.
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine, text


# Ensure we can import app.core.config regardless of current working dir
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

try:
    from app.core.config import settings
except Exception as e:
    print("Failed to import app.core.config. Run this from the repo root or backend folder.")
    raise


def column_exists(conn, col_name: str) -> bool:
    q = text(
        "SELECT COUNT(*) as cnt FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pagamentos' AND COLUMN_NAME = :col"
    )
    res = conn.execute(q, {"col": col_name}).scalar()
    return bool(res and int(res) > 0)


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        # Check criado_em
        if column_exists(conn, "criado_em"):
            print("Column 'criado_em' already exists.")
        else:
            print("Adding column 'criado_em'...")
            # Add criado_em with CURRENT_TIMESTAMP default
            conn.execute(text(
                "ALTER TABLE pagamentos ADD COLUMN criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ))
            print("Added 'criado_em'.")

        # Check atualizado_em
        if column_exists(conn, "atualizado_em"):
            print("Column 'atualizado_em' already exists.")
        else:
            print("Adding column 'atualizado_em'...")
            # Add atualizado_em with ON UPDATE CURRENT_TIMESTAMP so SQLAlchemy onupdate works
            # Note: setting DEFAULT NULL and ON UPDATE works on modern MySQL versions.
            conn.execute(text(
                "ALTER TABLE pagamentos ADD COLUMN atualizado_em DATETIME NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP"
            ))
            print("Added 'atualizado_em'.")

        # Make sure changes are persisted
        try:
            conn.execute(text("COMMIT"))
        except Exception:
            # Some drivers autocommit DDL; ignore commit errors
            pass

    print("Done. Restart your backend and retry the operation that failed.")


if __name__ == '__main__':
    main()
