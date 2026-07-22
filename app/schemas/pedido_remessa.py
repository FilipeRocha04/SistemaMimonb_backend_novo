from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.schemas.prato import PratoGroupCreate


class PedidoRemessaCreate(BaseModel):
    item_ids: Optional[list] = []
    observacao: Optional[str] = None
    endereco: Optional[str] = None
    # tipo da remessa: 'local' ou 'delivery'
    tipo: Optional[str] = 'local'
    status: Optional[str] = 'pendente'
    # grupos opcionais de itens (subconjunto de item_ids) a agrupar em "pratos"
    pratos: Optional[List[PratoGroupCreate]] = None


class PedidoRemessaRead(BaseModel):
    id: int
    pedido_id: int
    observacao: Optional[str]
    endereco: Optional[str]
    tipo: Optional[str] = 'local'
    status: str
    criado_em: Optional[datetime]

    model_config = {"from_attributes": True}
