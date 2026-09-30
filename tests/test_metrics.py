"""Unit tests for every deterministic KPI function. Hand-built fixtures with
known-correct expectations — no dependency on the real CSVs."""
from datetime import date

import pytest

from src import cost
from src.common import in_week, parse_ts
from src.ingest import deduplicate
from src.leaderboard import (
    LEADERBOARD_LABEL,
    resolve_roster,
    specialist_table,
    tier1_leaderboard,
)
from src.metrics import (
    channel_mix,
    csat_stats,
    repeat_contact_candidates,
    sla_breaches,
    sla_missing_count,
    transfer_count,
    weekly_volume,
)
from src.validation import validate

WS = date(2026, 6, 22)  # Monday


def T(**kw):
    base = {
        "ticket_id": "TK-X",
        "created_at": "2026-06-23 10:00",
        "first_response_at": "2026-06-23 10:05",
        "resolved_at": "2026-06-23 11:00",
        "status": "resolved",
        "channel": "chat",
        "customer_id": "C1",
        "order_id": "O1",
        "product_sku": "VA-EB-PL2",
        "category": "Connectivity",
        "priority": "Normal",
        "assigned_team": "Chat Frontline",
        "agent_id": "A1",
        "transfers": "0",
        "csat_score": "5",
        "refund_amount_inr": "",
        "refund_reason_code": "",
        "replacement_issued": "N",
        "customer_message": "pairing fails",
        "agent_notes": "reset done",
        "source_system": "helpdesk",
    }
    base.update(kw)
    return base


ROSTER = [
    {"agent_id": "A1", "name": "Tier One", "site": "Indore", "team": "Chat Frontline",
     "shift": "Day", "tier": "1", "from_date": "2023-01-01", "to_date": ""},
    {"agent_id": "A2", "name": "Tier Two", "site": "Indore", "team": "Escalations & Warranty",
     "shift": "Day", "tier": "2", "from_date": "2023-01-01", "to_date": ""},
    {"agent_id": "A3", "name": "Mover", "site": "Indore", "team": "Email Frontline",
     "shift": "Day", "tier": "1", "from_date": "2023-01-01", "to_date": "2026-06-01"},
    {"agent_id": "A3", "name": "Mover", "site": "Bengaluru", "team": "Logistics",
     "shift": "Day", "tier": "1", "from_date": "2026-06-02", "to_date": ""},
]


def test_weekly_volume_boundaries():
    rows = [
        T(ticket_id="a", created_at="2026-06-28 23:59"),  # Sunday in-week
        T(ticket_id="b", created_at="2026-06-29 00:00"),  # next Monday out
        T(ticket_id="c", created_at="2026-06-22 00:00"),  # Monday in
    ]
    assert weekly_volume(rows, WS) == 2


def test_channel_mix_sums_100():
    rows = [T(ticket_id="a", channel="chat"), T(ticket_id="b", channel="email"),
            T(ticket_id="c", channel="email")]
    mix = channel_mix(rows, WS)
    assert mix == {"chat": 33.33, "email": 66.67}
    assert abs(sum(mix.values()) - 100) < 0.01


def test_sla_boundary_exact_target_ok():
    # chat target 15 min: exactly 15:00 is NOT a breach (strictly-greater rule)
    rows = [T(ticket_id="a", created_at="2026-06-23 10:00",
               first_response_at="2026-06-23 10:15")]
    assert sla_breaches(rows, WS) == {}
    rows = [T(ticket_id="a", created_at="2026-06-23 10:00",
               first_response_at="2026-06-23 10:16")]
    assert sla_breaches(rows, WS) == {"chat": 1}


def test_sla_email_target():
    rows = [T(ticket_id="a", channel="email", created_at="2026-06-23 10:00",
               first_response_at="2026-06-23 18:00")]  # 480 min ok
    assert sla_breaches(rows, WS) == {}
    rows[0]["first_response_at"] = "2026-06-23 18:01"
    assert sla_breaches(rows, WS) == {"email": 1}


def test_sla_missing():
    rows = [T(ticket_id="a", first_response_at="")]
    assert sla_missing_count(rows, WS) == 1
    assert sla_breaches(rows, WS) == {}


def test_csat_excludes_blank_and_zero():
    rows = [T(ticket_id="a", csat_score=""), T(ticket_id="b", csat_score="0"),
            T(ticket_id="c", csat_score="4"), T(ticket_id="d", csat_score="2"),
            T(ticket_id="e", csat_score="9")]
    s = csat_stats(rows, WS)
    assert s["n"] == 2 and s["mean"] == 3.0 and s["response_rate_pct"] == 40.0


def test_transfer_and_money_math():
    rows = [T(ticket_id="a", transfers="2"), T(ticket_id="b", transfers="1"),
            T(ticket_id="c", channel="voice")]
    assert transfer_count(rows, WS) == 3
    assert cost.transfer_cost(rows, WS) == 3 * 305
    cc = cost.contact_cost(rows, WS)
    assert cc["by_channel"] == {"chat": 420, "voice": 520}
    assert cc["total_inr"] == 940
    assert cost.sla_credit_exposure(rows, WS) == 0
    assert cost.rate_for("carrier-pigeon") == 290  # unknown -> blended
    assert cost.replacement_plan_cost(1480) == 1820


