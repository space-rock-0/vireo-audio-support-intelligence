"""Vireo weekly digest + Tier-1 leaderboard. One command:

    python run_digest.py --week 2026-06-22 --output outputs/

Week must be a Monday (YYYY-MM-DD); other days are normalized back to Monday
with a warning. Data: ../Veo/*.csv or $VIREO_DATA_DIR. Paid API cost: Rs 0
(local rule/TF-IDF path; Ollama attempted only if reachable, never required).
"""
import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.common import in_week, parse_ts, week_monday  # noqa: E402
from src.ingest import load_reference_sets, load_roster, load_tickets, deduplicate  # noqa: E402
from src.leaderboard import (  # noqa: E402
    LEADERBOARD_LABEL,
    TIER2_NOTE,
    specialist_table,
    tier1_leaderboard,
)
from src.validation import validate  # noqa: E402
from src.themes import (  # noqa: E402
    OTHER,
    assign_themes,
    count_themes,
    emerging_terms,
    group_top_terms,
    load_taxonomy,
    weekly_digest_sections,
)
from src.metrics import (  # noqa: E402
    channel_mix,
    csat_stats,
    repeat_contact_candidates,
    same_issue_filter,
    sla_breaches,
    sla_missing_count,
    status_mix,
    transfer_count,
    weekly_volume,
)
from src.cost import (  # noqa: E402
    contact_cost,
    sla_credit_exposure,
    transfer_cost,
)

REPO = os.path.dirname(os.path.abspath(__file__))


