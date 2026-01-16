from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL

# SQLAlchemy connect_args differ between SQLite and other DBs (e.g. MySQL)
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Enable pool_pre_ping so SQLAlchemy checks connections from the pool before using them.
# This avoids "MySQL server has gone away" errors caused by stale/closed connections.
# You can also tune pool_recycle or MySQL's wait_timeout on the server side if needed.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


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
