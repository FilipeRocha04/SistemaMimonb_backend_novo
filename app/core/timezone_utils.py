from datetime import datetime, time, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    # fallback to a fixed -03:00 offset if zoneinfo isn't available
    BRAZIL_TZ = timezone(timedelta(hours=-3))


def make_aware_in_brazil(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in America/Sao_Paulo.

    If dt is naive, attach BRAZIL_TZ. If dt already has tzinfo, convert it
    to BRAZIL_TZ.
    """
    if dt is None:
        return None
    if getattr(dt, 'tzinfo', None) is None:
        # attach Brazil tz
        try:
            return dt.replace(tzinfo=BRAZIL_TZ)
        except Exception:
            # fallback: attach fixed offset
            return dt.replace(tzinfo=timezone(timedelta(hours=-3)))
    # convert to Brazil tz
    return dt.astimezone(BRAZIL_TZ)


def local_day_range_to_utc(date_str: str):
    """Given a local date string (YYYY-MM-DD or ISO datetime), return a tuple
    (start, end) covering that local day in America/Sao_Paulo, for comparing
    against `pedidos.criado_em`.

    NOTA IMPORTANTE: apesar do nome (mantido por compatibilidade com quem já
    importa esta função), o valor retornado NÃO é convertido para UTC. O
    MySQL do projeto roda com `time_zone=SYSTEM` (America/Sao_Paulo) e
    `criado_em` é preenchido via `NOW()` do próprio banco — ou seja, já vem
    salvo em horário local do Brasil, sem timezone. Converter o intervalo do
    filtro para UTC (como esta função fazia antes) deslocava a comparação em
    3 horas, fazendo pedidos criados entre meia-noite e 3h da manhã caírem no
    dia anterior no filtro "Hoje"/data específica. Comparar direto como
    horário local (naive) é o que efetivamente bate com o que está no banco.

    Examples:
      date_str = '2026-01-11' -> range covering 2026-01-11 00:00:00 .. 23:59:59.999999 (local)
      date_str = '2026-01-11T10:00:00' -> treats as that local datetime and returns start=end of that instant
    """
    if not date_str:
        return None, None

    # handle date-only strings
    try:
        if len(date_str) == 10:
            # YYYY-MM-DD
            d = datetime.fromisoformat(date_str)
            start_local = datetime.combine(d.date(), time.min)
            end_local = datetime.combine(d.date(), time.max)
        else:
            # try parsing full ISO datetime
            d = datetime.fromisoformat(date_str)
            # if a date-time was provided, treat both start and end as that instant
            start_local = d
            end_local = d
    except Exception:
        return None, None

    # Retorna os limites como horário local "naive" (sem tzinfo), igual ao
    # que é armazenado em `criado_em` pelo MySQL — nada de conversão de fuso.
    return start_local, end_local
