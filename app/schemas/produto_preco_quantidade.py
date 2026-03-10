from pydantic import BaseModel
from typing import Optional

class ProdutoPrecoQuantidadeRead(BaseModel):
    id: int
    produto_id: int
    quantidade: int
    preco: float

    model_config = {"from_attributes": True}

class ProdutoPrecoQuantidadeCreate(BaseModel):
    quantidade: int
    preco: float
