from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, text
import json
from typing import List
import traceback
import logging

from app.db.session import SessionLocal
from app.utils.pubsub import publish
from app.models.product import Produto as ProdutoModel
from app.models.client import Cliente as ClienteModel
import asyncio
from app.models.pedido import Pedido as PedidoModel
from app.models.pedido_item import PedidoItem
from app.schemas.pedido import PedidoCreate, PedidoRead
from app.models.pedido_remessa import PedidoRemessa as PedidoRemessaModel
from datetime import timezone
from app.core.timezone_utils import local_day_range_to_utc, BRAZIL_TZ

router = APIRouter(prefix="/orders", tags=["Orders"])

# module-level default for remessa status map (per-request handlers will overwrite when available)
remessa_status_map = {}


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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        return 'paid'
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


@router.post("/", response_model=PedidoRead)
async def create_order(payload: PedidoCreate, db: Session = Depends(get_db)):
    try:
        # map incoming payload to existing pedidos table columns
        tipo = 'delivery' if getattr(payload, 'delivery', False) else 'local'
        subtotal = float(getattr(payload, 'total', 0) or 0)
        adicional_10 = 0
        valor_total = subtotal
        # Do not store delivery address on the top-level pedido.observacao.
        # Per-remessa address should be stored in pedido_remessas.endereco below.
        observacao = None

        p = PedidoModel(
            cliente_id=payload.cliente_id,
            usuario_id=None,
            tipo=tipo,
            status=map_incoming_status(getattr(payload, 'status', None)),
            subtotal=subtotal,
            adicional_10=adicional_10,
            valor_total=valor_total,
            observacao=observacao,
        )

        # attach items as PedidoItem objects (normalized table)
        items_payload = getattr(payload, 'items', []) or []
        for it in items_payload:
            # handle both pydantic objects and plain dicts
            name = getattr(it, 'name', None) or (it.get('name') if isinstance(it, dict) else None) or (it.get('nome') if isinstance(it, dict) else None)
            qty = int(getattr(it, 'quantity', None) or (it.get('quantity') if isinstance(it, dict) else None) or (it.get('qty') if isinstance(it, dict) else 1) or 1)
            price = float(getattr(it, 'price', None) or (it.get('price') if isinstance(it, dict) else None) or (it.get('preco') if isinstance(it, dict) else 0) or 0)
            obs = getattr(it, 'observation', None) or (it.get('observation') if isinstance(it, dict) else None) or (it.get('observacao') if isinstance(it, dict) else None)
            prod_id = getattr(it, 'id', None) or (it.get('id') if isinstance(it, dict) else None)
            item_model = PedidoItem(produto_id=prod_id, nome=name or '', quantidade=qty, preco=price, observacao=obs)
            p.items.append(item_model)

        db.add(p)
        db.commit()
        db.refresh(p)

        # if the client provided a per-remessa observation or a delivery address,
        # persist it to pedido_remessas (per-remessa rows can hold endereco and observacao)
        try:
            rem_obs = getattr(payload, 'remessa_observacao', None)
            delivery_addr = getattr(payload, 'deliveryAddress', None)
            if rem_obs or delivery_addr:
                # model uses observacao_remessa column; map incoming remessa_observacao to that column
                pr = PedidoRemessaModel(pedido_id=p.id, observacao_remessa=rem_obs, endereco=delivery_addr)
                db.add(pr)
                db.commit()
                db.refresh(pr)
        except Exception:
            # non-fatal: don't block order creation if remessa persistence fails
            db.rollback()

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
                try:
                    asyncio.create_task(publish(event))
                except RuntimeError:
                    # fallback: run publish in event loop if possible
                    loop = asyncio.get_event_loop()
                    loop.create_task(publish(event))
        except Exception:
            # best-effort; don't block order creation on pubsub failures
            pass

        # attach any remessas for this pedido to the response
        remessas_list = []
        try:
            rem_rows = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == p.id).order_by(PedidoRemessaModel.id.asc()).all()
            # build remessas list and a quick lookup map of remessa status by id
            remessa_status_map = {}
            for rr in rem_rows:
                remessas_list.append({'id': rr.id, 'pedido_id': getattr(rr, 'pedido_id', None), 'observacao': getattr(rr, 'observacao_remessa', None), 'endereco': getattr(rr, 'endereco', None), 'status': getattr(rr, 'status', 'pendente'), 'criado_em': to_brasilia(rr.criado_em)})
                remessa_status_map[rr.id] = getattr(rr, 'status', 'pendente')
        except Exception:
            remessas_list = []
            remessa_status_map = {}

        data = {
            'id': p.id,
            'cliente_id': p.cliente_id,
            'usuario_id': p.usuario_id,
            'tipo': p.tipo,
            'status': p.status,
            'subtotal': float(p.subtotal or 0),
            'adicional_10': int(p.adicional_10 or 0),
            'valor_total': float(p.valor_total or 0),
            'observacao': p.observacao,
            'criado_em': to_brasilia(p.criado_em),
            'atualizado_em': getattr(p, 'atualizado_em', None),
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'remessa_status': remessa_status_map.get(getattr(it, 'remessa_id', None), None),
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
        }
        return data
    except Exception as e:
        db.rollback()
        tb = traceback.format_exc()
        logging.exception("Failed to create order: %s", e)
        # return full traceback in detail for easier debugging (can be removed later)
        raise HTTPException(status_code=500, detail=tb)


