from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.pagamento import Pagamento as PagamentoModel
from app.schemas.pagamento import PagamentoCreate, PagamentoRead

router = APIRouter(prefix="/pagamentos", tags=["Pagamentos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=PagamentoRead)
def create_pagamento(payload: PagamentoCreate, db: Session = Depends(get_db)):
    try:
        p = PagamentoModel(
            pedido=payload.pedido,
            forma_pagamento=payload.forma_pagamento,
            status=payload.status,
            valor=payload.valor,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return p
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[PagamentoRead])
def list_pagamentos(pedido: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        q = db.query(PagamentoModel)
        if pedido is not None:
            q = q.filter(PagamentoModel.pedido == pedido)
        rows = q.order_by(PagamentoModel.id.desc()).limit(1000).all()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
