from app.verticals.painters_us.pricing_engine_us import price_from_vision


def run_case(name: str, vision_surface: dict) -> dict:
    print("\n" + "=" * 80)
    print(f"CASE: {name}")
    print("- input:", vision_surface)
    result = price_from_vision(vision_surface)
    print("- output:", result)
    return result


def get_total(result: dict) -> float:
    # For priced outputs (not needs_review)
    total = result.get("total_usd", None)
    if total is None:
        return 0.0
    return float(total)


def main():
    # 1) interior wall (baseline)
    interior_wall_light = {
        "surface_type": "walls",
        "sqft": 500,
        "prep_level": "light",
        "access_risk": "low",
        "estimated_complexity": 1.0,  # low bucket
        "confidence": 0.95,
        "pricing_ready": True,
    }

    # 2) ceiling stains (more prep + a bit more access + some complexity)
    ceiling_stains = {
        "surface_type": "ceilings",
        "sqft": 200,
        "prep_level": "heavy",
        "access_risk": "medium",
        "estimated_complexity": 1.2,  # medium bucket
        "confidence": 0.92,
        "pricing_ready": True,
    }

    # 3) exterior peeling (highest base rate + heavy prep + high access + high complexity)
    exterior_peeling = {
        "surface_type": "exterior_siding",
        "sqft": 600,
        "prep_level": "heavy",
        "access_risk": "high",
        "estimated_complexity": 1.3,  # high bucket
        "confidence": 0.9,
        "pricing_ready": True,
    }

    # Extra sanity: same as interior wall but heavy prep
    interior_wall_heavy = {
        **interior_wall_light,
        "prep_level": "heavy",
    }

    r1 = run_case("Interior wall (light prep)", interior_wall_light)
    r1b = run_case("Interior wall (heavy prep)", interior_wall_heavy)
    r2 = run_case("Ceiling stains (heavy prep)", ceiling_stains)
    r3 = run_case("Exterior peeling (heavy prep)", exterior_peeling)

    t1 = get_total(r1)
    t1b = get_total(r1b)
    t2 = get_total(r2)
    t3 = get_total(r3)

    print("\n" + "=" * 80)
    print("SANITY CHECKS")
    print(f"- interior wall light total: {t1}")
    print(f"- interior wall heavy total: {t1b}")
    print(f"- ceiling stains total:      {t2}")
    print(f"- exterior peeling total:    {t3}")

    # Checklist assertions
    assert t1b > t1, "Heavy prep should be higher than light prep (same surface)"
    assert t3 > t1, "Exterior should be more expensive than interior (baseline)"

    print("✅ PASS: heavy prep > light prep")
    print("✅ PASS: exterior > interior")


if __name__ == "__main__":
    main()
