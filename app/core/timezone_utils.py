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
    """Given a local date string (YYYY-MM-DD or ISO datetime), return
    a tuple (start_utc, end_utc) representing the UTC datetime range for that
    local day in America/Sao_Paulo.

    Examples:
      date_str = '2026-01-11' -> range covering 2026-01-11 00:00:00-03:00 .. 23:59:59.999999-03:00
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

    # make them aware in Brazil tz and convert to UTC
    start_aware = make_aware_in_brazil(start_local)
    end_aware = make_aware_in_brazil(end_local)

    try:
        start_utc = start_aware.astimezone(timezone.utc)
        end_utc = end_aware.astimezone(timezone.utc)
    except Exception:
        # fallback: assume fixed -3 offset
        start_utc = (start_aware - timedelta(hours=3)).replace(tzinfo=timezone.utc)
        end_utc = (end_aware - timedelta(hours=3)).replace(tzinfo=timezone.utc)

    return start_utc, end_utc
