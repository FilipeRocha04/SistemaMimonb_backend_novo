# Adiciona SessionMiddleware para OAuth
import os
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
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
from app.routes import stats as stats_routes
from app.routes import google_oauth
from app.db import session as db_session
from app.core.config import settings
import logging
import threading
from collections import defaultdict
import time
from app.routes import produtos_precos_quantidade as produtos_precos_quantidade_routes

app = FastAPI(
    title="API Backend - FastAPI",
    version="1.0.0",
    description="Backend profissional com FastAPI",
    # Avoid automatic 307 redirects between /path and /path/
    # We'll register both variants on root endpoints to accept either form.
    redirect_slashes=False,
)

# Configure logging level from env
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
# Use a dedicated app logger to avoid uvicorn.access formatter expectations
_req_logger = logging.getLogger("app.request")
_req_logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

# In-memory request counters per route (method + path), guarded by a lock
_request_counts = defaultdict(int)
_req_lock = threading.Lock()
_global_request_count = 0


@app.middleware("http")
async def request_count_middleware(request: Request, call_next):
    # Prefer the mounted route path template when available
    path_template = None
    try:
        route = request.scope.get("route")
        if route and hasattr(route, "path"):
            path_template = route.path
    except Exception:
        path_template = None
    key_path = path_template or request.url.path
    key = f"{request.method} {key_path}"

    # Increment counter before executing handler
    with _req_lock:
        _request_counts[key] += 1
        count_val = _request_counts[key]
        # track global count across all routes
        global _global_request_count
        _global_request_count += 1
        global_count_val = _global_request_count

    # Log every N hits to avoid spam
    if count_val % settings.REQUEST_LOG_EVERY_N == 0:
        _req_logger.info(f"Request count threshold reached: {key} -> {count_val} (global={global_count_val})")

    # Optional per-request verbose logging for CRUD routes
    verbose = settings.REQUEST_LOG_VERBOSE
    prefixes = [p.strip() for p in (settings.REQUEST_LOG_INCLUDE_PREFIXES or "").split(",") if p.strip()]

    # Initialize per-request DB query counter
    db_count_token = None
    try:
        # set to 0; SQLAlchemy listener will increment during this request
        db_count_token = db_session.request_db_query_count.set(0)
    except Exception:
        db_count_token = None

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)

    # Read per-request DB query count
    per_req_db_count = None
    try:
        per_req_db_count = db_session.request_db_query_count.get()
        # reset the ContextVar to previous state
        if db_count_token is not None:
            try:
                db_session.request_db_query_count.reset(db_count_token)
            except Exception:
                pass
    except Exception:
        per_req_db_count = None
    if verbose:
        try:
            path_full = request.url.path
            # Log only for selected prefixes
            if any(path_full.startswith(pref) for pref in prefixes):
                qs = request.url.query
                path_qs = f"{path_full}?{qs}" if qs else path_full
                # Always log at INFO so it's visible even when LOG_LEVEL=INFO
                _req_logger.info(
                    f"{request.method} {path_qs} -> {response.status_code} in {duration_ms}ms | route_count={count_val} global_count={global_count_val}"
                )
                # Explicit Portuguese line for DB queries per request
                try:
                    total_global_db = db_session.get_global_db_queries_total()
                except Exception:
                    total_global_db = None
                if isinstance(per_req_db_count, int):
                    _req_logger.info(
                        f"Foram {per_req_db_count} requisições ao banco nesta requisição."
                    )
                if isinstance(total_global_db, int):
                    _req_logger.info(
                        f"Total global de requisições ao banco desde o início: {total_global_db}."
                    )
        except Exception:
            pass
    return response

# Configure CORS for local frontend dev (Vite default localhost:8080). Adjust in production.
# Configure CORS for local frontend dev (Vite default localhost:8080). Adjust in production.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"]
)

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
app.include_router(stats_routes.router)
app.include_router(google_oauth.router)
app.include_router(produtos_precos_quantidade_routes.router)


@app.on_event("startup")
def on_startup():
    # create database tables if they don't exist
    db_session.create_db()

@app.get("/")
def root():
    return {"status": "API rodando com sucesso 🚀"}
