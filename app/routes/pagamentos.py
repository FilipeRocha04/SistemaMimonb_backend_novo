from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.pagamento import Pagamento as PagamentoModel
from app.schemas.pagamento import PagamentoCreate, PagamentoRead

router = APIRouter(prefix="/pagamentos", tags=["Pagamentos"])


# Use shared get_db from app.db.session


@router.post("", response_model=PagamentoRead)
@router.post("/", response_model=PagamentoRead)
def create_pagamento(payload: PagamentoCreate, db: Session = Depends(get_db)):
    try:
        # Normalize forma_pagamento to accepted values
        def normalize_forma_pagamento(val: Optional[str]) -> Optional[str]:
            if not val:
                return None
            s = val.strip().lower()
            # Map to DB enum-friendly values (lowercase, no acentos)
            if s in {"pix"}:
                return "pix"
            if s in {"cash", "dinheiro"}:
                return "dinheiro"
            if s in {"card", "cartao", "cartão", "credito", "crédito", "debito", "débito"}:
                return "cartao"
            # Keep original value if it's something else
            return val

        forma = normalize_forma_pagamento(payload.forma_pagamento)
        p = PagamentoModel(
            pedido=payload.pedido,
            forma_pagamento=forma,
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


@router.get("", response_model=List[PagamentoRead])
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
