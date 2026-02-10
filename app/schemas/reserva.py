from pydantic import BaseModel
from typing import Optional
from datetime import date, time, datetime
from enum import Enum


class ReservaStatus(str, Enum):
    pendente = 'pendente'
    confirmada = 'confirmada'
    cancelada = 'cancelada'


class ReservaBase(BaseModel):
    mesa: Optional[str] = None
    cliente_id: Optional[int]
    data_reserva: date
    hora_reserva: time
    quantidade_pessoas: int
    # Default new reservations to 'confirmada' per requested behavior
    status: ReservaStatus = ReservaStatus.confirmada
    observacao: Optional[str] = None


class ReservaCreate(ReservaBase):
    criado_em: Optional[datetime] = None


class ReservaRead(ReservaBase):
    id: int
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None
    cliente_name: Optional[str] = None

    class Config:
        orm_mode = True
