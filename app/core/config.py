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
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://u235343041_mimonb2:Mimonb%402000@srv1524.hstgr.io:3306/u235343041_mimonb2"
    )


settings = Settings()
