from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class PagadorItensFormaPagamentoCreate(BaseModel):
    pagador_id: int
    forma_pagamento: str
    valor: float

class PagadorItensFormaPagamentoResponse(BaseModel):
    id: int
    pagador_id: int
    forma_pagamento: str
    valor: float
    criado_em: datetime

    class Config:
        from_attributes = True
