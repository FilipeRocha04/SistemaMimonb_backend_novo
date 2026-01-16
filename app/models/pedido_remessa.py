from sqlalchemy import Column, BigInteger, Text, DateTime, ForeignKey, String
from sqlalchemy.sql import func
from app.db.session import Base


class PedidoRemessa(Base):
    __tablename__ = 'pedido_remessas'
    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey('pedidos.id'), nullable=False)
    observacao_remessa = Column(Text, nullable=True)
    endereco = Column(String(255), nullable=True)
    # status of the remessa (pendente/pronto/etc). Default to 'pendente'.
    status = Column(String(20), nullable=False, server_default='pendente')
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
