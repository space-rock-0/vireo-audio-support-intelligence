"""Compute Phase 5 metrics from labeled sample + automated digest-factuality
audit. Writes evaluation/validation_metrics.json. Run after apply_labels.py.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import date  # noqa: E402
from src.common import in_week, parse_ts  # noqa: E402
from src.ingest import load_tickets, deduplicate  # noqa: E402
from src import metrics, cost  # noqa: E402
from src.leaderboard import tier1_leaderboard, specialist_table  # noqa: E402
from src.themes import assign_themes, count_themes, weekly_digest_sections  # noqa: E402
from src.ingest import load_roster  # noqa: E402

EV = os.path.dirname(__file__)
VEO = os.environ.get("VIREO_DATA_DIR", os.path.join(EV, "..", "..", "Veo"))


def main():
    with open(os.path.join(EV, "sample_labels.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {"reviewer": "agent-reviewer-v1 (single; strict written rules; see report.md limitations)"}

    # --- theme accuracy ---
    th = [r for r in rows if r["stratum"] == "theme"]
    agree = [r for r in th if r["human_label"] == r["predicted"]]
    out["theme"] = {"n": len(th), "agree": len(agree),
                    "accuracy": round(len(agree) / len(th), 3)}
    by_method: dict = {}
    for r in th:
        m = by_method.setdefault(r["method"], {"n": 0, "agree": 0})
        m["n"] += 1
        m["agree"] += 1 if r["human_label"] == r["predicted"] else 0
    for m in by_method.values():
        m["accuracy"] = round(m["agree"] / m["n"], 3)
    out["theme"]["by_method"] = by_method
    out["theme"]["errors"] = [
        {"id": r["item_id"], "pred": r["predicted"], "human": r["human_label"],
         "note": r["notes"]} for r in th if r["human_label"] != r["predicted"]
    ]

    # --- repeat precision/recall (positive class = same-issue) ---
    rp = [r for r in rows if r["stratum"] == "repeat"]
    tp = sum(1 for r in rp if r["predicted"] == "same-issue" and r["human_label"] == "same-issue")
    fp = sum(1 for r in rp if r["predicted"] == "same-issue" and r["human_label"] != "same-issue")
    fn = sum(1 for r in rp if r["predicted"] != "same-issue" and r["human_label"] == "same-issue")
    tn = sum(1 for r in rp if r["predicted"] != "same-issue" and r["human_label"] != "same-issue")
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    out["repeat"] = {"n": len(rp), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                     "precision": round(prec, 3), "recall": round(rec, 3),
                     "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0}
    out["repeat"]["fp_examples"] = [r["item_id"] for r in rp
                                    if r["predicted"] == "same-issue" and r["human_label"] != "same-issue"]
    out["repeat"]["fn_examples"] = [r["item_id"] for r in rp
                                    if r["predicted"] != "same-issue" and r["human_label"] == "same-issue"]

    # --- refund ---
    rf = [r for r in rows if r["stratum"] == "refund"]
    out["refund"] = {"n": len(rf),
                     "same_ticket_confirmed": sum(1 for r in rf if r["human_label"] == "confirmed-violation"),
                     "same_order_violations": sum(1 for r in rf if r["human_label"] == "violation")}

    # --- automated digest-factuality audit (30 checks, week 2026-06-21) ---
    raw = load_tickets(VEO)
    canon, _ = deduplicate(raw)
    roster = load_roster(VEO)
    by_id = {r["ticket_id"]: r for r in canon}
    WS, PW = date(2026, 6, 22), date(2026, 6, 15)
    wk = [r for r in canon if in_week(parse_ts(r["created_at"]), WS)]
    pwk = [r for r in canon if in_week(parse_ts(r["created_at"]), PW)]
    a = assign_themes(canon)
    cw = count_themes({t: a[t] for r in wk for t in [r["ticket_id"]]})
    cpw = count_themes({t: a[t] for r in pwk for t in [r["ticket_id"]]})
    sec = weekly_digest_sections("2026-06-22", cw, len(wk), cpw)
    checks = []
    checks.append(("digest_total==week_rows", sec["total_tickets"] == len(wk)))
    checks.append(("theme_counts_sum==total", sum(t["n"] for t in sec["themes"]) == sec["total_tickets"]))
    for t in sec["themes"][:5]:  # count correctness x5
        recount = sum(1 for r in wk if a[r["ticket_id"]]["theme"] == t["theme"])
        checks.append((f"count[{t['theme']}]", t["n"] == recount))
    for r in wk[:10]:  # id+date evidence x10
        checks.append((f"id-date[{r['ticket_id']}]",
                       r["ticket_id"] in by_id and in_week(parse_ts(r["created_at"]), WS)))
    board, un1 = tier1_leaderboard(canon, roster, WS)
    spec, un2 = specialist_table(canon, roster, WS)
    att = [r for r in canon if r["status"] in ("resolved", "closed")
           and in_week(parse_ts(r["resolved_at"]), WS)]
    checks.append(("leaderboard_reconciles",
                   sum(b["tickets_completed"] for b in board) + sum(s["tickets_completed"] for s in spec) + len(un1) == len(att)))
    checks.append(("tier2_absent_from_board", all("Warranty" not in b["team"] for b in board)))
    # Money checks recomputed from RAW week rows with literal policy rates —
    # not via the functions under test (else they verify Python multiplies).
    _targets = {"chat": 15, "email": 480, "voice": 120, "social": 240}
    _rates = {"chat": 210, "email": 260, "voice": 520, "social": 240}
    raw_br = 0
    for r in wk:
        c, f = parse_ts(r["created_at"]), parse_ts(r["first_response_at"])
        if c is None or f is None:
            continue
        if (f - c).total_seconds() / 60 > _targets[r["channel"]]:
            raw_br += 1
    br = metrics.sla_breaches(canon, WS)
    checks.append(("sla_breaches_recomputed", sum(br.values()) == raw_br))
    checks.append(("sla_credit==350x", cost.sla_credit_exposure(canon, WS) == raw_br * 350))
    raw_tc = sum(int(float(r["transfers"])) for r in wk if (r["transfers"] or "").strip())
    checks.append(("transfer_count_recomputed", metrics.transfer_count(canon, WS) == raw_tc))
    checks.append(("transfer_cost==305x", cost.transfer_cost(canon, WS) == raw_tc * 305))
    raw_cc = sum(_rates[r["channel"]] for r in wk)
    cc = cost.contact_cost(canon, WS)
    checks.append(("contact_total_recomputed", cc["total_inr"] == raw_cc))
    reps = metrics.repeat_contact_candidates(canon, WS)
    checks.append(("repeat_ids_exist", all(p["repeat_ticket_id"] in by_id and p["prior_ticket_id"] in by_id for p in reps)))
    errs = [name for name, ok in checks if not ok]
    out["factuality"] = {"checks": len(checks), "errors": len(errs), "error_rate": round(len(errs) / len(checks), 3),
                         "failed": errs}
    with open(os.path.join(EV, "validation_metrics.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1)[:2000])


if __name__ == "__main__":
    main()
