from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime



class PagamentoBase(BaseModel):
    pedido: Optional[int]
    status: Optional[str] = 'pendente'
    valor: float = 0.0
    forma_pagamento: str = 'dinheiro'

class PagamentoPagadorFormaBase(BaseModel):
    pagamento_id: int
    pagador_id: int
    forma_pagamento: str
    valor: float

class PagamentoPagadorFormaCreate(PagamentoPagadorFormaBase):
    pass

class PagamentoPagadorFormaRead(PagamentoPagadorFormaBase):
    id: int
    criado_em: Optional[datetime] = None

    class Config:
        orm_mode = True



class PagamentoCreate(PagamentoBase):
    pass



class PagamentoRead(PagamentoBase):
    id: int
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None
    detalhes_pagamento: Optional[List[PagamentoPagadorFormaRead]] = None

    class Config:
        orm_mode = True


class PagamentoUpdate(BaseModel):
    status: Optional[str] = None
    valor: Optional[float] = None
    forma_pagamento: Optional[str] = None
    # Adicione outros campos se necessário

    model_config = dict(from_attributes=True)
