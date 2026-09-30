"""Tier-1 volume leaderboard with roster-date attribution (D3/D4).

Label: "Tier 1 Tickets Completed (Attendance Volume)" — a volume/attendance
metric, NOT agent quality. Tier 2 (Escalations & Warranty) is excluded with a
visible note because policy §6 measures Tier 2 in resolution days.
"""
from __future__ import annotations

from datetime import date

from .common import parse_day, parse_ts
from .metrics import attendance_in_week

TIER1_TEAMS = {"Chat Frontline", "Email Frontline", "Voice Frontline"}
TIER2_TEAM = "Escalations & Warranty"
LEADERBOARD_LABEL = "Tier 1 Tickets Completed (Attendance Volume)"
TIER2_NOTE = "Tier 2 (Escalations & Warranty) excluded: policy §6 measures Tier 2 in resolution days, not tickets/week."


def resolve_roster(agent_id: str, on: date | None, roster: list[dict]) -> dict | None:
    """Roster row where from_date <= on <= to_date (blank to = active).

    Overlaps -> most recent from_date wins. No match -> None (caller logs).
    """
    if on is None:
        return None
    cands = []
    for r in roster:
        if (r.get("agent_id") or "").strip() != agent_id:
            continue
        frm = parse_day(r.get("from_date"))
        to = parse_day(r.get("to_date"))
        if frm is None or frm > on:
            continue
        if to is not None and to < on:
            continue
        cands.append((frm, r))
    if not cands:
        return None
    return max(cands, key=lambda t: t[0])[1]


def _counts(
    rows: list[dict], roster: list[dict], ws: date, want_tier1: bool
) -> tuple[dict, list[str]]:
    """Shared counter. want_tier1=True -> Tier-1 board rows; False -> rest."""
    counts: dict[str, dict] = {}
    unresolved: list[str] = []
    for r in attendance_in_week(rows, ws):
        aid = (r.get("agent_id") or "").strip()
        res_day = parse_ts(r.get("resolved_at"))
        day = res_day.date() if res_day else None
        entry = resolve_roster(aid, day, roster)
        if entry is None:
            unresolved.append(f"{r['ticket_id']}:{aid}")
            continue
        is_t1 = (entry.get("team") or "").strip() in TIER1_TEAMS
        if is_t1 != want_tier1:
            continue
        c = counts.setdefault(
            aid,
            {
                "agent_id": aid,
                "agent_name": (entry.get("name") or "").strip(),
                "team": (entry.get("team") or "").strip(),
                "shift": (entry.get("shift") or "").strip(),
                "site": (entry.get("site") or "").strip(),
                "tickets_completed": 0,
            },
        )
        c["tickets_completed"] += 1
    board = sorted(counts.values(), key=lambda c: (-c["tickets_completed"], c["agent_id"]))
    return board, unresolved


def tier1_leaderboard(
    rows: list[dict], roster: list[dict], ws: date
) -> tuple[list[dict], list[str]]:
    """Returns (board sorted desc, unresolved_log). Keyed on resolving agent_id."""
    return _counts(rows, roster, ws, want_tier1=True)


def specialist_table(
    rows: list[dict], roster: list[dict], ws: date
) -> tuple[list[dict], list[str]]:
    """Same shape for non-Tier-1 teams (Logistics/Billing/Returns/Tier 2).
    Separate table — never ranked against Tier 1 (D3). Returns (table, unresolved)
    so board + specialist + unresolved reconcile to the attendance total."""
    return _counts(rows, roster, ws, want_tier1=False)
