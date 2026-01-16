from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class DespesaBase(BaseModel):
    # accept date values; pydantic will parse strings like '2025-12-01' into date
    data: date
    descricao: Optional[str] = None
    categoria: Optional[str] = None
    pagamento: Optional[str] = None
    valor: float
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None


class DespesaCreate(DespesaBase):
    pass


class DespesaRead(DespesaBase):
    id: int

    class Config:
        orm_mode = True
