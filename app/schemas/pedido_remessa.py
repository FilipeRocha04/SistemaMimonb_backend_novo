from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PedidoRemessaCreate(BaseModel):
    item_ids: Optional[list] = []
    observacao: Optional[str] = None
    endereco: Optional[str] = None
    status: Optional[str] = 'pendente'


class PedidoRemessaRead(BaseModel):
    id: int
    pedido_id: int
    observacao: Optional[str]
    endereco: Optional[str]
    status: str
    criado_em: Optional[datetime]

    class Config:
        orm_mode = True
