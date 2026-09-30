"""Tests for the AI layer's deterministic core. The LLM path is tested only
for its failure contract (LLMUnavailable) — never for model output."""
import pytest

from src.themes import (
    OTHER,
    CATEGORY_TO_THEME,
    LLMUnavailable,
    assign_themes,
    count_themes,
    emerging_terms,
    group_top_terms,
    llm_normalize,
    load_taxonomy,
    map_ticket,
    weekly_digest_sections,
)

TAX = "theme_taxonomy.json"


def T(**kw):
    base = {
        "ticket_id": "TK-T",
        "customer_message": "",
        "agent_notes": "",
        "category": "Connectivity",
        "product_sku": "VA-EB-PL2",
    }
    base.update(kw)
    return base


def test_taxonomy_has_11_themes_with_definitions(tmp_path=None):
    import os
    tax = load_taxonomy(
        os.path.join(os.path.dirname(__file__), "..", TAX)
    )
    assert len(tax["themes"]) == 11


def test_direct_taxonomy_mapping():
    for cat, theme in CATEGORY_TO_THEME.items():
        th, cf, m = map_ticket(T(category=cat))
        assert (th, cf, m) == (theme, 1.0, "taxonomy")


def test_other_recovers_via_keywords():
    th, cf, m = map_ticket(
        T(category="Other", customer_message="Bluetooth pairing fails every time")
    )
    assert (th, m) == ("Connectivity & Pairing", "rule")
    th, cf, m = map_ticket(
        T(category="Other", customer_message="refund not received yet, checked bank")
    )
    assert (th, m) == ("Returns & Refunds", "rule")


def test_other_gibberish_stays_unclassified():
    th, cf, m = map_ticket(T(category="Other", customer_message="xyz abc qqq"))
    assert (th, cf, m) == (OTHER, 0.3, "rule-fallback")


def test_assign_count_reconciles():
    rows = [
        T(ticket_id="a", category="Connectivity"),
        T(ticket_id="b", category="Other",
          customer_message="battery drains by lunch"),
        T(ticket_id="c", category="Other", customer_message="xyz abc qqq"),
    ]
    a = assign_themes(rows)
    counts = count_themes(a)
    assert sum(counts.values()) == 3
    assert counts["Connectivity & Pairing"] == 1
    assert counts["Charging & Battery"] == 1
    assert counts[OTHER] == 1


def test_digest_sections_math_and_trigger():
    s = weekly_digest_sections(
        "2026-06-22",
        {"Connectivity & Pairing": 60, OTHER: 30, "Delivery & Shipping": 110},
        200,
        {"Connectivity & Pairing": 50, OTHER: 10, "Delivery & Shipping": 100},
    )
    assert s["total_tickets"] == 200
    th = {t["theme"]: t for t in s["themes"]}
    assert th["Connectivity & Pairing"]["n"] == 60
    assert th["Connectivity & Pairing"]["pct"] == 30.0
    assert th["Connectivity & Pairing"]["wow"] == 10
    assert s["other_watch"]["pct"] == 15.0
    assert s["other_watch"]["wow_pp"] == 8.8  # 15.0 - 10*100/160
    assert s["other_watch"]["trigger"] is True  # via WoW growth, not level
    s2 = weekly_digest_sections("2026-06-22", {OTHER: 40, "Delivery & Shipping": 160}, 200, None)
    assert s2["other_watch"]["trigger"] is True  # 20% > 15%
    s3 = weekly_digest_sections(
        "2026-06-22", {OTHER: 20, "Delivery & Shipping": 180}, 200,
        {OTHER: 10, "Delivery & Shipping": 170},
    )
    assert s3["other_watch"]["wow_pp"] == 4.4
    assert s3["other_watch"]["trigger"] is True  # WoW growth trigger
    with pytest.raises(AssertionError):
        weekly_digest_sections("2026-06-22", {OTHER: 40}, 199, None)


def test_llm_unavailable_contract():
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with pytest.raises(LLMUnavailable):
        llm_normalize(
            [T()], {"themes": [{"name": "Connectivity & Pairing", "definition": "x"}]},
            prompt_path=os.path.join(repo, "prompts", "theme_extraction.txt"),
            endpoint="http://127.0.0.1:1",  # nothing listens: fast refusal
        )


