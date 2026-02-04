from sqlalchemy import Column, Integer, String, DateTime, Numeric, BigInteger, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base

class Pagador(Base):
    __tablename__ = "pagadores"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

class PagamentoPagadorForma(Base):
    __tablename__ = "pagamento_pagador_forma"
    id = Column(Integer, primary_key=True, index=True)
    pagamento_id = Column(BigInteger, ForeignKey('pagamentos.id'), nullable=False)
    pagador_id = Column(Integer, ForeignKey('pagadores.id'), nullable=False)
    forma_pagamento = Column(String(80), nullable=False)
    valor = Column(Numeric(10, 2), nullable=False, default=0)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

# ...existing code...
