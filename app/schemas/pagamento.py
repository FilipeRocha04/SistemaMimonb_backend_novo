from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PagamentoBase(BaseModel):
    pedido: Optional[int]
    forma_pagamento: Optional[str]
    status: Optional[str] = 'pendente'
    valor: float = 0.0


class PagamentoCreate(PagamentoBase):
    pass


class PagamentoRead(PagamentoBase):
    id: int
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None

    class Config:
        orm_mode = True
