"""Data-quality checks from Phase 1 anomalies A1–A13. Pure function over
(raw_rows, canonical_rows, roster) -> validation_report dict."""
from __future__ import annotations

from .common import parse_day, parse_ts, to_num, valid_csat
from .leaderboard import resolve_roster


def validate(
    raw_rows: list[dict], rows: list[dict], roster: list[dict], refs: dict | None = None
) -> dict:
    rep: dict = {}

    # A1: duplicate ticket_ids in raw export (single pass: id -> counts + sources)
    stats: dict[str, dict] = {}
    for r in raw_rows:
        s = stats.setdefault(r["ticket_id"], {"n": 0, "srcs": set()})
        s["n"] += 1
        s["srcs"].add(r["source_system"])
    dup = {k: v for k, v in stats.items() if v["n"] > 1}
    rep["duplicate_ticket_id_groups"] = len(dup)
    rep["duplicate_extra_rows"] = sum(v["n"] - 1 for v in dup.values())
    rep["duplicate_cross_system_groups"] = sum(1 for v in dup.values() if len(v["srcs"]) > 1)

    # A2: resolution-before-first-response by source (canonical)
    for src in ("helpdesk", "legacy_fd"):
        sub = [r for r in rows if r["source_system"] == src and r["resolved_at"]]
        bad = sum(
            1
            for r in sub
            if parse_ts(r["resolved_at"]) is not None
            and parse_ts(r["first_response_at"]) is not None
            and parse_ts(r["resolved_at"]) < parse_ts(r["first_response_at"])
        )
        rep[f"res_before_first_{src}"] = {"n_resolved": len(sub), "violations": bad}

    # A2b: first_response before creation
    rep["first_before_created"] = sum(
        1
        for r in rows
        if parse_ts(r.get("first_response_at")) is not None
        and parse_ts(r.get("created_at")) is not None
        and parse_ts(r["first_response_at"]) < parse_ts(r["created_at"])
    )

    # A4: status <-> resolved_at consistency
    rep["status_timestamp_mismatch"] = sum(
        1
        for r in rows
        if ((r.get("status") or "").strip().lower() in ("resolved", "closed"))
        != bool((r.get("resolved_at") or "").strip())
    )

    # A5: financials
    neg, no_code, non_num, conflicts = 0, 0, 0, []
    for r in rows:
        amt = (r.get("refund_amount_inr") or "").strip()
        if amt:
            v = to_num(amt)
            if v is None:
                non_num += 1
            else:
                if v < 0:
                    neg += 1
                if not (r.get("refund_reason_code") or "").strip():
                    no_code += 1
                if (r.get("replacement_issued") or "").strip().upper() == "Y":
                    conflicts.append(r["ticket_id"])
    rep["refund_negative"] = neg
    rep["refund_no_code"] = no_code
    rep["refund_non_numeric"] = non_num
    rep["same_ticket_refund_replacement"] = conflicts

    # A5-ext: same ORDER carrying refund + replacement on different tickets.
    # Co-occurrence pattern for Phase 5 case review — NOT confirmed violations.
    by_order: dict[str, dict] = {}
    for r in rows:
        o = (r.get("order_id") or "").strip()
        if not o:
            continue
        e = by_order.setdefault(o, {"ref": [], "repl": []})
        if (r.get("refund_amount_inr") or "").strip():
            e["ref"].append(r["ticket_id"])
        if (r.get("replacement_issued") or "").strip().upper() == "Y":
            e["repl"].append(r["ticket_id"])
    rep["same_order_cross_ticket_pairs"] = [
        {"order": o, "refund_tickets": e["ref"], "replacement_tickets": e["repl"]}
        for o, e in sorted(by_order.items())
        if e["ref"] and e["repl"] and not set(e["ref"]) & set(e["repl"])
    ]

    # A6: CSAT out of range (same predicate as metrics.valid_csat)
    rep["csat_out_of_range"] = sum(
        1
        for r in rows
        if (r.get("csat_score") or "").strip() not in ("", "0")
        and valid_csat(r.get("csat_score")) is None
    )

    # Transfers: non-integral values are data errors (metrics counts integral only)
    rep["transfer_non_integral"] = sum(
        1
        for r in rows
        if (r.get("transfers") or "").strip()
        and (to_num(r.get("transfers")) is None or to_num(r.get("transfers")) != int(to_num(r.get("transfers"))))
    )

    # A7/A8: join coverage on canonical rows
    rep["blank_order_id"] = sum(1 for r in rows if not (r.get("order_id") or "").strip())
    rep["blank_agent_id"] = sum(1 for r in rows if not (r.get("agent_id") or "").strip())
    rep["blank_customer_id"] = sum(1 for r in rows if not (r.get("customer_id") or "").strip())
    rep["blank_product_sku"] = sum(1 for r in rows if not (r.get("product_sku") or "").strip())

    # A13: text completeness
    rep["empty_customer_message"] = sum(
        1 for r in rows if not (r.get("customer_message") or "").strip()
    )
    rep["empty_agent_notes"] = sum(
        1 for r in rows if not (r.get("agent_notes") or "").strip()
    )

    # Timestamps parseable
    rep["invalid_created"] = sum(
        1 for r in rows if parse_ts(r.get("created_at")) is None
    )
    rep["invalid_first_response"] = sum(
        1
        for r in rows
        if (r.get("first_response_at") or "").strip()
        and parse_ts(r.get("first_response_at")) is None
    )

    # Roster: overlaps + unresolved canonical tickets
    by_agent: dict[str, list] = {}
    for r in roster:
        by_agent.setdefault((r.get("agent_id") or "").strip(), []).append(r)
    overlaps = 0
    for aid, recs in by_agent.items():
        ivals = [
            (parse_day(x.get("from_date")) or parse_day("1900-01-01"),
             parse_day(x.get("to_date")) or parse_day("9999-12-31"))
            for x in recs
        ]
        for i in range(len(ivals)):
            for j in range(i + 1, len(ivals)):
                if ivals[i][0] <= ivals[j][1] and ivals[j][0] <= ivals[i][1]:
                    overlaps += 1
    rep["roster_overlaps"] = overlaps
    # Unmatched roster, two definitions (different questions):
    # - any_row: data-hygiene over all canonical rows (created-date fallback)
    # - attendance: leaderboard-relevant (resolved-date, attendance subset)
    un_any, un_att = 0, 0
    for r in rows:
        att = (r.get("status") or "").strip().lower() in ("resolved", "closed")
        res_day = parse_ts(r.get("resolved_at"))
        any_day = res_day or parse_ts(r.get("created_at"))
        if any_day is None or resolve_roster(
            (r.get("agent_id") or "").strip(), any_day.date(), roster
        ) is None:
            un_any += 1
        if att and (
            res_day is None
            or resolve_roster(
                (r.get("agent_id") or "").strip(), res_day.date(), roster
            )
            is None
        ):
            un_att += 1
    rep["roster_unresolved_any_row"] = un_any
    rep["roster_unresolved_attendance"] = un_att
    # FK orphan checks (council M2): every non-blank key must resolve against
    # its reference table. refs = {"orders": set, "customers": set, "skus": set,
    # "agents": set}; absent refs are skipped, never assumed.
    refs = refs or {}
    for col, refkey in (("order_id", "orders"), ("customer_id", "customers"),
                        ("product_sku", "skus"), ("agent_id", "agents")):
        ref = refs.get(refkey)
        if ref is None:
            rep[f"orphan_{col}"] = None
            continue
        rep[f"orphan_{col}"] = sum(
            1 for r in rows
            if (r.get(col) or "").strip() and (r.get(col) or "").strip() not in ref
        )
    rep["canonical_rows"] = len(rows)
    return rep
