# # Adiciona SessionMiddleware para OAuth
# import os
# from fastapi import FastAPI, Request
# from starlette.middleware.sessions import SessionMiddleware
# # Load .env automatically so environment variables defined in backend/.env are
# # available when running uvicorn without --env-file. This keeps local dev simpler.
# try:
#     from dotenv import load_dotenv
#     load_dotenv()
# except Exception:
#     # dotenv is optional; if not installed or .env not present, proceed silently
#     pass
# from fastapi.middleware.cors import CORSMiddleware
# from app.routes import health
# from app.routes import auth as auth_routes
# from app.routes import clients as clients_routes
# from app.routes import products as products_routes
# from app.routes import uploads as uploads_routes
# from app.routes import despesas as despesas_routes
# from app.routes import reservas as reservas_routes
# from app.routes import orders as orders_routes
# from app.routes import kitchen as kitchen_routes
# from app.routes import pagamentos as pagamentos_routes
# from app.routes import orders_ws
# from app.routes import users as users_routes
# from app.routes import stats as stats_routes
# NOTA SEGURANÇA: as duas linhas acima estavam ativas (sem '#') dentro deste
# bloco morto/comentado, e importavam app.routes.stats/orders_ws antes do
# load_dotenv() do bloco ativo mais abaixo — fazendo o carregamento de
# variáveis de ambiente (.env) rodar tarde demais para o app.core.config.
# Foram comentadas para restaurar a ordem correta de inicialização.
# from app.routes import google_oauth
# from app.db import session as db_session
# from app.core.config import settings
# import logging
# import threading
# from collections import defaultdict
# import time
# from app.routes import produtos_precos_quantidade as produtos_precos_quantidade_routes

# # Define request logger for middleware logging
# _req_logger = logging.getLogger("request_logger")

# app = FastAPI(
#     title="API Backend - FastAPI",
#     version="1.0.0",
#     description="Backend profissional com FastAPI",
#     # Avoid automatic 307 redirects between /path and /path/
#     # We'll register both variants on root endpoints to accept either form.
#     redirect_slashes=False,
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:8080"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# ## ...existing code...

# # Optional per-request verbose logging for CRUD routes
# @app.middleware("http")
# async def request_logging_middleware(request: Request, call_next):
#     verbose = settings.REQUEST_LOG_VERBOSE
#     prefixes = [p.strip() for p in (settings.REQUEST_LOG_INCLUDE_PREFIXES or "").split(",") if p.strip()]

#     # Initialize per-request DB query counter
#     db_count_token = None
#     try:
#         # set to 0; SQLAlchemy listener will increment during this request
#         db_count_token = db_session.request_db_query_count.set(0)
#     except Exception:
#         db_count_token = None

#     start = time.perf_counter()
#     response = await call_next(request)
#     duration_ms = int((time.perf_counter() - start) * 1000)

#     # Read per-request DB query count
#     per_req_db_count = None
#     try:
#         per_req_db_count = db_session.request_db_query_count.get()
#         # reset the ContextVar to previous state
#         if db_count_token is not None:
#             try:
#                 db_session.request_db_query_count.reset(db_count_token)
#             except Exception:
#                 pass
#     except Exception:
#         per_req_db_count = None
#     if verbose:
#         try:
#             path_full = request.url.path
#             # Log only for selected prefixes
#             if any(path_full.startswith(pref) for pref in prefixes):
#                 qs = request.url.query
#                 path_qs = f"{path_full}?{qs}" if qs else path_full
#                 # Always log at INFO so it's visible even when LOG_LEVEL=INFO
#                 _req_logger.info(
#                     f"{request.method} {path_qs} -> {response.status_code} in {duration_ms}ms"
#                 )
#                 # Explicit Portuguese line for DB queries per request
#                 try:
#                     total_global_db = db_session.get_global_db_queries_total()
#                 except Exception:
#                     total_global_db = None
#                 if isinstance(per_req_db_count, int):
#                     _req_logger.info(
#                         f"Foram {per_req_db_count} requisições ao banco nesta requisição."
#                     )
#                 if isinstance(total_global_db, int):
#                     _req_logger.info(
#                         f"Total global de requisições ao banco desde o início: {total_global_db}."
#                     )
#         except Exception:
#             pass
#     return response

# # Configure CORS for local frontend dev (Vite default localhost:8080). Adjust in production.
# # Configure CORS for local frontend dev (Vite default localhost:8080). Adjust in production.
# app.add_middleware(
#     SessionMiddleware,
#     secret_key=os.environ["SECRET_KEY"]
# )

# app.add_middleware(
#     CORSMiddleware,
#     # include Vite default port (5173) commonly used in frontend dev
#     allow_origins=["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:5173", "http://127.0.0.1:5173"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# app.include_router(health.router)
# app.include_router(auth_routes.router)
# app.include_router(clients_routes.router)
# app.include_router(products_routes.router)
# app.include_router(uploads_routes.router)
# app.include_router(despesas_routes.router)
# app.include_router(reservas_routes.router)
# app.include_router(orders_routes.router)
# app.include_router(kitchen_routes.router)
# app.include_router(pagamentos_routes.router)
# app.include_router(pagamentos_routes.router)
#app.include_router(stats_routes.router)
# app.include_router(users_routes.router)
# app.include_router(stats_routes.router)
# app.include_router(google_oauth.router)
# app.include_router(produtos_precos_quantidade_routes.router)


# @app.on_event("startup")
# def on_startup():
#     # create database tables if they don't exist
#     db_session.create_db()

