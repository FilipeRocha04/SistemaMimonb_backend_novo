import os
import mysql.connector
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', '')
# Parse DATABASE_URL format: mysql+pymysql://user:password@host:port/database
if DATABASE_URL.startswith('mysql+pymysql://'):
    DATABASE_URL = DATABASE_URL.replace('mysql+pymysql://', '')
    user, rest = DATABASE_URL.split(':')
    password, host_db = rest.split('@')
    host, db = host_db.split('/')
    host_port = host.split(':')
    if len(host_port) == 2:
        host, port = host_port
    else:
        host = host_port[0]
        port = '3306'
else:
    raise ValueError("DATABASE_URL format not recognized")

try:
    conn = mysql.connector.connect(
        host=host,
        user=user,
        password=password,
        port=int(port),
        database=db
    )
    cursor = conn.cursor()

    print("=== ALTERANDO COLUNA telefone PARA NULLABLE ===")
    
    # Verificar estrutura atual
    cursor.execute(f"DESCRIBE clientes;")
    columns = cursor.fetchall()
    print("\nEstrutura atual da tabela clientes:")
    for col in columns:
        print(f"  {col[0]}: {col[1]} (Null: {col[2]})")
    
    # Alterar a coluna
    alter_sql = "ALTER TABLE clientes MODIFY telefone VARCHAR(50) NULL;"
    cursor.execute(alter_sql)
    conn.commit()
    print("\n✅ Coluna telefone alterada para NULL com sucesso!")
    
    # Verificar estrutura após alteração
    cursor.execute(f"DESCRIBE clientes;")
    columns = cursor.fetchall()
    print("\nEstrutura atualizada da tabela clientes:")
    for col in columns:
        print(f"  {col[0]}: {col[1]} (Null: {col[2]})")
    
    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Erro: {str(e)}")
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'conn' in locals():
        conn.close()