def test_rs180_never_used():
    import pathlib
    import re
    src = pathlib.Path(__file__).parent.parent / "src"
    for f in src.glob("*.py"):
        if f.name.startswith("test_"):
            continue
        assert not re.search(r"(?<!\d)180(?!\d)", f.read_text()), f


def test_repeat_window_and_flags():
    rows = [
        T(ticket_id="p1", customer_id="C9", created_at="2026-05-25 10:00",
          resolved_at="2026-05-25 12:00", order_id="O9", product_sku="S1"),
        T(ticket_id="c1", customer_id="C9", created_at="2026-06-23 10:00",
          resolved_at="2026-06-23 11:00", order_id="O9", product_sku="S1"),
        T(ticket_id="p2", customer_id="C8", created_at="2026-05-25 10:00",
          resolved_at="2026-05-25 12:00", order_id="", product_sku="S2"),
        T(ticket_id="c2", customer_id="C8", created_at="2026-06-23 10:00",
          resolved_at="2026-06-23 11:00", order_id="", product_sku="S3"),
        T(ticket_id="p3", customer_id="C7", created_at="2026-06-23 10:00",
          resolved_at="", status="open", order_id="O7", product_sku="S1"),
        T(ticket_id="c3", customer_id="C7", created_at="2026-06-24 10:00",
          resolved_at="2026-06-24 11:00", order_id="O7", product_sku="S1"),
    ]
    out = repeat_contact_candidates(rows, WS)
    by_id = {o["repeat_ticket_id"]: o for o in out}
    assert set(by_id) == {"c1", "c2"}  # blank prior resolved_at skipped
    assert by_id["c1"]["same_order"] is True and by_id["c1"]["same_product"] is True
    assert by_id["c2"]["same_order"] is False and by_id["c2"]["same_product"] is False
    # 30-day edge: exactly 30d counts, 31d does not
    edge = [
        T(ticket_id="p", customer_id="CE", created_at="2026-05-24 10:00",
          resolved_at="2026-05-24 10:00"),
        T(ticket_id="c", customer_id="CE", created_at="2026-06-23 10:00",
          resolved_at="2026-06-23 11:00"),
    ]
    assert len(repeat_contact_candidates(edge, WS)) == 1  # 30d exactly
    edge[1]["created_at"] = "2026-06-24 10:01"
    assert repeat_contact_candidates(edge, WS) == []


def test_dedup_keep_helpdesk():
    rows = [
        T(ticket_id="D", source_system="legacy_fd", resolved_at="2026-06-23 06:00"),
        T(ticket_id="D", source_system="helpdesk", resolved_at="2026-06-23 11:00"),
        T(ticket_id="S", source_system="helpdesk"),
    ]
    canon, quar = deduplicate(rows)
    assert len(canon) == 2 and len(quar) == 1
    assert next(r for r in canon if r["ticket_id"] == "D")["source_system"] == "helpdesk"
    assert quar[0]["source_system"] == "legacy_fd"


def test_roster_overlap_most_recent_wins_and_missing():
    assert resolve_roster("A3", date(2026, 6, 23), ROSTER)["team"] == "Logistics"
    assert resolve_roster("A3", date(2026, 5, 1), ROSTER)["team"] == "Email Frontline"
    assert resolve_roster("ZZ", date(2026, 6, 23), ROSTER) is None
    assert resolve_roster("A1", None, ROSTER) is None


def test_leaderboard_tier1_only_and_attendance():
    rows = [
        T(ticket_id="t1", agent_id="A1", resolved_at="2026-06-23 11:00", status="resolved"),
        T(ticket_id="t2", agent_id="A1", resolved_at="2026-06-24 11:00", status="closed"),
        T(ticket_id="t3", agent_id="A2", resolved_at="2026-06-23 11:00", status="resolved"),  # Tier2 out
        T(ticket_id="t4", agent_id="A1", resolved_at="", status="open"),  # not attendance
        T(ticket_id="t5", agent_id="A1", resolved_at="2026-06-30 11:00", status="resolved"),  # next week
        T(ticket_id="t6", agent_id="ZZ", resolved_at="2026-06-23 11:00", status="resolved"),  # unknown agent
    ]
    board, unresolved = tier1_leaderboard(rows, ROSTER, WS)
    assert len(board) == 1
    assert board[0]["agent_id"] == "A1" and board[0]["tickets_completed"] == 2
    assert board[0]["agent_name"] == "Tier One"  # name from roster, id is key
    assert unresolved == ["t6:ZZ"]
    spec, spec_unres = specialist_table(rows, ROSTER, WS)
    assert [s["agent_id"] for s in spec] == ["A2"]
    assert spec_unres == ["t6:ZZ"]  # both tables log the same unresolved row
    assert sum(s["tickets_completed"] for s in spec) + sum(
        b["tickets_completed"] for b in board
    ) + len(unresolved) == 4  # t5 resolves next week; t4 open excluded
    assert LEADERBOARD_LABEL.startswith("Tier 1")


