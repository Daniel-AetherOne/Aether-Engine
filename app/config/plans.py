# app/config/plans.py

PLANS = {
    "starter_99": {
        "quote_limit": 99,
        "features": {
            "pdf": True,
            "branding": False,
            "whitelabel": False,
        },
    },
    "pro_199": {
        "quote_limit": 200,
        "features": {
            "pdf": True,
            "branding": True,
            "whitelabel": False,
        },
    },
    "business_399": {
        "quote_limit": None,  # unlimited
        "features": {
            "pdf": True,
            "branding": True,
            "whitelabel": True,
        },
    },
}
