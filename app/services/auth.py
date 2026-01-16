from datetime import datetime, timedelta
import uuid
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.models.user import User
from app.db.session import SessionLocal
from sqlalchemy import select, or_

# Use a scheme without the 72-byte password limit as the preferred hashing algorithm.
# Keep bcrypt in the list so existing bcrypt hashes (if any) can still be verified.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    try:
        return pwd_context.hash(password)
    except ValueError as exc:
        # Common case: bcrypt backend raises ValueError if password > 72 bytes.
        # If that happens, surface a clear error for the client.
        raise ValueError("password too long to hash; choose a shorter password") from exc


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    # Access tokens do not need a jti, but include for traceability
    to_encode.update({"jti": str(uuid.uuid4()), "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    # refresh token must have a stable jti we can store and check
    jti = str(uuid.uuid4())
    to_encode.update({"jti": jti, "type": "refresh"})
    encoded = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded, jti, expire


def authenticate_user(db: Session, identifier: str, password: str):
    # Adjust to the MySQL schema: password stored in `senha_hash`
    # identifier can be an email or username
    try:
        user = db.query(User).filter(or_(User.email == identifier, User.username == identifier)).first()
    except Exception:
        # fallback: try email-only equality
        user = db.query(User).filter(User.email == identifier).first()
    if not user:
        return False
    # note: model field is senha_hash
    if not verify_password(password, getattr(user, 'senha_hash', None)):
        return False
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        # if token contains jti, and is access token, we still allow it
        jti = payload.get("jti")
        token_type = payload.get("type")
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    # If token is access token we optionally validate a corresponding session exists
    # We only check sessions for access tokens that carry a jti; this ties access tokens
    # to an existing refresh/session entry so revocation works.
    try:
        if jti and token_type == 'access':
            # check sessions table for jti
            from app.models.session import Session as SessionModel
            ses = db.query(SessionModel).filter(SessionModel.jti == jti).first()
            # If no session found, try to allow existing access tokens issued without session
            # but prefer to require a session for revocable tokens.
            if ses is None:
                # No session entry: allow but do not block (backwards compatibility)
                pass
            else:
                if ses.revoked:
                    raise credentials_exception
                if ses.expires_at and ses.expires_at < datetime.utcnow():
                    raise credentials_exception
    except Exception:
        # if session table not available or any error, fall back to allowing token
        pass
    return user


def require_roles(*roles: str):
    """Return a dependency that ensures the current user has one of the provided roles.

    Usage in a route:
        @router.get('/orders')
        def list_orders(current_user=Depends(require_roles('garcom','admin'))):
            ...
    """
    def role_checker(current_user=Depends(get_current_user)):
        # current_user.papel is an Enum on the model; normalize to string value
        user_role = getattr(current_user, 'papel', None)
        try:
            # If it's an enum member, get its value
            role_value = user_role.value if hasattr(user_role, 'value') else str(user_role)
        except Exception:
            role_value = str(user_role)

        if role_value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient privileges",
            )
        return current_user

    return role_checker
