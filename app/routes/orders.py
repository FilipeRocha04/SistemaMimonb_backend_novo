from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, text
import json
from typing import List
import traceback
import logging

from app.db.session import get_db
from app.utils.pubsub import publish
from app.routes.orders_ws import notify_orders_update, schedule_coroutine
from app.models.product import Produto as ProdutoModel
from app.models.client import Cliente as ClienteModel
import asyncio
from app.models.pedido import Pedido as PedidoModel
from app.models.pedido_item import PedidoItem
from app.schemas.pedido import PedidoCreate, PedidoRead
from app.models.pagamento import Pagamento as PagamentoModel
from app.models.pedido_remessa import PedidoRemessa as PedidoRemessaModel
from app.models.prato import Prato as PratoModel
from app.models.pedido_categoria_status import PedidoCategoriaStatus as PedidoCategoriaStatusModel
from datetime import timezone, datetime
from app.core.timezone_utils import local_day_range_to_utc, BRAZIL_TZ

router = APIRouter(prefix="/orders", tags=["Orders"])

# module-level default for remessa status map (per-request handlers will overwrite when available)
remessa_status_map = {}

def effective_valor_total(subtotal, valor_total, adicional_10) -> float:
    """Return the correct effective total, applying 10% fee when adicional_10=1."""
    st = float(subtotal or 0)
    vt = float(valor_total or 0)
    if int(adicional_10 or 0) and vt < st * 1.05:
        return round(st * 1.1, 2)
    return vt if vt >= st - 0.01 else st

def is_finalized_status(s: str | None) -> bool:
    """Return True if a pedido status represents a finalized (immutable) order.

    Business rule: once the order is closed (paid or delivered), values must not change.
    We treat 'pago' and 'entregue' as finalized states.
    """
    try:
        st = (s or '').lower().strip()
        return st in ('pago', 'entregue')
    except Exception:
        return False


def resolve_current_price_for_item(it_like, db: Session) -> float:
    """Lookup the current product price in the produtos table to snapshot on item creation.

    Priority:
    - Use produto_id when available
    - Fallback: match by normalized name (lowercase exact)
    Returns 0.0 when not found.
    """
    try:
        # Accept both pedido item models and raw dict payloads
        prod_id = (
            getattr(it_like, 'produto_id', None)
            or getattr(it_like, 'id', None)  # when frontend sends product id as `id` and Pydantic maps it to the item.id field
            or (it_like.get('produto_id') if isinstance(it_like, dict) else None)
            or (it_like.get('id') if isinstance(it_like, dict) else None)
        )
        name = getattr(it_like, 'nome', None) or (it_like.get('name') if isinstance(it_like, dict) else None) or (it_like.get('nome') if isinstance(it_like, dict) else None)
        prod = None
        if prod_id:
            prod = db.query(ProdutoModel).filter(ProdutoModel.id == int(prod_id)).first()
        if not prod and name:
            prod = db.query(ProdutoModel).filter(func.lower(ProdutoModel.nome) == str(name).lower()).first()
        if prod:
            # preço atual é armazenado em ProdutoModel.preco (mapeado para preco_atual)
            try:
                return float(getattr(prod, 'preco', 0) or 0)
            except Exception:
                return 0.0
        # Fallback: if product not found, use client-provided price to avoid zeros
        try:
            client_price = (
                getattr(it_like, 'price', None)
                or (it_like.get('price') if isinstance(it_like, dict) else None)
                or (it_like.get('preco') if isinstance(it_like, dict) else None)
            )
            if client_price is not None:
                return float(client_price or 0)
        except Exception:
            pass
        return 0.0
    except Exception:
        return 0.0




def resolve_categoria_for_item(item, db: Session):
    """Return product.categoria for a PedidoItem-like object.
    Prefer produto_id lookup; if missing, try to find a product by name (case-insensitive).
    Returns None when no match is found.
    """
    try:
        # try by produto_id first
        prod_id = getattr(item, 'produto_id', None) or (item.get('produto_id') if isinstance(item, dict) else None)
        if prod_id:
            prod = db.query(ProdutoModel).filter(ProdutoModel.id == prod_id).first()
            if prod and getattr(prod, 'categoria', None):
                return getattr(prod, 'categoria')

        # fallback: try matching by name (normalize by lower)
        name = getattr(item, 'nome', None) or (item.get('name') if isinstance(item, dict) else None) or (item.get('nome') if isinstance(item, dict) else None)
        if name:
            # perform case-insensitive exact match on name column
            prod = db.query(ProdutoModel).filter(func.lower(ProdutoModel.nome) == str(name).lower()).first()
            if prod and getattr(prod, 'categoria', None):
                return getattr(prod, 'categoria')
    except Exception:
        return None
    return None


def is_beverage_category(raw: str | None) -> bool:
    """Return True if a category string looks like beverage/drink-related."""
    try:
        s = (raw or '').lower()
        return (
            'bebida' in s or 'bebidas' in s or 'vinho' in s or 'vinhos' in s or
            'drink' in s or 'drinks' in s or 'refri' in s or 'refrigerante' in s or
            'suco' in s or 'água' in s or 'agua' in s
        )
    except Exception:
        return False


def category_key_for_item(item, db: Session) -> str:
    """Return a simple category key for an item: 'bebida' or 'pizza'."""
    cat = resolve_categoria_for_item(item, db)
    return 'bebida' if is_beverage_category(cat) else 'pizza'


def upsert_category_status(db: Session, pedido_id: int, categoria_key: str, status: str):
    """Create or update a per-categoria status row for a pedido."""
    try:
        row = db.query(PedidoCategoriaStatusModel).filter(
            PedidoCategoriaStatusModel.pedido_id == pedido_id,
            PedidoCategoriaStatusModel.categoria == categoria_key,
        ).first()
        if not row:
            row = PedidoCategoriaStatusModel(pedido_id=pedido_id, categoria=categoria_key, status=status)
        else:
            row.status = status
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()


def compute_and_persist_category_statuses(db: Session, pedido_id: int):
    """Compute per-categoria statuses exclusively from item.status and persist.

    Regra:
    - Se todos os itens da categoria estiverem 'pronto' => 'pronto'
    - Se algum item estiver 'em_preparo' => 'em_preparo'
    - Caso contrário, se existir qualquer item pendente => 'pendente'
    - Sem itens na categoria => não persiste status
    """
    try:
        items = db.query(PedidoItem).filter(PedidoItem.pedido_id == pedido_id).all()
        if not items:
            # no items -> clear statuses
            try:
                db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == pedido_id).delete()
                db.commit()
            except Exception:
                db.rollback()
            return

        # categorize items
        pizza_items = []
        beverage_items = []
        for it in items:
            (beverage_items if is_beverage_category(resolve_categoria_for_item(it, db)) else pizza_items).append(it)

        def status_for(items_list):
            if not items_list:
                return None
            # derive only from item.status
            statuses = []
            for it in items_list:
                st = getattr(it, 'status', None)
                st_l = str(st or '').lower()
                statuses.append(st_l)
            if not statuses:
                return None
            all_ready = all(s and ('pront' in s or 'ready' in s) for s in statuses)
            any_preparing = any(s and ('prepar' in s or 'em_preparo' in s) for s in statuses)
            any_pending = any((not s) or ('pend' in s) for s in statuses)
            if all_ready:
                return 'pronto'
            if any_preparing:
                return 'em_preparo'
            if any_pending:
                return 'pendente'
            return 'pendente'

        pizza_status = status_for(pizza_items)
        beverage_status = status_for(beverage_items)

        if pizza_status:
            upsert_category_status(db, pedido_id, 'pizza', pizza_status)
        if beverage_status:
            upsert_category_status(db, pedido_id, 'bebida', beverage_status)
    except Exception:
        # non-fatal
        pass


def recompute_order_status_from_items(db: Session, order: PedidoModel) -> str:
    """Derive pedido.status a partir dos status dos itens.

    Regra:
    - Todos itens 'pronto' => pedido.status = 'pronto'
    - Mistura de 'pronto' e 'pendente' => 'em_preparo'
    - Nenhum item 'pronto' (todos pendentes) => 'pendente'
    - Sem itens => 'pendente'
    Retorna o novo status aplicado.
    """
    try:
        items = db.query(PedidoItem).filter(PedidoItem.pedido_id == order.id).all()
        if not items:
            new_status = 'pendente'
        else:
            statuses = [str(getattr(it, 'status', '') or '').lower() for it in items]
            # Treat 'entregue' as a ready/finalized status
            def is_ready(s):
                return ('pront' in s) or ('ready' in s) or ('entregue' in s)
            any_ready = any(is_ready(s) for s in statuses)
            all_ready = any_ready and all(is_ready(s) for s in statuses)
            if all_ready:
                new_status = 'pronto'
            elif any_ready:
                new_status = 'em_preparo'
            else:
                new_status = 'pendente'
        order.status = new_status
        db.add(order)
        db.commit()
        return new_status
    except Exception:
        # não bloquear fluxo por falha de recomputação; manter status atual
        db.rollback()
        return getattr(order, 'status', 'pendente')


