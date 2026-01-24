from fastapi import APIRouter, UploadFile, File, HTTPException
import uuid
import os
from minio import Minio

router = APIRouter()

@router.post("/uploads/image")
async def upload_image(file: UploadFile = File(...)):
    # Variáveis de ambiente
    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY")
    minio_bucket = os.getenv("MINIO_BUCKET", "mimonb")
    minio_public_url = os.getenv("MINIO_PUBLIC_URL")

    # Inicializa o cliente MinIO
    minio_client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=minio_endpoint.startswith("https")
    )

    # Gera nome único
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    key = f"produtos/{filename}"

    # Faz upload
    try:
        content = await file.read()
        minio_client.put_object(
            minio_bucket,
            key,
            data=content,
            length=len(content),
            content_type=file.content_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao subir imagem: {str(e)}")

    url = f"{minio_public_url}/{minio_bucket}/{key}"
    return {"key": key, "url": url}
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import uuid
import logging
import boto3
from botocore.client import Config

router = APIRouter(prefix="/uploads", tags=["uploads"])

logger = logging.getLogger(__name__)


class PresignRequest(BaseModel):
    filename: str
    content_type: str


# Support multiple env var names. Prefer explicit MINIO_ENDPOINT if provided.
_raw_endpoint = os.environ.get("MINIO_ENDPOINT") or os.environ.get("MINIO_URL") or "http://localhost:9000"
# whether to use https when talking to MinIO
MINIO_USE_SSL = os.environ.get("MINIO_USE_SSL", "0")
USE_SSL = str(MINIO_USE_SSL).lower() in ("1", "true", "yes")

# Normalize endpoint: boto3 requires a full URL (including scheme). If the
# .env contains just 'host:port' we prepend the appropriate scheme.
if not _raw_endpoint.startswith("http://") and not _raw_endpoint.startswith("https://"):
    scheme = "https://" if USE_SSL else "http://"
    MINIO_ENDPOINT = scheme + _raw_endpoint
else:
    MINIO_ENDPOINT = _raw_endpoint

MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY") or "minioadmin"
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY") or "minioadmin"
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "produtos")
# public-facing base url (optional) - fall back to endpoint; ensure it has scheme
_public_raw = os.environ.get("MINIO_PUBLIC_URL")
if _public_raw:
    if not _public_raw.startswith("http://") and not _public_raw.startswith("https://"):
        MINIO_PUBLIC_URL = ("https://" if USE_SSL else "http://") + _public_raw
    else:
        MINIO_PUBLIC_URL = _public_raw
else:
    MINIO_PUBLIC_URL = MINIO_ENDPOINT

_s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    use_ssl=USE_SSL,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


@router.post("/presign")
def presign_upload(req: PresignRequest):
    ext = ""
    if "." in req.filename:
        ext = "." + req.filename.rsplit(".", 1)[1]
    key = f"produtos/{uuid.uuid4().hex}{ext}"
    try:
        # Log useful debug info to help diagnose signature / connectivity issues.
        logger.info("presign requested filename=%s content_type=%s", req.filename, req.content_type)
        logger.info("using minio endpoint=%s bucket=%s use_ssl=%s", MINIO_ENDPOINT, MINIO_BUCKET, USE_SSL)
        # Ensure we have a concrete content type value; browsers may omit it for some files
        signed_content_type = req.content_type or "application/octet-stream"
        presigned_url = _s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": MINIO_BUCKET, "Key": key, "ContentType": signed_content_type},
            ExpiresIn=60 * 60,
        )
    except Exception as e:
        logger.exception("failed to generate presigned url")
        raise HTTPException(status_code=500, detail="Erro ao gerar presigned URL")
    public_url = f"{MINIO_PUBLIC_URL.rstrip('/')}/{MINIO_BUCKET}/{key}"
    logger.info("generated presigned_url for key=%s public_url=%s content_type=%s", key, public_url, signed_content_type)
    # Return the presigned URL plus the exact content_type that was signed so the
    # frontend can set the identical Content-Type header when doing the PUT.
    return {"presigned_url": presigned_url, "key": key, "public_url": public_url, "content_type": signed_content_type}



























@router.get("/presign-get")
def presign_get(key: str):
    """Generate a presigned GET URL for an existing object key.

    Returns JSON { presigned_url, key } so the frontend can fetch the object
    even when the bucket is private.
    """
    if not key:
        raise HTTPException(status_code=400, detail="Missing key parameter")
    try:
        presigned = _s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": MINIO_BUCKET, "Key": key},
            ExpiresIn=60 * 60,
        )
    except Exception:
        logger.exception("failed to generate presigned GET url for key=%s", key)
        raise HTTPException(status_code=500, detail="Erro ao gerar presigned GET URL")
    return {"presigned_url": presigned, "key": key}


