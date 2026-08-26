
import os
import uuid
from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException, Query
from minio import Minio

from app.services.auth import get_current_user
from app.core.rate_limit import limiter

router = APIRouter(prefix="/uploads", tags=["uploads"], dependencies=[Depends(get_current_user)])

# Tipos e tamanho máximo aceitos para upload de imagem de produto.
_ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_IMAGE_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB

# Rota para remover imagem do MinIO
@router.delete("/image")
async def delete_image(key: str = Query(...)):
    # Evita que a chave saia da pasta "produtos/" (path traversal / remoção
    # de objetos fora do escopo de imagens de produto).
    if not key.startswith("produtos/") or ".." in key:
        raise HTTPException(status_code=400, detail="Chave de imagem inválida")
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
@limiter.limit("20/minute")
async def upload_image(request: Request, file: UploadFile = File(...)):
    if file.content_type not in _ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido. Envie uma imagem (jpeg, png, webp ou gif).")

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


    # Calcula o tamanho real do arquivo
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > _MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Imagem excede o tamanho máximo permitido (8MB)")

    try:
        client.put_object(
            minio_bucket,
            key,
            file.file,
            length=file_size,
            part_size=10 * 1024 * 1024,
            content_type=file.content_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "key": key,
        "url": f"{minio_public_url}/{minio_bucket}/{key}"
    }