"""Small one-off script to add missing columns to the `clientes` table.

Run this once from the backend folder to add the `endereco` column if it's
missing in the remote MySQL database referenced by `backend/.env`.

Usage (from backend folder):
    py -3 scripts/add_missing_columns.py

This script checks information_schema to see if the column exists and runs
an ALTER TABLE only when needed. It prints the actions taken.
"""
import os
import sys
from sqlalchemy import create_engine, text

# Ensure backend folder is on sys.path so `import app` works when running this
# script directly.
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings


def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        # Check if the column `endereco` exists in the current database/schema
        check_sql = text(
            """
            SELECT COUNT(*) as cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'clientes'
              AND COLUMN_NAME = 'endereco'
            """
        )
        res = conn.execute(check_sql)
        cnt = int(res.scalar() or 0)
        if cnt == 0:
            print("Coluna 'endereco' não encontrada — executando ALTER TABLE ...")
            alter_sql = text("ALTER TABLE clientes ADD COLUMN endereco VARCHAR(500) NULL")
            conn.execute(alter_sql)
            print("Coluna 'endereco' adicionada com sucesso.")
        else:
            print("Coluna 'endereco' já existe. Nenhuma alteração necessária.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("Erro ao executar o script:", str(e))
        raise
