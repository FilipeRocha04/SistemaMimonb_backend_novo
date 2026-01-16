from sqlalchemy import Column, BigInteger, Integer, String, Date, Time, Text, Enum, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base
import enum


class ReservaStatus(enum.Enum):
    pendente = 'pendente'
    confirmada = 'confirmada'
    cancelada = 'cancelada'


class Reserva(Base):
    __tablename__ = 'reservas'

    id = Column(BigInteger, primary_key=True, index=True)
    mesa_id = Column(BigInteger, nullable=True)
    cliente_id = Column(BigInteger, nullable=True)
    cliente_id = Column(BigInteger, ForeignKey("clientes.id"), nullable=True)
    data_reserva = Column(Date, nullable=False)
    hora_reserva = Column(Time, nullable=False)
    quantidade_pessoas = Column(Integer, nullable=False, default=1)
    status = Column(Enum(ReservaStatus), nullable=False, default=ReservaStatus.pendente)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())
    # Optional relationship to Cliente model for convenience
    try:
        from app.models.client import Cliente  # noqa: F401
        from sqlalchemy.orm import relationship
        cliente = relationship("Cliente", backref="reservas")
    except Exception:
        pass
