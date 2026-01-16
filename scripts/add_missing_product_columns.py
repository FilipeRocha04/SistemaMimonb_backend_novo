"""Script para adicionar colunas faltantes na tabela `produtos`.

Use este script apenas em ambiente de desenvolvimento ou após fazer backup do banco.
Ele verifica `information_schema.COLUMNS` e executa ALTER TABLE adicionando apenas
as colunas que estiverem ausentes.

Execução (dentro da pasta backend):
    py -3 scripts/add_missing_product_columns.py
"""
import os
import sys
from sqlalchemy import create_engine, text

# Ensure backend folder is on sys.path so `import app` works when running this
# script directly (e.g. `py -3 scripts/add_missing_product_columns.py`).
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings


def main():
    engine = create_engine(settings.DATABASE_URL)
    desired_columns = {
        'nome': "VARCHAR(255) NOT NULL",
        'categoria': "VARCHAR(100) NULL",
        'preco': "DOUBLE NOT NULL DEFAULT 0.0",
        'descricao': "TEXT NULL",
        'ativo': "TINYINT(1) NOT NULL DEFAULT 1",
    }

    with engine.connect() as conn:
        # fetch existing columns for 'produtos'
        q = text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'produtos'
        """)
        res = conn.execute(q)
        existing = {row[0] for row in res.fetchall()}

        for col, col_def in desired_columns.items():
            if col in existing:
                print(f"Coluna '{col}' já existe — pulando")
                continue
            alter = text(f"ALTER TABLE produtos ADD COLUMN {col} {col_def}")
            print(f"Adicionando coluna '{col}'...")
            conn.execute(alter)
            print(f"Coluna '{col}' adicionada.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Erro ao executar o script:', e)
        raise
