from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
import logging
import threading
import contextvars

DATABASE_URL = settings.DATABASE_URL

# SQLAlchemy connect_args differ between SQLite and other DBs (e.g. MySQL)
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Enable pool_pre_ping so SQLAlchemy checks connections from the pool before using them.
# This avoids "MySQL server has gone away" errors caused by stale/closed connections.
# You can also tune pool_recycle or MySQL's wait_timeout on the server side if needed.
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.DB_POOL_RECYCLE,
    poolclass=QueuePool,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- Pool monitoring: log connects and checkouts to help diagnose excess connections ---
_pool_logger = logging.getLogger("app.db.pool")
_pool_logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
_connect_count = 0
_checkout_count = 0
_checkin_count = 0
_pool_lock = threading.Lock()

# --- Per-request DB query counting using ContextVar ---
# The FastAPI middleware sets this to 0 at the start of each request. SQLAlchemy
# listeners increment it on each executed cursor, allowing us to log the total
# number of DB roundtrips per HTTP request.
request_db_query_count = contextvars.ContextVar("request_db_query_count", default=None)
_global_db_query_count = 0


@event.listens_for(engine, "connect")
def _on_connect(dbapi_connection, connection_record):
    global _connect_count
    with _pool_lock:
        _connect_count += 1
        cnt = _connect_count
    # Log every N connects to avoid noisy output
    if cnt % settings.DB_LOG_EVERY_N == 0:
        _pool_logger.info(f"SQLAlchemy Pool CONNECT events: total opened={cnt}")


@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_connection, connection_record, connection_proxy):
    global _checkout_count
    with _pool_lock:
        _checkout_count += 1
        cnt = _checkout_count
    if cnt % settings.DB_LOG_EVERY_N == 0:
        _pool_logger.info(f"SQLAlchemy Pool CHECKOUT events: total checkouts={cnt}")


@event.listens_for(engine, "checkin")
def _on_checkin(dbapi_connection, connection_record):
    global _checkin_count
    with _pool_lock:
        _checkin_count += 1
        cnt = _checkin_count
    if cnt % settings.DB_LOG_EVERY_N == 0:
        _pool_logger.info(f"SQLAlchemy Pool CHECKIN events: total checkins={cnt}")


@event.listens_for(engine, "before_cursor_execute")
def _on_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    # increment per-request counter when present
    try:
        current = request_db_query_count.get()
        if current is not None:
            request_db_query_count.set(int(current) + 1)
    except Exception:
        pass
    # increment global counter
    global _global_db_query_count
    with _pool_lock:
        _global_db_query_count += 1


def get_global_db_queries_total() -> int:
    """Return the total number of DB roundtrips since process start."""
    try:
        return int(_global_db_query_count)
    except Exception:
        return 0


