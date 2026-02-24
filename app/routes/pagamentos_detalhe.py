from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.pagador import PagamentoPagadorForma as PagamentoPagadorFormaModel
from app.schemas.pagamento import PagamentoPagadorFormaRead, PagamentoPagadorFormaCreate, PagamentoPagadorFormaUpdate

from typing import List

router = APIRouter(prefix="/pagamentos/detalhe", tags=["PagamentosDetalhe"])

@router.patch("/{detalhe_id}", response_model=PagamentoPagadorFormaRead)
def update_pagamento_detalhe(detalhe_id: int = Path(...), payload: PagamentoPagadorFormaUpdate = None, db: Session = Depends(get_db)):
    detalhe = db.query(PagamentoPagadorFormaModel).filter(PagamentoPagadorFormaModel.id == detalhe_id).first()
    if not detalhe:
        raise HTTPException(status_code=404, detail="Detalhe de pagamento não encontrado")
    data = payload.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(detalhe, key, value)
    db.commit()
    db.refresh(detalhe)
    return detalhe

@router.delete("/{detalhe_id}", response_model=dict)
def delete_pagamento_detalhe(detalhe_id: int = Path(...), db: Session = Depends(get_db)):
    detalhe = db.query(PagamentoPagadorFormaModel).filter(PagamentoPagadorFormaModel.id == detalhe_id).first()
    if not detalhe:
        raise HTTPException(status_code=404, detail="Detalhe de pagamento não encontrado")
    db.delete(detalhe)
    db.commit()
    return {"ok": True}
