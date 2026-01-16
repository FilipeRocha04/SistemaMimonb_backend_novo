from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric
from sqlalchemy.sql import func
from app.db.session import Base


class Despesa(Base):
    __tablename__ = "despesas"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(String(10), nullable=False)  # ISO date YYYY-MM-DD
    descricao = Column(Text, nullable=True)
    categoria = Column(String(100), nullable=True)
    pagamento = Column(String(50), nullable=True)
    valor = Column(Numeric(10, 2), nullable=False, default=0)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())
