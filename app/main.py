from fastapi import FastAPI
# Load .env automatically so environment variables defined in backend/.env are
# available when running uvicorn without --env-file. This keeps local dev simpler.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv is optional; if not installed or .env not present, proceed silently
    pass
from fastapi.middleware.cors import CORSMiddleware
from app.routes import health
from app.routes import auth as auth_routes
from app.routes import clients as clients_routes
from app.routes import products as products_routes
from app.routes import uploads as uploads_routes
from app.routes import despesas as despesas_routes
from app.routes import reservas as reservas_routes
from app.routes import orders as orders_routes
from app.routes import kitchen as kitchen_routes
from app.routes import pagamentos as pagamentos_routes
from app.routes import users as users_routes
from app.db import session as db_session

app = FastAPI(
    title="API Backend - FastAPI",
    version="1.0.0",
    description="Backend profissional com FastAPI"
)

# Configure CORS for local frontend dev (Vite default localhost:8080). Adjust in production.
app.add_middleware(
    CORSMiddleware,
    # include Vite default port (5173) commonly used in frontend dev
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth_routes.router)
app.include_router(clients_routes.router)
app.include_router(products_routes.router)
app.include_router(uploads_routes.router)
app.include_router(despesas_routes.router)
app.include_router(reservas_routes.router)
app.include_router(orders_routes.router)
app.include_router(kitchen_routes.router)
app.include_router(pagamentos_routes.router)
app.include_router(users_routes.router)


@app.on_event("startup")
def on_startup():
    # create database tables if they don't exist
    db_session.create_db()

@app.get("/")
def root():
    return {"status": "API rodando com sucesso 🚀"}
