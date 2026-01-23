from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.produto_preco_quantidade import ProdutoPrecoQuantidade as ProdutoPrecoQuantidadeModel
from app.schemas.produto_preco_quantidade import ProdutoPrecoQuantidadeRead, ProdutoPrecoQuantidadeCreate

router = APIRouter(prefix="/produtos-precos-quantidade", tags=["Produtos Preços Quantidade"])

@router.get("/{produto_id}", response_model=List[ProdutoPrecoQuantidadeRead])
def get_precos_quantidade(produto_id: int, db: Session = Depends(get_db)):
    precos = db.query(ProdutoPrecoQuantidadeModel).filter(ProdutoPrecoQuantidadeModel.produto_id == produto_id).all()
    return precos

@router.post("/{produto_id}", response_model=ProdutoPrecoQuantidadeRead)
def add_preco_quantidade(produto_id: int, payload: ProdutoPrecoQuantidadeCreate, db: Session = Depends(get_db)):
    preco = ProdutoPrecoQuantidadeModel(produto_id=produto_id, quantidade=payload.quantidade, preco=payload.preco)
    db.add(preco)
    db.commit()
    db.refresh(preco)
    return preco

@router.delete("/{preco_id}")
def delete_preco_quantidade(preco_id: int, db: Session = Depends(get_db)):
    preco = db.query(ProdutoPrecoQuantidadeModel).filter(ProdutoPrecoQuantidadeModel.id == preco_id).first()
    if not preco:
        raise HTTPException(status_code=404, detail="Preço por quantidade não encontrado")
    db.delete(preco)
    db.commit()
    return {"detail": "Preço removido"}