# @app.get("/")
# def root():
#     return {"status": "API rodando com sucesso 🚀"}


# Adiciona SessionMiddleware para OAuth
import os
import time
import asyncio
import logging
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware


# Load .env automatically
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
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
from app.routes import produtos_precos_quantidade as produtos_precos_quantidade_routes
from app.routes import orders_ws
from app.db import session as db_session
from app.core.config import settings
from app.routes.orders_last_updated import router as orders_last_updated_router
from fastapi import FastAPI, Request
import time
from fastapi.responses import PlainTextResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.rate_limit import limiter



# Logger
_req_logger = logging.getLogger("request_logger")

# =========================
# FASTAPI APP
# =========================
app = FastAPI(
    title="API Backend - FastAPI",
    version="1.0.0",
    description="Backend profissional com FastAPI",
    redirect_slashes=False,
)

# =========================
# RATE LIMITING (slowapi)
# =========================
# Limite global (default_limits definido em app.core.rate_limit) aplicado a
# toda rota via SlowAPIMiddleware; rotas específicas (ex.: /auth/login) usam
# @limiter.limit(...) com um valor mais restritivo.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# =========================
# TRATAMENTO CENTRALIZADO DE ERROS
# =========================
# Vários endpoints fazem `raise HTTPException(status_code=500, detail=str(e))`,
# o que pode vazar mensagens internas (erros de driver de banco, caminhos,
# etc.) para o cliente. Em produção, normalizamos o texto de qualquer erro
# 5xx antes de responder, mas preservamos o detalhe original nos logs do
# servidor para diagnóstico.
_err_logger = logging.getLogger("app.errors")


@app.exception_handler(StarletteHTTPException)
async def sanitized_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        _err_logger.error(
            "Erro 500 em %s %s: %s", request.method, request.url.path, exc.detail
        )
        if settings.APP_ENV == "production":
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": "Erro interno do servidor"},
            )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


# =========================
# HEADERS DE SEGURANÇA
# =========================
# Apenas headers que não têm risco de quebrar o app (não inclui CSP, que
# exigiria auditar todo script/estilo inline do frontend antes de ativar).
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.middleware("http")
async def log_request_time(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    print(f"{request.url.path} demorou {duration:.4f}s")
    return response

app.include_router(orders_routes.router)
app.include_router(products_routes.router)

# =========================
# ENV + CORS
# =========================

# CORS para desenvolvimento e produção
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://mimonbforneria.projetosapp.com.br",
        "https://www.mimonbforneria.projetosapp.com.br"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# SESSION (OAuth / Google)
# =========================
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
)

# =========================
# REQUEST LOGGING
# =========================
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    verbose = settings.REQUEST_LOG_VERBOSE
    prefixes = [
        p.strip()
        for p in (settings.REQUEST_LOG_INCLUDE_PREFIXES or "").split(",")
        if p.strip()
    ]

    db_count_token = None
    try:
        db_count_token = db_session.request_db_query_count.set(0)
    except Exception:
        pass

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)

    try:
        per_req_db_count = db_session.request_db_query_count.get()
        if db_count_token:
            db_session.request_db_query_count.reset(db_count_token)
    except Exception:
        per_req_db_count = None

    if verbose:
        try:
            path = request.url.path
            if any(path.startswith(pref) for pref in prefixes):
                _req_logger.info(
                    f"{request.method} {path} -> {response.status_code} in {duration_ms}ms"
                )
                if isinstance(per_req_db_count, int):
                    _req_logger.info(
                        f"Foram {per_req_db_count} requisições ao banco nesta requisição."
                    )
        except Exception:
            pass

    return response

# =========================
# ROUTES
# =========================
# =========================
# ROUTES
# =========================
app.include_router(stats_routes.router)
app.include_router(health.router)
app.include_router(auth_routes.router)
app.include_router(clients_routes.router)
app.include_router(products_routes.router)
app.include_router(uploads_routes.router)
app.include_router(despesas_routes.router)
app.include_router(reservas_routes.router)
app.include_router(orders_routes.router)
app.include_router(pagamentos_routes.router)
app.include_router(google_oauth.router)
app.include_router(produtos_precos_quantidade_routes.router)
app.include_router(orders_ws.router)
from app.routes import pagadores
app.include_router(pagadores.router)
app.include_router(orders_last_updated_router)
from app.routes import pagamentos_detalhe
app.include_router(pagamentos_detalhe.router)
from app.routes import pagamentos_itens
app.include_router(pagamentos_itens.router)
# =========================
@app.on_event("startup")
async def on_startup():
    db_session.create_db()
    # Captura o loop principal para permitir que as rotas de pedidos (sync,
    # rodando em threadpool) agendem notificações WebSocket de forma segura.
    orders_ws.set_main_loop(asyncio.get_running_loop())
    # Escuta o Redis (se configurado) para repassar eventos de pedidos/cozinha
    # aos clientes WebSocket/SSE conectados a ESTE worker, mesmo quando o
    # evento foi originado por outro worker do gunicorn.
    from app.utils import redis_bus
    from app.utils.pubsub import publish_local
    redis_bus.start_listener({
        "orders_update": orders_ws.broadcast_local,
        "kitchen_event": publish_local,
    })

@app.get("/loaderio-2e84d0b509c246e5778c61b55e9bf194.txt")
def loaderio_verification():
    return PlainTextResponse(
        "loaderio-2e84d0b509c246e5778c61b55e9bf194"
    )

@app.get("/")
def root():
    return {"status": "API rodando com sucesso 🚀"}









