from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import date, time, datetime
from app.schemas.pedido_remessa import PedidoRemessaRead


class PedidoItem(BaseModel):
    id: Optional[int] = None
    remessa_id: Optional[int] = None
    # produto_id do item, usado para resolver categoria
    produto_id: Optional[int] = None
    name: str
    quantity: int
    price: float
    # quando verdadeiro, aplica metade do preço do produto no momento da venda
    metade: Optional[bool] = None
    # fator aplicado ao preço base (ex.: 0.5 para meia). Somente leitura em respostas
    preco_fator: Optional[float] = None
    observation: Optional[str] = None
    # categoria/categoria normalizada vinda do backend
    categoria: Optional[str] = None
    category: Optional[str] = None


class PedidoBase(BaseModel):
    # mesa_numero deve ser realmente opcional no payload de criação
    mesa_numero: Optional[str] = None
    cliente_id: Optional[int]
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


class PedidoRead(BaseModel):
    id: int
    cliente_id: Optional[int]
    cliente_nome: Optional[str] = None
    usuario_id: Optional[int]
    tipo: Optional[str]
    status: Optional[str]
    subtotal: float
    adicional_10: int
    valor_total: float
    observacao: Optional[str]
    items: Optional[List[PedidoItem]] = []
    remessas: Optional[List[PedidoRemessaRead]] = []
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None

    class Config:
        orm_mode = True
        # allow extra fields coming from manual dict responses (e.g., categoria)
        extra = "allow"
