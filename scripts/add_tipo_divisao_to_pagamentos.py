#!/usr/bin/env python3
"""
Script para adicionar a coluna 'tipo_divisao' à tabela 'pagamentos'
Esta coluna irá armazenar se o pagamento foi feito como 'igualitaria' ou 'itens'
"""

import sys
sys.path.insert(0, '/app')

from sqlalchemy import text
from app.db.session import SessionLocal

def migrate():
    db = SessionLocal()
    try:
        # Verificar se a coluna já existe
        result = db.execute(text("""
            PRAGMA table_info(pagamentos)
        """))
        columns = [row[1] for row in result.fetchall()]
        
        if 'tipo_divisao' in columns:
            print("✓ Coluna 'tipo_divisao' já existe em 'pagamentos'")
            return
        
        # Adicionar a coluna
        print("Adicionando coluna 'tipo_divisao' à tabela 'pagamentos'...")
        db.execute(text("""
            ALTER TABLE pagamentos 
            ADD COLUMN tipo_divisao VARCHAR(20) DEFAULT 'igualitaria'
        """))
        db.commit()
        print("✓ Coluna 'tipo_divisao' adicionada com sucesso!")
        
    except Exception as e:
        print(f"✗ Erro ao adicionar coluna: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == '__main__':
    migrate()
