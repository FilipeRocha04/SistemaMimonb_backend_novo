from fastapi import APIRouter, Depends, HTTPException
import logging
from typing import List
from sqlalchemy.orm import Session

import os
from app.db.session import SessionLocal
from app.models.product import Produto as ProdutoModel
from app.models.product_price import ProdutoPreco as ProdutoPrecoModel
from app.schemas.product import ProdutoCreate, ProdutoRead
from app.schemas.product_price import ProdutoPrecoRead
import urllib.parse

router = APIRouter(prefix="/products", tags=["Products"])

logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=ProdutoRead)
def create_product(payload: ProdutoCreate, db: Session = Depends(get_db)):
    try:
        logger.info("create_product payload.categoria=%r unidade=%r unidade_valor=%r", payload.categoria, getattr(payload, 'unidade', None), getattr(payload, 'unidade_valor', None))
        # Ensure we store only the object key in the DB. If the client sent a full URL,
        # extract the bucket/key path (e.g. /<bucket>/produtos/uuid.png -> produtos/uuid.png)
        imagem_val = getattr(payload, 'imagem', None)
        if isinstance(imagem_val, str) and imagem_val.startswith(('http://', 'https://')):
            try:
                parsed = urllib.parse.urlparse(imagem_val)
                path = parsed.path.lstrip('/')
                # if path begins with the bucket name, remove it
                if path.startswith(f"{os.environ.get('MINIO_BUCKET','')}/"):
                    imagem_key = path.split('/', 1)[1]
                else:
                    imagem_key = path
            except Exception:
                imagem_key = imagem_val
        else:
            imagem_key = imagem_val

        p = ProdutoModel(nome=payload.nome, categoria=payload.categoria, unidade=payload.unidade, unidade_valor=payload.unidade_valor or 0.0, preco=payload.preco or 0.0, descricao=payload.descricao, ativo=payload.ativo, imagem=imagem_key)
        db.add(p)
        db.commit()
        db.refresh(p)
        logger.info("created product id=%s categoria=%r", p.id, p.categoria)
        # create initial price history entry
        try:
            pp = ProdutoPrecoModel(produto_id=p.id, preco=p.preco)
            db.add(pp)
            db.commit()
        except Exception:
            db.rollback()
        return p
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[ProdutoRead])
def list_products(db: Session = Depends(get_db)):
    try:
        rows = db.query(ProdutoModel).order_by(ProdutoModel.id.desc()).all()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{product_id}", response_model=ProdutoRead)
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(ProdutoModel).filter(ProdutoModel.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return p


@router.get("/{product_id}/prices", response_model=List[ProdutoPrecoRead])
def get_product_prices(product_id: int, db: Session = Depends(get_db)):
    p = db.query(ProdutoModel).filter(ProdutoModel.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    rows = db.query(ProdutoPrecoModel).filter(ProdutoPrecoModel.produto_id == product_id).order_by(ProdutoPrecoModel.id.desc()).all()
    return rows


@router.put("/{product_id}", response_model=ProdutoRead)
def update_product(product_id: int, payload: ProdutoCreate, db: Session = Depends(get_db)):
    p = db.query(ProdutoModel).filter(ProdutoModel.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    try:
        logger.info("update_product payload.categoria=%r unidade=%r unidade_valor=%r", payload.categoria, getattr(payload, 'unidade', None), getattr(payload, 'unidade_valor', None))
        old_price = p.preco
        new_price = payload.preco or 0.0
        p.nome = payload.nome
        p.categoria = payload.categoria
        p.unidade = payload.unidade
        p.unidade_valor = payload.unidade_valor or 0.0
        p.preco = new_price
        p.descricao = payload.descricao
        p.ativo = payload.ativo
        # Same sanitization: accept either a key or a full URL but store only the key
        imagem_val = getattr(payload, 'imagem', None)
        if isinstance(imagem_val, str) and imagem_val.startswith(('http://', 'https://')):
            try:
                parsed = urllib.parse.urlparse(imagem_val)
                path = parsed.path.lstrip('/')
                if path.startswith(f"{os.environ.get('MINIO_BUCKET','')}/"):
                    imagem_key = path.split('/', 1)[1]
                else:
                    imagem_key = path
            except Exception:
                imagem_key = imagem_val
        else:
            imagem_key = imagem_val
        p.imagem = imagem_key
        db.add(p)
        db.commit()
        db.refresh(p)
        logger.info("updated product id=%s categoria=%r unidade=%r unidade_valor=%r", p.id, p.categoria, p.unidade, p.unidade_valor)
        # if price changed, add price history entry
        if old_price != new_price:
            try:
                pp = ProdutoPrecoModel(produto_id=p.id, preco=new_price)
                db.add(pp)
                db.commit()
            except Exception:
                db.rollback()
        return p
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(ProdutoModel).filter(ProdutoModel.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    try:
        db.delete(p)
        db.commit()
        return {"detail": "Produto removido com sucesso"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
