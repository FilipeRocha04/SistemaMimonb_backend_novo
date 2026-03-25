#!/usr/bin/env python3
"""
Script para adicionar a coluna 'pagar_depois' à tabela pedidos.
"""
import sqlite3
import sys

def add_pagar_depois_column():
    try:
        # Conecta ao banco de dados
        conn = sqlite3.connect('../mimonb.db')
        cursor = conn.cursor()
        
        # Verifica se a coluna já existe
        cursor.execute("PRAGMA table_info(pedidos)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'pagar_depois' in columns:
            print("✓ Coluna 'pagar_depois' já existe na tabela 'pedidos'")
            conn.close()
            return True
        
        # Adiciona a coluna
        cursor.execute("""
            ALTER TABLE pedidos 
            ADD COLUMN pagar_depois SMALLINT NOT NULL DEFAULT 0
        """)
        
        conn.commit()
        print("✓ Coluna 'pagar_depois' adicionada com sucesso à tabela 'pedidos'")
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"✗ Erro ao adicionar coluna: {e}")
        return False
    except Exception as e:
        print(f"✗ Erro inesperado: {e}")
        return False

if __name__ == '__main__':
    success = add_pagar_depois_column()
    sys.exit(0 if success else 1)
