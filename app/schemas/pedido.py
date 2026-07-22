from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import date, time, datetime
from app.schemas.pedido_remessa import PedidoRemessaRead
from app.schemas.prato import PratoRead, PratoGroupCreate


class PedidoItem(BaseModel):
    id: Optional[int] = None
    remessa_id: Optional[int] = None
    prato_id: Optional[int] = None
    # produto_id do item, usado para resolver categoria
    produto_id: Optional[int] = None
    name: str
    quantity: float
    price: float
    observation: Optional[str] = None
    # Referência client-side opcional (ver PratoGroupCreate.client_refs),
    # usada para correlacionar este item com o pedido_item real que será
    # criado a partir dele, quando a quantidade de um mesmo produto é
    # dividida entre pratos diferentes.
    client_ref: Optional[str] = None
    # categoria/categoria normalizada vinda do backend
    categoria: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None


class PedidoBase(BaseModel):
    # mesa_numero deve ser realmente opcional no payload de criação
    mesa_numero: Optional[str] = None
    cliente_id: Optional[int] = None
    items: Optional[List[PedidoItem]] = []
    total: float = 0.0
    status: Optional[str] = 'pendente'
    waiter: Optional[str] = None
    data_pedido: Optional[date] = None
    hora_pedido: Optional[time] = None
    # delivery flag: when true the pedido.tipo should be set to 'delivery'
    delivery: Optional[bool] = False
    # optional delivery address (will be stored in observacao by the backend)
    deliveryAddress: Optional[str] = None


class PedidoCreate(PedidoBase):
    # Optional per-remessa observation. When provided, a PedidoRemessa row
    # will be created associated with the new Pedido.
    remessa_observacao: Optional[str] = None
    # Grupos opcionais de itens (por produto_id) a agrupar em "pratos" já na
    # criação do pedido, associados à remessa inicial criada automaticamente.
    pratos: Optional[List[PratoGroupCreate]] = None


class PedidoRead(BaseModel):
    id: int
    cliente_id: Optional[int]
    cliente_nome: Optional[str] = None
    usuario_id: Optional[int]
    mesa: Optional[str] = None
    tipo: Optional[str]
    status: Optional[str]
    subtotal: float
    adicional_10: int
    valor_total: float
    pagar_depois: int = 0
    observacao: Optional[str]
    items: Optional[List[PedidoItem]] = []
    remessas: Optional[List[PedidoRemessaRead]] = []
    pratos: Optional[List[PratoRead]] = []
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None

    model_config = {"from_attributes": True, "extra": "allow"}
