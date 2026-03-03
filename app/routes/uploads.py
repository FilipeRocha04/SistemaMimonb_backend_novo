
import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from minio import Minio

router = APIRouter(prefix="/uploads", tags=["uploads"])

# Rota para remover imagem do MinIO
@router.delete("/image")
async def delete_image(key: str = Query(...)):
    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY")
    minio_bucket = os.getenv("MINIO_BUCKET", "mimonb")
    minio_secure = os.getenv("MINIO_SECURE", "False") == "True"

    client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=minio_secure
    )

    try:
        client.remove_object(minio_bucket, key)
        return {"detail": "Imagem removida com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY")
    minio_bucket = os.getenv("MINIO_BUCKET", "mimonb")
    minio_public_url = os.getenv("MINIO_PUBLIC_URL")
    minio_secure = os.getenv("MINIO_SECURE", "False") == "True"

    if not all([minio_endpoint, minio_access_key, minio_secret_key, minio_public_url]):
        raise HTTPException(status_code=500, detail="MinIO não configurado corretamente")

    client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=minio_secure
    )

    # Garante que bucket exista
    if not client.bucket_exists(minio_bucket):
        client.make_bucket(minio_bucket)

    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    key = f"produtos/{filename}"

    try:
        client.put_object(
            minio_bucket,
            key,
            file.file,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=file.content_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "key": key,
        "url": f"{minio_public_url}/{minio_bucket}/{key}"
    }