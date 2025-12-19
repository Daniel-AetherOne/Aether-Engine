from app.verticals.painters_us.pricing_engine_us import price_from_vision

vision_surface = {
    "surface_type": "walls",
    "sqft": 500,
    "prep_level": "medium",
    "access_risk": "high",
    "estimated_complexity": 1.3,
    "confidence": 0.95,
    "pricing_ready": False,
}

result = price_from_vision(vision_surface)

print("=== PRICING RESULT ===")
print(result)
