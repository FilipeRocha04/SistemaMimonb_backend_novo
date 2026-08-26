from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User as UserModel
from app.schemas.user import UserRead
from app.services.auth import get_current_user

# NOTA: este router não está registrado em app.main atualmente (código
# morto/órfão) — o frontend usa /auth/users, não /users. Protegido mesmo
# assim por padrão (deny-by-default), caso venha a ser registrado no futuro.
router = APIRouter(prefix="/usuarios", tags=["Users"], dependencies=[Depends(get_current_user)])


# Use shared get_db from app.db.session


@router.get("", response_model=List[UserRead])
@router.get("/", response_model=List[UserRead])
def list_users(db: Session = Depends(get_db)):
    try:
        rows = db.query(UserModel).order_by(UserModel.id.desc()).limit(200).all()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user
