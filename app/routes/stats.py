from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, case as sa_case
from datetime import datetime, timedelta

from app.db.session import get_db
from app.models.pagamento import Pagamento as PagamentoModel
from app.models.pedido import Pedido as PedidoModel
from app.models.pedido_item import PedidoItem as PedidoItemModel
from app.models.product import Produto as ProdutoModel
from app.core.timezone_utils import BRAZIL_TZ

router = APIRouter(prefix="/stats", tags=["Stats"])


def compute_effective_total(db: Session, filters: list) -> float:
    """Replica a fórmula do frontend: por pedido usa GREATEST(valor_total, soma_dos_itens).

    Isso garante que pedidos com valor_total desatualizado no banco sejam contados
    pelo valor real dos itens, igual ao que a tela de pedidos exibe.
    """
    item_sums_sq = (
        db.query(
            PedidoItemModel.pedido_id.label('pedido_id'),
            func.coalesce(func.sum(PedidoItemModel.quantidade * PedidoItemModel.preco), 0).label('item_sum')
        )
        .group_by(PedidoItemModel.pedido_id)
        .subquery()
    )
    result = (
        db.query(
            func.coalesce(
                func.sum(
                    sa_case(
                        (
                            func.coalesce(PedidoModel.valor_total, 0) >= func.coalesce(item_sums_sq.c.item_sum, 0) - 0.01,
                            func.coalesce(PedidoModel.valor_total, 0)
                        ),
                        else_=func.coalesce(item_sums_sq.c.item_sum, 0)
                    )
                ),
                0
            )
        )
        .outerjoin(item_sums_sq, PedidoModel.id == item_sums_sq.c.pedido_id)
        .filter(*filters)
        .scalar()
    )
    return float(result or 0)


# =========================
# WEEKLY REVENUE
# =========================
@router.get("/weekly_revenue")
def weekly_revenue(db: Session = Depends(get_db)):
    try:
        today = datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date()
        # Domingo = 6, Segunda = 0 ...
        weekday = today.weekday()
        # Se hoje é domingo (6), começa nova semana
        if weekday == 6:
            start_of_week = today
            end_of_week = today + timedelta(days=6)
        else:
            # Semana começa no domingo anterior
            start_of_week = today - timedelta(days=weekday+1)
            end_of_week = start_of_week + timedelta(days=6)

        print(f"[DEBUG] Período semanal: {start_of_week} a {end_of_week}")
        # Use consistent day key (data_pedido or data)
        day_key = PedidoModel.data_pedido if hasattr(PedidoModel, 'data_pedido') else PedidoModel.data

        week_filters = [day_key >= start_of_week, day_key <= end_of_week]
        effective = compute_effective_total(db, week_filters)

        from app.models.pagador import PagamentoPagadorForma
        pedidos_ids_week = db.query(PedidoModel.id).filter(*week_filters).subquery()
        pagamentos_ids_week = db.query(PagamentoModel.id).filter(PagamentoModel.pedido.in_(pedidos_ids_week)).subquery()
        payment_total = float(db.query(func.coalesce(func.sum(PagamentoPagadorForma.valor), 0)).filter(PagamentoPagadorForma.pagamento_id.in_(pagamentos_ids_week)).scalar() or 0)

        revenue = payment_total if payment_total > 0 else effective
        print(f"[DEBUG weekly_revenue] week {start_of_week}..{end_of_week} effective={effective} payment_total={payment_total} revenue={revenue}")
        return {"weeklyRevenue": revenue}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# MONTHLY REVENUE
# =========================
@router.get("/monthly_revenue")
def monthly_revenue(db: Session = Depends(get_db)):
    try:
        # Calcular início e fim do mês atual
        today = datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date()
        start_of_month = today.replace(day=1)
        if today.month == 12:
            end_of_month = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
        else:
            end_of_month = today.replace(month=today.month+1, day=1) - timedelta(days=1)

        # Use consistent day key
        day_key = PedidoModel.data_pedido if hasattr(PedidoModel, 'data_pedido') else PedidoModel.data

        month_filters = [day_key >= start_of_month, day_key <= end_of_month]
        effective = compute_effective_total(db, month_filters)

        from app.models.pagador import PagamentoPagadorForma
        pedidos_ids_month = db.query(PedidoModel.id).filter(*month_filters).subquery()
        pagamentos_ids_month = db.query(PagamentoModel.id).filter(PagamentoModel.pedido.in_(pedidos_ids_month)).subquery()
        payment_total = float(db.query(func.coalesce(func.sum(PagamentoPagadorForma.valor), 0)).filter(PagamentoPagadorForma.pagamento_id.in_(pagamentos_ids_month)).scalar() or 0)

        revenue = payment_total if payment_total > 0 else effective
        print(f"[DEBUG monthly_revenue] month {start_of_month}..{end_of_month} effective={effective} payment_total={payment_total} revenue={revenue}")
        return {"monthlyRevenue": revenue}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# DAILY REVENUE DETAILS
