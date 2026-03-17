from fastapi import Body
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from app.db.session import get_db
from app.schemas import pagamento
from app.models import pagamento as pagamento_model
from app.schemas.pagador_itens_forma_pagamento import PagadorItensFormaPagamentoCreate
# Modelo de leitura para pagamentos_itens_pagador
from pydantic import BaseModel
from typing import Optional

class PagamentoItemPagadorRead(BaseModel):
    id: int
    pedido: int
    pedido_item_id: int
    pagador: int
    produto_preco_id: int
    valor: float
    taxa_10: float
    
    model_config = {"from_attributes": True}

class PagamentoItemPagadorCreate(BaseModel):
    pedido_id: int
    pedido_item_id: int
    pagador_id: int
    produto_id: int
    valor: float
    taxa_10: float

router = APIRouter(
    prefix="/pagamentos-itens",
    tags=["pagamentos-itens"]
)

# Endpoint para criar pagamentos por itens
@router.post("/", status_code=201)
def create_pagamentos_itens(
    pagamentos: List[PagamentoItemPagadorCreate] = Body(...),
    db: Session = Depends(get_db)
):
    try:
        ids_criados = []
        for pagamento in pagamentos:
            # Buscar o produto_preco_id a partir do produto_id
            result = db.execute(
                text("SELECT id FROM produto_precos WHERE produto_id = :produto_id LIMIT 1"),
                {"produto_id": pagamento.produto_id}
            )
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail=f"Nenhum preço encontrado para o produto {pagamento.produto_id}")
            
            produto_preco_id = row[0]
            
            db.execute(
                text(
                    """
                    INSERT INTO pagamentos_itens_pagador
                    (pedido_id, pedido_item_id, pagador_id, produto_preco_id, valor, taxa_10)
                    VALUES (:pedido_id, :pedido_item_id, :pagador_id, :produto_preco_id, :valor, :taxa_10)
                    """
                ),
                {
                    "pedido_id": pagamento.pedido_id,
                    "pedido_item_id": pagamento.pedido_item_id,
                    "pagador_id": pagamento.pagador_id,
                    "produto_preco_id": produto_preco_id,
                    "valor": pagamento.valor,
                    "taxa_10": pagamento.taxa_10,
                }
            )
        db.commit()
        
        # Buscar os IDs dos registros criados
        result = db.execute(
            text("""
                SELECT id FROM pagamentos_itens_pagador 
                WHERE pedido_id = :pedido_id 
                ORDER BY id DESC LIMIT 1
            """),
            {"pedido_id": pagamentos[0].pedido_id}
        )
        row = result.fetchone()
        ultimo_id = row[0] if row else None
        
        return {"ok": True, "ids": ids_criados, "ultimo_id": ultimo_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))



# Endpoint para listar os 100 primeiros registros
@router.get("/", response_model=List[PagamentoItemPagadorRead])
def list_pagamentos_itens(db: Session = Depends(get_db)):
    result = db.execute("SELECT * FROM pagamentos_itens_pagador LIMIT 100")
    rows = result.fetchall()
    # Converte para dicts
    return [PagamentoItemPagadorRead(**dict(row)) for row in rows]


# Endpoint para salvar as formas de pagamento de cada pagador na divisão por itens
@router.post("/pagadores-itens-formas-pagamento/", status_code=201)
def criar_pagador_itens_formas_pagamento(
    pagamento_itens_pagador_id: int,
    formas: List[PagadorItensFormaPagamentoCreate] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Salva as formas de pagamento para cada pagador na divisão por itens
    """
    try:
        registros_criados = []
        
        for forma in formas:
            db.execute(
                text("""
                    INSERT INTO pagadores_itens_forma_pagamento
                    (pagamento_itens_pagador_id, pagador_id, forma_pagamento, valor)
                    VALUES (:pagamento_itens_pagador_id, :pagador_id, :forma_pagamento, :valor)
                """),
                {
                    "pagamento_itens_pagador_id": pagamento_itens_pagador_id,
                    "pagador_id": forma.pagador_id,
                    "forma_pagamento": forma.forma_pagamento,
                    "valor": forma.valor
                }
            )
            registros_criados.append(forma)
        
        db.commit()
        
        return {
            "mensagem": "Formas de pagamento salvas com sucesso",
            "registros": registros_criados
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao salvar formas de pagamento: {str(e)}"
        )
