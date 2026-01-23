from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth, OAuthError
from jose import jwt
from sqlalchemy.orm import Session
import os

from app.db.session import SessionLocal
from app.models.user import User as UserModel, RoleEnum
from app.services.auth import create_access_token

router = APIRouter(prefix="/auth/google", tags=["OAuth"])

# =========================
# ENV
# =========================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    },
)

# =========================
# ROUTES
# =========================
@router.get("/login")
async def login_via_google(request: Request):
    redirect_uri = request.url_for("auth_google_callback")
    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
        prompt="select_account"
    )


@router.get("/callback", name="auth_google_callback")
async def auth_google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)

        if "id_token" not in token:
            raise HTTPException(
                status_code=400,
                detail="id_token não retornado pelo Google"
            )

        user_info = jwt.get_unverified_claims(token["id_token"])

    except OAuthError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Erro no login Google: {error.error}"
        )

    email = user_info.get("email")
    username = email.split("@")[0]

    db: Session = SessionLocal()

    user = db.query(UserModel).filter(UserModel.email == email).first()

    if not user:
        user = UserModel(
            email=email,
            username=username,
            senha_hash="google_oauth",
            papel=RoleEnum.garcom
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    papel = user.papel.value if hasattr(user.papel, "value") else user.papel

    access_token = create_access_token({
        "sub": user.email,
        "papel": papel,
        "username": user.username,
    })

    # ✅ redireciona para o frontend correto
    redirect_url = f"{FRONTEND_URL}/dashboard?access_token={access_token}"

    return RedirectResponse(url=redirect_url)
