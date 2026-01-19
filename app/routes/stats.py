from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from datetime import datetime, timedelta

from app.db.session import get_db
from app.models.pagamento import Pagamento as PagamentoModel
from app.models.pedido import Pedido as PedidoModel
from app.core.timezone_utils import BRAZIL_TZ

router = APIRouter(prefix="/stats", tags=["Stats"])


# Use shared get_db from app.db.session


@router.get("/weekly_revenue")
def weekly_revenue(db: Session = Depends(get_db)):
    """
    Weekly revenue (faturamento semanal) as the total value of orders sold in the
    last 7 days, independent of payment status.

    Implementation: sum of `pedidos.valor_total` where `pedidos.criado_em >= now - 7 days`.
    Returns: { "weeklyRevenue": float }
    """
    try:
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        total = (
            db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
            .filter(PedidoModel.criado_em >= seven_days_ago)
            .scalar()
        )
        try:
            total_float = float(total)
        except Exception:
            total_float = 0.0
        return {"weeklyRevenue": total_float}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monthly_revenue")
def monthly_revenue(db: Session = Depends(get_db)):
    """
    Monthly revenue (faturamento mensal) as the total value of orders sold in the
    last 30 days, independent of payment status.

    Implementation: sum of `pedidos.valor_total` where `pedidos.criado_em >= now - 30 days`.
    Returns: { "monthlyRevenue": float }
    """
    try:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        total = (
            db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
            .filter(PedidoModel.criado_em >= thirty_days_ago)
            .scalar()
        )
        try:
            total_float = float(total)
        except Exception:
            total_float = 0.0
        return {"monthlyRevenue": total_float}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily_revenue")
def daily_revenue(db: Session = Depends(get_db)):
    """
    Daily revenue (faturamento diário): sum of `pedidos.valor_total` for today's date.

    We prefer the `pedidos.data` (DATE) column for day-bound correctness.
    For older rows where `data` may be NULL, also include rows where
    DATE(`criado_em`) == today.
    Returns: { "dailyRevenue": float }
    """
    try:
        try:
            today = (datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date())
        except Exception:
            today = datetime.utcnow().date()

        total = (
            db.query(func.coalesce(func.sum(PedidoModel.valor_total), 0))
            .filter(
                or_(
                    PedidoModel.data == today,
                    and_(PedidoModel.data == None, func.date(PedidoModel.criado_em) == today)
                )
            )
            .scalar()
        )
        try:
            total_float = float(total)
        except Exception:
            total_float = 0.0
        return {"dailyRevenue": total_float}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/average_ticket")
def average_ticket(startDate: str | None = None, endDate: str | None = None, allDates: bool = False, db: Session = Depends(get_db)):
    """
    Average Ticket (Ticket Médio): average of `pedidos.valor_total` over a period.

        Period selection:
        - If startDate/endDate (YYYY-MM-DD) are provided, use inclusive day bounds and filter by `pedidos.data`.
            For rows where `data` is NULL, fall back to DATE(`criado_em`) within the same bounds.
        - If allDates=true and no explicit dates, compute over all orders.
        - Otherwise (default), compute for today using `pedidos.data == hoje` (or DATE(`criado_em`) when `data` is NULL).

    Returns: { "averageTicket": float, "count": int }
    """
    try:
        # Build base query
        q = db.query(PedidoModel)

        # Apply date filters when provided
        if startDate or endDate:
            # Use inclusive bounds on DATE(columns)
            # Convert strings to date objects
            try:
                sd = (datetime.strptime(startDate, "%Y-%m-%d").date() if startDate else None)
            except Exception:
                sd = None
            try:
                ed = (datetime.strptime(endDate, "%Y-%m-%d").date() if endDate else None)
            except Exception:
                ed = None

            # Build filter conditions (inclusive)
            conds = []
            if sd and ed:
                conds.append(
                    or_(
                        and_(PedidoModel.data >= sd, PedidoModel.data <= ed),
                        and_(PedidoModel.data == None, func.date(PedidoModel.criado_em) >= sd, func.date(PedidoModel.criado_em) <= ed),
                    )
                )
            elif sd:
                conds.append(
                    or_(
                        PedidoModel.data >= sd,
                        and_(PedidoModel.data == None, func.date(PedidoModel.criado_em) >= sd),
                    )
                )
            elif ed:
                conds.append(
                    or_(
                        PedidoModel.data <= ed,
                        and_(PedidoModel.data == None, func.date(PedidoModel.criado_em) <= ed),
                    )
                )
            if conds:
                q = q.filter(*conds)

        # Default filter: today when no dates and not allDates
        if not startDate and not endDate and not allDates:
            try:
                today = (datetime.now(BRAZIL_TZ).date() if BRAZIL_TZ else datetime.utcnow().date())
            except Exception:
                today = datetime.utcnow().date()
            q = q.filter(
                or_(
                    PedidoModel.data == today,
                    and_(PedidoModel.data == None, func.date(PedidoModel.criado_em) == today)
                )
            )

        rows = q.all()
        count = len(rows)
        total = 0.0
        for r in rows:
            try:
                total += float(getattr(r, 'valor_total', 0) or 0)
            except Exception:
                pass

        avg = (total / count) if count > 0 else 0.0
        return {"averageTicket": float(avg), "count": int(count)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/average_ticket_per_day")
def average_ticket_per_day(startDate: str | None = None, endDate: str | None = None, db: Session = Depends(get_db)):
    """
    Average ticket grouped by day.

    Rules:
    - Day key uses `pedidos.data` when present, else DATE(`criado_em`).
    - If startDate/endDate provided (YYYY-MM-DD), apply inclusive bounds on that same day key.
    - Returns a list sorted by day ascending: [{ date: 'YYYY-MM-DD', averageTicket: float, count: int }].
    """
    try:
        # Parse input dates
        try:
            sd = (datetime.strptime(startDate, "%Y-%m-%d").date() if startDate else None)
        except Exception:
            sd = None
        try:
            ed = (datetime.strptime(endDate, "%Y-%m-%d").date() if endDate else None)
        except Exception:
            ed = None

        # Day key: COALESCE(pedidos.data, DATE(pedidos.criado_em))
        day_key = func.coalesce(PedidoModel.data, func.date(PedidoModel.criado_em))

        q = db.query(
            day_key.label('dia'),
            func.coalesce(func.avg(PedidoModel.valor_total), 0).label('avg_valor'),
            func.count(PedidoModel.id).label('count_pedidos'),
        )

        # Apply bounds on the same day key (inclusive)
        if sd and ed:
            q = q.filter(day_key >= sd, day_key <= ed)
        elif sd:
            q = q.filter(day_key >= sd)
        elif ed:
            q = q.filter(day_key <= ed)

        q = q.group_by(day_key).order_by(day_key.asc())
        rows = q.all()
        out = []
        for dia, avg_valor, count_pedidos in rows:
            try:
                # dia may be a datetime.date or string depending on dialect
                if hasattr(dia, 'isoformat'):
                    date_str = dia.isoformat()
                else:
                    date_str = str(dia)
                out.append({
                    'date': date_str,
                    'averageTicket': float(avg_valor or 0),
                    'count': int(count_pedidos or 0),
                })
            except Exception:
                pass
        return { 'days': out }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
