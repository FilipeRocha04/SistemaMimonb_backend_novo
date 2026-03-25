#!/usr/bin/env python3
"""
Script simples para adicionar a coluna 'pagar_depois' à tabela pedidos.
"""
import sqlite3

# Conecta ao banco de dados
conn = sqlite3.connect('mimonb.db')
cursor = conn.cursor()

try:
    # Verifica se a coluna já existe
    cursor.execute("PRAGMA table_info(pedidos)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'pagar_depois' in columns:
        print("✓ Coluna 'pagar_depois' já existe")
    else:
        # Adiciona a coluna
        cursor.execute("ALTER TABLE pedidos ADD COLUMN pagar_depois INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        print("✓ Coluna 'pagar_depois' adicionada com sucesso!")
        
except Exception as e:
    print(f"✗ Erro: {e}")
finally:
    conn.close()
