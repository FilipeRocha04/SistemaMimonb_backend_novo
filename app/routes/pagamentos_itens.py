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

from app.services.auth import get_current_user

router = APIRouter(
    prefix="/pagamentos-itens",
    tags=["pagamentos-itens"],
    dependencies=[Depends(get_current_user)],
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
        
        # Buscar todos os IDs dos registros criados para este pedido
        result = db.execute(
            text("""
                SELECT id FROM pagamentos_itens_pagador 
                WHERE pedido_id = :pedido_id 
                ORDER BY id DESC LIMIT :limit
            """),
            {"pedido_id": pagamentos[0].pedido_id, "limit": len(pagamentos)}
        )
        ids_criados = [row[0] for row in result.fetchall()]
        ids_criados.reverse()  # Reverter para ordem correta
        
        return {"ok": True, "ids_criados": ids_criados}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[PagamentoItemPagadorRead])
def list_pagamentos_itens(pedido_id: int = None, db: Session = Depends(get_db)):
    if pedido_id is not None:
        result = db.execute(
            text("SELECT * FROM pagamentos_itens_pagador WHERE pedido_id = :pedido_id LIMIT 100"),
            {"pedido_id": pedido_id}
        )
    else:
        result = db.execute(text("SELECT * FROM pagamentos_itens_pagador LIMIT 100"))
    
    rows = result.fetchall()
    # Converte para dicts manualmente e mapeia os campos
    output = []
    for row in rows:
        row_dict = dict(zip(result.keys(), row))
        # Mapear pedido_id para pedido e pagador_id para pagador
        row_dict['pedido'] = row_dict.pop('pedido_id')
        row_dict['pagador'] = row_dict.pop('pagador_id')
        output.append(PagamentoItemPagadorRead(**row_dict))
    return output


@router.get("/formas-pagamento-por-pedido/")
def get_formas_pagamento_por_pedido(pedido_id: int, db: Session = Depends(get_db)):
    """
    Busca todas as formas de pagamento salvas para um pedido com divisão por itens
    Retorna: {pagador_id: {forma_pagamento: valor, ...}, ...}
    """
    try:
        result = db.execute(
            text("""
                SELECT DISTINCT 
                    pifp.pagador_id,
                    pifp.forma_pagamento,
                    pifp.valor
                FROM pagadores_itens_forma_pagamento pifp
                INNER JOIN pagamentos_itens_pagador pip ON pifp.pagamento_itens_pagador_id = pip.id
                WHERE pip.pedido_id = :pedido_id
                ORDER BY pifp.pagador_id, pifp.forma_pagamento
            """),
            {"pedido_id": pedido_id}
        )
        
        rows = result.fetchall()
        
        # Agrupar formas por pagador
        formas_por_pagador = {}
        for row in rows:
            pagador_id = row[0]
            forma = row[1]
            valor = row[2]
            
            if pagador_id not in formas_por_pagador:
                formas_por_pagador[pagador_id] = {}
            
            formas_por_pagador[pagador_id][forma] = valor
        
        return formas_por_pagador
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar formas de pagamento: {str(e)}"
        )


@router.delete("/deletar-por-pedido/")
def deletar_pagamentos_itens_por_pedido(pedido_id: int, db: Session = Depends(get_db)):
    """
    Deleta todos os registros de pagamentos_itens_pagador e pagadores_itens_forma_pagamento para um pedido
    """
    try:
        # Primeiro, buscar todos os IDs de pagamentos_itens_pagador para este pedido
        result = db.execute(
            text("SELECT id FROM pagamentos_itens_pagador WHERE pedido_id = :pedido_id"),
            {"pedido_id": pedido_id}
        )
        pagamento_itens_ids = [row[0] for row in result.fetchall()]
        
        # Deletar todos os registros de pagadores_itens_forma_pagamento relacionados
        if pagamento_itens_ids:
            placeholders = ','.join([f":id_{i}" for i in range(len(pagamento_itens_ids))])
            params = {f"id_{i}": pid for i, pid in enumerate(pagamento_itens_ids)}
            db.execute(
                text(f"DELETE FROM pagadores_itens_forma_pagamento WHERE pagamento_itens_pagador_id IN ({placeholders})"),
                params
            )
        
        # Deletar todos os registros de pagamentos_itens_pagador
        db.execute(
            text("DELETE FROM pagamentos_itens_pagador WHERE pedido_id = :pedido_id"),
            {"pedido_id": pedido_id}
        )
        
        db.commit()
        
        return {
            "mensagem": "Registros deletados com sucesso",
            "ids_deletados": pagamento_itens_ids
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao deletar registros: {str(e)}"
        )

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


@router.get("/formas-pagamento-por-pedido/")
def get_formas_pagamento_por_pedido(pedido_id: int, db: Session = Depends(get_db)):
    """
    Busca todas as formas de pagamento salvas para um pedido com divisão por itens
    Retorna: {pagador_id: {forma_pagamento: valor, ...}, ...}
    """
    try:
        result = db.execute(
            text("""
                SELECT DISTINCT 
                    pifp.pagador_id,
                    pifp.forma_pagamento,
                    pifp.valor
                FROM pagadores_itens_forma_pagamento pifp
                INNER JOIN pagamentos_itens_pagador pip ON pifp.pagamento_itens_pagador_id = pip.id
                WHERE pip.pedido_id = :pedido_id
                ORDER BY pifp.pagador_id, pifp.forma_pagamento
            """),
            {"pedido_id": pedido_id}
        )
        
        rows = result.fetchall()
        
        # Agrupar formas por pagador
        formas_por_pagador = {}
        for row in rows:
            pagador_id = row[0]
            forma = row[1]
            valor = row[2]
            
            if pagador_id not in formas_por_pagador:
                formas_por_pagador[pagador_id] = {}
            
            formas_por_pagador[pagador_id][forma] = valor
        
        return formas_por_pagador
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar formas de pagamento: {str(e)}"
        )
