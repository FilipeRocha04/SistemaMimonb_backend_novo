from fastapi import APIRouter, UploadFile, File, HTTPException
import uuid
import os
from minio import Minio

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY")
    minio_bucket = os.getenv("MINIO_BUCKET", "mimonb")
    minio_public_url = os.getenv("MINIO_PUBLIC_URL")

    if not all([minio_endpoint, minio_access_key, minio_secret_key, minio_public_url]):
        raise HTTPException(status_code=500, detail="MinIO não configurado corretamente")

    client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=False  # MinIO está interno
    )

    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    key = f"produtos/{filename}"

    try:
        content = await file.read()
        client.put_object(
            minio_bucket,
            key,
            data=content,
            length=len(content),
            content_type=file.content_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "key": key,
        "url": f"{minio_public_url}/{minio_bucket}/{key}"
    }
