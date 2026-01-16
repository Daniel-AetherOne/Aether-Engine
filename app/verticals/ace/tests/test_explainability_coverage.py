from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

import pytest

from app.verticals.ace.engine.quote_engine import QuoteEngine
from app.verticals.ace.engine.context import ActiveData, QuoteInput, QuoteLineInput


def _make_minimal_data() -> ActiveData:
    # Houd dit minimaal maar compleet genoeg om de standaard rules te laten lopen
    return ActiveData(
        tables={
            "articles": {
                "SKU1": {
                    "buyPrice": "10.00",
                    "weightKg": "2.0",
                    "supplier": "SUP1",
                    "productGroup": "A",
                }
            },
            "supplier_factors": {"SUP1": "1.0"},
            "currency_markup_pct": {"EUR": "0"},
            "tiers": [
                {"min": 1, "max": 9, "pct": "0"},
                {"min": 10, "max": 24, "pct": "3"},
                {"min": 25, "pct": "5"},
            ],
            "postcode_zones": {"1234": "C"},
            "zone_rate_eur_per_kg": {
                "C": "0.10"
            },  # forceer transport > 0 zodat rule explain triggert
            "customer_profile_discount_pct": {"B": "2"},
            "customer_max_extra_discount_pct": {"B": "2"},
            "min_margin_pct_by_group": {
                "A": "0"
            },  # maak margin altijd OK in dit scenario
        }
    )


def _make_input() -> QuoteInput:
    return QuoteInput(
        currency="EUR",
        ship_to_postcode="1234AB",
        customer_segment="B",
        discount_percent=None,
        lines=[QuoteLineInput(line_id="l1", sku="SKU1", qty=25)],
    )


def _load_ruleset_yaml_path() -> str:
    # Pas aan als jouw pad anders is:
    p = Path("app/verticals/ace/rules/rule_sets/v1.yaml")
    if not p.exists():
        raise AssertionError(f"Ruleset yaml not found at: {p}")
    return str(p)


def _extract_rule_ids_in_order(engine: QuoteEngine) -> List[str]:
    loaded = engine.rule_loader.get()
    return list(loaded.ruleset.execution_order)


def _has_min_margin_entry(steps: List[str]) -> bool:
    # We accepteren zowel OK als BLOCK varianten
    # (jouw MinMarginRule rendert via add_check -> "OK: ..." / "BLOCK: ...")
    for s in steps:
        s_low = s.lower()
        if "minimummarge" in s_low and (
            s_low.startswith("ok:")
            or s_low.startswith("block:")
            or "block" in s_low
            or "ok" in s_low
        ):
            return True
    return False


@pytest.mark.integration
def test_explainability_coverage_per_rule_and_per_line():
    """
    HARD gate:
    - Elke line moet steps non-empty hebben
    - Minimummarge check moet altijd aanwezig zijn (OK/BLOCK)
    - Elke rule in executionOrder moet minstens 1 explain entry veroorzaken in dit scenario,
      tenzij expliciet toegestaan als no-op.
    - Warnings en blocking blijven gescheiden
    """
    engine = QuoteEngine.from_yaml_file(_load_ruleset_yaml_path())
    data = _make_minimal_data()
    qin = _make_input()

    fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    out = engine.calculate(qin, data, quote_id="explain_cov_1", now=fixed_now)

    payload: Dict[str, Any] = asdict(out)

    # ---- warnings vs blocking separation ----
    assert isinstance(payload.get("blocks", []), list)
    # warnings zitten in ctx, maar QuoteOutputV1 heeft mogelijk geen warnings field (afhankelijk van jouw model)
    # Als je later warnings toevoegt aan output: voeg hier een assert toe dat ze geen overlap hebben.

    # ---- per-line output checks ----
    assert "lines" in payload, "Quote output must include lines[] for explainability."
    assert payload["lines"], "Expected at least 1 output line."

    for line in payload["lines"]:
        steps = line.get("steps") or []
        assert isinstance(steps, list), "line.steps must be a list[str]"
        assert (
            len(steps) > 0
        ), "Each line must have non-empty steps (priceBreakdown non-empty)."
        assert _has_min_margin_entry(
            steps
        ), "Each line must include a minimummarge check entry (OK/BLOCK)."

    # ---- per-rule coverage (in this scenario) ----
    rule_ids = _extract_rule_ids_in_order(engine)

    # Deze set is jouw escape hatch:
    # rules die *bewust* geen line-explain entry hoeven te produceren in het MVP scenario.
    NO_OP_ALLOWED: Set[str] = set(
        [
            # voorbeeld: "some_rule_id",
        ]
    )

    # We checken coverage door te eisen dat de step-strings minstens 1x 'gelinkt' zijn aan een rule effect.
    # Omdat we (bewust) strings consumeren, doen we dit via keywords.
    #
    # Richtlijn: zorg dat iedere rule een herkenbaar label heeft in een step/check/meta string.
    # In jouw 4.3 edits hebben we o.a.: "Netto inkoop", "Transport", "Klantkorting", "Staffelkorting", "Minimummarge".
    steps_all: List[str] = []
    for line in payload["lines"]:
        steps_all.extend(line.get("steps") or [])

    joined = "\n".join(steps_all).lower()

    # Map rule_id -> keyword(s) die in steps moeten voorkomen als de rule loopt
    # Pas deze aan aan jouw rule IDs/titles indien nodig.
    expected_markers: Dict[str, List[str]] = {
        # net_cost
        "net_cost_1": ["netto inkoop"],
        # transport
        "transport_1": ["transport"],
        # tier discount
        "tier_discount_1": ["staffel", "staffelkorting"],
        # customer discount
        "customer_discount_1": ["klantkorting"],
        # min margin
        "min_margin_1": ["minimummarge"],
    }

    missing: List[str] = []
    for rid in rule_ids:
        if rid in NO_OP_ALLOWED:
            continue
        markers = expected_markers.get(rid)
        if not markers:
            # HARD fail: we kennen de rule nog niet -> dwing dev om marker toe te voegen of no-op te whitelisten
            missing.append(
                f"{rid} (no marker mapping; add to expected_markers or NO_OP_ALLOWED)"
            )
            continue
        if not any(m in joined for m in markers):
            missing.append(f"{rid} (markers not found in line.steps)")

    assert not missing, "Explainability coverage failed:\n- " + "\n- ".join(missing)