def test_validation_spot_checks():
    raw = [
        T(ticket_id="D", source_system="legacy_fd", resolved_at="2026-06-23 06:00",
          first_response_at="2026-06-23 10:00"),
        T(ticket_id="D", source_system="helpdesk", resolved_at="2026-06-23 11:00"),
        T(ticket_id="B", refund_amount_inr="100", refund_reason_code="",
          replacement_issued="Y", csat_score="9"),
    ]
    canon = list(raw)  # validation must catch the legacy violation pre-dedup too
    refs = {"orders": {"O1"}, "customers": {"C1"}, "skus": {"VA-EB-PL2"}, "agents": {"A1"}}
    rep = validate(raw, canon, ROSTER, refs)
    assert rep["duplicate_ticket_id_groups"] == 1
    assert rep["duplicate_cross_system_groups"] == 1
    assert rep["res_before_first_legacy_fd"]["violations"] == 1
    assert rep["res_before_first_helpdesk"]["violations"] == 0
    assert rep["refund_no_code"] == 1
    assert rep["same_ticket_refund_replacement"] == ["B"]
    assert rep["csat_out_of_range"] == 1
    assert rep["roster_unresolved_any_row"] == 0
    assert rep["roster_unresolved_attendance"] == 0
    assert rep["orphan_order_id"] == 0
    assert rep["orphan_customer_id"] == 0
    assert rep["orphan_product_sku"] == 0
    assert rep["orphan_agent_id"] == 0
    bad = [dict(r, order_id="NOPE") for r in canon[:1]]
    assert validate(raw, bad, ROSTER, refs)["orphan_order_id"] == 1
    assert validate(raw, canon, ROSTER)["orphan_order_id"] is None  # refs absent: skipped


def test_parse_ts_invalid():
    assert parse_ts("") is None and parse_ts("not-a-date") is None
    assert in_week(parse_ts("2026-06-28 23:59"), WS)
    assert not in_week(parse_ts("2026-06-29 00:00"), WS)


def test_importorskip_duckdb_ingest(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    from src import ingest
    assert hasattr(ingest, "load_tickets") and hasattr(ingest, "deduplicate")


def test_read_csv_multiline_round_trip(tmp_path):
    """A3: quoted fields with embedded newlines parse as single rows."""
    from src.ingest import _read_csv
    p = tmp_path / "m.csv"
    p.write_text(
        'a,b\n1,"line1\nline2"\n2,plain\n', encoding="utf-8"
    )
    cols, rows = _read_csv(str(p))
    assert cols == ["a", "b"]
    assert len(rows) == 2  # embedded newline did NOT split the row
    assert rows[0]["b"].replace("\r\n", "\n") == "line1\nline2"


def test_same_issue_filter_and_trust_flag():
    from src.metrics import same_issue_filter
    rows = [
        T(ticket_id="p", customer_id="CF", created_at="2026-05-25 10:00",
          resolved_at="2026-05-25 12:00", order_id="OF",
          product_sku="SF", category="Connectivity", source_system="legacy_fd"),
        T(ticket_id="c", customer_id="CF", created_at="2026-06-23 10:00",
          resolved_at="2026-06-23 11:00", order_id="OF",
          product_sku="SF", category="Billing & Payments"),
    ]
    out = repeat_contact_candidates(rows, WS)
    assert len(out) == 1
    assert out[0]["prior_trusted_gap"] is False  # legacy prior flagged, still counted
    assert out[0]["same_category"] is False
    assert same_issue_filter(out[0]) is True  # same product + same order
    out[0]["same_order"] = False
    assert same_issue_filter(out[0]) is False  # diff order + diff category


def test_status_mix_and_week_monday():
    from src.common import week_monday
    from src.metrics import status_mix
    assert week_monday(date(2026, 6, 24)) == date(2026, 6, 22)
    rows = [T(ticket_id="a", status="resolved"), T(ticket_id="b", status="open")]
    mix = status_mix(rows, WS)
    assert mix["resolved"]["n"] == 1 and mix["open"]["pct"] == 50.0


def test_same_order_validation_and_fractional_transfer():
    rows = [
        T(ticket_id="r1", order_id="OX", refund_amount_inr="100",
          refund_reason_code="CANCEL"),
        T(ticket_id="r2", order_id="OX", replacement_issued="Y"),
        T(ticket_id="f1", transfers="1.5"),
    ]
    rep = validate(rows, rows, ROSTER)
    assert rep["same_order_cross_ticket_pairs"] == [
        {"order": "OX", "refund_tickets": ["r1"], "replacement_tickets": ["r2"]}
    ]
    assert rep["transfer_non_integral"] == 1
    from src.metrics import transfer_count
    assert transfer_count(rows, WS) == 0  # fractional excluded, not floored


def test_channel_case_normalised():
    rows = [T(ticket_id="a", channel="Chat")]
    assert channel_mix(rows, WS) == {"chat": 100.0}
