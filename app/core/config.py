import os
from pathlib import Path


# If a local .env file exists in the backend folder, load it into os.environ
# (simple parser so we don't need an extra dependency like python-dotenv).
env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    # Load .env and OVERRIDE any existing environment variables so the
    # local backend/.env is authoritative for development.
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, val = line.split('=', 1)
        key = key.strip()
        val = val.strip()
        # remove possible surrounding quotes
        if (val.startswith("\"") and val.endswith("\"")) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        # Always set/override so the .env in backend/ takes precedence
        os.environ[key] = val


class Settings:
    """Lightweight settings loader using environment variables.

    This avoids depending on pydantic's BaseSettings and works reliably
    with different pydantic versions installed in the environment.
    """

    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-to-a-secure-random-string")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
    # refresh token lifetime in days
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", str(14)))
    # Read DATABASE_URL from env, but be resilient to an accidental repeated
    # prefix like "DATABASE_URL=DATABASE_URL=..." which was observed in a
    # malformed .env file. If detected, strip the duplicate prefix so SQLAlchemy
    # receives a valid URL.
    raw_db = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://u235343041_mimonb2:Mimonb%402000@srv1524.hstgr.io:3306/u235343041_mimonb2"
    )
    if isinstance(raw_db, str) and raw_db.startswith("DATABASE_URL="):
        # remove the first 'DATABASE_URL=' that was accidentally included
        raw_db = raw_db.split("=", 1)[1]
    DATABASE_URL: str = raw_db

    # Connection pool tuning (defaults chosen for small/medium apps)
    APP_ENV: str = os.getenv("APP_ENV", os.getenv("ENV", "development")).lower()
    # Environment-aware defaults (can be overridden via env)
    _default_pool_size = 5 if APP_ENV == "development" else 10
    _default_max_overflow = 2 if APP_ENV == "development" else 20
    _default_pool_recycle = 900 if APP_ENV == "development" else 1800

    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", str(_default_pool_size)))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", str(_default_max_overflow)))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", str(_default_pool_recycle)))  # seconds

    # Logging and monitoring controls
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    # Log request counters every N hits per route
    REQUEST_LOG_EVERY_N: int = int(os.getenv("REQUEST_LOG_EVERY_N", "100"))
    # Log pool events every N occurrences
    DB_LOG_EVERY_N: int = int(os.getenv("DB_LOG_EVERY_N", "50"))
    # Verbose per-request logging (development aid)
    REQUEST_LOG_VERBOSE: bool = str(os.getenv("REQUEST_LOG_VERBOSE", "0")).strip().lower() in {"1", "true", "yes", "on"}
    # Comma-separated route prefixes to include for verbose logging
    REQUEST_LOG_INCLUDE_PREFIXES: str = os.getenv(
        "REQUEST_LOG_INCLUDE_PREFIXES",
        "/orders,/pagamentos,/products,/clients,/reservas,/users"
    )


settings = Settings()
