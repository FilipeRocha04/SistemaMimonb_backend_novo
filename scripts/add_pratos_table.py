"""
Cria a tabela 'pratos' e a coluna 'pedido_items.prato_id'.

Um "prato" agrupa um ou mais itens de uma remessa (montado no momento em
que os itens são adicionados ao pedido), para exibir contagem "Prato 1",
"Prato 2"... igual já é feito com as remessas.

Segue o padrão dos outros scripts em backend/scripts/ (ex: add_remessa_tipo.py):
usa o engine/DATABASE_URL do próprio app.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.db.session import engine, DATABASE_URL


def main():
    is_sqlite = DATABASE_URL.startswith('sqlite')

    create_table_sql = (
        "CREATE TABLE IF NOT EXISTS pratos ("
        "id BIGINT NOT NULL AUTO_INCREMENT, "
        "pedido_id BIGINT NOT NULL, "
        "remessa_id BIGINT NOT NULL, "
        "observacao TEXT NULL, "
        "criado_em DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "PRIMARY KEY (id), "
        "KEY idx_pratos_pedido_id (pedido_id), "
        "KEY idx_pratos_remessa_id (remessa_id), "
        "CONSTRAINT fk_pratos_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE, "
        "CONSTRAINT fk_pratos_remessa FOREIGN KEY (remessa_id) REFERENCES pedido_remessas(id) ON DELETE CASCADE"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    )
    create_table_sql_sqlite = (
        "CREATE TABLE IF NOT EXISTS pratos ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "pedido_id INTEGER NOT NULL, "
        "remessa_id INTEGER NOT NULL, "
        "observacao TEXT NULL, "
        "criado_em DATETIME DEFAULT CURRENT_TIMESTAMP"
        ")"
    )

    add_column_sql = "ALTER TABLE pedido_items ADD COLUMN prato_id BIGINT NULL"
    add_fk_sql = (
        "ALTER TABLE pedido_items ADD CONSTRAINT fk_pedido_items_prato "
        "FOREIGN KEY (prato_id) REFERENCES pratos(id) ON DELETE SET NULL"
    )
    add_index_sql = "ALTER TABLE pedido_items ADD KEY idx_pedido_items_prato_id (prato_id)"
    add_column_sql_sqlite = "ALTER TABLE pedido_items ADD COLUMN prato_id INTEGER NULL"

    with engine.begin() as conn:
        conn.execute(text(create_table_sql_sqlite if is_sqlite else create_table_sql))
        print('CREATE_TABLE_OK')

        try:
            conn.execute(text(add_column_sql_sqlite if is_sqlite else add_column_sql))
            print('ADD_COLUMN_OK')
        except Exception as e:
            print('ADD_COLUMN_SKIPPED_OR_FAILED:', e)

        if not is_sqlite:
            try:
                conn.execute(text(add_index_sql))
                print('ADD_INDEX_OK')
            except Exception as e:
                print('ADD_INDEX_SKIPPED_OR_FAILED:', e)

            try:
                conn.execute(text(add_fk_sql))
                print('ADD_FK_OK')
            except Exception as e:
                print('ADD_FK_SKIPPED_OR_FAILED:', e)


if __name__ == "__main__":
    main()
