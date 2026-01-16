from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ProdutoPrecoRead(BaseModel):
    id: int
    produto_id: int
    preco: float
    criado_em: Optional[datetime] = None

    class Config:
        orm_mode = True
