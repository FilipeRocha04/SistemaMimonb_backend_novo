from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.pagamento import Pagamento as PagamentoModel
from app.models.pagador import PagamentoPagadorForma as PagamentoPagadorFormaModel
from app.schemas.pagamento import PagamentoCreate, PagamentoRead, PagamentoPagadorFormaCreate, PagamentoPagadorFormaRead, PagamentoUpdate

router = APIRouter(prefix="/pagamentos", tags=["Pagamentos"])


# Use shared get_db from app.db.session


@router.post("", response_model=PagamentoRead)
@router.post("/", response_model=PagamentoRead)
def create_pagamento(payload: PagamentoCreate, db: Session = Depends(get_db)):
    try:
        # Ajusta forma_pagamento para o valor aceito pelo banco
        forma = payload.forma_pagamento
        if forma == 'card':
            forma = 'cartao'
        p = PagamentoModel(
            pedido=payload.pedido,
            status=payload.status,
            valor=payload.valor,
            forma_pagamento=forma,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return p
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[PagamentoRead])
@router.get("/", response_model=List[PagamentoRead])
def list_pagamentos(pedido: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        q = db.query(PagamentoModel)
        if pedido is not None:
            q = q.filter(PagamentoModel.pedido == pedido)
        rows = q.order_by(PagamentoModel.id.desc()).limit(1000).all()
        # Adiciona detalhes de pagadores/formas
        for pagamento in rows:
            detalhes = db.query(PagamentoPagadorFormaModel).filter(PagamentoPagadorFormaModel.pagamento_id == pagamento.id).all()
            pagamento.detalhes_pagamento = detalhes
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para criar detalhes de pagamento (pagador + forma)
@router.post("/detalhe", response_model=PagamentoPagadorFormaRead)
def create_pagamento_detalhe(payload: PagamentoPagadorFormaCreate, db: Session = Depends(get_db)):
    try:
        detalhe = PagamentoPagadorFormaModel(
            pagamento_id=payload.pagamento_id,
            pagador_id=payload.pagador_id,
            forma_pagamento=payload.forma_pagamento,
            valor=payload.valor,
        )
        db.add(detalhe)
        db.commit()
        db.refresh(detalhe)
        return detalhe
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{pagamento_id}", response_model=PagamentoRead)
def update_pagamento(pagamento_id: int = Path(...), payload: PagamentoUpdate = None, db: Session = Depends(get_db)):
    pagamento = db.query(PagamentoModel).filter(PagamentoModel.id == pagamento_id).first()
    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    data = payload.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(pagamento, key, value)
    db.commit()
    db.refresh(pagamento)
    return pagamento