# Use shared get_db from app.db.session


def map_incoming_status(s: any) -> str:
    """Normalize incoming status strings to the application's canonical stored values.

    Rules:
    - If missing/falsey -> 'pendente'
    - If contains english or portuguese tokens, map accordingly to Portuguese defaults.
    """
    if not s:
        return 'pendente'
    try:
        st = str(s).lower()
    except Exception:
        return 'pendente'
    if 'pend' in st:
        return 'pendente'
    # map to the DB enum values used in the `pedidos` table
    # 'em_preparo' represents the preparing state in the DB
    if 'prepar' in st or 'preparing' in st or 'em_preparo' in st:
        return 'em_preparo'
    # map 'pronto' / 'ready' to a 'pronto' DB value (prefer explicit 'pronto')
    if 'pront' in st or 'ready' in st:
        return 'pronto'
    if 'entreg' in st or 'deliv' in st:
        return 'entregue'
    if 'cancel' in st:
        return 'cancelado'
    # payments: map payment tokens to the internal 'paid' status so UIs
    # render the order as paid instead of accidentally reverting to pending.
    if 'pag' in st or 'paid' in st:
        return 'pago'
    # fallback
    return 'pendente'


def to_brasilia(dt):
    """Convert a datetime to America/Sao_Paulo timezone for API responses.

    Behavior:
    - If dt is None -> returns None
    - If dt is naive, assume it is in UTC and attach tzinfo=UTC before converting.
    - If zoneinfo is available, convert to that zone; otherwise return the original dt.
    """
    try:
        if dt is None:
            return None
        # if zoneinfo is configured, use it
        if BRAZIL_TZ is not None:
            # ensure dt is timezone-aware (assume UTC if naive)
            if getattr(dt, 'tzinfo', None) is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(BRAZIL_TZ)
        # no zoneinfo available: best-effort, return dt unchanged
        return dt
    except Exception:
        return dt


@router.post("", response_model=PedidoRead)
@router.post("/", response_model=PedidoRead)
def create_order(payload: PedidoCreate, db: Session = Depends(get_db)):
    try:
        # map incoming payload to existing pedidos table columns
        # Determine initial remessa type from payload.delivery; do not persist on Pedido
        tipo = 'delivery' if getattr(payload, 'delivery', False) else 'local'
        # Do not trust client-provided totals; compute from item snapshots
        subtotal = 0.0
        adicional_10 = 0
        valor_total = 0.0
        # Definir a data (dia) do pedido independentemente de estar pago.
        # Permitir data_pedido retroativa/futura se enviada no payload
        data_pedido = getattr(payload, 'data_pedido', None)
        if not data_pedido:
            try:
                data_pedido = (datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date())
            except Exception:
                data_pedido = datetime.utcnow().date()

        # Buscar o maior numero_diario do dia informado
        max_num = db.query(func.max(PedidoModel.numero_diario)).filter(PedidoModel.data_pedido == data_pedido).scalar()
        if max_num is None:
            numero_diario = 1
        else:
            numero_diario = max_num + 1
        observacao = None

        p = PedidoModel(
            cliente_id=payload.cliente_id,
            usuario_id=None,
            mesa=getattr(payload, 'mesa_numero', None),
            status=map_incoming_status(getattr(payload, 'status', None)),
            subtotal=0.0,
            adicional_10=adicional_10,
            valor_total=0.0,
            data=data_pedido,
            observacao=observacao,
            numero_diario=numero_diario,
            data_pedido=data_pedido,
        )

        # attach items as PedidoItem objects (normalized table)
        items_payload = getattr(payload, 'items', []) or []
        # Mapa client_ref -> PedidoItem, usado depois (já com id atribuído
        # pelo commit abaixo) para correlacionar pratos com precisão quando a
        # quantidade de um mesmo produto foi dividida em mais de uma linha.
        client_ref_to_item: dict = {}
        for it in items_payload:
            # handle both pydantic objects and plain dicts
            name = getattr(it, 'name', None) or (it.get('name') if isinstance(it, dict) else None) or (it.get('nome') if isinstance(it, dict) else None)
            # Corrige: aceita valores fracionados corretamente, sem sobrescrever 0.5 para 1 ou 0
            qty_raw = getattr(it, 'quantity', None)
            if qty_raw is None and isinstance(it, dict):
                qty_raw = it.get('quantity', None)
            if qty_raw is None and isinstance(it, dict):
                qty_raw = it.get('qty', None)
            try:
                if isinstance(qty_raw, str) and "/" in qty_raw:
                    num, denom = qty_raw.split("/")
                    qty = float(num) / float(denom)
                else:
                    qty = float(qty_raw)
                if qty < 0.01:
                    continue  # ignora itens com quantidade zero ou negativa
            except Exception:
                continue  # ignora itens com quantidade inválida
            # Snapshot price from produtos at creation time
            base_price = resolve_current_price_for_item(it, db)
            # Se for metade, quantidade já será 0.5, então só multiplicar pelo preço unitário
            price = base_price
            obs = getattr(it, 'observation', None) or (it.get('observation') if isinstance(it, dict) else None) or (it.get('observacao') if isinstance(it, dict) else None)
            prod_id = getattr(it, 'id', None) or (it.get('id') if isinstance(it, dict) else None)
            if qty > 0:
                item_model = PedidoItem(produto_id=prod_id, nome=name or '', quantidade=qty, preco=price, observacao=obs, status='pendente')
                p.items.append(item_model)
                client_ref = getattr(it, 'client_ref', None) or (it.get('client_ref') if isinstance(it, dict) else None)
                if client_ref:
                    client_ref_to_item[str(client_ref)] = item_model
                try:
                    subtotal += float(price) * float(qty)
                except Exception:
                    pass

        db.add(p)
        db.commit()
        db.refresh(p)
        # client_ref -> id real do pedido_item, agora que o commit acima
        # atribuiu ids autoincrementados aos objetos ORM já em memória.
        client_ref_to_item_id = {ref: m.id for ref, m in client_ref_to_item.items() if getattr(m, 'id', None)}

        # Now that items are persisted, compute and freeze initial totals based on snapshots
        try:
            p.subtotal = round(float(subtotal), 2)
            # respect adicional_10 flag when computing valor_total
            if getattr(p, 'adicional_10', 0):
                p.valor_total = round(float(subtotal) * 1.1, 2)
            else:
                p.valor_total = round(float(subtotal), 2)
            db.add(p)
            db.commit()
            db.refresh(p)
        except Exception:
            pass

        # Always create an initial remessa for the order and store type there
        pr = None
        try:
            rem_obs = getattr(payload, 'remessa_observacao', None)
            delivery_addr = getattr(payload, 'deliveryAddress', None)
            pr = PedidoRemessaModel(
                pedido_id=p.id,
                observacao_remessa=rem_obs,
                endereco=delivery_addr,
                tipo=tipo,
            )
            db.add(pr)
            db.commit()
            db.refresh(pr)
            # associate all current items of this newly created order to this remessa
            try:
                # load fresh items and set their remessa_id
                items_rows = db.query(PedidoItem).filter(PedidoItem.pedido_id == p.id).all()
                for it_row in items_rows:
                    it_row.remessa_id = pr.id
                    db.add(it_row)
                db.commit()
            except Exception:
                db.rollback()
        except Exception:
            # non-fatal: don't block order creation if remessa persistence fails
            db.rollback()

        # Monta "pratos" (agrupamentos de itens) já na criação do pedido, se
        # enviados. Preferencialmente correlaciona via client_refs (ver
        # PedidoItem.client_ref), que identifica com precisão cada linha de
        # item mesmo quando um mesmo produto foi dividido em mais de uma
        # linha entre pratos diferentes. Se o grupo não enviar client_refs
        # (clientes antigos), cai para o esquema legado: item_ids referencia
        # o produto (mesmo id usado em items[].id no payload) e só suporta um
        # produto pertencendo a um único prato por inteiro.
        try:
            pratos_payload = getattr(payload, 'pratos', None) or []
            if pratos_payload and pr is not None:
                items_rows = db.query(PedidoItem).filter(PedidoItem.pedido_id == p.id).all()
                produto_to_item_id = {
                    it_row.produto_id: it_row.id for it_row in items_rows if it_row.produto_id is not None
                }
                for group in pratos_payload:
                    # group é um PratoGroupCreate (Pydantic) quando vem via
                    # PedidoCreate; aceita também dict por segurança.
                    group_item_ids = getattr(group, 'item_ids', None)
                    if group_item_ids is None and isinstance(group, dict):
                        group_item_ids = group.get('item_ids')
                    group_item_ids = group_item_ids or []
                    group_client_refs = getattr(group, 'client_refs', None)
                    if group_client_refs is None and isinstance(group, dict):
                        group_client_refs = group.get('client_refs')
                    group_client_refs = group_client_refs or []
                    group_observacao = getattr(group, 'observacao', None)
                    if group_observacao is None and isinstance(group, dict):
                        group_observacao = group.get('observacao')
                    real_ids = [client_ref_to_item_id[r] for r in group_client_refs if r in client_ref_to_item_id]
                    if not real_ids:
                        real_ids = [produto_to_item_id[pid] for pid in group_item_ids if pid in produto_to_item_id]
                    if not real_ids:
                        continue
                    prato = PratoModel(pedido_id=p.id, remessa_id=pr.id, observacao=group_observacao)
                    db.add(prato)
                    db.commit()
                    db.refresh(prato)
                    db.query(PedidoItem).filter(PedidoItem.id.in_(real_ids)).update(
                        {'prato_id': prato.id}, synchronize_session=False
                    )
                    db.commit()
        except Exception:
            logging.exception("Failed to create pratos for new order %s", p.id)

        # Recarrega o pedido para que p.items reflita o prato_id recém-setado
        # (o UPDATE em lote acima não atualiza os objetos já carregados na sessão).
        try:
            db.refresh(p)
        except Exception:
            pass

        # initialize per-categoria status rows (pendente) based on items present
        try:
            items_rows = db.query(PedidoItem).filter(PedidoItem.pedido_id == p.id).all()
            has_pizza = any(category_key_for_item(it, db) == 'pizza' for it in items_rows)
            has_beverage = any(category_key_for_item(it, db) == 'bebida' for it in items_rows)
            if has_pizza:
                upsert_category_status(db, p.id, 'pizza', 'pendente')
            if has_beverage:
                upsert_category_status(db, p.id, 'bebida', 'pendente')
        except Exception:
            pass

        # publish per-item events for kitchen
        try:
            # ensure we have a client name to include in events (query if relation not loaded)
            client_name = None
            try:
                if getattr(p, 'cliente', None) and getattr(p.cliente, 'nome', None):
                    client_name = getattr(p.cliente, 'nome')
                elif getattr(p, 'cliente_id', None):
                    c = db.query(ClienteModel).filter(ClienteModel.id == p.cliente_id).first()
                    if c:
                        client_name = getattr(c, 'nome', None)
            except Exception:
                client_name = None

            for it in p.items:
                categoria = resolve_categoria_for_item(it, db)

                event = {
                    'type': 'order_item',
                    'action': 'added',
                    'order_id': p.id,
                    'cliente_id': p.cliente_id,
                    'cliente_nome': client_name,
                    'item': {
                        'id': it.id,
                        'produto_id': it.produto_id,
                        'name': it.nome,
                        'quantity': it.quantidade,
                        'price': float(it.preco or 0),
                        'observation': it.observacao,
                        'categoria': categoria,
                    }
                }
                # schedule publish without awaiting to avoid blocking
                schedule_coroutine(publish(event))
        except Exception:
            # best-effort; don't block order creation on pubsub failures
            pass

        # attach any remessas for this pedido to the response
        remessas_list = []
        try:
            rem_rows = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == p.id).order_by(PedidoRemessaModel.id.asc()).all()
            # build remessas list
            for rr in rem_rows:
                remessas_list.append({
                    'id': rr.id,
                    'pedido_id': getattr(rr, 'pedido_id', None),
                    'observacao': getattr(rr, 'observacao_remessa', None),
                    'endereco': getattr(rr, 'endereco', None),
                    'tipo': getattr(rr, 'tipo', 'local'),
                    'status': getattr(rr, 'status', 'pendente'),
                    'criado_em': to_brasilia(rr.criado_em)
                })
        except Exception:
            remessas_list = []

        pratos_list = []
        try:
            prato_rows = db.query(PratoModel).filter(PratoModel.pedido_id == p.id).order_by(PratoModel.id.asc()).all()
            for pr_row in prato_rows:
                pratos_list.append({
                    'id': pr_row.id,
                    'pedido_id': pr_row.pedido_id,
                    'remessa_id': pr_row.remessa_id,
                    'observacao': pr_row.observacao,
                    'criado_em': to_brasilia(pr_row.criado_em),
                })
        except Exception:
            pratos_list = []

        data = {
            'id': p.id,
            'cliente_id': p.cliente_id,
            'usuario_id': p.usuario_id,
            # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
            'tipo': None,
            'status': p.status,
            'subtotal': float(p.subtotal or 0),
            'adicional_10': int(p.adicional_10 or 0),
            'valor_total': effective_valor_total(p.subtotal, p.valor_total, p.adicional_10),
            'pagar_depois': int(p.pagar_depois or 0),
            'observacao': p.observacao,
            'criado_em': p.criado_em,
            'atualizado_em': getattr(p, 'atualizado_em', None),
            'numero_diario': p.numero_diario,
            'data_pedido': str(p.data_pedido) if p.data_pedido else None,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                    'observation': it.observacao,
                    'categoria': resolve_categoria_for_item(it, db),
                    'category': resolve_categoria_for_item(it, db),
                }
                for it in p.items
            ],
            'remessas': remessas_list,
            'pratos': pratos_list,
            # include per-categoria statuses (optional for clients)
            'category_status': {
                'pizza': db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == p.id, PedidoCategoriaStatusModel.categoria == 'pizza').first().status if db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == p.id, PedidoCategoriaStatusModel.categoria == 'pizza').first() else None,
                'bebida': db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == p.id, PedidoCategoriaStatusModel.categoria == 'bebida').first().status if db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == p.id, PedidoCategoriaStatusModel.categoria == 'bebida').first() else None,
            },
        }
        # Notifica clientes WebSocket sobre novo pedido
        schedule_coroutine(notify_orders_update())
        return data
    except Exception as e:
        db.rollback()
        tb = traceback.format_exc()
        logging.exception("Failed to create order: %s", e)
        # return full traceback in detail for easier debugging (can be removed later)
        raise HTTPException(status_code=500, detail=tb)


