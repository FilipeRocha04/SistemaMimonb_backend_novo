from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from app.db.session import get_db
from app.models.pedido import Pedido as PedidoModel
from app.core.timezone_utils import BRAZIL_TZ

router = APIRouter()

@router.get("/orders/last_updated")
def orders_last_updated(db: Session = Depends(get_db)):
    # Retorna o maior valor de data_pedido ou atualizado_em
    last = db.query(func.max(PedidoModel.atualizado_em)).scalar()
    # Se não houver campo atualizado_em, pode usar data_pedido ou criado_em
    if not last:
        last = db.query(func.max(PedidoModel.data_pedido)).scalar()
    if not last:
        last = db.query(func.max(PedidoModel.criado_em)).scalar()
    # Formatar como string ISO
    if isinstance(last, datetime):
        last = last.astimezone(BRAZIL_TZ).isoformat()
    elif last:
        last = str(last)
    return {"last_updated": last or "1970-01-01T00:00:00Z"}
