# VIREO AUDIO — PHASE 5 EVALUATION REPORT (29 Sep 2026)

**Reviewer:** agent-reviewer-v1 (single reviewer, strict written rules: taxonomy definitions + adjudication note + Task A/B). **Limitation, stated plainly:** one non-human reviewer, no inter-rater agreement, small-n strata. Numbers below are measured on the sample — not population guarantees. Wilson 95% intervals shown where n permits.
Machine source: `evaluation/validation_metrics.json`. Sample: `evaluation/sample_labels.csv` (seed 42).

## 1. Sample design (N=79)

- **Theme (41):** 11 predicted themes × 4 target (2 taxonomy-method + 1 rule + 1 fallback/disagreement); 3 short where small-theme pools exhausted (41, not 44).
- **Repeat (30):** 15 `same_issue_filter`-positive (8 same-order, 7 same-category-only) + 15 filter-negative candidates.
- **Refund (8):** 4 same-ticket conflicts + first 4 same-order pairs by order id (deterministic, NOT random — no prevalence claim over the 99).
- **Digest factuality (25 automated checks):** week 2026-06-22 — totals, 5 recounts, 10 ID/date evidence, leaderboard reconciliation, Tier-2 absence, SLA/transfer/contact arithmetic, repeat ID existence.

## 2. Theme classification: accuracy 75.6% (31/41)

| Method | n | Accuracy |
|---|---|---|
| taxonomy (stored-tag map) | 30 | **80.0%** (24/30) |
| rule (keyword rescue) | 10 | **70.0%** (7/10) |
| rule-fallback | 1 | 0% (n=1, ignore) |

10 errors, all single-theme confusions (no multi-label adjudication needed):
- Firmware-vs-battery (3): TH-TK-242757, TH-TK-241840, TH-TK-254652 — progress-bar/brick vs drain wording.
- Enquiry-vs-connectivity (2): TH-TK-252014, TH-TK-246439 — pre-sales connect-two queries (adjudication note now covers).
- Billing-boundary (2): TH-TK-245392 (invoice/GST), TH-TK-243566 (failed-payment).
- Damage-routing (1): TH-TK-244986 (transit damage → Delivery).
- Cancel-routing (1): TH-TK-248394 (cancel+refund → Returns).
- Charging-vs-warranty (1): TH-TK-248223 (case fault, no claim → Charging).
Wilson 95% CI overall: **60–87%**. Digest impact: weekly theme shares are directionally reliable at n≈150; point shares carry sampling + accuracy noise — the digest shows counts and WoW deltas, never rank-claims off small gaps.

## 3. Repeat-contact: precision 60% / recall 90% / F1 0.72 (n=30)

- TP 9 · FP 6 · FN 1 · TN 14.
- Recall is in-sample unweighted over the balanced 15/15 draw; population is ~60% filter-positive, so the reweighted recall is ≈93% — same direction, noted for method honesty.
- **FP pattern (all 6): same-order, different-symptom** — invoice→pairing, cancel→address-change, refund-delay→duplicate-charge, DOA-damage→address-change, payment-failure→compatibility-query, delivery-delay→warranty-status. The filter's `same_order` leg over-trusts order identity.
- **FN pattern (1): same-symptom, different-order** — wrong-item delivered twice (RP-TK-246305). Recall loss lives in replacement/re-shipment chains where order_id changes.
- Wilson 95% CI: precision **36–80%**, recall **60–98%**. Wide — the sample is small and the reviewer is single. The business case uses the conservative end (see §5).

## 4. Refund/replacement: 4/4 conflicts confirmed, 0/4 same-order violations

- All 4 same-ticket refund+Y flags are genuine policy §5 escalations.
- All 4 sampled same-order cross-ticket pairs are compliant patterns (distinct issues on one order, or sequential remedy chains). **The 99-order co-occurrence set is not a violation set** — confirmed by sample, as the baseline report already framed it.

## 5. Digest factuality: 25/25 checks pass, error rate 0.0

Money and count checks recompute from raw week rows with literal policy rates (not via the functions under test); theme recounts are self-consistency; leaderboard reconciliation + Tier-2 absence are independent. No failures.

## 6. Error taxonomy (observed instances)

- ambiguous-complaint: TH-TK-245392 (invoice in account text).
- multi-issue-ticket: TH-TK-248394, TH-TK-244986, plus 1,953 disagreement-audit rows with both themes present (deterministic full-population count, not human-validated).
- firmware-vs-battery wording: 3 theme errors.
- same-order-different-symptom: 6 repeat FPs.
- same-symptom-different-order: 1 repeat FN (re-shipment chains).
- slang/code-switching: present in sample (Hinglish) but caused 0 measured errors — rules handled it.
- migration artifact: none observed in sample (dedup + trust-flag working).

## 7. Business-metric setting (avoidable share, conservative end)

- Deterministic filter keeps 2,267/3,787 candidate pairs (59.9%).
- Measured filter precision 60% (CI 36–80%) → estimated true same-issue ≈ 2,267 × 0.60 ≈ 1,360 / 18 mo; recall 90% implies true total ≈ 1,360/0.9 ≈ **1,510 / 18 mo ≈ 19/week**.
- At mean contact cost ₹274: central estimate **≈19/week ≈ ₹5.2k/week ≈ ₹68k/quarter exposure**; precision-CI-implied range **≈12–26/wk (≈₹40–95k/qtr)**.
- **Committed business metric:** "Reduce 30-day same-issue repeat contacts from ~12–19/week (~₹40–68k/qtr exposure) by 25% via fix-first-time + same-device history surfacing — worth ~₹10–17k/quarter at current volume, central ~₹17k." The committed case uses the range floor; the central number is shown alongside, never as a promise.
- Opportunity vs realized savings is separated everywhere (brief §12): the tool identifies the class; realization needs operational action.

## 8. What was NOT fixed within budget (known failures shipped)

- Theme accuracy 75.6% stands — fixing needs labeled-data iteration, out of the 5-hour cap.
- Repeat FP leg (`same_order` over-trust) and FN leg (order-changing re-shipments) documented, not re-tuned — re-tuning on n=30 would be overfitting.
- Single reviewer, no inter-rater reliability. Second reviewer recommended before any SLA-linked incentive use.
