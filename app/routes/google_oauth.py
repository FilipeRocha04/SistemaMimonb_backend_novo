

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.config import Config
from starlette.requests import Request as StarletteRequest
import os
from jose import jwt
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User as UserModel, RoleEnum
from app.services.auth import create_access_token

router = APIRouter(prefix="/auth/google", tags=["OAuth"])

# Carregar variáveis do .env
config = Config('.env')

oauth = OAuth(config)
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@router.get('/login')
async def login_via_google(request: Request):
    redirect_uri = request.url_for('auth_google_callback')
    # Força o Google a mostrar seleção de conta
    return await oauth.google.authorize_redirect(request, redirect_uri, prompt="select_account")




@router.get('/callback')
async def auth_google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        print("TOKEN GOOGLE:", token)
        if 'id_token' not in token:
            raise HTTPException(status_code=400, detail=f"id_token não retornado pelo Google. Token: {token}")
        user_info = jwt.get_unverified_claims(token['id_token'])
    except OAuthError as error:
        raise HTTPException(status_code=400, detail=f"Erro no login Google: {error.error}")

    # Busca/cria usuário no banco
    db: Session = SessionLocal()
    email = user_info.get('email')
    name = user_info.get('name')
    username = email.split('@')[0] if email else None
    user = db.query(UserModel).filter(UserModel.email == email).first()
    if not user:
        # Cria usuário novo com papel padrão garcom
        papel = RoleEnum.garcom
        user = UserModel(email=email, username=username, senha_hash='google_oauth', papel=papel)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Se o usuário já existe, mantém o papel cadastrado (admin, garcom, etc)
    papel = user.papel.value if hasattr(user.papel, 'value') else user.papel
    access_token = create_access_token({"sub": user.email, "papel": papel, "username": user.username})

    # Redireciona para o frontend com o token
    frontend_url = f"http://localhost:8080/dashboard?access_token={access_token}"
    return RedirectResponse(frontend_url)
