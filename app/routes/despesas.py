from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.despesa import Despesa as DespesaModel
from app.schemas.despesa import DespesaCreate, DespesaRead

router = APIRouter(prefix="/despesas", tags=["Despesas"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=DespesaRead)
def create_despesa(payload: DespesaCreate, db: Session = Depends(get_db)):
    try:
        d = DespesaModel(
            data=payload.data,
            descricao=payload.descricao,
            categoria=payload.categoria,
            pagamento=payload.pagamento,
            valor=payload.valor,
        )
        # if client provided created/updated timestamps use them
        if getattr(payload, 'criado_em', None):
            d.criado_em = payload.criado_em
        if getattr(payload, 'atualizado_em', None):
            d.atualizado_em = payload.atualizado_em
        db.add(d)
        db.commit()
        db.refresh(d)
        return d
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[DespesaRead])
def list_despesas(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    categoria: Optional[str] = None,
    pagamento: Optional[str] = None,
    sortKey: Optional[str] = "data",
    sortDir: Optional[str] = "desc",
    db: Session = Depends(get_db),
):
    try:
        q = db.query(DespesaModel)
        if startDate:
            q = q.filter(DespesaModel.data >= startDate)
        if endDate:
            q = q.filter(DespesaModel.data <= endDate)
        if categoria:
            q = q.filter(DespesaModel.categoria == categoria)
        if pagamento:
            q = q.filter(DespesaModel.pagamento == pagamento)

        # simple ordering
        if sortKey == "value" or sortKey == "valor":
            if sortDir == "asc":
                q = q.order_by(DespesaModel.valor.asc())
            else:
                q = q.order_by(DespesaModel.valor.desc())
        else:
            if sortDir == "asc":
                q = q.order_by(DespesaModel.data.asc())
            else:
                q = q.order_by(DespesaModel.data.desc())

        # pagination
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{despesa_id}", response_model=DespesaRead)
def get_despesa(despesa_id: int, db: Session = Depends(get_db)):
    d = db.query(DespesaModel).filter(DespesaModel.id == despesa_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    return d


@router.put("/{despesa_id}", response_model=DespesaRead)
def update_despesa(despesa_id: int, payload: DespesaCreate, db: Session = Depends(get_db)):
    d = db.query(DespesaModel).filter(DespesaModel.id == despesa_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    try:
        d.data = payload.data
        d.descricao = payload.descricao
        d.categoria = payload.categoria
        d.pagamento = payload.pagamento
        d.valor = payload.valor
        if getattr(payload, 'atualizado_em', None):
            d.atualizado_em = payload.atualizado_em
        db.add(d)
        db.commit()
        db.refresh(d)
        return d
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{despesa_id}")
def delete_despesa(despesa_id: int, db: Session = Depends(get_db)):
    d = db.query(DespesaModel).filter(DespesaModel.id == despesa_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    try:
        db.delete(d)
        db.commit()
        return {"detail": "Despesa removida com sucesso"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
