from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.schemas import pagamento
from app.models import pagamento as pagamento_model

router = APIRouter(
    prefix="/pagamentos-itens",
    tags=["pagamentos-itens"]
)

# Modelo de leitura para pagamentos_itens_pagador
from pydantic import BaseModel
from typing import Optional

class PagamentoItemPagadorRead(BaseModel):
    id: int
    pedido: int
    pedido_item_id: int
    pagador: int
    produto_preco_id: int
    valor: float
    taxa_10: float
    
    model_config = {"from_attributes": True}

# Endpoint para listar os 100 primeiros registros
@router.get("/", response_model=List[PagamentoItemPagadorRead])
def list_pagamentos_itens(db: Session = Depends(get_db)):
    result = db.execute("SELECT * FROM pagamentos_itens_pagador LIMIT 100")
    rows = result.fetchall()
    # Converte para dicts
    return [PagamentoItemPagadorRead(**dict(row)) for row in rows]