@router.get("/", response_model=List[PedidoRead])
def list_orders(db: Session = Depends(get_db), date_from: str = None, date_to: str = None):
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

        rows = query.order_by(PedidoModel.id.desc()).all()
        out = []
        for r in rows:
            # fetch remessas early so we can annotate each item with its remessa status
            try:
                rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == r.id).order_by(PedidoRemessaModel.id.asc()).all()
                remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
            except Exception:
                remessa_status_map = {}

                d = {
                'id': r.id,
                'cliente_id': r.cliente_id,
                'cliente_nome': getattr(r.cliente, 'nome', None) if getattr(r, 'cliente', None) else None,
                'usuario_id': r.usuario_id,
                'tipo': r.tipo,
                'status': r.status,
                'subtotal': float(r.subtotal or 0),
                'adicional_10': int(r.adicional_10 or 0),
                'valor_total': float(r.valor_total or 0),
                'observacao': r.observacao,
                'items': [
                    {
                        'id': it.id,
                        'remessa_id': getattr(it, 'remessa_id', None),
                        'remessa_status': remessa_status_map.get(getattr(it, 'remessa_id', None), None),
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
            # include remessas for each pedido (if any)
            # remessas already fetched above in order to compute remessa_status_map; reuse if present
            try:
                if 'rems' in locals():
                    rems_list = rems
                else:
                    rems_list = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == r.id).order_by(PedidoRemessaModel.id.asc()).all()
                d['remessas'] = [
                    {
                        'id': rr.id,
                        'pedido_id': getattr(rr, 'pedido_id', None),
                        'observacao': getattr(rr, 'observacao_remessa', None),
                        'endereco': getattr(rr, 'endereco', None),
                        'status': getattr(rr, 'status', 'pendente'),
                        'criado_em': to_brasilia(r.criado_em),
                    }
                    for rr in rems_list
                ]
            except Exception:
                d['remessas'] = []
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
        # fetch remessas early so items can include remessa_status
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == r.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        d = {
            'id': r.id,
            'cliente_id': r.cliente_id,
            'cliente_nome': getattr(r.cliente, 'nome', None) if getattr(r, 'cliente', None) else None,
            'usuario_id': r.usuario_id,
            'tipo': r.tipo,
            'status': r.status,
            'subtotal': float(r.subtotal or 0),
            'adicional_10': int(r.adicional_10 or 0),
            'valor_total': float(r.valor_total or 0),
            'observacao': r.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'remessa_status': remessa_status_map.get(getattr(it, 'remessa_id', None), None),
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
                    'status': getattr(rr, 'status', 'pendente'),
                    'criado_em': to_brasilia(rr.criado_em),
                }
                for rr in rems
            ]
        except Exception:
            d['remessas'] = []
        return d
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{order_id}/remessas", response_model=PedidoRead)
async def create_remessa_for_order(order_id: int, payload: dict, db: Session = Depends(get_db)):
    """Create a per-pedido remessa and optionally associate existing items to it.

    Expected payload: { item_ids: [1,2,3], observacao?: str, endereco?: str }
    This will create a PedidoRemessa row linked to the pedido and set
    pedido_items.remessa_id for the provided item ids (only if they belong to the pedido).
    """
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

        # default remessa status map; will be populated later if possible
        remessa_status_map = {}

        # prepare remessa status map for items (used in response). Best-effort.
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        item_ids = payload.get('item_ids', []) or []
        observacao = payload.get('observacao') or payload.get('remessa_observacao')
        endereco = payload.get('endereco') or payload.get('deliveryAddress')

        # determine requested status (allow frontend to request 'pronto')
        requested_status = payload.get('status') or payload.get('status_remessa') or 'pendente'
        pr = PedidoRemessaModel(pedido_id=order.id, observacao_remessa=observacao, endereco=endereco, status=requested_status)
        db.add(pr)
        db.commit()
        db.refresh(pr)

        moved_items = []
        if item_ids:
            # only update items that belong to this order
            items_to_move = db.query(PedidoItem).filter(PedidoItem.pedido_id == order.id).filter(PedidoItem.id.in_(item_ids)).all()
            for it in items_to_move:
                it.remessa_id = pr.id
                db.add(it)
                moved_items.append(it)
            db.commit()

        # after moving items into the new remessa, recompute order-level status
        # If there are no remaining "active" items (i.e., every item belongs to a remessa
        # whose status is 'pronto'), mark the pedido as 'pronto'. This keeps the
        # overall pedido.status in sync with fully-ready remessas while allowing
        # partial remessas to leave the pedido as 'pendente'.
        try:
            still_active = False
            all_items = db.query(PedidoItem).filter(PedidoItem.pedido_id == order.id).all()
            for ait in all_items:
                # item without remessa -> still active
                if not getattr(ait, 'remessa_id', None):
                    still_active = True
                    break
                # item in a remessa; check remessa status
                rr = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.id == ait.remessa_id).first()
                if not rr or getattr(rr, 'status', 'pendente') != 'pronto':
                    still_active = True
                    break

            if not still_active:
                try:
                    order.status = 'pronto'
                    db.add(order)
                    db.commit()
                    db.refresh(order)
                    # publish an order-level updated event
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
                        try:
                            asyncio.create_task(publish(event))
                        except RuntimeError:
                            loop = asyncio.get_event_loop()
                            loop.create_task(publish(event))
                    except Exception:
                        pass
                except Exception:
                    db.rollback()
        except Exception:
            # non-fatal; don't block remessa creation on status recompute failures
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
                    }
                }
                try:
                    asyncio.create_task(publish(event))
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                    loop.create_task(publish(event))
        except Exception:
            pass

        # return fresh order state
        db.refresh(order)
        # reuse existing get_order logic by building the response dict
        # fetch remessas early to annotate items with remessa status
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}
        d = {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'usuario_id': order.usuario_id,
            'tipo': order.tipo,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': float(order.valor_total or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'remessa_status': remessa_status_map.get(getattr(it, 'remessa_id', None), None),
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
                    'status': getattr(rr, 'status', 'pendente'),
                    'criado_em': to_brasilia(rr.criado_em),
                }
                for rr in rems
            ]
        except Exception:
            d['remessas'] = []

        return d
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception('Failed to create remessa for order: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{order_id}/items", response_model=PedidoRead)
async def add_items_to_order(order_id: int, payload: dict, db: Session = Depends(get_db)):
    """Append items to an existing pedido (used by frontend 'Adicionar' action).

    Expected payload: { items: [ { id, name, quantity, price, observation }, ... ] }
    """
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

        items_payload = payload.get('items', []) or []
        added = []
        for it in items_payload:
            name = it.get('name') or it.get('nome') or ''
            qty = int(it.get('quantity') or it.get('qty') or 1)
            price = float(it.get('price') or it.get('preco') or 0)
            obs = it.get('observation') or it.get('observacao')
            prod_id = it.get('id')
            from app.models.pedido_item import PedidoItem as PI
            item_model = PI(produto_id=prod_id, nome=name, quantidade=qty, preco=price, observacao=obs)
            order.items.append(item_model)
            added.append(item_model)

        # recompute subtotal/valor_total
        subtotal = float(order.subtotal or 0)
        for a in added:
            subtotal += float(a.preco) * int(a.quantidade)
        order.subtotal = subtotal
        order.valor_total = subtotal  # keep same behavior; service not applied here

        db.add(order)
        db.commit()
        db.refresh(order)

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
                try:
                    asyncio.create_task(publish(event))
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                    loop.create_task(publish(event))
        except Exception:
            pass

        # build response
        # fetch remessas for this order so we can include remessa_status per item
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # include remessa status per item in the response
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # include remessa status per item
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # include remessa status per item in response
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # include remessa status per item in the response
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # include remessa status per item for this order
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # include remessa status map for items in this response
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # include remessa status per item in response
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

        return {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'usuario_id': order.usuario_id,
            'tipo': order.tipo,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': float(order.valor_total or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'remessa_status': remessa_status_map.get(getattr(it, 'remessa_id', None), None),
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
async def delete_order(order_id: int, db: Session = Depends(get_db)):
    try:
        order = db.query(PedidoModel).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')
        # capture order id and delete
        db.delete(order)
        db.commit()

        # notify kitchen to remove order/items
        try:
            event = {'type': 'order', 'action': 'deleted', 'order_id': order_id}
            try:
                asyncio.create_task(publish(event))
            except RuntimeError:
                loop = asyncio.get_event_loop()
                loop.create_task(publish(event))
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
async def delete_order_item(order_id: int, item_id: int, db: Session = Depends(get_db)):
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

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
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        # subtract from totals
        try:
            order.subtotal = float(order.subtotal or 0) - float(item.preco or 0) * int(item.quantidade or 1)
            order.valor_total = float(order.subtotal)
        except Exception:
            pass

        # capture item info before deletion
        item_payload = {
            'id': item.id,
            'remessa_id': getattr(item, 'remessa_id', None),
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

        # publish deletion event for this item
        try:
            categoria = resolve_categoria_for_item(item_payload, db)
            event = {
                'type': 'order_item',
                'action': 'deleted',
                'order_id': order.id,
                'item': {**item_payload, 'categoria': categoria}
            }
            try:
                asyncio.create_task(publish(event))
            except RuntimeError:
                loop = asyncio.get_event_loop()
                loop.create_task(publish(event))
        except Exception:
            pass

        return {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'cliente_nome': getattr(order.cliente, 'nome', None) if getattr(order, 'cliente', None) else None,
            'usuario_id': order.usuario_id,
            'tipo': order.tipo,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': float(order.valor_total or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'remessa_status': remessa_status_map.get(getattr(it, 'remessa_id', None), None),
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
async def update_order_item_quantity(order_id: int, item_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update quantity (or price) of an order item and recompute totals.

    Expected payload: { quantity: int, price?: float }
    """
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

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
                item.quantidade = int(payload['quantity'])
            except Exception:
                pass
        if 'price' in payload:
            try:
                item.preco = float(payload['price'])
            except Exception:
                pass

        # recompute subtotal and valor_total from remaining items
        subtotal = 0.0
        for it in (getattr(order, 'items', []) or []):
            try:
                subtotal += float(it.preco or 0) * int(it.quantidade or 1)
            except Exception:
                pass
        order.subtotal = subtotal
        order.valor_total = subtotal

        db.add(order)
        db.commit()
        db.refresh(order)

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
            try:
                asyncio.create_task(publish(event))
            except RuntimeError:
                loop = asyncio.get_event_loop()
                loop.create_task(publish(event))
        except Exception:
            pass

        return {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'cliente_nome': getattr(order.cliente, 'nome', None) if getattr(order, 'cliente', None) else None,
            'usuario_id': order.usuario_id,
            'tipo': order.tipo,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': float(order.valor_total or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'remessa_status': remessa_status_map.get(getattr(it, 'remessa_id', None), None),
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
async def update_order(order_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update top-level order fields such as status.

    Expected payload example: { "status": "preparando" }
    """
    try:
        order = db.query(PedidoModel).options(joinedload(PedidoModel.items)).filter(PedidoModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail='Pedido not found')

        updated = False
        # allow updating status
        if 'status' in payload and payload['status'] is not None:
            try:
                # Special-case payment status: accept explicit 'paid'/'pago' and
                # set internal status to 'paid' so UIs render as Pago.
                st_raw = str(payload['status']).lower()
                if st_raw.strip() in ('paid', 'pago') or (' pago' in st_raw) or st_raw.endswith(' pago'):
                    mapped = 'paid'
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
                order.status = mapped
                updated = True
            except Exception:
                pass

            # allow toggling the 10% adicional flag
            if 'adicional_10' in payload and payload['adicional_10'] is not None:
                try:
                    # normalize to 0/1
                    val = int(bool(payload['adicional_10']))
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

        # other top-level updates (e.g., observacao) can be added here if needed
        if not updated:
            # nothing to change
            db.refresh(order)
            # return current state
            pass

        db.add(order)
        db.commit()
        # log status after commit to verify persistence
        try:
            import logging as _logging
            _logging.debug(f"[orders.update] after commit before refresh status={getattr(order, 'status', None)!r}")
        except Exception:
            pass
        db.refresh(order)
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
            try:
                asyncio.create_task(publish(event))
            except RuntimeError:
                loop = asyncio.get_event_loop()
                loop.create_task(publish(event))
        except Exception:
            pass

        # fetch remessas for this order so we can include remessa_status per item
        try:
            rems = db.query(PedidoRemessaModel).filter(PedidoRemessaModel.pedido_id == order.id).order_by(PedidoRemessaModel.id.asc()).all()
            remessa_status_map = {rr.id: getattr(rr, 'status', 'pendente') for rr in rems}
        except Exception:
            remessa_status_map = {}

        return {
            'id': order.id,
            'cliente_id': order.cliente_id,
            'cliente_nome': getattr(order.cliente, 'nome', None) if getattr(order, 'cliente', None) else None,
            'usuario_id': order.usuario_id,
            'tipo': order.tipo,
            'status': order.status,
            'subtotal': float(order.subtotal or 0),
            'adicional_10': int(order.adicional_10 or 0),
            'valor_total': float(order.valor_total or 0),
            'observacao': order.observacao,
            'items': [
                {
                    'id': it.id,
                    'remessa_id': getattr(it, 'remessa_id', None),
                    'remessa_status': remessa_status_map.get(getattr(it, 'remessa_id', None), None),
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
