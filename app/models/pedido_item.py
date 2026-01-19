from sqlalchemy import Column, BigInteger, Integer, ForeignKey, String, Numeric, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base


class PedidoItem(Base):
    __tablename__ = 'pedido_items'

    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey('pedidos.id'), nullable=False)
    # optional association to a per-pedido remessa (shipment/partial delivery)
    remessa_id = Column(BigInteger, ForeignKey('pedido_remessas.id'), nullable=True)
    produto_id = Column(BigInteger, nullable=True)
    nome = Column(String(255), nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    preco = Column(Numeric(12, 2), nullable=False, default=0.0)
    # fator aplicado ao preço base do produto no momento da venda (ex.: 0.5 para meia pizza)
    preco_fator = Column(Numeric(4, 2), nullable=False, default=1.0)
    observacao = Column(Text, nullable=True)
    # status de preparo do item: 'pendente' | 'pronto'
    status = Column(String(20), nullable=False, server_default='pendente')

    # relationship backref is set on Pedido model
