# =========================
# IMPORTS
# =========================
from fastapi import Body
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timedelta
from pydantic import BaseModel

from app.schemas.user import (
    UserCreate,
    UserRead,
    Token,
    UserUpdate,
    LoginRequest,
    ForgotPasswordRequest
)
from app.services import auth as auth_service
from app.db.session import get_db
from app.models.user import User as UserModel


# =========================
# ROUTER
# =========================
router = APIRouter(prefix="/auth", tags=["Auth"])


# =========================
# SCHEMAS AUXILIARES
# =========================
class ResetPasswordRequest(BaseModel):
    token: str
    password: str


# =========================
# ENDPOINTS
# =========================

# Endpoint protegido para listar usuários
@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user)
):
    # Apenas admin pode ver todos os usuários
    cur_role = getattr(
        getattr(current_user, 'papel', None),
        'value',
        getattr(current_user, 'papel', None)
    )
    if cur_role != 'admin':
        raise HTTPException(status_code=403, detail="Privilégios insuficientes")

    try:
        result = db.execute(
            text("SELECT email, username, papel FROM users ORDER BY id DESC LIMIT 100")
        )
        rows = [dict(r) for r in result.mappings().all()]
        return {"count": len(rows), "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# VERIFY EMAIL
# =========================
@router.post("/verify", response_model=Token)
def verify_email(token: str = Body(..., embed=True), db: Session = Depends(get_db)):
    from app.services import auth as auth_service_module
    from app.models.user import User as UserModel
    import logging

    try:
        data = auth_service_module.decode_token(token)
        if not data or data.get("action") != "verify":
            raise HTTPException(status_code=400, detail="Token inválido ou expirado")

        email = data.get("sub")
        if not email:
            raise HTTPException(status_code=400, detail="Token inválido")

        user = db.query(UserModel).filter(UserModel.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        if hasattr(user, 'email_verificado'):
            user.email_verificado = True

        db.commit()

        access_token_expires = timedelta(
            minutes=auth_service.settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        access_token = auth_service.create_access_token(
            data={"sub": user.email},
            expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}

    except Exception as e:
        logging.getLogger('auth').warning(f'Falha ao verificar email: {e}')
        raise HTTPException(status_code=400, detail="Falha ao verificar email")


# =========================
# RESET PASSWORD
# =========================
@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    from app.services import auth as auth_service_module
    from app.models.user import User as UserModel
    import logging

    try:
        data = auth_service_module.decode_token(payload.token)
        if not data or data.get("action") != "reset":
            raise Exception("Token inválido ou expirado")

        email = data.get("sub")
        if not email:
            raise Exception("Token inválido")

        user = db.query(UserModel).filter(UserModel.email == email).first()
        if not user:
            raise Exception("Usuário não encontrado")

        user.senha_hash = auth_service_module.get_password_hash(payload.password)
        db.commit()

        return {"ok": True, "message": "Senha redefinida com sucesso!"}

    except Exception as e:
        logging.getLogger('auth').warning(f'Falha ao redefinir senha: {e}')
        return {"ok": False, "message": str(e)}


# =========================
# REGISTER
# =========================
@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserModel).filter(UserModel.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email já registrado")

    username = getattr(user_in, 'username', None)
    if username:
        if any(c.isupper() for c in username):
            raise HTTPException(
                status_code=400,
                detail="Nome de usuário não pode conter letras maiúsculas"
            )
        if db.query(UserModel).filter(UserModel.username == username).first():
            raise HTTPException(status_code=400, detail="Nome de usuário já em uso")

    hashed = auth_service.get_password_hash(user_in.password)

    user = UserModel(
        email=user_in.email,
        username=getattr(user_in, 'username', None),
        senha_hash=hashed,
        papel='garcom'
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    from app.utils.email import send_verification_email_sync as send_verification_email
    from app.services import auth as auth_service_module

    verification_token = auth_service_module.create_access_token(
        {"sub": user.email, "action": "verify"},
        expires_delta=timedelta(hours=24)
    )
    try:
        send_verification_email(user.email, verification_token)
    except Exception as e:
        import logging
        logging.getLogger('auth').warning(
            f'Falha ao enviar email de verificação: {e}'
        )

    return user


# =========================
# LOGIN
# =========================
@router.post("/login", response_model=Token)
def login(
    form_data: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db)
):
    user = auth_service.authenticate_user(
        db,
        form_data.identifier,
        form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Email ou senha incorretos")

    access_token_expires = timedelta(
        minutes=auth_service.settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = auth_service.create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )

    refresh_token, jti, refresh_expires = auth_service.create_refresh_token(
        data={"sub": user.email}
    )

    try:
        from app.models.session import Session as SessionModel
        ses = SessionModel(
            jti=jti,
            user_email=user.email,
            expires_at=refresh_expires
        )
        db.add(ses)
        db.commit()
    except Exception:
        db.rollback()

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=auth_service.settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )

    return {"access_token": access_token, "token_type": "bearer"}
