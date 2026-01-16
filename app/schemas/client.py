from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClienteCreate(BaseModel):
    nome: str
    telefone: Optional[str] = None
    endereco: Optional[str] = None
    observacoes: Optional[str] = None


class ClienteRead(BaseModel):
    id: int
    nome: str
    telefone: Optional[str] = None
    endereco: Optional[str] = None
    observacoes: Optional[str] = None
    criado_em: Optional[datetime] = None

    class Config:
        orm_mode = True