@router.get("", response_model=List[PedidoRead])
@router.get("", response_model=List[PedidoRead])
@router.get("/", response_model=List[PedidoRead])
def list_orders(db: Session = Depends(get_db), date_from: str = None, date_to: str = None, active_only: bool = False):
    try:
        query = db.query(PedidoModel).options(joinedload(PedidoModel.items), joinedload(PedidoModel.cliente))

        # If the caller provided date filters in local Brasilia dates (YYYY-MM-DD
        # or ISO datetimes), convert them to UTC range and apply to the query.
        if date_from:
            # if only a single date_from is provided, treat date_to as same day
            if not date_to:
                date_to = date_from
            start_utc, _ = local_day_range_to_utc(date_from)
            _, end_utc = local_day_range_to_utc(date_to)
            if start_utc and end_utc:
                query = query.filter(PedidoModel.criado_em >= start_utc, PedidoModel.criado_em <= end_utc)

        # active_only: usado pela tela da cozinha para evitar buscar/reprocessar
        # todo o histórico de pedidos a cada atualização. Restringe a pedidos de
        # hoje que ainda não foram finalizados (pago/entregue).
        if active_only:
            today_str = datetime.now(BRAZIL_TZ).strftime('%Y-%m-%d')
            start_utc, end_utc = local_day_range_to_utc(today_str)
            if start_utc and end_utc:
                query = query.filter(PedidoModel.criado_em >= start_utc, PedidoModel.criado_em <= end_utc)
            query = query.filter(func.lower(PedidoModel.status).notin_(['pago', 'entregue']))

        rows = query.order_by(PedidoModel.id.desc()).all()
        order_ids = [r.id for r in rows]

        # Preload payment status for all pedidos in this page to avoid N+1 queries from the frontend
        paid_ids = set()
        payment_methods_map: dict = {}
        try:
            if order_ids:
                pays = db.query(PagamentoModel).filter(
                    PagamentoModel.pedido.in_(order_ids)
                ).all()
                for p in pays:
                    st = str(getattr(p, 'status', '') or '').lower()
                    if 'pago' in st or 'paid' in st:
                        paid_ids.add(getattr(p, 'pedido', None))
                # Preload payment methods with values for all orders in this page
                from app.models.pagador import PagamentoPagadorForma as PagamentoPagadorFormaModel
                pf_rows = (
                    db.query(
                        PagamentoModel.pedido,
                        PagamentoPagadorFormaModel.forma_pagamento,
                        func.coalesce(func.sum(PagamentoPagadorFormaModel.valor), 0).label('total'),
                    )
                    .join(PagamentoPagadorFormaModel, PagamentoPagadorFormaModel.pagamento_id == PagamentoModel.id)
                    .filter(PagamentoModel.pedido.in_(order_ids))
                    .group_by(PagamentoModel.pedido, PagamentoPagadorFormaModel.forma_pagamento)
                    .all()
                )
                for pedido_id, forma, total in pf_rows:
                    if pedido_id not in payment_methods_map:
                        payment_methods_map[pedido_id] = []
                    if forma:
                        payment_methods_map[pedido_id].append({'forma': forma, 'valor': float(total)})
        except Exception:
            paid_ids = set()
            payment_methods_map = {}

        # Preload remessas for all pedidos in this page to avoid N+1 queries
        remessas_map: dict = {}
        try:
            if order_ids:
                all_rems = (
                    db.query(PedidoRemessaModel)
                    .filter(PedidoRemessaModel.pedido_id.in_(order_ids))
                    .order_by(PedidoRemessaModel.pedido_id.asc(), PedidoRemessaModel.id.asc())
                    .all()
                )
                for rem in all_rems:
                    remessas_map.setdefault(rem.pedido_id, []).append(rem)
        except Exception:
            remessas_map = {}

        # Preload pratos for all pedidos in this page to avoid N+1 queries
        pratos_map: dict = {}
        try:
            if order_ids:
                all_pratos = (
                    db.query(PratoModel)
                    .filter(PratoModel.pedido_id.in_(order_ids))
                    .order_by(PratoModel.pedido_id.asc(), PratoModel.id.asc())
                    .all()
                )
                for prato in all_pratos:
                    pratos_map.setdefault(prato.pedido_id, []).append(prato)
        except Exception:
            pratos_map = {}

        # Preload product categories for all items in this page to avoid N+1 queries
        categoria_map: dict = {}
        try:
            produto_ids = {
                it.produto_id
                for r in rows
                for it in (getattr(r, 'items', []) or [])
                if getattr(it, 'produto_id', None)
            }
            if produto_ids:
                for prod in db.query(ProdutoModel).filter(ProdutoModel.id.in_(produto_ids)).all():
                    categoria_map[prod.id] = getattr(prod, 'categoria', None)
        except Exception:
            categoria_map = {}

        def _categoria_for_item(it):
            prod_id = getattr(it, 'produto_id', None)
            if prod_id and prod_id in categoria_map:
                return categoria_map[prod_id]
            # fallback raro: item sem produto_id (match por nome), preço da consulta individual
            return resolve_categoria_for_item(it, db)

        out = []
        for r in rows:
            rems_list = remessas_map.get(r.id, [])
            pratos_list = pratos_map.get(r.id, [])

            items_out = []
            for it in (getattr(r, 'items', []) or []):
                categoria = _categoria_for_item(it)
                items_out.append({
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                    'observation': it.observacao,
                    'categoria': categoria,
                    'category': categoria,
                })

            d = {
                'id': r.id,
                'cliente_id': r.cliente_id,
                'cliente_nome': getattr(r.cliente, 'nome', None) if getattr(r, 'cliente', None) else None,
                'usuario_id': r.usuario_id,
                'mesa': getattr(r, 'mesa', None),
                # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
                'tipo': None,
                'status': r.status,
                'subtotal': float(r.subtotal or 0),
                'adicional_10': int(r.adicional_10 or 0),
                'valor_total': effective_valor_total(r.subtotal, r.valor_total, r.adicional_10),
                'pagar_depois': int(r.pagar_depois or 0),
                'observacao': r.observacao,
                'paid': (r.id in paid_ids),
                'formas_pagamento': payment_methods_map.get(r.id, []),
                'numero_diario': getattr(r, 'numero_diario', None),
                'data_pedido': str(getattr(r, 'data_pedido', None)) if getattr(r, 'data_pedido', None) else None,
                'items': items_out,
                'criado_em': to_brasilia(r.criado_em),
                'atualizado_em': getattr(r, 'atualizado_em', None),
            }
            d['remessas'] = [
                {
                    'id': rr.id,
                    'pedido_id': getattr(rr, 'pedido_id', None),
                    'observacao': getattr(rr, 'observacao_remessa', None),
                    'endereco': getattr(rr, 'endereco', None),
                    'tipo': getattr(rr, 'tipo', 'local'),
                    'status': getattr(rr, 'status', 'pendente'),
                    # use remessa creation time, not the pedido time
                    'criado_em': to_brasilia(rr.criado_em),
                }
                for rr in rems_list
            ]
            d['pratos'] = [
                {
                    'id': p.id,
                    'pedido_id': p.pedido_id,
                    'remessa_id': p.remessa_id,
                    'observacao': p.observacao,
                    'criado_em': to_brasilia(p.criado_em),
                }
                for p in pratos_list
            ]
            out.append(d)
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{order_id}", response_model=PedidoRead)
def get_order(order_id: int, db: Session = Depends(get_db)):
    try:
        r = db.query(PedidoModel).options(joinedload(PedidoModel.items), joinedload(PedidoModel.cliente)).filter(PedidoModel.id == order_id).first()
        if not r:
            raise HTTPException(status_code=404, detail='Pedido not found')
        print(f"[DEBUG BACKEND] GET /orders/{order_id} - Carregado do DB: pagar_depois={r.pagar_depois}")
        # fetch remessas early so items can include remessa_status
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == r.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # Determine paid status and payment methods for this order
        is_paid = False
        order_formas_pagamento: list = []
        try:
            pays = db.query(PagamentoModel).filter(PagamentoModel.pedido == r.id).all()
            for p in pays:
                st = str(getattr(p, 'status', '') or '').lower()
                if 'pago' in st or 'paid' in st:
                    is_paid = True
                    break
            from app.models.pagador import PagamentoPagadorForma as PagamentoPagadorFormaModel
            pay_ids = [p.id for p in pays]
            if pay_ids:
                pf_rows = (
                    db.query(
                        PagamentoPagadorFormaModel.forma_pagamento,
                        func.coalesce(func.sum(PagamentoPagadorFormaModel.valor), 0).label('total'),
                    )
                    .filter(PagamentoPagadorFormaModel.pagamento_id.in_(pay_ids))
                    .group_by(PagamentoPagadorFormaModel.forma_pagamento)
                    .all()
                )
                for forma, total in pf_rows:
                    if forma:
                        order_formas_pagamento.append({'forma': forma, 'valor': float(total)})
        except Exception:
            is_paid = False
            order_formas_pagamento = []

        d = {
            'id': r.id,
            'cliente_id': r.cliente_id,
            'cliente_nome': getattr(r.cliente, 'nome', None) if getattr(r, 'cliente', None) else None,
            'usuario_id': r.usuario_id,
            'mesa': getattr(r, 'mesa', None),
            # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
            'tipo': None,
            'status': r.status,
            'subtotal': float(r.subtotal or 0),
            'adicional_10': int(r.adicional_10 or 0),
            'valor_total': effective_valor_total(r.subtotal, r.valor_total, r.adicional_10),
            'pagar_depois': int(r.pagar_depois or 0),
            'observacao': r.observacao,
            'paid': is_paid,
            'formas_pagamento': order_formas_pagamento,
            'numero_diario': getattr(r, 'numero_diario', None),
            'data_pedido': str(getattr(r, 'data_pedido', None)) if getattr(r, 'data_pedido', None) else None,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                        'observation': it.observacao,
                    'categoria': resolve_categoria_for_item(it, db),
                    'category': resolve_categoria_for_item(it, db),
                }
                for it in (getattr(r, 'items', []) or [])
            ],
                'criado_em': to_brasilia(r.criado_em),
                'atualizado_em': getattr(r, 'atualizado_em', None),
        }
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == r.id).order_by(PedidoRemessaModel.id.asc()).all()
            d['remessas'] = [
                {
                    'id': rr.id,
                    'pedido_id': getattr(rr, 'pedido_id', None),
                    'observacao': getattr(rr, 'observacao_remessa', None),
                    'endereco': getattr(rr, 'endereco', None),
                    'tipo': getattr(rr, 'tipo', 'local'),
                    'status': getattr(rr, 'status', 'pendente'),
                    'criado_em': to_brasilia(rr.criado_em),
                }
                for rr in rems
            ]
        except Exception:
            d['remessas'] = []
        try:
            pratos = db.query(PratoModel).filter(PratoModel.pedido_id == r.id).order_by(PratoModel.id.asc()).all()
            d['pratos'] = [
                {
                    'id': p.id,
                    'pedido_id': p.pedido_id,
                    'remessa_id': p.remessa_id,
                    'observacao': p.observacao,
                    'criado_em': to_brasilia(p.criado_em),
                }
                for p in pratos
            ]
        except Exception:
            d['pratos'] = []
        print(f"[DEBUG BACKEND] GET /orders/{order_id} - Retornando resposta: pagar_depois={d.get('pagar_depois')}")
        return d
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: int, db: Session = Depends(get_db)):
    """Delete an order (pedido) and its items/remessas.

    This is used by the mobile Orders page to allow deleting a comanda.
    """
    try:
        order = db.query(PedidoModel).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido not found")

        # Delete related remessas first (if any), then items, per-categoria statuses, pagamentos, detalhes_pagamento, then the order itself.
        try:
            # pratos referenciam remessas via FK; apagar antes de apagar as remessas
            db.query(PratoModel).filter(PratoModel.pedido_id == order.id).delete()
        except Exception:
            pass

        try:
            db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).delete()
        except Exception:
            pass

        try:
            db.query(PedidoItem).filter(PedidoItem.pedido_id == order.id).delete()
        except Exception:
            pass

        try:
            db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == order.id).delete()
        except Exception:
            pass

        # Remover pagamentos e detalhes de pagamento vinculados ao pedido
        try:
            # Primeiro remover formas de pagamento da divisão por itens
            from sqlalchemy import text
            db.execute(text("""
                DELETE FROM pagadores_itens_forma_pagamento 
                WHERE pagamento_itens_pagador_id IN (
                    SELECT id FROM pagamentos_itens_pagador 
                    WHERE pedido_id = :pedido_id
                )
            """), {"pedido_id": order.id})
        except Exception:
            pass
        
        try:
            # Depois remover pagamentos_itens_pagador
            from sqlalchemy import text
            db.execute(text("DELETE FROM pagamentos_itens_pagador WHERE pedido_id = :pedido_id"), {"pedido_id": order.id})
        except Exception:
            pass
        
        try:
            # Depois remover pagadores_formas_pagamento
            from sqlalchemy import text
            db.execute(text("DELETE FROM pagadores_formas_pagamento WHERE pedido_id = :pedido_id"), {"pedido_id": order.id})
        except Exception:
            pass
        
        try:
            pagamentos = db.query(PagamentoModel).filter(PagamentoModel.pedido == order.id).all()
            from app.models.pagador import PagamentoPagadorForma as PagamentoPagadorFormaModel
            for pagamento in pagamentos:
                db.query(PagamentoPagadorFormaModel).filter(PagamentoPagadorFormaModel.pagamento_id == pagamento.id).delete()
            db.query(PagamentoModel).filter(PagamentoModel.pedido == order.id).delete()
        except Exception:
            pass

        db.delete(order)
        db.commit()
        # Notifica clientes WebSocket sobre remoção de pedido
        schedule_coroutine(notify_orders_update())
        return
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception("Failed to delete order: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete order")


