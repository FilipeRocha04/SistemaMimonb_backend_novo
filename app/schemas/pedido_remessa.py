from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PedidoRemessaCreate(BaseModel):
    item_ids: Optional[list] = []
    observacao: Optional[str] = None
    endereco: Optional[str] = None
    # tipo da remessa: 'local' ou 'delivery'
    tipo: Optional[str] = 'local'
    status: Optional[str] = 'pendente'


class PedidoRemessaRead(BaseModel):
    id: int
    pedido_id: int
    observacao: Optional[str]
    endereco: Optional[str]
    tipo: Optional[str] = 'local'
    status: str
    criado_em: Optional[datetime]

    class Config:
        orm_mode = True
