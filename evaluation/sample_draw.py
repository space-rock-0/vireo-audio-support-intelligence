"""Phase 5 stratified sampler. Deterministic (seed 42). Outputs
evaluation/sample_labels.csv with predicted labels; human (reviewer) fills
`human_label` + `notes`. No LLM in the sampling path.
Strata: themes 11x4=44 (2 taxonomy + 1 rule + 1 fallback/disagreement),
repeat 30 (15 same_issue_filter-positive / 15 filter-negative candidates),
refund 8 (4 same-ticket conflicts + 4 same-order pairs).
"""
import csv
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.ingest import load_tickets, deduplicate, load_roster  # noqa: E402
from src.metrics import repeat_contact_candidates, same_issue_filter  # noqa: E402
from src.themes import (  # noqa: E402
    assign_themes,
    audit_disagreements,
    explain_ticket,
)

SEED = 42
VEO = os.environ.get("VIREO_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "Veo"))
OUT = os.path.join(os.path.dirname(__file__), "sample_labels.csv")

rng = random.Random(SEED)


def excerpt(t, n=300):
    txt = f"MSG: {(t.get('customer_message') or '').strip()} || NOTES: {(t.get('agent_notes') or '').strip()}"
    txt = " ".join(txt.split())
    return txt[:n]


def main():
    raw = load_tickets(VEO)
    canon, _ = deduplicate(raw)
    by_id = {r["ticket_id"]: r for r in canon}
    assignment = assign_themes(canon)

    rows_out = []

    # --- Theme stratum: per predicted theme, 2 taxonomy + 1 rule + 1 fallback/disagree ---
    by_theme = {}
    for tid, v in assignment.items():
        by_theme.setdefault(v["theme"], []).append((tid, v["method"]))
    disag = {e["ticket_id"] for e in audit_disagreements(canon)}
    for theme, items in sorted(by_theme.items()):
        tax = [t for t in items if t[1] == "taxonomy"]
        rule = [t for t in items if t[1] == "rule"]
        fb = [t for t in items if t[1] == "rule-fallback"]
        hard = [t for t in items if t[0] in disag]
        pick = rng.sample(tax, min(2, len(tax))) + rng.sample(rule, min(1, len(rule)))
        pool = [t for t in (fb + hard) if t not in pick]
        if pool:
            pick += rng.sample(pool, 1)
        for tid, method in pick:
            t = by_id[tid]
            rows_out.append({
                "item_id": f"TH-{tid}", "stratum": "theme",
                "ticket_id": tid, "pair_id": "",
                "channel": t["channel"], "source_system": t["source_system"],
                "predicted": assignment[tid]["theme"],
                "method": method,
                "text": excerpt(t),
                "human_label": "", "notes": "",
            })

    # --- Repeat stratum: all-window pairs, 15 filter+ / 15 filter- ---
    from datetime import date, timedelta
    pairs = []
    day = date(2024, 12, 29)
    for i in range(79):
        w = day + timedelta(days=7 * i)
        pairs += repeat_contact_candidates(canon, w)
    pos = [p for p in pairs if same_issue_filter(p)]
    neg = [p for p in pairs if not same_issue_filter(p)]
    pos_pick = rng.sample(pos, 15)
    neg_pick = rng.sample(neg, 15)
    for p in pos_pick + neg_pick:
        a, b = by_id[p["prior_ticket_id"]], by_id[p["repeat_ticket_id"]]
        rows_out.append({
            "item_id": f"RP-{p['repeat_ticket_id']}", "stratum": "repeat",
            "ticket_id": p["repeat_ticket_id"], "pair_id": p["prior_ticket_id"],
            "channel": b["channel"], "source_system": b["source_system"],
            "predicted": "same-issue" if same_issue_filter(p) else "not-same-issue",
            "method": f"same_order={p['same_order']} same_product={p['same_product']} same_category={p['same_category']} gap={p['gap_days']}d",
            "text": f"PRIOR[{p['prior_ticket_id']}]: {excerpt(a, 250)} || REPEAT: {excerpt(b, 250)}",
            "human_label": "", "notes": "",
        })

    # --- Refund stratum ---
    conflicts = ["TK-241405", "TK-244372", "TK-250483", "TK-252411"]
    for tid in conflicts:
        t = by_id[tid]
        rows_out.append({
            "item_id": f"RF-{tid}", "stratum": "refund",
            "ticket_id": tid, "pair_id": "",
            "channel": t["channel"], "source_system": t["source_system"],
            "predicted": f"conflict refund={t['refund_amount_inr']} replacement={t['replacement_issued']} order={t['order_id']}",
            "method": "same-ticket",
            "text": excerpt(t),
            "human_label": "", "notes": "",
        })
    # 4 same-order cross-ticket pairs (first 4 by order id for determinism)
    from src.validation import validate
    rep = validate(raw, canon, load_roster(VEO))
    for e in rep["same_order_cross_ticket_pairs"][:4]:
        tids = e["refund_tickets"] + e["replacement_tickets"]
        texts = " || ".join(f"{tid}: {excerpt(by_id[tid], 180)}" for tid in tids if tid in by_id)
        rows_out.append({
            "item_id": f"RF-{e['order']}", "stratum": "refund",
            "ticket_id": "|".join(tids), "pair_id": e["order"],
            "channel": "", "source_system": "",
            "predicted": f"same-order co-occurrence order={e['order']}",
            "method": "cross-ticket",
            "text": texts,
            "human_label": "", "notes": "",
        })

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    print(f"wrote {len(rows_out)} items to {OUT}")
    from collections import Counter
    print(Counter(r["stratum"] for r in rows_out))


if __name__ == "__main__":
    main()
