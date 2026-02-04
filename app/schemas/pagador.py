from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PagadorBase(BaseModel):
    nome: str

class PagadorCreate(PagadorBase):
    pass

class PagadorRead(PagadorBase):
    id: int
    criado_em: Optional[datetime] = None
    class Config:
        orm_mode = True

# ...existing code...