# =========================
@router.get("/daily_revenue_details")
def daily_revenue_details(
    startDate: str | None = None,
    endDate: str | None = None,
    db: Session = Depends(get_db),
):
    # -------------------------
    # Date parsing helpers
    # -------------------------
    def parse_date(s: str | None):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    sd = parse_date(startDate)
    ed = parse_date(endDate)

    if not sd and not ed:
        today = datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date()
        sd = ed = today

    try:
        # Usar sempre data_pedido (ou data) para filtro, nunca criado_em
        day_key = PedidoModel.data_pedido if hasattr(PedidoModel, 'data_pedido') else PedidoModel.data

        filters = []
        if sd and ed:
            filters.extend([day_key >= sd, day_key <= ed])
        elif sd:
            filters.append(day_key >= sd)
        elif ed:
            filters.append(day_key <= ed)

        # -------------------------
        # Comandas com 10% (adicional_10=1)
        # -------------------------
        comandas_10_count = (
            db.query(func.count(PedidoModel.id))
            .filter(*filters, PedidoModel.adicional_10 == 1)
            .scalar() or 0
        )
        comandas_10_total = (
            db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
            .filter(*filters, PedidoModel.adicional_10 == 1)
            .scalar() or 0
        )

        print(f"🔍 DEBUG - sd: {sd}, ed: {ed}")
        print(f"🔍 DEBUG - filters: {filters}")

        # ------------------------- 
        # Orders summary
        # -------------------------
        # Use same day_key as other endpoints
        day_key = PedidoModel.data_pedido if hasattr(PedidoModel, 'data_pedido') else PedidoModel.data

        effective_total = compute_effective_total(db, filters)
        print(f"[DEBUG daily_revenue_details] filters {sd}..{ed} effective={effective_total}")

        order_count = (
            db.query(func.count(PedidoModel.id))
            .filter(*filters)
            .scalar()
        ) or 0

        print(f"🔍 DEBUG - order_count: {order_count}")

        total_revenue = effective_total
        average_ticket = total_revenue / max(order_count, 1)

        # -------------------------
        # Top products
        # -------------------------
        items_q = (
            db.query(
                PedidoItemModel.nome.label("nome"),
                func.coalesce(func.sum(PedidoItemModel.quantidade), 0).label("qty"),
                func.coalesce(func.sum(PedidoItemModel.quantidade * PedidoItemModel.preco), 0).label("revenue"),
                func.max(ProdutoModel.categoria).label("categoria"),
            )
            .join(PedidoModel, PedidoItemModel.pedido_id == PedidoModel.id)
            .outerjoin(ProdutoModel, PedidoItemModel.produto_id == ProdutoModel.id)
            .filter(*filters)
            .group_by(PedidoItemModel.nome)
            .order_by(func.coalesce(func.sum(PedidoItemModel.quantidade), 0).desc())
        )

        top_rows = items_q.all()

        top_products = [
            {
                "name": nome or "Produto",
                "quantity": float(qty or 0),
                "revenue": float(rev or 0),
                "category": str(categoria or '').lower().strip(),
            }
            for nome, qty, rev, categoria in top_rows
        ]

        print(f"🔍 DEBUG - top_products count: {len(top_products)}")

        # -------------------------
        # Items totals - VERSÃO SIMPLIFICADA
        # -------------------------
        total_lines = (
            db.query(func.count(PedidoItemModel.id))
            .join(PedidoModel, PedidoItemModel.pedido_id == PedidoModel.id)
            .filter(*filters)
            .scalar() or 0
        )
        total_lines = int(total_lines)

        print(f"🔍 DEBUG - total_lines ANTES: {total_lines}")

        # Teste SEM filtros para ver se encontra os itens
        total_lines_sem_filtro = (
            db.query(func.count(PedidoItemModel.id))
            .join(PedidoModel, PedidoItemModel.pedido_id == PedidoModel.id)
            .scalar() or 0
        )
        
        print(f"🔍 DEBUG - total_lines SEM FILTRO: {total_lines_sem_filtro}")

        # Verificar se o pedido_id 524 existe
        pedido_existe = db.query(PedidoModel).filter(PedidoModel.id == 524).first()
        print(f"🔍 DEBUG - Pedido 524 existe? {pedido_existe is not None}")
        if pedido_existe:
            print(f"🔍 DEBUG - Pedido 524 data: {pedido_existe.data}")
            print(f"🔍 DEBUG - Pedido 524 criado_em: {pedido_existe.criado_em}")


        # -------------------------
        # Payment breakdown (usando pagamento_pagador_forma)
        # -------------------------
        from app.models.pagador import PagamentoPagadorForma
        # Seleciona todos os pagamentos dos pedidos filtrados
        pedidos_ids = db.query(PedidoModel.id).filter(*filters).subquery()
        pagamentos_ids = db.query(PagamentoModel.id).filter(PagamentoModel.pedido.in_(pedidos_ids)).subquery()
        pf_rows = (
            db.query(
                PagamentoPagadorForma.forma_pagamento.label("method"),
                func.count(PagamentoPagadorForma.id).label("count"),
                func.coalesce(func.sum(PagamentoPagadorForma.valor), 0).label("total"),
            )
            .filter(PagamentoPagadorForma.pagamento_id.in_(pagamentos_ids))
            .group_by(PagamentoPagadorForma.forma_pagamento)
            .all()
        )

        payment_breakdown = [
            {
                "method": method or "outros",
                "count": int(count or 0),
                "total": float(total or 0),
            }
            for method, count, total in pf_rows
        ]

        # Use actual payment totals (PagamentoPagadorForma) as source of truth for revenue.
        # This correctly reflects service fees (e.g. 10%) that may not be stored in pedido.valor_total.
        payment_total_sum = sum(row["total"] for row in payment_breakdown)
        if payment_total_sum > 0:
            total_revenue = float(payment_total_sum)
            average_ticket = total_revenue / max(order_count, 1)

        resp_date = sd.isoformat() if sd == ed else None

        # Soma das quantidades para alinhar com PDF e frontend
        items_sold = (
            db.query(func.coalesce(func.sum(PedidoItemModel.quantidade), 0))
            .join(PedidoModel, PedidoItemModel.pedido_id == PedidoModel.id)
            .filter(*filters)
            .scalar() or 0
        )
        # -------------------------
        # Orders List detalhado
        # -------------------------
        pedidos = db.query(PedidoModel).filter(*filters).all()
        orders_list = []
        for pedido in pedidos:
            cliente_nome = None
            if hasattr(pedido, 'cliente') and pedido.cliente:
                cliente_nome = getattr(pedido.cliente, 'nome', None)
            itens = []
            for item in getattr(pedido, 'items', []):
                itens.append({
                    "name": item.nome,
                    "quantity": float(item.quantidade),
                    "unitPrice": float(item.preco),
                    "total": float(item.quantidade) * float(item.preco)
                })
            pagamento = db.query(PagamentoModel).filter(PagamentoModel.pedido == pedido.id).first()
            payment_method = pagamento.forma_pagamento if pagamento else None
            orders_list.append({
                "id": pedido.id,
                "customer": cliente_nome,
                "items": itens,
                "total": float(pedido.valor_total),
                "paymentMethod": payment_method
            })
        return {
            "date": resp_date,
            "startDate": sd.isoformat() if sd else None,
            "endDate": ed.isoformat() if ed else None,
            "orders": {
                "count": order_count,
                "totalRevenue": total_revenue,
                "averageTicket": average_ticket,
            },
            "items": {
                "lines": total_lines,
                "itemsSold": float(items_sold),
            },
            "comandas10": {
                "count": int(comandas_10_count),
                "total": float(comandas_10_total),
            },
            "topProducts": top_products,
            "paymentBreakdown": payment_breakdown,
            "ordersList": orders_list,
        }
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# DAILY REVENUE
# =========================
@router.get("/daily_revenue")
def daily_revenue(db: Session = Depends(get_db)):
    try:
        today = datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date()

        day_key = PedidoModel.data_pedido if hasattr(PedidoModel, 'data_pedido') else PedidoModel.data
        today_filters = [day_key == today]
        effective = compute_effective_total(db, today_filters)

        # Use actual payment totals as source of truth (includes service fees)
        from app.models.pagador import PagamentoPagadorForma
        pedidos_ids_today = db.query(PedidoModel.id).filter(*today_filters).subquery()
        pagamentos_ids_today = db.query(PagamentoModel.id).filter(PagamentoModel.pedido.in_(pedidos_ids_today)).subquery()
        payment_total = db.query(
            func.coalesce(func.sum(PagamentoPagadorForma.valor), 0)
        ).filter(PagamentoPagadorForma.pagamento_id.in_(pagamentos_ids_today)).scalar() or 0
        payment_total = float(payment_total)

        revenue = payment_total if payment_total > 0 else effective
        print(f"[DEBUG daily_revenue] date {today} effective={effective} payment_total={payment_total} revenue={revenue}")
        return {"dailyRevenue": revenue}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# DAILY REVENUE COMPARISON
