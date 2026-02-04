from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.pagador import Pagador as PagadorModel
from app.schemas.pagador import PagadorCreate, PagadorRead

router = APIRouter(prefix="/pagadores", tags=["Pagadores"])

@router.post("", response_model=PagadorRead)
@router.post("/", response_model=PagadorRead)
def create_pagador(payload: PagadorCreate, db: Session = Depends(get_db)):
    try:
        pagador = PagadorModel(nome=payload.nome)
        db.add(pagador)
        db.commit()
        db.refresh(pagador)
        return pagador
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=List[PagadorRead])
@router.get("/", response_model=List[PagadorRead])
def list_pagadores(db: Session = Depends(get_db)):
    try:
        rows = db.query(PagadorModel).order_by(PagadorModel.id.desc()).limit(1000).all()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ...existing code...