def get_db():
    """FastAPI dependency that provides a scoped SQLAlchemy Session.

    Ensures the connection is checked out from the pool and always returned
    after the request, preventing leaks and excessive new connections.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_db():
    # Import models here so they are registered on the metadata
    try:
        import app.models.user  # noqa: F401
        import app.models.session  # noqa: F401
        import app.models.client  # noqa: F401
        import app.models.product  # noqa: F401
        import app.models.product_price  # noqa: F401
        import app.models.despesa  # noqa: F401
        import app.models.reserva  # noqa: F401
        import app.models.pedido  # noqa: F401
        import app.models.pedido_item  # noqa: F401
        import app.models.pedido_remessa  # noqa: F401
        import app.models.pedido_categoria_status  # noqa: F401
    except Exception:
        pass
    Base.metadata.create_all(bind=engine)
    # Ensure backward-compatible columns exist (useful when adding columns to existing DB)
    try:
        inspector = inspect(engine)
        if "reservas" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("reservas")]
            if "atualizado_em" not in cols:
                try:
                    # Use a transactional connection for the DDL
                    with engine.begin() as conn:
                        if DATABASE_URL.startswith("sqlite"):
                            conn.execute(text("ALTER TABLE reservas ADD COLUMN atualizado_em DATETIME"))
                        else:
                            conn.execute(text("ALTER TABLE reservas ADD COLUMN atualizado_em DATETIME NULL"))
                except Exception as exc:
                    # Don't raise here; warn and continue so server can start for further debugging.
                    print("Warning: failed to add column 'atualizado_em' to 'reservas':", exc)
            # Ensure mesa_id and cliente_id allow NULL when model expects nullable=True
            try:
                col_info = {c['name']: c for c in inspector.get_columns('reservas')}
                for col_name in ('mesa_id', 'cliente_id'):
                    if col_name in col_info and not col_info[col_name].get('nullable', True):
                        try:
                            with engine.begin() as conn:
                                if DATABASE_URL.startswith("sqlite"):
                                    # SQLite doesn't support MODIFY; skip and warn
                                    print(f"Warning: cannot alter column nullability for '{col_name}' on SQLite automatically. Please migrate the table manually.")
                                else:
                                    # MySQL / MariaDB: modify column to BIGINT NULL
                                    conn.execute(text(f"ALTER TABLE reservas MODIFY COLUMN {col_name} BIGINT NULL"))
                        except Exception as exc2:
                            print(f"Warning: failed to modify nullability for column '{col_name}':", exc2)
            except Exception:
                pass
                # Ensure foreign key constraint from reservas.cliente_id -> clientes.id exists (MySQL/MariaDB only)
                try:
                    fks = inspector.get_foreign_keys('reservas')
                    has_cliente_fk = any('cliente_id' in fk.get('constrained_columns', []) and fk.get('referred_table') in ('clientes', 'cliente') for fk in fks)
                    if not has_cliente_fk:
                        try:
                            with engine.begin() as conn:
                                if DATABASE_URL.startswith('sqlite'):
                                    print("Warning: cannot add foreign key constraint on SQLite automatically. Please migrate the table manually.")
                                else:
                                    # Add FK with ON DELETE SET NULL to avoid cascade deletions
                                    conn.execute(text("ALTER TABLE reservas ADD CONSTRAINT fk_reservas_cliente_id FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE SET NULL"))
                        except Exception as exc_fk:
                            print("Warning: failed to add foreign key constraint reservas(cliente_id) -> clientes(id):", exc_fk)
                except Exception:
                    pass
    except Exception:
        # If inspector fails for any reason, continue silently to avoid blocking startup.
        pass

        # Defensive check: if there is an existing `pedidos` table but it lacks the
        # `atualizado_em` column (older schema), try to add it so the SQLAlchemy
        # model and DB stay in sync. Failure is non-fatal and only warns.
        try:
            inspector2 = inspect(engine)
            if 'pedidos' in inspector2.get_table_names():
                pedido_cols = [c['name'] for c in inspector2.get_columns('pedidos')]
                if 'atualizado_em' not in pedido_cols:
                    try:
                        with engine.begin() as conn:
                            if DATABASE_URL.startswith('sqlite'):
                                conn.execute(text("ALTER TABLE pedidos ADD COLUMN atualizado_em DATETIME"))
                            else:
                                conn.execute(text("ALTER TABLE pedidos ADD COLUMN atualizado_em DATETIME NULL"))
                    except Exception as exc_p:
                        print("Warning: failed to add column 'atualizado_em' to 'pedidos':", exc_p)
                # If items column is missing, add a text column to store serialized items
                if 'itens_json' not in pedido_cols:
                    try:
                        with engine.begin() as conn:
                            if DATABASE_URL.startswith('sqlite'):
                                conn.execute(text("ALTER TABLE pedidos ADD COLUMN itens_json TEXT"))
                            else:
                                conn.execute(text("ALTER TABLE pedidos ADD COLUMN itens_json TEXT NULL"))
                    except Exception as exc_items:
                        print("Warning: failed to add column 'itens_json' to 'pedidos':", exc_items)
        except Exception:
            pass

    # Ensure pedido_items.status column exists for item-level preparation status
    try:
        inspector3 = inspect(engine)
        if 'pedido_items' in inspector3.get_table_names():
            item_cols = [c['name'] for c in inspector3.get_columns('pedido_items')]
            if 'status' not in item_cols:
                try:
                    with engine.begin() as conn:
                        if DATABASE_URL.startswith('sqlite'):
                            # SQLite: add column without NOT NULL/DEFAULT constraints
                            conn.execute(text("ALTER TABLE pedido_items ADD COLUMN status VARCHAR(20)"))
                            # Backfill existing rows to 'pendente' where NULL
                            conn.execute(text("UPDATE pedido_items SET status = 'pendente' WHERE status IS NULL"))
                        else:
                            # MySQL/MariaDB: add NOT NULL with DEFAULT
                            conn.execute(text("ALTER TABLE pedido_items ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pendente'"))
                except Exception as exc_status:
                    print("Warning: failed to add column 'status' to 'pedido_items':", exc_status)
            else:
                # Ensure existing NULLs are backfilled to 'pendente'
                try:
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE pedido_items SET status = 'pendente' WHERE status IS NULL"))
                except Exception:
                    pass
    except Exception:
        # Non-fatal: continue startup even if inspector fails
        pass
