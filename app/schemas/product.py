from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ProdutoCreate(BaseModel):
    nome: str
    categoria: Optional[str] = None
    unidade: Optional[str] = None
    unidade_valor: Optional[float] = 0.0
    preco: Optional[float] = 0.0
    descricao: Optional[str] = None
    ativo: Optional[bool] = True
    imagem: Optional[str] = None


class ProdutoRead(BaseModel):
    id: int
    nome: str
    categoria: Optional[str] = None
    unidade: Optional[str] = None
    unidade_valor: Optional[float] = 0.0
    preco: Optional[float] = 0.0
    descricao: Optional[str] = None
    ativo: Optional[bool] = True
    imagem: Optional[str] = None
    criado_em: Optional[datetime] = None

    class Config:
        orm_mode = True
