from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class PratoGroupCreate(BaseModel):
    """Um grupo de itens (já sendo movidos para a remessa) a agrupar num prato."""
    item_ids: List[int] = []
    # Referências client-side (ver PedidoItem.client_ref) usadas para
    # correlacionar com precisão os pedido_itens recém-criados na criação do
    # pedido, já que um mesmo produto pode gerar mais de uma linha quando sua
    # quantidade é dividida entre pratos diferentes (item_ids, por produto_id,
    # não suporta esse caso). Tem prioridade sobre item_ids quando presente.
    client_refs: Optional[List[str]] = None
    observacao: Optional[str] = None


class PratoRead(BaseModel):
    id: int
    pedido_id: int
    remessa_id: int
    observacao: Optional[str] = None
    criado_em: Optional[datetime] = None

    model_config = {"from_attributes": True}
