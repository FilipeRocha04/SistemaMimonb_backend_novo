"""Add preco_fator column to pedido_items if missing.

Usage (from repo root or backend folder):
  python backend/scripts/add_pedido_items_preco_fator.py

This script is idempotent.
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # type: ignore


def column_exists(conn, table: str, col: str) -> bool:
    q = text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    )
    return bool(int(conn.execute(q, {"t": table, "c": col}).scalar() or 0))


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        if column_exists(conn, "pedido_items", "preco_fator"):
            print("Column 'preco_fator' already exists on pedido_items.")
        else:
            print("Adding column 'preco_fator' to pedido_items...")
            conn.execute(text("ALTER TABLE pedido_items ADD COLUMN preco_fator DECIMAL(4,2) NOT NULL DEFAULT 1.00"))
            try:
                conn.execute(text("COMMIT"))
            except Exception:
                pass
            print("Added 'preco_fator'.")


if __name__ == "__main__":
    main()
