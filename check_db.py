import os
from sqlalchemy import create_engine, text

# Usar a URL de conexão do .env
DATABASE_URL = os.getenv("DATABASE_URL", "mysql://mimonb:Filipe%402004@31.97.31.73:3306/mimonbdevofc")
# Converter mysql:// para mysql+pymysql://
DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://")
engine = create_engine(DATABASE_URL, echo=False)

try:
    with engine.connect() as conn:
        # Verificar campos da tabela clientes
        result = conn.execute(text("DESCRIBE clientes"))
        print("=== ESTRUTURA DA TABELA CLIENTES ===")
        for row in result:
            print(f"{row[0]}: {row[1]} (Null: {row[2]}, Key: {row[3]})")
        
        # Verificar se existe constraint UNIQUE no campo nome
        print("\n=== CONSTRAINTS UNICAS ===")
        result = conn.execute(text("""
            SELECT CONSTRAINT_NAME, COLUMN_NAME 
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
            WHERE TABLE_NAME = 'clientes' AND CONSTRAINT_NAME != 'PRIMARY'
        """))
        for row in result:
            print(f"Constraint: {row[0]} - Coluna: {row[1]}")
        
        # Verificar triggers
        print("\n=== TRIGGERS ===")
        result = conn.execute(text("""
            SELECT TRIGGER_NAME, EVENT_MANIPULATION, ACTION_TIMING
            FROM INFORMATION_SCHEMA.TRIGGERS 
            WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = 'clientes'
        """))
        triggers = result.fetchall()
        if triggers:
            for row in triggers:
                print(f"Trigger: {row[0]} - Event: {row[1]} - Timing: {row[2]}")
        else:
            print("Nenhum trigger encontrado")
            
except Exception as e:
    print(f"Erro: {e}")
    import traceback
    traceback.print_exc()
