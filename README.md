# vireo-support — Weekly Digest + Tier-1 Attendance Leaderboard

Small, reproducible, AI-assisted support analytics for Vireo Audio. Deterministic
Python owns every number; a local rule/TF-IDF layer (and optionally Ollama)
proposes complaint themes only. Paid API cost: **Rs 0**.

## Prerequisites

- Python 3.10+ (`python --version`)
- No API keys. No cloud. No database server.
- Optional: Ollama with `llama3.1:8b` for LLM theme polish — never required.

## Data placement

The 5 supplied CSVs come from the assignment data pack (Vireo Audio, Set A).
Copy them into `../Veo/` (the folder next to this repo), or point anywhere
with an env var:

```
Veo/
  tickets.csv agents.csv customers.csv orders.csv products.csv
```

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/   # smoke test: 35 pass, no data needed
```

Then place the data (next section) and run the tool.

## Configuration

| Var | Default | Meaning |
|---|---|---|
| `VIREO_DATA_DIR` | `../Veo` | folder with the 5 CSVs |
| `MODEL_BACKEND` | `rule` | theme experiments only (`src/themes.py`): `rule` default, `ollama` for LLM polish. The digest CLI always runs the Rs 0 rule path. |

Prompts are versioned in `prompts/` (v1). Temperature is 0 everywhere; LLM
outputs are validated (ticket IDs ⊆ input) and all counts are recomputed in
code (`src/themes.py: count_themes`).

## Run

```bash
python run_digest.py --week 2026-06-22 --output outputs/
```

`--week` is the Monday `YYYY-MM-DD` (other days normalize back to Monday).
Try any Monday between 2024-12-30 and 2026-06-29.

## Outputs (`outputs/`)

| File | What |
|---|---|
| `digest.md` | weekly digest: business box, themes + WoW, cost signals, leaderboard top 15 |
| `leaderboard.csv` | Tier-1 attendance board (agent_id key, names display-only) |
| `specialist.csv` | Logistics/Billing/Returns/Tier-2 volumes — separate, never ranked vs Tier 1 |
| `themes.csv` | per-ticket theme + confidence + method, with evidence IDs |
| `kpis.json` | all weekly KPIs, machine-readable |
| `validation.json` | data-quality report (duplicates, timestamp violations, refund conflicts) |
| `cost.json` | Rs 0 paid cost + basis |

## Architecture

```
Veo/*.csv
    |
    v
ingest.py (DuckDB load -> dedup keep-helpdesk -> canonical 11,875)
    |
    +--> metrics.py + cost.py (deterministic KPIs: volume, SLA, CSAT, costs, repeats)
    +--> themes.py (taxonomy map + keyword rules + TF-IDF; Ollama optional)
    +--> leaderboard.py (roster-date attribution -> Tier-1 board + specialist table)
    +--> validation.py (A1-A13 checks)
    |
    v
run_digest.py -> outputs/ (digest.md, CSVs, JSONs)
```

Week basis: KPIs filter by **created** week; the leaderboard filters by
**resolved** week (attendance, D2). Tables label which.

## Data assumptions

1. Timestamps are IST display values; never converted (legacy UTC/IST shift is
   diagnostic only — no shift applied).
2. Canonical N = 11,875 (12,528 raw minus 653 quarantined cross-system
   duplicates; helpdesk copy kept).
3. `legacy_fd.resolved_at` is untrusted (69.5% precede first response) —
   excluded from durations; SLA uses creation→first-response only.
4. Attendance = resolved + closed (policy §8/§10).
5. CSAT blanks and legacy zeros are no-response, excluded from averages.
6. Business case uses policy channel costs (210/260/520/240); blended 290 only
   as fallback. The informal Rs 180 is never used (grep-tested).
7. Repeat contact = same customer, next ticket 0–30d after prior resolution;
   same-issue via deterministic filter (same product AND same order/category),
   precision 60% / recall 90% on n=30 human review.

## Known limitations

- Theme accuracy ~76% (n=41 review); weekly shares are directional.
- Repeat filter FP pattern: same-order/different-symptom; FN: re-shipment
  order changes. Avoidable share uses the range floor.
- Single reviewer, no inter-rater reliability (second reviewer needed before
  any incentive use).
- 99 same-order refund/replacement co-occurrences are patterns, not violations
  (sampled 0/4 violations); only the 4 same-ticket conflicts are escalations.
- Emerging-terms signal is weak at ~150–200 tickets/week — glance only.
- No deploy/auth/cloud; CLI + files by design ("I don't need a platform").

## AI usage and cost

- Build-time: general coding assistance; no customer data sent anywhere.
- Runtime: rule/TF-IDF theme mapping (scikit-learn, local) + optional Ollama
  `llama3.1:8b` (temp 0, validated JSON). **Rs 0 paid API per run and per month.**
- Discarded: paid per-ticket classification (Arjun's no-surprise-bill
  constraint), free-form LLM summaries (evidence rule), autonomous actions.

## Evaluation

`evaluation/`: seeded sampler (n=79), labels, metrics (theme 75.6%,
repeat P60/R90/F1 0.72, refund 4/4 + 0/4, factuality 25/25), full report.
`pytest tests/` → 35 passed.

```
MONDAY HANDOFF

1. How to run it:
   python run_digest.py --week <MONDAY YYYY-MM-DD> --output outputs/

2. The number to watch:
   30-day same-issue repeats ≈12–19/week (~₹40–68k/qtr exposure). A 25% cut
   is worth ~₹10–17k/quarter. It measures whether fixes hold first time.

3. Known risk:
   Repeat filter precision is 60% — treat weekly counts as estimates with
   evidence IDs (themes.csv), not payroll-grade truth.
```
