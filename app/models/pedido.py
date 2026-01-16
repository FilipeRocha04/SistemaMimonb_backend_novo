from sqlalchemy import Column, BigInteger, String, Date, Time, Text, Numeric, DateTime, ForeignKey, SmallInteger
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Pedido(Base):
    __tablename__ = 'pedidos'
    id = Column(BigInteger, primary_key=True, index=True)
    cliente_id = Column(BigInteger, ForeignKey('clientes.id'), nullable=True)
    usuario_id = Column(BigInteger, nullable=True)
    tipo = Column(String(20), nullable=False, default='local')  # 'local' or 'delivery'
    status = Column(String(50), nullable=False, default='pendente')
    subtotal = Column(Numeric(12, 2), nullable=False, default=0.0)
    adicional_10 = Column(SmallInteger, nullable=False, default=0)  # 0 or 1
    valor_total = Column(Numeric(12, 2), nullable=False, default=0.0)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    # relationship to items (PedidoItem)
    items = relationship('PedidoItem', backref='pedido', cascade='all, delete-orphan', lazy='selectin')
    # optional joined cliente relationship for convenience
    from app.models.client import Cliente  # local import to avoid circular
    from sqlalchemy.orm import relationship as _relationship
    cliente = _relationship('Cliente', lazy='joined', viewonly=True)