@router.post("/{order_id}/remessas", response_model=PedidoRead)
def create_remessa_for_order(order_id: int, payload: dict, db: Session = Depends(get_db)):
    """Create a per-pedido remessa and optionally associate existing items to it.

    Expected payload: { item_ids: [1,2,3], observacao?: str, endereco?: str }
    This will create a PedidoRemessa row linked to the pedido and set
    pedido_items.remessa_id for the provided item ids (only if they belong to the pedido).
    """
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

        # prepare existing remessas (optional, not used for item status control)
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        item_ids = payload.get('item_ids', []) or []
        observacao = payload.get('observacao') or payload.get('remessa_observacao')
        endereco = payload.get('endereco') or payload.get('deliveryAddress')

        # determine requested status (allow frontend to request 'pronto')
        requested_status = payload.get('status') or payload.get('status_remessa') or 'pendente'
        # tipo da remessa deve ser definido explicitamente no payload; padrão 'local'
        remessa_tipo = payload.get('tipo') or 'local'
        pr = PedidoRemessaModel(pedido_id=order.id, observacao_remessa=observacao, endereco=endereco, status=requested_status, tipo=remessa_tipo)
        db.add(pr)
        db.commit()
        db.refresh(pr)

        moved_items = []
        if item_ids:
            # only update items that belong to this order
            items_to_move = db.query(PedidoItem).filter(PedidoItem.pedido_id == order.id).filter(PedidoItem.id.in_(item_ids)).all()
            for it in items_to_move:
                it.remessa_id = pr.id
                # atualizar status do item com base no payload (exclusivo na tabela pedido_itens)
                try:
                    it.status = map_incoming_status(requested_status)
                except Exception:
                    it.status = 'pendente'
                db.add(it)
                moved_items.append(it)
            db.commit()

        # Monta "pratos" (agrupamentos de itens desta remessa), se solicitado.
        # Cada grupo em payload['pratos'] deve ser {item_ids: [...], observacao?}
        # com item_ids sendo subconjunto dos itens movidos para esta remessa.
        try:
            prato_groups = payload.get('pratos') or []
            moved_ids = {it.id for it in moved_items}
            for group in prato_groups:
                group_item_ids = [i for i in (group.get('item_ids') or []) if i in moved_ids]
                if not group_item_ids:
                    continue
                prato = PratoModel(
                    pedido_id=order.id,
                    remessa_id=pr.id,
                    observacao=group.get('observacao'),
                )
                db.add(prato)
                db.commit()
                db.refresh(prato)
                db.query(PedidoItem).filter(PedidoItem.id.in_(group_item_ids)).update(
                    {'prato_id': prato.id}, synchronize_session=False
                )
                db.commit()
        except Exception:
            logging.exception("Failed to create pratos for remessa %s", pr.id)

        # Recalcular status do pedido com base nos itens após atualização
        try:
            recompute_order_status_from_items(db, order)
        except Exception:
            pass
        # Não alterar status do pedido com base em remessas; controle é exclusivo em pedido_itens

        # recompute per-categoria statuses and persist
        try:
            compute_and_persist_category_statuses(db, order.id)
        except Exception:
            pass

        # publish events for moved items so UIs/kitchen can react
        try:
            client_name = None
            try:
                if getattr(order, 'cliente', None) and getattr(order.cliente, 'nome', None):
                    client_name = getattr(order.cliente, 'nome')
                elif getattr(order, 'cliente_id', None):
                    c = db.query(ClienteModel).filter(ClienteModel.id == order.cliente_id).first()
                    if c:
                        client_name = getattr(c, 'nome', None)
            except Exception:
                client_name = None

            for it in moved_items:
                categoria = resolve_categoria_for_item(it, db)
                event = {
                    'type': 'order_item',
                    'action': 'moved_to_remessa',
                    'order_id': order.id,
                    'cliente_id': order.cliente_id,
                    'cliente_nome': client_name,
                    'item': {
                        'id': it.id,
                        'produto_id': it.produto_id,
                        'name': it.nome,
                        'quantity': it.quantidade,
                        'price': float(it.preco or 0),
                        'observation': it.observacao,
                        'categoria': categoria,
                        'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    }
                }
                schedule_coroutine(publish(event))
        except Exception:
            pass

        # return fresh order state
        db.refresh(order)
        # reuse existing get_order logic by building the response dict
        # fetch remessas for response (not used for item status control)
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []
        d = {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'usuario_id': order.usuario_id,
            # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
            'tipo': None,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': effective_valor_total(order.subtotal, order.valor_total, order.adicional_10),
            'pagar_depois': int(order.pagar_depois or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                    'observation': it.observacao,
                    'categoria': resolve_categoria_for_item(it, db),
                    'category': resolve_categoria_for_item(it, db),
                }
                for it in (getattr(order, 'items', []) or [])
            ],
            'criado_em': to_brasilia(order.criado_em),
            'atualizado_em': getattr(order, 'atualizado_em', None),
        }
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            d['remessas'] = [
                {
                    'id': rr.id,
                    'pedido_id': getattr(rr, 'pedido_id', None),
                    'observacao': getattr(rr, 'observacao_remessa', None),
                    'endereco': getattr(rr, 'endereco', None),
                    'tipo': getattr(rr, 'tipo', 'local'),
                    'status': getattr(rr, 'status', 'pendente'),
                    'criado_em': to_brasilia(rr.criado_em),
                }
                for rr in rems
            ]
        except Exception:
            d['remessas'] = []
        try:
            pratos = db.query(PratoModel).filter(PratoModel.pedido_id == order.id).order_by(PratoModel.id.asc()).all()
            d['pratos'] = [
                {
                    'id': p.id,
                    'pedido_id': p.pedido_id,
                    'remessa_id': p.remessa_id,
                    'observacao': p.observacao,
                    'criado_em': to_brasilia(p.criado_em),
                }
                for p in pratos
            ]
        except Exception:
            d['pratos'] = []
        # include per-categoria statuses (optional)
        try:
            cat_rows = db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == order.id).all()
            d['category_status'] = {cr.categoria: cr.status for cr in cat_rows}
        except Exception:
            d['category_status'] = {}

        # Notifica clientes WebSocket sobre nova remessa
        schedule_coroutine(notify_orders_update())
        return d
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception('Failed to create remessa for order: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{order_id}/remessas/{remessa_id}", response_model=PedidoRead)
def update_remessa_for_order(order_id: int, remessa_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update an existing remessa for a pedido (status/observacao/endereco) without creating a new one.

    Expected payload: { status?: str, observacao?: str, endereco?: str }
    - Validates the remessa belongs to the given pedido.
    - Applies status normalization via map_incoming_status.
    - Does NOT alter item remessa associations; items remain in the same remessa.
    - Returns the fresh order state including items and remessas.
    """
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

        remessa = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.id == remessa_id).first()
        if not remessa or int(getattr(remessa, 'pedido_id', 0)) != int(order.id):
            raise HTTPException(status_code=404, detail='Remessa not found for this pedido')

        # Update fields from payload
        if 'status' in payload or 'status_remessa' in payload:
            try:
                incoming = payload.get('status') or payload.get('status_remessa')
                remessa.status = map_incoming_status(incoming)
            except Exception:
                # keep current status if normalization fails
                pass
        if 'observacao' in payload or 'remessa_observacao' in payload:
            remessa.observacao_remessa = payload.get('observacao') or payload.get('remessa_observacao')
        if 'endereco' in payload or 'deliveryAddress' in payload:
            remessa.endereco = payload.get('endereco') or payload.get('deliveryAddress')

        db.add(remessa)
        db.commit()
        db.refresh(remessa)

        # If status provided, propagate to items in this remessa so pedido.status reflects reality
        try:
            if 'status' in payload or 'status_remessa' in payload:
                incoming = payload.get('status') or payload.get('status_remessa')
                item_status = map_incoming_status(incoming)
                from app.models.pedido_item import PedidoItem as PI
                items_in_remessa = db.query(PI).filter(PI.pedido_id == order.id, PI.remessa_id == remessa.id).all()
                for it in items_in_remessa:
                    it.status = item_status
                    db.add(it)
                db.commit()
        except Exception:
            pass
        db.refresh(order)

        # Per-categoria statuses depend on item.status only; recompute for consistency
        try:
            compute_and_persist_category_statuses(db, order.id)
        except Exception:
            pass

        # Recompute pedido.status from item statuses (may have changed above)
        try:
            recompute_order_status_from_items(db, order)
        except Exception:
            pass

        # Publish event so kitchen/frontends update remessa state
        try:
            event = {
                'type': 'remessa',
                'action': 'updated',
                'order_id': order.id,
                'remessa': {
                    'id': remessa.id,
                    'pedido_id': getattr(remessa, 'pedido_id', None),
                    'status': getattr(remessa, 'status', None),
                    'observacao': getattr(remessa, 'observacao_remessa', None),
                    'endereco': getattr(remessa, 'endereco', None),
                }
            }
            # PATCH: notifica via WebSocket orders_ws
            schedule_coroutine(notify_orders_update())
            # Mantém publish para outros listeners
            schedule_coroutine(publish(event))
        except Exception:
            pass

        # Build response with fresh order state (items + remessas)
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        d = {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'usuario_id': order.usuario_id,
            # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
            'tipo': None,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': effective_valor_total(order.subtotal, order.valor_total, order.adicional_10),
            'pagar_depois': int(order.pagar_depois or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                    'observation': it.observacao,
                    'categoria': resolve_categoria_for_item(it, db),
                    'category': resolve_categoria_for_item(it, db),
                }
                for it in (getattr(order, 'items', []) or [])
            ],
            'criado_em': to_brasilia(order.criado_em),
            'atualizado_em': getattr(order, 'atualizado_em', None),
        }
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            d['remessas'] = [
                {
                    'id': rr.id,
                    'pedido_id': getattr(rr, 'pedido_id', None),
                    'observacao': getattr(rr, 'observacao_remessa', None),
                    'endereco': getattr(rr, 'endereco', None),
                    'tipo': getattr(rr, 'tipo', 'local'),
                    'status': getattr(rr, 'status', 'pendente'),
                    'criado_em': to_brasilia(rr.criado_em),
                }
                for rr in rems
            ]
        except Exception:
            d['remessas'] = []
        try:
            pratos = db.query(PratoModel).filter(PratoModel.pedido_id == order.id).order_by(PratoModel.id.asc()).all()
            d['pratos'] = [
                {
                    'id': p.id,
                    'pedido_id': p.pedido_id,
                    'remessa_id': p.remessa_id,
                    'observacao': p.observacao,
                    'criado_em': to_brasilia(p.criado_em),
                }
                for p in pratos
            ]
        except Exception:
            d['pratos'] = []
        # include per-categoria statuses (optional)
        try:
            cat_rows = db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == order.id).all()
            d['category_status'] = {cr.categoria: cr.status for cr in cat_rows}
        except Exception:
            d['category_status'] = {}

        return d
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception('Failed to update remessa for order: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{order_id}/items", response_model=PedidoRead)
def add_items_to_order(order_id: int, payload: dict, db: Session = Depends(get_db)):
    """Append items to an existing pedido (used by frontend 'Adicionar' action).

    Expected payload: { items: [ { id, name, quantity, price, observation }, ... ] }
    """
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

        # Block financial mutations for finalized orders
        if is_finalized_status(getattr(order, 'status', None)):
            raise HTTPException(status_code=409, detail='Pedido já finalizado; itens não podem ser alterados')

        items_payload = payload.get('items', []) or []
        added = []
        for it in items_payload:
            name = it.get('name') or it.get('nome') or ''
            qty = float(it.get('quantity') or it.get('qty') or 1)
            # Sempre salva o preço atual do produto no item
            prod_id = it.get('id')
            remessa_id = it.get('remessa_id')
            obs = it.get('observation') or it.get('observacao')
            from app.models.pedido_item import PedidoItem as PI
            price = resolve_current_price_for_item({'id': prod_id}, db)
            item_model = PI(produto_id=prod_id, nome=name, quantidade=qty, preco=price, observacao=obs, status='pendente', remessa_id=remessa_id)
            order.items.append(item_model)
            added.append(item_model)

        # recompute subtotal/valor_total considerando todos os itens do pedido
        subtotal = sum(float(item.preco) * float(item.quantidade) for item in order.items)
        order.subtotal = subtotal
        # respect adicional_10 flag when computing valor_total
        try:
            if getattr(order, 'adicional_10', 0):
                order.valor_total = round(subtotal * 1.1, 2)
            else:
                order.valor_total = round(subtotal, 2)
        except Exception:
            order.valor_total = subtotal

        db.add(order)
        db.commit()
        db.refresh(order)

        # itens novos pendentes podem alterar o status geral do pedido
        try:
            recompute_order_status_from_items(db, order)
        except Exception:
            pass

        # publish added items to kitchen
        try:
            # compute client name once (relation may not be loaded)
            client_name = None
            try:
                if getattr(order, 'cliente', None) and getattr(order.cliente, 'nome', None):
                    client_name = getattr(order.cliente, 'nome')
                elif getattr(order, 'cliente_id', None):
                    c = db.query(ClienteModel).filter(ClienteModel.id == order.cliente_id).first()
                    if c:
                        client_name = getattr(c, 'nome', None)
            except Exception:
                client_name = None

            for a in added:
                categoria = resolve_categoria_for_item(a, db)
                event = {
                    'type': 'order_item',
                    'action': 'added',
                    'order_id': order.id,
                    'cliente_id': order.cliente_id,
                    'cliente_nome': client_name,
                    'item': {
                        'id': a.id,
                        'produto_id': a.produto_id,
                        'name': a.nome,
                        'quantity': a.quantidade,
                        'price': float(a.preco or 0),
                        'observation': a.observacao,
                        'categoria': categoria,
                    }
                }
                schedule_coroutine(publish(event))
        except Exception:
            pass

        # build response
        # fetch remessas for this order so we can include remessa_status per item
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # include remessa status per item in the response
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # include remessa status per item
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # include remessa status per item in response
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # include remessa status per item in the response
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # include remessa status per item for this order
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # include remessa status map for items in this response
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # fetch remessas for this order so items can include remessa_status
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # fetch remessas for this order so items can include remessa_status
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # recompute per-categoria statuses and persist (new items may change category readiness)
        try:
            compute_and_persist_category_statuses(db, order.id)
        except Exception:
            pass

        return {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'usuario_id': order.usuario_id,
            # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
            'tipo': None,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': effective_valor_total(order.subtotal, order.valor_total, order.adicional_10),
            'pagar_depois': int(order.pagar_depois or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                        'observation': it.observacao,
                    'categoria': resolve_categoria_for_item(it, db),
                    'category': resolve_categoria_for_item(it, db),
                }
                for it in (getattr(order, 'items', []) or [])
            ],
            'criado_em': to_brasilia(order.criado_em),
            'atualizado_em': getattr(order, 'atualizado_em', None),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception('Failed to add items to order: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    try:
        order = db.query(PedidoModel).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')
        # delete related remessas, items and per-categoria statuses before deleting the pedido
        try:
            # pratos referenciam remessas via FK; apagar antes de apagar as remessas
            db.query(PratoModel).filter(PratoModel.pedido_id == order.id).delete()
        except Exception:
            pass

        try:
            db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).delete()
        except Exception:
            pass

        try:
            db.query(PedidoItem).filter(PedidoItem.pedido_id == order.id).delete()
        except Exception:
            pass

        try:
            db.query(PedidoCategoriaStatusModel).filter(PedidoCategoriaStatusModel.pedido_id == order.id).delete()
        except Exception:
            pass

        # capture order id and delete
        db.delete(order)
        db.commit()

        # notify kitchen to remove order/items
        try:
            event = {'type': 'order', 'action': 'deleted', 'order_id': order_id}
            schedule_coroutine(publish(event))
        except Exception:
            pass

        return {"detail": "Pedido deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception('Failed to delete order: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{order_id}/items/{item_id}", response_model=PedidoRead)
def delete_order_item(order_id: int, item_id: int, db: Session = Depends(get_db)):
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

        # Guard: finalized orders cannot be changed
        if is_finalized_status(getattr(order, 'status', None)):
            raise HTTPException(status_code=409, detail='Pedido já finalizado; itens não podem ser alterados')

        # find item
        item = None
        for it in (getattr(order, 'items', []) or []):
            if it.id == item_id:
                item = it
                break
        if not item:
            raise HTTPException(status_code=404, detail='Item not found')

        # prepare remessa status map for this order so responses can include remessa_status
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # subtract from totals
        try:
            order.subtotal = float(order.subtotal or 0) - float(item.preco or 0) * float(item.quantidade or 1)
            # respect adicional_10 flag when computing valor_total
            if getattr(order, 'adicional_10', 0):
                order.valor_total = round(float(order.subtotal or 0) * 1.1, 2)
            else:
                order.valor_total = round(float(order.subtotal or 0), 2)
        except Exception:
            pass

        # capture item info before deletion
        item_payload = {
            'id': item.id,
            'remessa_id': getattr(item, 'remessa_id', None),
            'prato_id': getattr(item, 'prato_id', None),
            'produto_id': item.produto_id,
            'name': item.nome,
            'quantity': item.quantidade,
            'price': float(item.preco or 0),
            'observation': item.observacao,
        }

        db.delete(item)
        db.add(order)
        db.commit()
        db.refresh(order)

        # remover item pode promover o status do pedido (ex.: restam apenas itens prontos)
        try:
            recompute_order_status_from_items(db, order)
        except Exception:
            pass

        # publish deletion event for this item
        try:
            categoria = resolve_categoria_for_item(item_payload, db)
            event = {
                'type': 'order_item',
                'action': 'deleted',
                'order_id': order.id,
                'item': {**item_payload, 'categoria': categoria}
            }
            schedule_coroutine(publish(event))
        except Exception:
            pass

        # recompute per-categoria statuses and persist (item removal may change readiness)
        try:
            compute_and_persist_category_statuses(db, order.id)
        except Exception:
            pass

        return {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'cliente_nome': getattr(order.cliente, 'nome', None) if getattr(order, 'cliente', None) else None,
            'usuario_id': order.usuario_id,
            # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
            'tipo': None,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': effective_valor_total(order.subtotal, order.valor_total, order.adicional_10),
            'pagar_depois': int(order.pagar_depois or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                        'observation': it.observacao,
                    'categoria': resolve_categoria_for_item(it, db),
                    'category': resolve_categoria_for_item(it, db),
                }
                for it in (getattr(order, 'items', []) or [])
            ],
            'criado_em': to_brasilia(order.criado_em),
            'atualizado_em': getattr(order, 'atualizado_em', None),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception('Failed to delete order item: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{order_id}/items/{item_id}", response_model=PedidoRead)
def update_order_item_quantity(order_id: int, item_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update quantity, price, or price factor of an order item and recompute totals.

    Expected payload:
        - { quantity: int }
        - { price?: float }
    """
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

        # Guard: finalized orders cannot be changed
        if is_finalized_status(getattr(order, 'status', None)):
            raise HTTPException(status_code=409, detail='Pedido já finalizado; itens não podem ser alterados')

        item = None
        for it in (getattr(order, 'items', []) or []):
            if it.id == item_id:
                item = it
                break
        if not item:
            raise HTTPException(status_code=404, detail='Item not found')

        # apply updates
        if 'quantity' in payload:
            try:
                item.quantidade = float(payload['quantity'])
            except Exception:
                pass
        if 'price' in payload:
            try:
                item.preco = float(payload['price'])
            except Exception:
                pass
        if 'status' in payload:
            try:
                novo_status = str(payload['status'])
                # Só permite marcar como entregue se já estiver pronto
                if novo_status == 'entregue' and item.status != 'pronto':
                    # HTTP 409 = Conflict, para frontend exibir toast customizado
                    raise HTTPException(status_code=409, detail='ITEM_NOT_READY')
                item.status = novo_status
                # Se o novo status for 'entregue', verificar se todos os itens da remessa estão entregues
                if item.status == 'entregue' and item.remessa_id:
                    from app.models.pedido_item import PedidoItem as PI
                    from app.models.pedido_remessa import PedidoRemessa as PR
                    remessa_id = item.remessa_id
                    # Busca todos os itens da remessa
                    itens_remessa = db.query(PI).filter(PI.remessa_id == remessa_id).all()
                    if itens_remessa and all(it.status == 'entregue' for it in itens_remessa):
                        remessa = db.query(PR).filter(PR.id == remessa_id).first()
                        if remessa and remessa.status != 'entregue':
                            remessa.status = 'entregue'
                            db.add(remessa)
                            db.commit()
                            db.refresh(remessa)
            except HTTPException:
                raise
            except Exception:
                pass
        # support explicit price factor (e.g., meia pizza)

        # commit e refresh para garantir que order.items está atualizado
        db.add(order)
        db.commit()
        db.refresh(order)
        # recompute subtotal and valor_total from all items (still mutable)
        subtotal = 0.0
        for it in (getattr(order, 'items', []) or []):
            try:
                subtotal += float(it.preco or 0) * float(it.quantidade or 1)
            except Exception:
                pass
        order.subtotal = subtotal
        # respect adicional_10 flag when computing valor_total
        try:
            if getattr(order, 'adicional_10', 0):
                order.valor_total = round(subtotal * 1.1, 2)
            else:
                order.valor_total = round(subtotal, 2)
        except Exception:
            order.valor_total = subtotal

        db.add(order)
        db.commit()
        db.refresh(order)

        # quantidade/preço não muda preparo, mas manter status coerente caso frontend altere estados em outros fluxos
        try:
            recompute_order_status_from_items(db, order)
        except Exception:
            pass

        # publish updated item event
        try:
            categoria = resolve_categoria_for_item(item, db)
            prod_id = getattr(item, 'produto_id', None)
            event = {
                'type': 'order_item',
                'action': 'updated',
                'order_id': order.id,
                'item': {
                    'id': item.id,
                    'produto_id': prod_id,
                    'name': item.nome,
                    'quantity': item.quantidade,
                    'price': float(item.preco or 0),
                    'observation': item.observacao,
                    'categoria': categoria,
                }
            }
            schedule_coroutine(publish(event))
        except Exception:
            pass

        return {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'cliente_nome': getattr(order.cliente, 'nome', None) if getattr(order, 'cliente', None) else None,
            'usuario_id': order.usuario_id,
            # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
            'tipo': None,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': effective_valor_total(order.subtotal, order.valor_total, order.adicional_10),
            'pagar_depois': int(order.pagar_depois or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                        'observation': it.observacao,
                    'categoria': resolve_categoria_for_item(it, db),
                    'category': resolve_categoria_for_item(it, db),
                }
                for it in (getattr(order, 'items', []) or [])
            ],
            'criado_em': to_brasilia(order.criado_em),
            'atualizado_em': getattr(order, 'atualizado_em', None),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception('Failed to update order item: %s', e)
        raise HTTPException(status_code=500, detail=str(e))



@router.patch("/{order_id}", response_model=PedidoRead)
def update_order(order_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Update top-level order fields such as status.

    Expected payload example: { "status": "preparando" }
    """
    try:
        print(f"[DEBUG BACKEND] PATCH /orders/{order_id} recebido com payload: {payload}")
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')
        
        print(f"[DEBUG BACKEND] Order carregado do DB: pagar_depois={order.pagar_depois}")

        updated = False
        # allow updating status
        if 'status' in payload and payload['status'] is not None:
            try:
                # Special-case payment status: accept explicit 'paid'/'pago' and
                # set internal status to 'paid' so UIs render as Pago.
                st_raw = str(payload['status']).lower()
                if st_raw.strip() in ('paid', 'pago') or (' pago' in st_raw) or st_raw.endswith(' pago'):
                    mapped = 'pago'
                else:
                    # map incoming status and ensure a safe default
                    mapped = map_incoming_status(payload['status'])
                    if not mapped:
                        mapped = 'pendente'
                # debug log
                try:
                    import logging as _logging
                    _logging.debug(f"[orders.update] incoming status={payload['status']} mapped={mapped}")
                except Exception:
                    pass
                # If order is already finalized, prevent status changes that might imply financial mutation
                if is_finalized_status(getattr(order, 'status', None)) and mapped != getattr(order, 'status', None):
                    raise HTTPException(status_code=409, detail='Pedido finalizado; status não pode ser alterado')
                order.status = mapped
                updated = True
            except Exception:
                pass

            # allow toggling the 10% adicional flag
            if 'adicional_10' in payload and payload['adicional_10'] is not None:
                try:
                    # normalize to 0/1
                    val = int(bool(payload['adicional_10']))
                    # If finalized, do not allow changing adicional_10 (freezes totals)
                    if is_finalized_status(getattr(order, 'status', None)):
                        raise HTTPException(status_code=409, detail='Pedido finalizado; adicional_10 não pode ser alterado')
                    order.adicional_10 = val
                    # recompute valor_total accordingly
                    subtotal = float(order.subtotal or 0)
                    if val:
                        order.valor_total = round(subtotal * 1.1, 2)
                    else:
                        order.valor_total = round(subtotal, 2)
                    updated = True
                except Exception:
                    pass

        # Also allow toggling the 10% adicional flag even when 'status' is not provided
        # This ensures clients can PATCH only adicional_10 and have it persisted.
        if 'adicional_10' in payload and payload['adicional_10'] is not None:
            try:
                val = int(bool(payload['adicional_10']))
                if is_finalized_status(getattr(order, 'status', None)):
                    raise HTTPException(status_code=409, detail='Pedido finalizado; adicional_10 não pode ser alterado')
                order.adicional_10 = val
                subtotal = float(order.subtotal or 0)
                if val:
                    order.valor_total = round(subtotal * 1.1, 2)
                else:
                    order.valor_total = round(subtotal, 2)
                updated = True
            except Exception:
                pass

        # Allow toggling the pagar_depois flag
        print(f"[DEBUG BACKEND] Verificando se 'pagar_depois' está no payload...")
        print(f"[DEBUG BACKEND] Payload recebido: {payload}")
        print(f"[DEBUG BACKEND] 'pagar_depois' in payload: {'pagar_depois' in payload}")
        if 'pagar_depois' in payload:
            print(f"[DEBUG BACKEND] payload['pagar_depois'] = {payload['pagar_depois']}")
        
        if 'pagar_depois' in payload and payload['pagar_depois'] is not None:
            try:
                # Converte para inteiro: 0 ou 1
                incoming_val = payload['pagar_depois']
                # Se for string, converte
                if isinstance(incoming_val, str):
                    val = int(incoming_val)
                else:
                    val = int(bool(incoming_val))
                print(f"[DEBUG BACKEND] Atualizando pagar_depois para {val} para order {order.id}")
                order.pagar_depois = val
                updated = True
            except Exception as e:
                print(f"[DEBUG BACKEND] Erro ao atualizar pagar_depois: {e}")
                pass

        # If the incoming status transitions the order to a finalized state, compute and freeze totals now.
        try:
            incoming_status = payload.get('status')
            if incoming_status is not None and is_finalized_status(map_incoming_status(incoming_status)):
                # recompute from items to ensure a consistent frozen value
                subtotal = 0.0
                for it in (getattr(order, 'items', []) or []):
                    try:
                        subtotal += float(getattr(it, 'preco', 0) or 0) * float(getattr(it, 'quantidade', 1) or 1)
                    except Exception:
                        pass
                order.subtotal = round(subtotal, 2)
                # Accept adicional_10 from payload when freezing totals at finalization
                if 'adicional_10' in payload and payload['adicional_10'] is not None:
                    try:
                        order.adicional_10 = int(bool(payload['adicional_10']))
                    except Exception:
                        pass
                if getattr(order, 'adicional_10', 0):
                    order.valor_total = round(subtotal * 1.1, 2)
                else:
                    order.valor_total = round(subtotal, 2)
                updated = True
        except Exception:
            pass

        # other top-level updates (e.g., observacao) can be added here if needed
        if not updated:
            # nothing to change
            db.refresh(order)
            # return current state
            pass

        db.add(order)
        db.commit()
        print(f"[DEBUG BACKEND] Após commit: order.pagar_depois = {order.pagar_depois}")
        
        # Verificar direto no banco se foi salvo
        try:
            from sqlalchemy import text
            result = db.execute(text("SELECT pagar_depois FROM pedidos WHERE id = :id"), {"id": order.id}).fetchone()
            print(f"[DEBUG BACKEND] SELECT direto do DB após commit: pagar_depois = {result[0] if result else 'NOT FOUND'}")
        except Exception as e:
            print(f"[DEBUG BACKEND] Erro ao fazer SELECT: {e}")
        
        # log status after commit to verify persistence
        try:
            import logging as _logging
            _logging.debug(f"[orders.update] after commit before refresh status={getattr(order, 'status', None)!r}")
        except Exception:
            pass
        db.refresh(order)
        print(f"[DEBUG BACKEND] Após refresh: order.pagar_depois = {order.pagar_depois}")
        try:
            import logging as _logging
            _logging.debug(f"[orders.update] after refresh status={getattr(order, 'status', None)!r}")
        except Exception:
            pass
        # double-check database raw value in case SQLAlchemy/refresh differs
        try:
            row = db.execute(text("SELECT status FROM pedidos WHERE id = :id"), {"id": order.id}).fetchone()
            try:
                import logging as _logging
                _logging.debug(f"[orders.update] raw DB status select for id={order.id}: {row[0] if row else None!r}")
            except Exception:
                pass
        except Exception:
            pass

    # publish order-level update so other UIs/kitchen can react
        try:
            client_name = None
            try:
                if getattr(order, 'cliente', None) and getattr(order.cliente, 'nome', None):
                    client_name = getattr(order.cliente, 'nome')
                elif getattr(order, 'cliente_id', None):
                    c = db.query(ClienteModel).filter(ClienteModel.id == order.cliente_id).first()
                    if c:
                        client_name = getattr(c, 'nome', None)
            except Exception:
                client_name = None

            event = {
                'type': 'order',
                'action': 'updated',
                'order_id': order.id,
                'status': order.status,
                'cliente_id': order.cliente_id,
                'cliente_nome': client_name,
            }
            schedule_coroutine(publish(event))
        except Exception:
            pass

        # fetch remessas for this order so we can include remessa_status per item
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
        except Exception:
            rems = []

        # Notifica clientes WebSocket sobre atualização de pedido
        schedule_coroutine(notify_orders_update())
        return {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'cliente_nome': getattr(order.cliente, 'nome', None) if getattr(order, 'cliente', None) else None,
            'usuario_id': order.usuario_id,
            # Deprecated: stop returning pedidos.tipo; use remessas[].tipo
            'tipo': None,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': effective_valor_total(order.subtotal, order.valor_total, order.adicional_10),
            'pagar_depois': int(order.pagar_depois or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'prato_id': getattr(it, 'prato_id', None),
                    'status': getattr(it, 'status', None),
                    'produto_id': it.produto_id,
                    'name': it.nome,
                    'quantity': it.quantidade,
                    'price': float(it.preco),
                    'observation': it.observacao,
                    'categoria': resolve_categoria_for_item(it, db),
                    'category': resolve_categoria_for_item(it, db),
                }
                for it in (getattr(order, 'items', []) or [])
            ],
            'criado_em': to_brasilia(order.criado_em),
            'atualizado_em': getattr(order, 'atualizado_em', None),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception('Failed to update order: %s', e)
        raise HTTPException(status_code=500, detail=str(e))
