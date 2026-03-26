from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)
try:
    with engine.connect() as conn:
        sql = "ALTER TABLE pedidos MODIFY COLUMN status ENUM('pendente','em_preparo','pronto','aguardando','entregue','cancelado','pago') NOT NULL DEFAULT 'pendente'"
        conn.execute(text(sql))
        conn.commit()
        print('✓ ENUM status atualizado com sucesso! "pago" adicionado.')
except Exception as e:
    print(f'Erro: {e}')
