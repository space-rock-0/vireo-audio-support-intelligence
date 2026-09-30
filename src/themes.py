"""Minimal AI layer: theme normalisation, grouping, weekly narrative.

Design (D8/D9): deterministic code owns taxonomy mapping and ALL counts.
Keyword rules cut across the 14% 'Other' bucket. TF-IDF surfaces group terms
and emerging-term signals. An LLM (Ollama local, Rs 0) is attempted ONLY for
still-unclassified tickets and narrative polish — every LLM output is validated
(ticket IDs ⊆ input) and counts are recomputed outside the model.
Without Ollama running, the rule/TF-IDF path is the whole system.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

CATEGORY_TO_THEME = {
    "Connectivity": "Connectivity & Pairing",
    "Charging & Battery": "Charging & Battery",
    "Audio Quality": "Audio Quality & Mic",
    "App & Firmware": "App & Firmware",
    "Delivery & Shipping": "Delivery & Shipping",
    "Returns & Refunds": "Returns & Refunds",
    "Billing & Payments": "Billing & Payments",
    "Warranty & Repair": "Warranty & Repair",
    "Account & Login": "Account & Help",
    "Product Enquiry": "Product Enquiry",
}

# Word-boundary regexes (C1: bare substrings mis-fired — 'pair' hit 'repair',
# 'led' hit 'failed/cancelled', 'mic' hit 'dynamic'). Curated from the 12.5k-row
# vocabulary. Ties resolve to the earliest theme below (documented, tested).
KEYWORD_RULES = {
    "Connectivity & Pairing": [r"\bpair\w*\b", r"\bbluetooth\b", r"\bconnect\w*\b", r"\bdisconnect\w*\b", r"\bwifi\b", r"\bwi-fi\b", r"\bsignal\b", r"\brang\w*\b", r"\bstutter\w*\b"],
    "Charging & Battery": [r"\bbatter\w*\b", r"\bcharg\w*\b", r"\bdrain\w*\b", r"\bbackup\b", r"\bled\b", r"\bgreen light\b", r"\bdie[sd]?\b", r"\bdischarg\w*\b"],
    "Audio Quality & Mic": [r"\bsound\w*\b", r"\baudio\b", r"\bmic\b", r"\bhiss\b", r"\bhear\w*\b", r"\bvolum\w*\b", r"\bnois\w*\b", r"\bsilent\b", r"\bone side\b", r"\bbuds?\b"],
    "App & Firmware": [r"\bapp\b", r"\bfirmware\b", r"\bupdat\w*\b", r"\bcrash\w*\b", r"\botp\b", r"\blogin\b", r"\blog in\b", r"\bwhite screen\b"],
    "Delivery & Shipping": [r"\bdeliver\w*\b", r"\bcourier\b", r"\btrack\w*\b", r"\bshipped\b", r"\bship\w*\b", r"\bpickup\b", r"\bpick up\b", r"\bdispatch\w*\b", r"\bparcel\b", r"\bpackag\w*\b", r"\baddress\w*\b", r"\bpincode\b", r"\bpin code\b"],
    "Returns & Refunds": [r"\brefund\w*\b", r"\breturn\w*\b", r"\bmoney back\b", r"\bpicked up\b", r"\breplac\w*\b", r"\breship\w*\b"],
    "Billing & Payments": [r"\bpayment\b", r"\bpay\b", r"\bcharged twice\b", r"\bdoubl\w*\b", r"\bcoupon\b", r"\bdiscount\b", r"\binvoic\w*\b", r"\bgst\w*\b", r"\bprice\b", r"\boffer\w*\b", r"\bbank\b", r"\bdebit\w*\b"],
    "Warranty & Repair": [r"\bwarrant\w*\b", r"\brepair\w*\b", r"\bservice centre\b", r"\bservice center\b", r"\brma\b", r"\bclaim\b"],
    "Account & Help": [r"\baccount\b", r"\botp\b", r"\blogin\b", r"\bpassword\b", r"\baddress\w*\b", r"\bcompatib\w*\b", r"\bsamsung\b", r"\biphone\b", r"\btv\b"],
    "Product Enquiry": [r"\bcompatib\w*\b", r"\bbefore i buy\b", r"\bwill this\b"],
}
OTHER = "Other / Unclassified"


def load_taxonomy(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _text(t: dict) -> str:
    return f"{t.get('customer_message') or ''}\n{t.get('agent_notes') or ''}".lower()


def keyword_scores(text: str) -> dict[str, int]:
    return {
        theme: sum(1 for pat in pats if re.search(pat, text))
        for theme, pats in KEYWORD_RULES.items()
    }


def explain_ticket(t: dict) -> dict:
    """Auditable view: stored-category theme vs rule winner (C2).
    Disagreements form a Phase 5 review stratum — intake trust is measured,
    not assumed (brief §10-Q1)."""
    cat = (t.get("category") or "").strip()
    tax_theme = CATEGORY_TO_THEME.get(cat)
    scores = keyword_scores(_text(t))
    rule_theme = max(scores, key=lambda k: scores[k])
    return {
        "ticket_id": t.get("ticket_id"),
        "category": cat,
        "taxonomy_theme": tax_theme,
        # stored_hits==0 with a rule winner = genuine suspect (10% of tagged);
        # stored_hits>0 = multi-issue text, expected (brief error taxonomy).
        "stored_hits": scores.get(tax_theme, 0) if tax_theme else 0,
        "winner_hits": scores[rule_theme],
        "rule_theme": rule_theme if scores[rule_theme] > 0 else None,
        "agree": tax_theme is not None and tax_theme == rule_theme,
    }


def audit_disagreements(rows: list[dict]) -> list[dict]:
    """Tickets where the stored tag and the rule winner differ (C2 stratum)."""
    return [e for r in rows for e in [explain_ticket(r)]
            if e["taxonomy_theme"] and e["rule_theme"] and not e["agree"]]


def map_ticket(t: dict) -> tuple[str, float, str]:
    """Returns (theme, confidence, method). Deterministic."""
    cat = (t.get("category") or "").strip()
    if cat in CATEGORY_TO_THEME and cat != "Other":
        return CATEGORY_TO_THEME[cat], 1.0, "taxonomy"
    scores = keyword_scores(_text(t))
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best, 0.7, "rule"
    return OTHER, 0.3, "rule-fallback"


def assign_themes(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for r in rows:
        th, cf, m = map_ticket(r)
        out[r["ticket_id"]] = {"theme": th, "confidence": cf, "method": m}
    return out


def count_themes(assignment: dict[str, dict]) -> dict[str, int]:
    """Counts recomputed in code — never taken from an LLM (brief §6)."""
    out: dict[str, int] = {}
    for v in assignment.values():
        out[v["theme"]] = out.get(v["theme"], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def group_top_terms(
    rows: list[dict], family_of: dict[str, str], k: int = 10
) -> tuple[dict[str, list[str]], list[str]]:
    """Top TF-IDF terms per (category, family) group — digest evidence.
    Returns (terms, skipped_groups): small weeks vanish loudly, not silently."""
    groups: dict[str, list[str]] = {}
    for r in rows:
        key = f"{(r.get('category') or '').strip()} | {family_of.get((r.get('product_sku') or '').strip(), '?')}"
        groups.setdefault(key, []).append(_text(r))
    out, skipped = {}, []
    for key, texts in groups.items():
        if len(texts) < 3:
            skipped.append(key)
            continue
        vec = TfidfVectorizer(max_features=500, stop_words="english", ngram_range=(1, 2))
        m = vec.fit_transform(texts)
        means = np.asarray(m.mean(axis=0)).ravel()
        terms = vec.get_feature_names_out()
        out[key] = [terms[i] for i in means.argsort()[::-1][:k]]
    return out, skipped


def emerging_terms(cur: list[str], prev: list[str], k: int = 10) -> list[tuple[str, float]]:
    """Terms gaining TF share week-over-week — emerging-issue signal.
    Empty/short baseline week -> [] (first-week noise is not signal)."""
    if not prev or len(prev) < 20:
        return []
    vec = CountVectorizer(max_features=1000, stop_words="english", ngram_range=(1, 2))
    all_m = vec.fit_transform([t.lower() for t in cur + prev])
    n_c, n_p = len(cur), len(prev)
    terms = vec.get_feature_names_out()
    scored = []
    for i, t in enumerate(terms):
        col = all_m[:, i]
        c = float(col[:n_c].sum()) / max(n_c, 1)
        p = float(col[n_c:].sum()) / max(n_p, 1)
        if c > p and c >= 3 / max(n_c, 1):
            scored.append((t, round(c - p, 4)))
    return sorted(scored, key=lambda x: -x[1])[:k]


class LLMUnavailable(Exception):
    pass


def llm_normalize(
    tickets: list[dict],
    taxonomy: dict,
    prompt_path: str,
    model: str = "llama3.1:8b",
    endpoint: str = "http://localhost:11434",
) -> dict[str, str]:
    """One Ollama call for still-unclassified tickets. Validates IDs ⊆ input.
    Raises LLMUnavailable on any failure (connect, parse, schema, ID leak) —
    caller falls back to rule mapping. Rs 0 paid cost either way."""
    names = [t["name"] for t in taxonomy["themes"]]
    with open(prompt_path, encoding="utf-8") as f:
        template = f.read()
    tax = "\n".join(f"- {t['name']}: {t['definition']}" for t in taxonomy["themes"])
    payload_tickets = [
        {
            "ticket_id": t["ticket_id"],
            "customer_message": (t.get("customer_message") or "")[:800],
            "agent_notes": (t.get("agent_notes") or "")[:400],
            "category": t.get("category"),
            "product_family": t.get("product_family", ""),
        }
        for t in tickets
    ]
    prompt = template.replace("{TAXONOMY}", tax) + "\n" + json.dumps(
        {"tickets": payload_tickets}
    )
    req = urllib.request.Request(
        endpoint + "/api/generate",
        data=json.dumps(
            {"model": model, "prompt": prompt, "stream": False,
             "options": {"temperature": 0}, "format": "json"}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            outer = json.loads(resp.read().decode())
        data = json.loads(outer["response"])
    except Exception as e:
        raise LLMUnavailable(f"ollama call failed: {e}") from e
    valid_ids = {t["ticket_id"] for t in tickets}
    out = {}
    try:
        for item in data["themes"]:
            if item["theme"] not in names:
                raise ValueError(f"off-taxonomy theme: {item['theme']}")
            for tid in item["evidence_ticket_ids"]:
                if tid not in valid_ids:
                    raise ValueError(f"hallucinated ticket id: {tid}")
                if tid in out:
                    raise ValueError(f"duplicate ticket id across themes: {tid}")
                out[tid] = item["theme"]
    except (KeyError, TypeError, ValueError) as e:
        raise LLMUnavailable(f"schema/evidence validation failed: {e}") from e
    # Partial-return contract: caller merges out over rule mapping; uncovered
    # input IDs keep their rule theme. Coverage = len(out)/len(valid_ids).
    return out


def validate_polished(draft: dict, polished: str) -> bool:
    """I3 enforcement: every number, date, and TK-ID in the deterministic draft
    must appear verbatim in the polished paragraph — else discard the polish."""
    hay = polished
    needles = set(re.findall(r"TK-\d+|\d{4}-\d{2}-\d{2}|\d+(?:\.\d+)?%?", json.dumps(draft)))
    return all(n in hay for n in needles if re.search(r"[A-Za-z0-9]", n))


def weekly_digest_sections(
    week: str,
    counts: dict[str, int],
    total: int,
    prev_counts: dict[str, int] | None = None,
) -> dict:
    """Deterministic digest body. Numbers in, numbers out — no LLM."""
    assert total == sum(counts.values()), "digest total must equal theme counts"
    prev_counts = prev_counts or {}
    themes = [
        {
            "theme": th,
            "n": n,
            "pct": round(n * 100 / total, 1) if total else 0.0,
            "wow": n - prev_counts.get(th, 0),
            "wow_pp": round(n * 100 / total - prev_counts.get(th, 0) * 100 / max(sum(prev_counts.values()), 1), 1) if total else 0.0,
        }
        for th, n in counts.items()
    ]
    other = next((t for t in themes if t["theme"] == OTHER), {"n": 0, "pct": 0.0, "wow_pp": 0.0})
    trig = bool(other["pct"] > 15 or other.get("wow_pp", 0) > 3)
    return {
        "week": week,
        "total_tickets": total,
        "themes": themes,
        "other_watch": {
            "pct": other["pct"],
            "wow_pp": other.get("wow_pp", 0.0),
            "trigger": trig,
            "note": "Review trigger: Other/Unclassified above 15% of the week or growing >3pp WoW.",
        },
    }
