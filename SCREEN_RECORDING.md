# Screen recording — 3 minutes, no slides (direct screen walkthrough)

## Timeline

### 0:00–0:25 Problem + design
- Priya wants a weekly digest + leaderboard, "no platform". Arjun: must take
  contacts out of the queue, no surprise model bill. Neha: don't rank warranty
  on counts; "already told your colleague" repeats.
- Design: deterministic Python owns numbers; local rules/TF-IDF propose
  themes; Tier-1-only board; one quantified metric. Show repo tree.

### 0:25–1:00 Prompts
- Open `prompts/theme_extraction.txt` (v1): structured JSON, temp 0,
  evidence-IDs-only rule. `prompts/digest_summary.txt`: polish guardrail
  (numbers immutable). `prompts/judge_or_review.txt`: eval adjudication.

### 1:00–1:35 Version changes + discarded
- v1 keyword rules → regex word-boundaries after review caught
  repair→pair / failed→led misfires (show diff + recount delta 82→67 Other).
- Discarded: paid per-ticket classification, free-form summaries, re-tuning
  on n=30. Show `git log` or the phase files.

### 1:35–2:25 Final tool demo
- `python run_digest.py --week 2026-06-22 --output outputs/` (live run).
- Open `outputs/digest.md`: business box, theme table, leaderboard top 15
  with Tier-2 note. Open `leaderboard.csv`.

### 2:25–2:50 Validation
- `pytest tests/` → 35 passed. Open `evaluation/report.md`: theme 75.6%,
  repeat P60/R90, factuality 25/25. Show one FP example (same-order,
  different-symptom).

### 2:50–3:00 Cost + business outcome
- `outputs/cost.json`: Rs 0/run, Rs 0/month. Business metric: ~12–19
  repeats/week, ~₹10–17k/quarter for a 25% cut. Monday handoff (README).
