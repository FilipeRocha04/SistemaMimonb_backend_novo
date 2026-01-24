from datetime import datetime, timedelta
import uuid
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.models.user import User
from app.db.session import get_db


# ======================================================
# CONFIGURAÇÕES DE SEGURANÇA
# ======================================================

# Preferir pbkdf2_sha256 e manter bcrypt apenas para compatibilidade
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ======================================================
# FUNÇÕES DE SENHA
# ======================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    try:
        return pwd_context.hash(password)
    except ValueError as exc:
        raise ValueError(
            "A senha é muito longa para ser processada com segurança"
        ) from exc


# ======================================================
# TOKENS JWT
# ======================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "access"
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "jti": jti,
        "type": "refresh"
    })
    encoded = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded, jti, expire


def create_reset_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(hours=1)
    )
    to_encode.update({
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "reset"
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        return None


# ======================================================
# AUTENTICAÇÃO
# ======================================================

def authenticate_user(db: Session, identifier: str, password: str):
    """
    Autentica usuário por email ou username.
    """
    try:
        user = (
            db.query(User)
            .filter(or_(User.email == identifier, User.username == identifier))
            .first()
        )
    except Exception:
        user = db.query(User).filter(User.email == identifier).first()

    if not user:
        return False

    if not verify_password(password, getattr(user, "senha_hash", None)):
        return False

    return user


# ======================================================
# DEPENDÊNCIAS DE AUTORIZAÇÃO
# ======================================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        email: str = payload.get("sub")
        if not email:
            raise credentials_exception

        jti = payload.get("jti")
        token_type = payload.get("type")

    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise credentials_exception

    # Validação opcional de sessão (se existir)
    try:
        if jti and token_type == "access":
            from app.models.session import Session as SessionModel

            session_db = (
                db.query(SessionModel)
                .filter(SessionModel.jti == jti)
                .first()
            )

            if session_db:
                if session_db.revoked:
                    raise credentials_exception
                if session_db.expires_at and session_db.expires_at < datetime.utcnow():
                    raise credentials_exception
    except Exception:
        # fallback silencioso para compatibilidade
        pass

    return user


def require_roles(*roles: str):
    """
    Dependência para restringir acesso por papel (role).

    Exemplo:
        @router.get("/orders")
        def list_orders(user=Depends(require_roles("admin", "gerente"))):
            ...
    """
    def role_checker(current_user=Depends(get_current_user)):
        user_role = getattr(current_user, "papel", None)

        try:
            role_value = (
                user_role.value
                if hasattr(user_role, "value")
                else str(user_role)
            )
        except Exception:
            role_value = str(user_role)

        if role_value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissões insuficientes para acessar este recurso",
            )

        return current_user

    return role_checker
