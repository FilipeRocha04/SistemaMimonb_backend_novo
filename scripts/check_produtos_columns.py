"""Check columns on produtos table and print them.

Run from backend folder:
    py -3 scripts/check_produtos_columns.py
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
        try:
            q = text("SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'produtos'")
            res = conn.execute(q)
            rows = res.fetchall()
            if not rows:
                print("Tabela 'produtos' não encontrada no banco de dados atual.")
                return
            print("Colunas encontradas na tabela 'produtos':")
            for r in rows:
                print(f" - {r[0]} | type={r[1]} | nullable={r[2]} | default={r[3]}")
        except Exception as e:
            print('Erro ao consultar information_schema:', e)


if __name__ == '__main__':
    main()
