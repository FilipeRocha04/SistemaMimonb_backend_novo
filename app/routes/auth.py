from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timedelta

from app.schemas.user import UserCreate, UserRead, Token, UserUpdate, LoginRequest, ForgotPasswordRequest
from app.services import auth as auth_service
from app.db.session import SessionLocal
from app.models.user import User as UserModel
from app.db import session as db_session

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/register", response_model=UserRead)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    # check existing
    if db.query(UserModel).filter(UserModel.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email já registrado")

    # validate username if provided: must be lowercase only
    username = getattr(user_in, 'username', None)
    if username:
        if any(c.isupper() for c in username):
            raise HTTPException(status_code=400, detail="Nome de usuário não pode conter letras maiúsculas")
        # ensure unique username
        if db.query(UserModel).filter(UserModel.username == username).first():
            raise HTTPException(status_code=400, detail="Nome de usuário já em uso")

    hashed = auth_service.get_password_hash(user_in.password)
    # map to MySQL schema columns: username, senha_hash and papel
    user = UserModel(email=user_in.email, username=getattr(user_in, 'username', None), senha_hash=hashed, papel=user_in.papel)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(form_data: LoginRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    # accepts identifier (email OR username) + password
    user = auth_service.authenticate_user(db, form_data.identifier, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Email ou senha incorretos")
    # create access token (short lived)
    access_token_expires = timedelta(minutes=auth_service.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    # create refresh token (longer lived) and store session
    refresh_token, jti, refresh_expires = auth_service.create_refresh_token(data={"sub": user.email})
    # persist session record
    try:
        from app.models.session import Session as SessionModel
        ses = SessionModel(jti=jti, user_email=user.email, expires_at=refresh_expires)
        db.add(ses)
        db.commit()
    except Exception:
        # non-fatal: continue even if session table not present
        db.rollback()
    # set refresh token as httpOnly cookie (frontend need not store it)
    # secure should be True in production (HTTPS). Using secure=False for local dev.
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


@router.get("/me", response_model=UserRead)
def read_users_me(current_user=Depends(auth_service.get_current_user)):
    return current_user


@router.post("/refresh", response_model=Token)
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    # read refresh token from cookie
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Token de refresh ausente")
    try:
        payload = auth_service.jwt.decode(token, auth_service.settings.SECRET_KEY, algorithms=[auth_service.settings.ALGORITHM])
        email = payload.get("sub")
        jti = payload.get("jti")
        if email is None or jti is None:
            raise HTTPException(status_code=401, detail="Token de refresh inválido")
    except Exception:
        raise HTTPException(status_code=401, detail="Token de refresh inválido")
    # check session exists and not revoked/expired
    try:
        from app.models.session import Session as SessionModel
        ses = db.query(SessionModel).filter(SessionModel.jti == jti).first()
        if not ses or ses.revoked or (ses.expires_at and ses.expires_at < __import__('datetime').datetime.utcnow()):
            raise HTTPException(status_code=401, detail="Token de refresh revogado ou expirado")
    except HTTPException:
        raise
    except Exception:
        # if sessions table missing, allow token
        ses = None

    # issue new access token
    access_token_expires = timedelta(minutes=auth_service.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(data={"sub": email}, expires_delta=access_token_expires)

    # Rotate refresh token: create new refresh token + session, revoke old session if present
    try:
        new_refresh_token, new_jti, new_expires = auth_service.create_refresh_token(data={"sub": email})
        from app.models.session import Session as SessionModel
        # create new session row
        new_ses = SessionModel(jti=new_jti, user_email=email, expires_at=new_expires)
        db.add(new_ses)
        # revoke old session
        if ses:
            ses.revoked = True
            db.add(ses)
        db.commit()
        # set new refresh cookie
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=auth_service.settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
            path="/",
        )
    except Exception:
        db.rollback()

    return {"access_token": access_token, "token_type": "bearer"}



@router.post('/forgot-password')
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Trigger a password reset flow.

    Security note: do NOT reveal whether the email exists. Return a generic message.
    In a production system you would generate a short-lived reset token and send an email.
    """
    try:
        # look up user but don't reveal existence
        user = db.query(UserModel).filter(UserModel.email == payload.email).first()
        if user:
            # TODO: generate reset token and send email. For now we just record a log entry.
            try:
                import logging
                logging.getLogger('auth').info(f'Password reset requested for {payload.email}')
            except Exception:
                pass
    except Exception:
        # swallow errors to avoid leaking details
        pass

    return {"ok": True, "message": "Se o e-mail estiver cadastrado, enviamos um link de recuperação."}


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), current_user=Depends(auth_service.get_current_user)):
    try:
        from app.models.session import Session as SessionModel
        rows = db.query(SessionModel).filter(SessionModel.user_email == current_user.email).order_by(SessionModel.created_at.desc()).all()
        return [{"jti": r.jti, "created_at": r.created_at, "expires_at": r.expires_at, "revoked": r.revoked} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{jti}/revoke")
def revoke_session(jti: str, db: Session = Depends(get_db), current_user=Depends(auth_service.get_current_user)):
    try:
        from app.models.session import Session as SessionModel
        ses = db.query(SessionModel).filter(SessionModel.jti == jti, SessionModel.user_email == current_user.email).first()
        if not ses:
            raise HTTPException(status_code=404, detail="Sessão não encontrada")
        ses.revoked = True
        db.add(ses)
        db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user=Depends(auth_service.get_current_user)):
    """Delete a user. Only admins or the user themself can delete.
    This will also remove any session rows for the user's email.
    """
    target = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # normalize current_user role value
    cur_role = getattr(getattr(current_user, 'papel', None), 'value', getattr(current_user, 'papel', None))
    if current_user.email != target.email and cur_role != 'admin':
        raise HTTPException(status_code=403, detail="Privilégios insuficientes")

    try:
        # remove sessions for this user (if sessions table exists)
        try:
            from app.models.session import Session as SessionModel
            db.query(SessionModel).filter(SessionModel.user_email == target.email).delete()
        except Exception:
            # ignore if sessions table missing
            pass

        # delete the user
        db.delete(target)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True}


# Dev/debug route: list users directly from the database
# Use Postman or browser to call: GET /auth/dev/users
@router.get("/dev/users")
def list_users_debug(db: Session = Depends(get_db)):
    try:
        result = db.execute(text("SELECT id, email, username, papel, criado_em FROM users ORDER BY id DESC LIMIT 100"))
        rows = [dict(r) for r in result.mappings().all()]
        return {"count": len(rows), "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dev/db")
def db_info():
    # return which DB URL the app is using and engine info for debugging
    try:
        engine_url = str(db_session.engine.url)
    except Exception:
        engine_url = None
    return {"settings_database_url": getattr(auth_service, 'settings', {}).DATABASE_URL if hasattr(auth_service, 'settings') else None,
            "engine_url": engine_url}



@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: int, user_in: UserUpdate, db: Session = Depends(get_db), current_user=Depends(auth_service.get_current_user)):
    # Only admins or the user themselves can update
    target = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # normalize current_user role value
    cur_role = getattr(getattr(current_user, 'papel', None), 'value', getattr(current_user, 'papel', None))
    if current_user.email != target.email and cur_role != 'admin':
        raise HTTPException(status_code=403, detail="Privilégios insuficientes")

    # update fields
    updated = False
    if user_in.email:
        # ensure unique
        existing = db.query(UserModel).filter(UserModel.email == user_in.email, UserModel.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email já em uso")
        target.email = user_in.email
        updated = True
    if user_in.papel:
        target.papel = user_in.papel
        updated = True
    if getattr(user_in, 'username', None):
        # username must not contain uppercase letters
        if any(c.isupper() for c in user_in.username):
            raise HTTPException(status_code=400, detail="Nome de usuário não pode conter letras maiúsculas")
        # ensure unique username
        existing_u = db.query(UserModel).filter(UserModel.username == user_in.username, UserModel.id != user_id).first()
        if existing_u:
            raise HTTPException(status_code=400, detail="Nome de usuário já em uso")
        target.username = user_in.username
        updated = True
    if user_in.password:
        target.senha_hash = auth_service.get_password_hash(user_in.password)
        updated = True

    if updated:
        db.add(target)
        db.commit()
        db.refresh(target)

    return target
