from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base


class PedidoCategoriaStatus(Base):
    __tablename__ = 'pedido_categoria_status'

    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey('pedidos.id'), nullable=False, index=True)
    # chave simples da categoria usada na cozinha: 'pizza' ou 'bebida'
    categoria = Column(String(50), nullable=False)
    # status dessa categoria para o pedido: 'pendente', 'em_preparo', 'pronto'
    status = Column(String(20), nullable=False, server_default='pendente')
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
