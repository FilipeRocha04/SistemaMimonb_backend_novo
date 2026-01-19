"""Add a DATE column `data` to the `pedidos` table and backfill from `criado_em`.

Usage (from repo root):
  python backend/scripts/add_data_column_to_pedidos.py

This script is idempotent and prints actions taken. It requires DATABASE_URL
configured in backend/app/core/config.py (loaded via backend/.env).
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

# Ensure backend package is importable
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

try:
    from app.core.config import settings
except Exception as e:
    print("Failed to import app.core.config. Run this from the repo root or backend folder.")
    raise


def column_exists(conn, table: str, col_name: str) -> bool:
    q = text(
        "SELECT COUNT(*) as cnt FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :col"
    )
    res = conn.execute(q, {"table": table, "col": col_name}).scalar()
    return bool(res and int(res) > 0)


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        # Add column `data` if missing
        if column_exists(conn, "pedidos", "data"):
            print("Column 'data' already exists on pedidos.")
        else:
            print("Adding column 'data' (DATE) to pedidos ...")
            # Use NULL default; we will backfill from criado_em for existing rows
            conn.execute(text("ALTER TABLE pedidos ADD COLUMN data DATE NULL"))
            print("Added column 'data'.")

        # Backfill from criado_em when data is NULL
        print("Backfilling 'data' from 'criado_em' where NULL ...")
        conn.execute(text("UPDATE pedidos SET data = DATE(criado_em) WHERE data IS NULL AND criado_em IS NOT NULL"))
        print("Backfill complete.")

        # Commit changes (some drivers autocommit DDL; ignore errors)
        try:
            conn.execute(text("COMMIT"))
        except Exception:
            pass

    print("Done. Restart your backend to use the new column.")


if __name__ == '__main__':
    main()
