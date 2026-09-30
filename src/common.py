"""Shared parsing helpers. All timestamps are IST display values — never converted (D6)."""
from __future__ import annotations

from datetime import date, datetime, timedelta


def parse_ts(s: str | None) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_day(s: str | None) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def week_monday(d: date) -> date:
    """Monday of d's ISO week. Live: used by Phase 6 digest week labels."""
    return d - timedelta(days=d.weekday())


def week_rows(rows: list[dict], ws: date) -> list[dict]:
    """Rows created in [ws, ws+7d). THE created-week filter — every
    metrics.py/cost.py KPI uses it. Resolution-week filtering lives only in
    leaderboard.py (attendance) by design: volume is counted when the customer
    contacted, leaderboard when the agent closed."""
    return [r for r in rows if in_week(parse_ts(r.get("created_at")), ws)]


def valid_csat(v: str | None) -> int | None:
    """CSAT 1–5 as int, else None. Blanks and legacy '0' are no-response (A6).
    Shared by metrics (averages) and validation (range check) so the two can
    never disagree on fractional or out-of-range scores."""
    s = (v or "").strip()
    if s in ("", "0"):
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    return n if 1 <= n <= 5 else None


def is_resolved_at_trusted(row: dict) -> bool:
    """D6 guardrail: only helpdesk resolved_at is timestamp-trustworthy.
    Legacy copies carry the UTC/IST reconstruction shift. Call this before
    ANY resolved_at arithmetic outside SLA (which uses first_response_at)."""
    return (row.get("source_system") or "").strip() == "helpdesk" and bool(
        (row.get("resolved_at") or "").strip()
    )


def in_week(dt: datetime | date | None, ws: date) -> bool:
    if dt is None:
        return False
    d = dt.date() if isinstance(dt, datetime) else dt
    return ws <= d < ws + timedelta(days=7)


def to_num(s: str | None) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None