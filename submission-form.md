# Submission form: Vireo Audio support tickets (Set A)

## 1. What did you build, and what business outcome does it move? State the number and the money.

I built a one-command weekly digest and agent leaderboard:

`python run_digest.py --week <Monday> --output outputs/`

There is no platform, dashboard or login. Priya said she does not need a platform, so I did not build one.

**The finding.** Neha's frontline complaint, "I already told your colleague this", is measurable. About **12-19 customers a week contact us again within 30 days about the same issue**. Eight in ten of those concern the same product model.

**The goal, as a number.** Cut 30-day same-issue repeats by about 25%. That takes repeats from roughly 8-13% of tickets to roughly 6-10% (12-19 a week against a mean of ~150 tickets a week).

**The money.** About **Rs 10-17k a quarter** saved. Current exposure is about Rs 40-68k a quarter, priced at the policy's per-contact costs (§ on cost, Rs 290 blended). A 25% cut of that exposure is the saving.

**How I measured it.** 11,875 de-duplicated tickets, and a repeat filter I checked by hand (precision 60%, recall 90%). Precision is weak, so read the money as an estimate. The confidence interval allows up to about 26 repeats a week (~Rs 95k a quarter exposure). I commit to the lower figure on purpose.

**Scale note.** If real volume is 650 tickets a week, exposure scales roughly with volume. I did not build the case on that, because the export does not show it .

## 2. What does one run cost, and what would a month cost at Vireo's volume (roughly 650 tickets a week)? Show the arithmetic.

**I used no paid calls in the product.**

- One run: 0 input tokens x price + 0 output tokens x price + 0 embedding cost = **Rs 0**.
- One month at 650 tickets a week: 4.33 weekly runs x Rs 0 = **Rs 0**. Cost does not depend on volume.

Theme mapping runs locally on hand-written keyword rules plus scikit-learn TF-IDF. A run takes about a minute on a laptop. `outputs/cost.json` records the zeros and the basis. An Ollama path exists in code but is never required.

**650 a week does not appear in the data.** Observed mean is ~150 a week. The busiest week is 240. The last two full months run 157-231. It could be growth since June, other channels, or a round figure. The answer holds in all three cases.

For context on money (this is not a saving):

- Observed contact cost: Rs 3,248,430 / 79 weeks x 13 = about **Rs 5.35 lakh a quarter**.
- At 650 a week: 650 x Rs 290 x 13 = about **Rs 24.5 lakh a quarter**.

## 3. How do you know it works? Sample size, how you checked, error rate, and the kind of case it gets wrong.

I checked a seeded, stratified sample of **79 items** by hand. One reviewer, written rules. There is no second reviewer, so this is v1 evidence.

| Check | n | Result |
|---|---|---|
| Theme labels | 41 | **75.6% accurate** (31/41). Stored-tag mapping 80%, keyword rescue 70% |
| Repeat-issue filter | 30 (15 flagged, 15 not) | **Precision 60%, recall 90%, F1 0.72.** Wilson 95% CI for precision: 36-80% |
| Refund cases | 8 | 0 violations found |
| Digest numbers | 25 checks | 0 errors. I recomputed money and counts from raw rows using the policy rates, not the code under test |

**Where it fails**

- Themes: firmware confused with battery, pre-sales questions confused with connectivity, invoice/GST and transit-damage routing. Ten errors are listed with ticket IDs in the report.
- Repeats: 6 false positives, all same-order but different-symptom pairs (for example an invoice query followed by a pairing problem). 1 false negative: a re-shipment that changed the order ID (wrong item sent twice).
- Two of the 30 repeat items are borderline. Together they move precision by about 13 points.

**Code checks:** 35 unit tests pass. They cover SLA boundaries, 30-day edges, roster overlap and dedup. A clean-environment rehearsal (fresh install, tests, digest) reproduced the outputs exactly.

## 4. Did you change, narrow, or push back on the client's ask? What, when, and why.

Yes, four times. Three decisions came before any code. The fourth came after baselines existed.

1. **Leaderboard.** Priya asked to rank all agents by tickets closed. I shipped a **Tier-1-only volume board** and a separate table for specialists. Policy §6 measures Tier 2 in resolution days, and Neha said those cases "take days by design". Ranking warranty agents on weekly counts would punish the people handling the hardest work. The board is still prominent. I fixed the comparison.
2. **Digest scope.** She asked for a digest of complaints. I added a repeat-contact measure, because a complaint count says what people say, not what costs money.
3. **Cost standard.** Arjun's informal Rs 180 per contact is replaced by the policy's Rs 290 blended and channel rates (210/260/520/240), following Priya's own on-record correction. A test fails the build if 180 returns to the code.
4. **Model bill.** Arjun feared a surprise per-ticket bill. The production path makes no paid calls by design.
5. **Metric choice (decided after baselines).** I did not pick one metric up front. Repeat contacts won on measurability and queue impact. SLA breaches and transfers stay as secondary levers.