def test_group_top_terms_smoke():
    rows = [
        T(ticket_id=str(i), category="Connectivity",
          customer_message="bluetooth pairing disconnects phone wifi signal")
        for i in range(4)
    ]
    out, skipped = group_top_terms(rows, {"VA-EB-PL2": "earbuds"}, k=3)
    key = "Connectivity | earbuds"
    assert key in out and len(out[key]) == 3 and skipped == []
    assert all(isinstance(t, str) and t for t in out[key])


def test_emerging_terms_flags_surge():
    cur = ["firmware update stuck frozen bricked"] * 6 + ["delivery late courier"] * 20
    prev = ["delivery late courier"] * 20 + ["refund pending bank"] * 6
    em = emerging_terms(cur, prev, k=5)
    assert any("firmware" in t or "stuck" in t for t, _ in em)


def test_emerging_empty_baseline_returns_silence():
    assert emerging_terms(["a b c"] * 5, [], k=5) == []
    assert emerging_terms(["a b c"] * 5, ["x y z"] * 5, k=5) == []


def test_tie_break_is_taxonomy_order():
    # otp+login hit both App & Firmware and Account & Help: earliest wins.
    th, _, m = map_ticket(
        T(category="Other", customer_message="otp not coming, cannot login")
    )
    assert (th, m) == ("App & Firmware", "rule")


def test_word_boundaries_hold():
    # 'repair' must NOT score Connectivity ('pair'); 'failed' must NOT score Charging ('led')
    th, _, _ = map_ticket(
        T(category="Other", customer_message="sent unit for repair, no update on warranty claim")
    )
    assert th == "Warranty & Repair"
    th, _, _ = map_ticket(
        T(category="Other", customer_message="payment failed twice, bank debited")
    )
    assert th == "Billing & Payments"


def test_disagreement_audit_stratum():
    from src.themes import audit_disagreements, explain_ticket
    rows = [
        T(ticket_id="a", category="Delivery & Shipping",
          customer_message="refund not received, checked bank twice"),
        T(ticket_id="b", category="Delivery & Shipping",
          customer_message="courier tracking stuck, parcel late"),
    ]
    e = explain_ticket(rows[0])
    assert e["taxonomy_theme"] == "Delivery & Shipping"
    assert e["rule_theme"] == "Returns & Refunds" and e["agree"] is False
    assert [d["ticket_id"] for d in audit_disagreements(rows)] == ["a"]


def test_validate_polished_guards_numbers():
    from src.themes import validate_polished
    draft = {"week": "2026-06-22", "total": 199, "ids": ["TK-240001"]}
    good = "Week 2026-06-22 had 199 tickets including TK-240001."
    bad = "Week 2026-06-22 had 250 tickets."
    assert validate_polished(draft, good) is True
    assert validate_polished(draft, bad) is False


def test_llm_success_and_duplicate_guard(monkeypatch):
    import json as _json
    from src import themes as _th
    from src.themes import LLMUnavailable, llm_normalize

    def fake_ok(req, timeout=120):
        body = _th.json.dumps({"themes": [
            {"theme": "Connectivity & Pairing", "summary": "s",
             "evidence_ticket_ids": ["TK-1"], "confidence": 0.9}]})
        outer = _th.json.dumps({"response": body})

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return outer.encode()
        return R()

    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.setattr(_th.urllib.request, "urlopen", fake_ok)
    out = llm_normalize(
        [{"ticket_id": "TK-1", "customer_message": "x", "agent_notes": "",
          "category": "Other"}],
        {"themes": [{"name": "Connectivity & Pairing", "definition": "x"}]},
        prompt_path=os.path.join(repo, "prompts", "theme_extraction.txt"),
    )
    assert out == {"TK-1": "Connectivity & Pairing"}

    def fake_dup(req, timeout=120):
        body = _th.json.dumps({"themes": [
            {"theme": "Connectivity & Pairing", "summary": "s",
             "evidence_ticket_ids": ["TK-1"], "confidence": 0.9},
            {"theme": "App & Firmware", "summary": "s",
             "evidence_ticket_ids": ["TK-1"], "confidence": 0.5}]})
        outer = _th.json.dumps({"response": body})

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return outer.encode()
        return R()

    monkeypatch.setattr(_th.urllib.request, "urlopen", fake_dup)
    with pytest.raises(LLMUnavailable):
        llm_normalize(
            [{"ticket_id": "TK-1", "customer_message": "x", "agent_notes": "",
              "category": "Other"}],
            {"themes": [{"name": "Connectivity & Pairing", "definition": "x"},
                        {"name": "App & Firmware", "definition": "y"}]},
            prompt_path=os.path.join(repo, "prompts", "theme_extraction.txt"),
        )
