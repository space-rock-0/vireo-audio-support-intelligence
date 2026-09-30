"""Pure KPI functions over canonical ticket rows (list[dict]).

No I/O, no LLM, no side effects. Week filter: created_at in [ws, ws+7d),
except leaderboard-style resolution filters which live in leaderboard.py.
"""
from __future__ import annotations

from datetime import date, datetime

from .common import (
    in_week,
    is_resolved_at_trusted,
    parse_ts,
    to_num,
    valid_csat,
    week_rows,
)

SLA_TARGETS_MIN = {"chat": 15, "email": 480, "voice": 120, "social": 240}


def weekly_volume(rows: list[dict], ws: date) -> int:
    return len(week_rows(rows, ws))


def channel_mix(rows: list[dict], ws: date) -> dict[str, float]:
    wk = week_rows(rows, ws)
    n = len(wk)
    mix: dict[str, float] = {}
    for r in wk:
        c = (r.get("channel") or "").strip().lower()
        mix[c] = mix.get(c, 0) + 1
    return {k: round(v * 100 / n, 2) for k, v in sorted(mix.items())} if n else {}


def status_mix(rows: list[dict], ws: date) -> dict[str, dict]:
    """Status distribution by CREATED week (joins channel_mix, not the board)."""
    wk = week_rows(rows, ws)
    n = len(wk)
    mix: dict[str, int] = {}
    for r in wk:
        s = (r.get("status") or "").strip().lower()
        mix[s] = mix.get(s, 0) + 1
    return {k: {"n": v, "pct": round(v * 100 / n, 2)} for k, v in sorted(mix.items())} if n else {}


def attendance_in_week(rows: list[dict], ws: date) -> list[dict]:
    """Resolved/closed rows by RESOLVED week — the leaderboard population (D2).
    NOTE the dual week basis: every other KPI here filters by created week;
    only attendance filters by resolved week. Phase 6 tables must label which."""
    return [
        r
        for r in rows
        if (r.get("status") or "").strip().lower() in ("resolved", "closed")
        and in_week(parse_ts(r.get("resolved_at")), ws)
    ]


def _breach(r: dict) -> bool | None:
    """True/False, or None when timestamps missing/invalid. Strictly-greater rule."""
    c, f = parse_ts(r.get("created_at")), parse_ts(r.get("first_response_at"))
    if c is None or f is None:
        return None
    target = SLA_TARGETS_MIN.get((r.get("channel") or "").strip().lower())
    if target is None:
        return None
    return (f - c).total_seconds() / 60 > target


def sla_breaches(rows: list[dict], ws: date) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in week_rows(rows, ws):
        if _breach(r):
            c = (r.get("channel") or "").strip().lower()
            out[c] = out.get(c, 0) + 1
    return dict(sorted(out.items()))


def sla_missing_count(rows: list[dict], ws: date) -> int:
    return sum(1 for r in week_rows(rows, ws) if _breach(r) is None)


def csat_stats(rows: list[dict], ws: date) -> dict:
    wk = week_rows(rows, ws)
    vals = [v for r in wk if (v := valid_csat(r.get("csat_score"))) is not None]
    n_wk = len(wk)
    return {
        "n": len(vals),
        "response_rate_pct": round(len(vals) * 100 / n_wk, 2) if n_wk else 0.0,
        "mean": round(sum(vals) / len(vals), 3) if vals else None,
    }


def transfer_count(rows: list[dict], ws: date) -> int:
    """Integral transfer counts only; fractional values are data errors
    surfaced by validation (transfer_non_integral), never silently floored."""
    total = 0
    for r in week_rows(rows, ws):
        v = to_num(r.get("transfers"))
        if v is not None and v == int(v):
            total += int(v)
    return total


def repeat_contact_candidates(
    rows: list[dict], ws: date, window_days: int = 30
) -> list[dict]:
    """Consecutive date-sorted pairs per customer; repeat ticket created in week.

    0 <= (repeat.created - prior.resolved) <= window. Blank prior
    resolved_at is skipped (undercounts, never overcounts).
    """
    by_cust: dict[str, list[dict]] = {}
    for r in rows:
        by_cust.setdefault((r.get("customer_id") or "").strip(), []).append(r)
    out = []
    for cust, arr in by_cust.items():
        arr = sorted(arr, key=lambda r: parse_ts(r.get("created_at")) or datetime.min)
        for prev, cur in zip(arr, arr[1:]):
            pr = parse_ts(prev.get("resolved_at"))
            cc = parse_ts(cur.get("created_at"))
            if pr is None or cc is None:
                continue
            dt_days = (cc - pr).total_seconds() / 86400
            if not (0 <= dt_days <= window_days):
                continue
            if not in_week(cc, ws):
                continue
            co = (cur.get("order_id") or "").strip()
            out.append(
                {
                    "prior_ticket_id": prev["ticket_id"],
                    "repeat_ticket_id": cur["ticket_id"],
                    "customer_id": cust,
                    "gap_days": round(dt_days, 2),
                    "prior_trusted_gap": is_resolved_at_trusted(prev),
                    "same_order": bool(co) and co == (prev.get("order_id") or "").strip(),
                    "same_product": (cur.get("product_sku") or "").strip()
                    == (prev.get("product_sku") or "").strip(),
                    "same_category": (cur.get("category") or "").strip()
                    == (prev.get("category") or "").strip(),
                    "repeat_channel": (cur.get("channel") or "").strip(),
                    "repeat_category": (cur.get("category") or "").strip(),
                }
            )
    return out


def same_issue_filter(pair: dict) -> bool:
    """D7 Stage-2 deterministic predicate: same product AND (same order
    OR same category). Defines Phase 5's sampling frame; precision/recall of
    this rule against human labels decides the business metric."""
    return bool(pair.get("same_product")) and bool(
        pair.get("same_order") or pair.get("same_category")
    )