# =========================
@router.get("/daily_revenue_comparison")
def daily_revenue_comparison(db: Session = Depends(get_db)):
    try:
        today = datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date()
        yesterday = today - timedelta(days=1)

        day_key = PedidoModel.data_pedido if hasattr(PedidoModel, 'data_pedido') else PedidoModel.data

        t_total = compute_effective_total(db, [day_key == today])
        y_total = compute_effective_total(db, [day_key == yesterday])

        change_pct = ((t_total - y_total) / y_total * 100) if y_total > 0 else (100 if t_total > 0 else 0)

        return {
            "today": t_total,
            "yesterday": y_total,
            "changePct": round(change_pct, 2),
            "isPositive": t_total >= y_total,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# AVERAGE TICKET
# =========================
@router.get("/average_ticket")
def average_ticket(
    startDate: str | None = None,
    endDate: str | None = None,
    allDates: bool = False,
    db: Session = Depends(get_db),
):
    try:
        q = db.query(PedidoModel)

        # Sempre filtrar por data_pedido
        if startDate or endDate:
            sd = datetime.strptime(startDate, "%Y-%m-%d").date() if startDate else None
            ed = datetime.strptime(endDate, "%Y-%m-%d").date() if endDate else None

            if sd and ed:
                q = q.filter(PedidoModel.data_pedido >= sd, PedidoModel.data_pedido <= ed)
            elif sd:
                q = q.filter(PedidoModel.data_pedido >= sd)
            elif ed:
                q = q.filter(PedidoModel.data_pedido <= ed)

        if not startDate and not endDate and not allDates:
            today = datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date()
            q = q.filter(PedidoModel.data_pedido == today)

        rows = q.all()
        total = sum(float(r.valor_total or 0) for r in rows)
        count = len(rows)

        return {
            "averageTicket": total / count if count > 0 else 0,
            "count": count,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# AVERAGE TICKET PER DAY
# =========================
@router.get("/average_ticket_per_day")
def average_ticket_per_day(
    startDate: str | None = None,
    endDate: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        sd = datetime.strptime(startDate, "%Y-%m-%d").date() if startDate else None
        ed = datetime.strptime(endDate, "%Y-%m-%d").date() if endDate else None

        day_key = PedidoModel.data_pedido

        q = db.query(
            day_key.label("dia"),
            func.coalesce(func.avg(PedidoModel.valor_total), 0),
            func.count(PedidoModel.id),
        )

        if sd and ed:
            q = q.filter(day_key >= sd, day_key <= ed)
        elif sd:
            q = q.filter(day_key >= sd)
        elif ed:
            q = q.filter(day_key <= ed)

        q = q.group_by(day_key).order_by(day_key.asc())

        rows = q.all()

        return {
            "days": [
                {
                    "date": dia.isoformat() if hasattr(dia, "isoformat") else str(dia),
                    "averageTicket": float(avg or 0),
                    "count": int(count or 0),
                }
                for dia, avg, count in rows if dia is not None
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))