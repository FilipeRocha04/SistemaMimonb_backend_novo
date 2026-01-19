from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User as UserModel
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["Users"])


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
