# app/config/plans.py

PLANS = {
    "starter_99": {
        "quote_limit": 20,
        "features": {
            "pdf": False,
            "branding": False,
            "whitelabel": False,
        },
    },
    "growth_199": {
        "quote_limit": 200,
        "features": {
            "pdf": True,
            "branding": True,
            "whitelabel": False,
        },
    },
    "pro_399": {
        "quote_limit": None,  # unlimited
        "features": {
            "pdf": True,
            "branding": True,
            "whitelabel": True,
        },
    },
}

