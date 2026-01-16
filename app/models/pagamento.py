from sqlalchemy import Column, Integer, String, DateTime, Numeric, BigInteger, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base


class Pagamento(Base):
    __tablename__ = "pagamentos"

    id = Column(BigInteger, primary_key=True, index=True)
    # The database column is named `pedido_id` and is a FK to pedidos.id.
    # Keep the Python attribute name `pedido` so existing Pydantic schemas and
    # API payloads that use `pedido` continue to work. SQLAlchemy will map the
    # attribute to the `pedido_id` column in the DB.
    pedido = Column('pedido_id', BigInteger, ForeignKey('pedidos.id'), nullable=True)
    forma_pagamento = Column(String(80), nullable=True)
    status = Column(String(50), nullable=True)
    valor = Column(Numeric(10, 2), nullable=False, default=0)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())
