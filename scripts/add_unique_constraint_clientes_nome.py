"""
Script para adicionar constraint UNIQUE ao campo nome da tabela clientes.
Primeiro remove registros duplicados (mantendo o mais antigo) e depois adiciona a constraint.
"""

from sqlalchemy import create_engine, text
import os
from app.db.session import Base
from app.models.client import Cliente

# Importar configurações
from app.core.config import settings

# Criar engine
DATABASE_URL = os.getenv("DATABASE_URL", settings.DATABASE_URL)
engine = create_engine(DATABASE_URL, echo=True)

def add_unique_constraint():
    with engine.begin() as connection:
        print("🔄 Iniciando migração...")
        
        # Passo 1: Verificar se existem duplicatas
        print("\n📋 Verificando registros duplicados...")
        result = connection.execute(text("""
            SELECT LOWER(nome), COUNT(*) as count
            FROM clientes
            GROUP BY LOWER(nome)
            HAVING count > 1
        """))
        
        duplicates = result.fetchall()
        if duplicates:
            print(f"⚠️  Encontrados {len(duplicates)} nomes duplicados:")
            for nome, count in duplicates:
                print(f"   - '{nome}': {count} registros")
            
            # Passo 2: Remover duplicatas mantendo o primeiro (menor id)
            print("\n🗑️  Removendo registros duplicados (mantendo o mais antigo)...")
            connection.execute(text("""
                DELETE FROM clientes
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM clientes
                    GROUP BY LOWER(nome)
                )
            """))
            print("✅ Registros duplicados removidos")
        else:
            print("✅ Nenhum registro duplicado encontrado")
        
        # Passo 3: Adicionar constraint UNIQUE
        print("\n🔐 Adicionando constraint UNIQUE ao campo nome...")
        try:
            connection.execute(text("""
                ALTER TABLE clientes
                ADD CONSTRAINT uk_clientes_nome UNIQUE (nome)
            """))
            print("✅ Constraint UNIQUE adicionado com sucesso!")
        except Exception as e:
            if "already exists" in str(e).lower() or "constraint" in str(e).lower():
                print("ℹ️  Constraint UNIQUE já existe")
            else:
                raise
        
        print("\n🎉 Migração concluída com sucesso!")

if __name__ == "__main__":
    try:
        add_unique_constraint()
    except Exception as e:
        print(f"\n❌ Erro durante migração: {e}")
        raise
