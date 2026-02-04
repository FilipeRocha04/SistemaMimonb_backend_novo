from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from datetime import datetime, timedelta

from app.db.session import get_db
from app.models.pagamento import Pagamento as PagamentoModel
from app.models.pedido import Pedido as PedidoModel
from app.models.pedido_item import PedidoItem as PedidoItemModel
from app.core.timezone_utils import BRAZIL_TZ

router = APIRouter(prefix="/stats", tags=["Stats"])


# =========================
# WEEKLY REVENUE
# =========================
@router.get("/weekly_revenue")
def weekly_revenue(db: Session = Depends(get_db)):
    try:
        # Calcular início e fim da semana atual (segunda a domingo)
        today = datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        total = (
            db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
            .filter(PedidoModel.data_pedido >= start_of_week, PedidoModel.data_pedido <= end_of_week)
            .scalar()
        )

        return {"weeklyRevenue": float(total or 0)}
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

        total = (
            db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
            .filter(PedidoModel.data_pedido >= start_of_month, PedidoModel.data_pedido <= end_of_month)
            .scalar()
        )

        return {"monthlyRevenue": float(total or 0)}
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
        total_revenue = (
            db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
            .filter(*filters)
            .scalar()
        ) or 0

        order_count = (
            db.query(func.count(PedidoModel.id))
            .filter(*filters)
            .scalar()
        ) or 0

        print(f"🔍 DEBUG - order_count: {order_count}")

        total_revenue = float(total_revenue)
        average_ticket = total_revenue / max(order_count, 1)

        # -------------------------
        # Top products
        # -------------------------
        items_q = (
            db.query(
                PedidoItemModel.nome.label("nome"),
                func.coalesce(func.sum(PedidoItemModel.quantidade), 0).label("qty"),
                func.coalesce(func.sum(PedidoItemModel.quantidade * PedidoItemModel.preco), 0).label("revenue"),
            )
            .join(PedidoModel, PedidoItemModel.pedido_id == PedidoModel.id)
            .filter(*filters)
            .group_by(PedidoItemModel.nome)
            .order_by(func.coalesce(func.sum(PedidoItemModel.quantidade), 0).desc())
        )

        top_rows = items_q.limit(10).all()

        top_products = [
            {
                "name": nome or "Produto",
                "quantity": float(qty or 0),
                "revenue": float(rev or 0),
            }
            for nome, qty, rev in top_rows
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
        # Payment breakdown
        # -------------------------
        pays = (
            db.query(
                PagamentoModel.forma_pagamento.label("method"),
                func.count(PagamentoModel.id).label("count"),
                func.coalesce(func.sum(PagamentoModel.valor), 0).label("total"),
            )
            .join(PedidoModel, PagamentoModel.pedido == PedidoModel.id)
            .filter(*filters)
            .group_by(PagamentoModel.forma_pagamento)
            .all()
        )

        payment_breakdown = [
            {
                "method": method or "outros",
                "count": int(count or 0),
                "total": float(total or 0),
            }
            for method, count, total in pays
        ]

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

        # Usar apenas data_pedido/data, nunca criado_em
        total = (
            db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
            .filter(PedidoModel.data_pedido == today)
            .scalar()
        )

        return {"dailyRevenue": float(total or 0)}
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

        def total_for(day):
            return (
                db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
                .filter(PedidoModel.data_pedido == day)
                .scalar()
            ) or 0

        t_total = float(total_for(today))
        y_total = float(total_for(yesterday))

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