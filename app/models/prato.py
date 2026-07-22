from sqlalchemy import Column, BigInteger, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base


class Prato(Base):
    __tablename__ = 'pratos'

    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey('pedidos.id'), nullable=False)
    remessa_id = Column(BigInteger, ForeignKey('pedido_remessas.id'), nullable=False)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
