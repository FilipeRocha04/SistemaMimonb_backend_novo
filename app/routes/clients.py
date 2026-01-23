from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.client import Cliente as ClienteModel
from app.schemas.client import ClienteCreate, ClienteRead

router = APIRouter(prefix="/clients", tags=["Clients"])


# Use shared get_db from app.db.session


@router.post("", response_model=ClienteRead)
@router.post("/", response_model=ClienteRead)
def create_client(payload: ClienteCreate, db: Session = Depends(get_db)):
    try:
        client = ClienteModel(
            nome=payload.nome,
            telefone=payload.telefone,
            endereco=payload.endereco,
            observacoes=payload.observacoes,
            ativo=(payload.ativo if payload.ativo is not None else True),
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        return client
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[ClienteRead])
@router.get("/", response_model=List[ClienteRead])
def list_clients(db: Session = Depends(get_db)):
    try:
        rows = db.query(ClienteModel).order_by(ClienteModel.id.desc()).limit(200).all()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{client_id}", response_model=ClienteRead)
def get_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(ClienteModel).filter(ClienteModel.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.put("/{client_id}", response_model=ClienteRead)
def update_client(client_id: int, payload: ClienteCreate, db: Session = Depends(get_db)):
    client = db.query(ClienteModel).filter(ClienteModel.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    try:
        client.nome = payload.nome
        client.telefone = payload.telefone
        client.endereco = payload.endereco
        client.observacoes = payload.observacoes
        # allow toggling 'ativo' just like product activation
        if hasattr(payload, 'ativo'):
            client.ativo = bool(payload.ativo)
        db.add(client)
        db.commit()
        db.refresh(client)
        return client
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(ClienteModel).filter(ClienteModel.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    try:
        db.delete(client)
        db.commit()
        return {"detail": "Cliente removido com sucesso"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
