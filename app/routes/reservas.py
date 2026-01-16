from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from sqlalchemy.orm import Session
import traceback

from app.db.session import SessionLocal
from app.models.reserva import Reserva as ReservaModel
from app.models.client import Cliente as ClienteModel
from app.schemas.reserva import ReservaCreate, ReservaRead

router = APIRouter(prefix="/reservas", tags=["Reservas"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=ReservaRead)
def create_reserva(payload: ReservaCreate, db: Session = Depends(get_db)):
    try:
        r = ReservaModel(
            mesa_id=payload.mesa_id,
            cliente_id=payload.cliente_id,
            data_reserva=payload.data_reserva,
            hora_reserva=payload.hora_reserva,
            quantidade_pessoas=payload.quantidade_pessoas,
            status=payload.status,
            observacao=payload.observacao,
        )
        if getattr(payload, 'criado_em', None):
            r.criado_em = payload.criado_em
        db.add(r)
        db.commit()
        db.refresh(r)
        return r
    except Exception as e:
        db.rollback()
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=tb)


@router.get("/", response_model=List[ReservaRead])
def list_reservas(
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=1000),
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        q = db.query(ReservaModel)
        if start:
            q = q.filter(ReservaModel.data_reserva >= start)
        if end:
            q = q.filter(ReservaModel.data_reserva <= end)
        if status:
            q = q.filter(ReservaModel.status == status)

        q = q.order_by(ReservaModel.data_reserva.desc(), ReservaModel.hora_reserva.asc())
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()

        # attach cliente_name when possible to help the frontend
        client_ids = list({r.cliente_id for r in rows if r.cliente_id})
        clients_map = {}
        if client_ids:
            clients = db.query(ClienteModel).filter(ClienteModel.id.in_(client_ids)).all()
            clients_map = {c.id: c.nome for c in clients}

        out = []
        for r in rows:
            item = {
                'id': r.id,
                'mesa_id': r.mesa_id,
                'cliente_id': r.cliente_id,
                'data_reserva': r.data_reserva,
                'hora_reserva': r.hora_reserva,
                'quantidade_pessoas': r.quantidade_pessoas,
                'status': r.status.value if hasattr(r.status, 'value') else r.status,
                'observacao': r.observacao,
                'criado_em': r.criado_em,
                'atualizado_em': r.atualizado_em,
                'cliente_name': clients_map.get(r.cliente_id) if r.cliente_id else None,
            }
            out.append(item)

        return out
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=tb)


@router.get("/{reserva_id}", response_model=ReservaRead)
def get_reserva(reserva_id: int, db: Session = Depends(get_db)):
    r = db.query(ReservaModel).filter(ReservaModel.id == reserva_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reserva não encontrada")
        try:
            return r
        except Exception as e:
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=tb)


@router.put("/{reserva_id}", response_model=ReservaRead)
def update_reserva(reserva_id: int, payload: ReservaCreate, db: Session = Depends(get_db)):
    r = db.query(ReservaModel).filter(ReservaModel.id == reserva_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reserva não encontrada")
    try:
        r.mesa_id = payload.mesa_id
        r.cliente_id = payload.cliente_id
        r.data_reserva = payload.data_reserva
        r.hora_reserva = payload.hora_reserva
        r.quantidade_pessoas = payload.quantidade_pessoas
        r.status = payload.status
        r.observacao = payload.observacao
        db.add(r)
        db.commit()
        db.refresh(r)
        return r
    except Exception as e:
        db.rollback()
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=tb)


@router.delete("/{reserva_id}")
def delete_reserva(reserva_id: int, db: Session = Depends(get_db)):
    r = db.query(ReservaModel).filter(ReservaModel.id == reserva_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reserva não encontrada")
    try:
        db.delete(r)
        db.commit()
        return {"detail": "Reserva removida com sucesso"}
    except Exception as e:
        db.rollback()
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=tb)