def load_family_map(data_dir):
    fam = {}
    with open(os.path.join(data_dir, "products.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fam[r["sku"].strip()] = r["family"].strip()
    return fam


def write_csv(path, rows, cols):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def render_digest(path, ctx):
    L = []
    L.append(f"# Vireo Support Weekly Digest — week of {ctx['week']}")
    L.append("")
    L.append(f"**{LEADERBOARD_LABEL}** (see leaderboard table below). {TIER2_NOTE}")
    L.append("")
    L.append("## 1. Business box")
    L.append(f"- This week: {ctx['repeat_wk']} repeat candidates ({ctx['same_issue_wk']} same-issue by filter). "
             f"Window: repeat ticket created this week, prior resolved within the previous 30 days.")
    L.append(f"- Baseline: ~29 filter-positive/week (~12–19 true same-issue; committed case uses the range floor — Phase 5 eval).")
    L.append(f"- Quarter exposure ≈ ₹40–68k at current volume; 25% cut ≈ ₹10–17k/quarter.")
    L.append("")
    L.append(f"## 2. Volume: {ctx['total']} tickets (prev week {ctx['prev_total']})")
    L.append("")
    L.append("| Theme | n | share | WoW |")
    L.append("|---|---|---|---|")
    for t in ctx["sections"]["themes"]:
        L.append(f"| {t['theme']} | {t['n']} | {t['pct']}% | {t['wow']:+d} |")
    L.append("")
    L.append("## 3. Cost signals")
    L.append(f"- SLA breaches: {ctx['sla_total']} (credit exposure ₹{ctx['sla_cost']:,})")
    L.append(f"- Transfers: {ctx['transfers']} (re-handling ₹{ctx['transfer_cost']:,})")
    L.append(f"- Contact cost this week: ₹{ctx['contact']['total_inr']:,}")
    L.append(f"- CSAT: n={ctx['csat']['n']}, {ctx['csat']['response_rate_pct']}%, mean {ctx['csat']['mean']}")
    L.append("")
    L.append("## 4. Tier-1 attendance leaderboard (top 15)")
    L.append("")
    L.append("| # | Agent | Team | Shift | Completed |")
    L.append("|---|---|---|---|---|")
    for i, b in enumerate(ctx["board"][:15], 1):
        L.append(f"| {i} | {b['agent_name']} ({b['agent_id']}) | {b['team']} | {b['shift']} | {b['tickets_completed']} |")
    L.append("")
    L.append(f"_Specialist teams (Logistics/Billing/Returns/Tier 2) tracked separately: "
             f"{len(ctx['spec'])} agents, not ranked against Tier 1._")
    L.append("")
    L.append("## 5. Suggested next actions (threshold-triggered, owner = role)")
    for line in ctx["actions"]:
        L.append(f"- {line}")
    if not ctx["actions"]:
        L.append("- No threshold crossings — routine watch until next digest.")
    L.append("")
    L.append("## 6. Limitations")
    L.append("- Theme accuracy ~76%; repeat filter precision 60% — counts are estimates with evidence IDs in themes.csv.")
    L.append("- Legacy resolved_at excluded from durations; SLA uses first-response only.")
    L.append("- 4 same-ticket refund+replacement conflicts need Team Lead + Finance escalation (see validation.json).")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True, help="Monday YYYY-MM-DD")
    ap.add_argument("--output", default="outputs")
    args = ap.parse_args()
    try:
        day = datetime.strptime(args.week, "%Y-%m-%d").date()
    except ValueError:
        sys.exit("error: --week must be YYYY-MM-DD")
    ws = week_monday(day)
    if ws != day:
        print(f"warning: {day} is not a Monday; normalized to {ws}")
    prev = ws - timedelta(days=7)
    data_dir = os.environ.get("VIREO_DATA_DIR", os.path.join(REPO, "..", "Veo"))
    if not os.path.isdir(data_dir):
        sys.exit(f"error: data dir not found: {data_dir} (set VIREO_DATA_DIR)")
    missing = [f for f in ("tickets.csv", "agents.csv", "customers.csv",
                           "orders.csv", "products.csv")
               if not os.path.isfile(os.path.join(data_dir, f))]
    if missing:
        sys.exit(f"error: missing in {data_dir}: {', '.join(missing)}")

    raw = load_tickets(data_dir)
    canon, quar = deduplicate(raw)
    roster = load_roster(data_dir)
    fam = load_family_map(data_dir)
    by_id = {r["ticket_id"]: r for r in canon}
    wk = [r for r in canon if in_week(parse_ts(r["created_at"]), ws)]
    pwk = [r for r in canon if in_week(parse_ts(r["created_at"]), prev)]
    if not wk:
        print(f"warning: no tickets in week {ws} (outside 2024-12-30–2026-06-29 data?) — outputs will be empty")

    assignment = assign_themes(canon)
    cw = count_themes({t: assignment[t] for r in wk for t in [r["ticket_id"]]})
    cpw = count_themes({t: assignment[t] for r in pwk for t in [r["ticket_id"]]})
    sections = weekly_digest_sections(str(ws), cw, len(wk), cpw)

    board, unres = tier1_leaderboard(canon, roster, ws)
    spec, unres2 = specialist_table(canon, roster, ws)
    assert (sum(b["tickets_completed"] for b in board)
            + sum(s["tickets_completed"] for s in spec) + len(unres) == len(
                [r for r in canon if r["status"] in ("resolved", "closed")
                 and in_week(parse_ts(r["resolved_at"]), ws)])) and not unres2, \
        "board + specialist + unresolved must reconcile to attendance"
    reps = repeat_contact_candidates(canon, ws)
    si = sum(1 for p in reps if same_issue_filter(p))
    cc = contact_cost(canon, ws)
    gterms, _ = group_top_terms(wk, fam, k=5)
    em = emerging_terms([r.get("customer_message") or "" for r in wk],
                        [r.get("customer_message") or "" for r in pwk], k=8)

    # Threshold-triggered action box (deterministic; owners are roles, not names)
    br_wk = sla_breaches(canon, ws)
    actions = []
    for t in sections["themes"]:
        if t["wow"] >= 10 and t["theme"] != OTHER:
            actions.append(f"Spike: {t['theme']} (+{t['wow']} WoW) — owner: Support Ops lead; "
                           f"triage batch/product cause by next digest.")
    if br_wk.get("email", 0) > 10:
        actions.append(f"Email first-response tail: {br_wk['email']} breaches — owner: Queue lead; "
                       f"review staffing and queue order.")
    wk_conf = sum(1 for r in wk if (r.get("refund_amount_inr") or "").strip()
                  and (r.get("replacement_issued") or "").strip().upper() == "Y")
    if wk_conf:
        actions.append(f"{wk_conf} refund+replacement conflict(s) this week — owner: Team Lead + Finance "
                       f"(policy §5: escalate same day).")
    if len(reps) > 60:
        actions.append(f"Repeat candidates {len(reps)} vs ~48/wk average — owner: Support Ops lead; "
                       f"fix-first-time review of top repeat themes.")

    out = os.path.abspath(args.output)
    os.makedirs(out, exist_ok=True)
    ctx = {
        "week": str(ws), "total": len(wk), "prev_total": len(pwk),
        "sections": sections, "board": board, "spec": spec,
        "repeat_wk": len(reps), "same_issue_wk": si,
        "sla_total": sum(sla_breaches(canon, ws).values()),
        "sla_cost": sla_credit_exposure(canon, ws),
        "transfers": transfer_count(canon, ws),
        "transfer_cost": transfer_cost(canon, ws),
        "contact": cc, "csat": csat_stats(canon, ws),
        "emerging": em, "actions": actions,
    }
    render_digest(os.path.join(out, "digest.md"), ctx)
    write_csv(os.path.join(out, "leaderboard.csv"), board,
              ["agent_id", "agent_name", "team", "shift", "site", "tickets_completed"])
    write_csv(os.path.join(out, "specialist.csv"), spec,
              ["agent_id", "agent_name", "team", "shift", "site", "tickets_completed"])
    write_csv(os.path.join(out, "themes.csv"),
              [{"ticket_id": r["ticket_id"], **assignment[r["ticket_id"]]} for r in wk],
              ["ticket_id", "theme", "confidence", "method"])
    kpis = {
        "week": str(ws), "volume": weekly_volume(canon, ws),
        "channel_mix": channel_mix(canon, ws), "status_mix": status_mix(canon, ws),
        "sla_breaches": sla_breaches(canon, ws), "sla_missing": sla_missing_count(canon, ws),
        "csat": csat_stats(canon, ws), "contact_cost_inr": cc,
        "transfer_cost_inr": transfer_cost(canon, ws),
        "repeat_candidates": len(reps), "repeat_same_issue": si,
        "tier1_agents": len(board), "specialist_agents": len(spec),
        "unresolved_attendance": unres,
        "group_top_terms": gterms,
    }
    with open(os.path.join(out, "kpis.json"), "w") as f:
        json.dump(kpis, f, indent=1)
    with open(os.path.join(out, "validation.json"), "w") as f:
        json.dump(validate(raw, canon, roster, load_reference_sets(data_dir)), f, indent=1, default=str)
    with open(os.path.join(out, "cost.json"), "w") as f:
        json.dump({"paid_api_cost_inr_per_run": 0,
                   "paid_api_cost_inr_per_month_at_650_per_week": 0,
                   "basis": "local rule/TF-IDF path; no paid model calls (D9/D11)"}, f, indent=1)
    print(f"week={ws} tickets={len(wk)} themes={len(cw)} "
          f"board={len(board)} spec={len(spec)} repeat={len(reps)}/{si} -> {out}")


if __name__ == "__main__":
    main()
