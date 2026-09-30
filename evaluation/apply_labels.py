"""Apply reviewer-v1 labels (agent reviewer, strict adjudication rules from
theme_taxonomy.json + Task A/B in prompts/judge_or_review.txt).
Single reviewer; limitation disclosed in evaluation/report.md.
Run: python evaluation/apply_labels.py  (rewrites sample_labels.csv)
"""
import csv
import os

PATH = os.path.join(os.path.dirname(__file__), "sample_labels.csv")

# item_id -> (human_label, notes). Absent = agree with predicted.
LABELS = {
    # --- theme corrections (human = corrected canonical theme) ---
    "TH-TK-245392": ("Billing & Payments", "invoice/GST regen is billing-domain action, not account access"),
    "TH-TK-242757": ("Charging & Battery", "primary symptom battery drain; fw push was the attempted fix"),
    "TH-TK-241840": ("App & Firmware", "progress-bar hang is fw-update-stuck, not battery charging"),
    "TH-TK-254652": ("App & Firmware", "spinning-circle brick, replacement raised as bricked"),
    "TH-TK-252014": ("Product Enquiry", "pre-sales connect-two-together query; agent shared specs (adjudication note)"),
    "TH-TK-248394": ("Returns & Refunds", "cancellation + refund initiated"),
    "TH-TK-246439": ("Product Enquiry", "pre-sales connect-two query per adjudication note"),
    "TH-TK-243566": ("Billing & Payments", "failed-payment-no-order, DUP-PAYMENT class; refund issued"),
    "TH-TK-248223": ("Charging & Battery", "case-not-charging resolved by cleaning; no warranty claim/RMA"),
    "TH-TK-244986": ("Delivery & Shipping", "transit damage + courier damage claim"),
    # --- repeat FPs: predicted same-issue, human says different symptom ---
    "RP-TK-249673": ("not-same-issue", "delivery-delay vs warranty-claim-status: different symptoms"),
    "RP-TK-252676": ("not-same-issue", "app-crash vs out-for-delivery tracking: different symptoms"),
    "RP-TK-250274": ("not-same-issue", "GST-invoice request vs laptop-pairing failure: different symptoms"),
    "RP-TK-254890": ("not-same-issue", "refund-delay vs duplicate-charge discovery; same order, borderline, strict-read different symptom"),
    "RP-TK-248015": ("not-same-issue", "DOA damage vs address-change request: different symptoms"),
    "RP-TK-242037": ("not-same-issue", "payment failure vs compatibility query: different symptoms"),
    # --- repeat FN: predicted not-same-issue, human says same issue ---
    "RP-TK-246305": ("same-issue", "wrong-item delivered twice; 'nothing has changed' recurrence, same product"),
    # --- borderline TP kept with note ---
    "RP-TK-250012": ("same-issue", "cancel-then-return-pickup same-order resolution chain; kept as same issue"),
    # --- refund: same-order pairs are pattern-not-violation ---
    "RF-VR880243": ("legitimate-separate-issues", "duplicate-charge refund + defective-unit replacement: distinct issues, compliant"),
    "RF-VR880347": ("sequential-remedy-chain", "pickup-miss/refund-promise texts; no same-ticket conflict"),
    "RF-VR880705": ("sequential-remedy-chain", "refund-delay + cancel + follow-up; no same-ticket conflict"),
    "RF-VR880710": ("sequential-remedy-chain", "pickup-miss then display-fault; no same-ticket conflict"),
}
# 4 same-ticket conflicts confirmed violations:
for tid in ("TK-241405", "TK-244372", "TK-250483", "TK-252411"):
    LABELS[f"RF-{tid}"] = ("confirmed-violation", "refund amount + replacement_issued=Y on one ticket (policy §5 escalation)")


def main():
    with open(PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    n = 0
    for r in rows:
        if r["item_id"] in LABELS:
            r["human_label"], r["notes"] = LABELS[r["item_id"]]
            n += 1
        else:
            r["human_label"] = r["predicted"]  # agree
    with open(PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"labeled {n} deviations, {len(rows) - n} agreements")


if __name__ == "__main__":
    main()
