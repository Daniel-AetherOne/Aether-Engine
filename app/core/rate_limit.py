# app/core/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

# 1 gedeelde Limiter voor de hele app
limiter = Limiter(
    key_func=lambda req: f"{get_remote_address(req)}:{req.headers.get('x-user-id', 'anon')}"
)

# Optioneel: alias als je ergens een decorator zonder 'limiter.' wilt gebruiken
exempt = limiter.exempt