## 5. What is wrong with what you are handing us? Be specific: bugs, shortcuts, things you know are off.

- **Theme accuracy is 75.6%.** Weekly theme shares are directional. A +2 point week-on-week gap is noise. The digest shows counts and changes, never rankings from small gaps.
- **Repeat precision is 60% (CI 36-80%).** The weekly figure is an estimate with evidence IDs. It is not fit for incentives or rostering without a second reviewer.
- **`resolved_at` is corrupt in 69.6% of migrated rows** (2,045 of 2,937 canonical), likely a UTC vs IST issue. I excluded it rather than repair it. This means **no handle-time baseline before Sep 2025**.
- **The repeat filter over-trusts shared order IDs** (all 6 false positives) and misses order-ID changes (the 1 false negative). I did not retune on n=30, because that would overfit. The flaw ships documented.
- **Refund cases mostly unreviewed.** 95 of 99 same-order refund + replacement pairs were not checked. I sampled 4 and found no violation. The "pattern, not violation" reading is 4/99 evidence.
- **The LLM path was never run against a real model.** No server was available. Its hallucination rate is unmeasured. The rule path carries production.
- **Emerging-terms output is demoted to diagnostics.** Review showed it surfacing stopwords ("buy", "sir", "madam").

## 6. What did you deliberately leave out, and why that rather than something else?

**Left out:** deployment, auth, cloud, multi-user database, streaming, per-agent performance scoring, auto-replies, autonomous ticket actions, retraining pipelines, observability, a handle-time baseline, and a paid-model path.

**Why these:** Priya said "I don't need a platform". Every item above only matters at multi-user scale. I spent the time on the three things she asked for (digest, leaderboard, a measured number) plus the cost control Arjun needs. Handle time was left out because the source field is corrupt, and building on it would create false precision. Agent scoring was left out because the data cannot fairly compare Tier 1 and Tier 2 work. The paid-model path lost to Arjun's cost constraint.

## 7. Anything you built or found that nobody asked for?

- **The export miscounts itself.** `wc -l` says 37,996 rows. Quoted multiline messages mean there are **12,528 real tickets**. Any line-based analysis silently miscounts. After removing 653 duplicates, **11,875 canonical tickets**.
- **Duplicate quarantine.** 653 ticket IDs sit in both systems with different resolution times. This is the Freshdesk migration problem Sameer warned about. I kept them for audit instead of dropping them.
- **4 real refund + replacement violations on single tickets.** Policy §5 says escalate same day. They are separated from the 99 compliant same-order cases.
- **Intake-bot audit.** The stored category disagrees with the ticket text in 3,151 tickets (1,198 with no textual support at all). The "Other" bucket fell from 14% to 0.6% unclassified after remapping.
- **Week-label bug caught.** A timezone string labelled weeks by Sunday. I relabelled to ISO Mondays and re-verified sums. I also added a guard against truncated seconds that could flip an SLA breach. That guard is preventive only, since this export has no seconds.

## 8. What did you use AI for?

**In the product:** no paid AI and no model calls. Theme mapping is keyword rules plus local TF-IDF. Model bill: Rs 0.

**To build it:** an AI coding agent (OpenCode with Muse Spark) under my direction, across 8 gated phases. I re-ran verification commands after each phase and did not trust the agent's reports. Stack: Python 3.12, DuckDB, scikit-learn, pytest.
**Cost of build tooling:** Rs 0 (free tier).

**Where it helped**
- Normalising themes: the "Other" bucket went from 1,691 tickets to 67.
- Scaffolding speed (35 tests).
- Five review passes caught real defects: regex misfires, prose numbers that contradicted the JSON, and an unlabelled digest window.

**Where it wasted time**
- Numbers hand-copied into prose wrongly, twice. Each is now a regression test.
- One truncated file write.
- An over-clever test that tripped on its own docstring.

**What I threw away**
- Paid per-ticket classification (cost constraint).
- Free-form LLM summaries (every claim must trace to a ticket ID).
- Retuning the repeat filter on n=30 (overfitting risk).
- The emerging-terms digest section (stopword noise).
- A proposed DuckDB-to-stdlib rewrite (churn, no gain).

**Screen recording :** https://drive.google.com/file/d/17Lsk_o6IPmt9-kx2r_Ol9RFvQX_OuZIs/view?usp=sharing

## 9. Someone picks this up on Monday and you are unreachable. The three things they need to know.

1. **Run it:** `python run_digest.py --week <MONDAY> --output outputs/` after the README setup (about 5 minutes). It makes no paid calls.
2. **Watch this number:** same-issue repeats, about 12-19 a week. A 25% cut is worth about Rs 10-17k a quarter.
3. **Do not overtrust it:** repeat precision is 60%. Treat figures as estimates with evidence IDs. Keep Tier 2 off the volume board. Get a second reviewer before anyone uses this for incentives.

## 10. Honest hours spent. One number.

**3** 

## 12. GitHub Repo Link

https://github.com/space-rock-0/vireo-audio-support-intelligence

