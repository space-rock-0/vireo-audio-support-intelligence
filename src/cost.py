"""Money math. Policy §4 rates (D11). Channel-specific preferred; blended Rs 290
fallback. The deprecated informal figure from the email thread is never used."""
from __future__ import annotations

from datetime import date

from .common import week_rows
from .metrics import sla_breaches, transfer_count

CONTACT_RATES_INR = {"chat": 210, "email": 260, "voice": 520, "social": 240}
BLENDED_RATE_INR = 290
TRANSFER_RATE_INR = 305
SLA_CREDIT_INR = 350


def rate_for(channel: str) -> int:
    return CONTACT_RATES_INR.get((channel or "").strip().lower(), BLENDED_RATE_INR)


def contact_cost(rows: list[dict], ws: date) -> dict:
    by: dict[str, int] = {}
    for r in week_rows(rows, ws):
        c = (r.get("channel") or "").strip().lower()
        by[c] = by.get(c, 0) + rate_for(c)
    return {"by_channel": dict(sorted(by.items())), "total_inr": sum(by.values())}


def transfer_cost(rows: list[dict], ws: date) -> int:
    return transfer_count(rows, ws) * TRANSFER_RATE_INR


def sla_credit_exposure(rows: list[dict], ws: date) -> int:
    return sum(sla_breaches(rows, ws).values()) * SLA_CREDIT_INR


def replacement_plan_cost(unit_cost_inr: float) -> float:
    """Policy §5: unit cost + Rs 340 logistics. No refurbishment recovery."""
    return unit_cost_inr + 340
