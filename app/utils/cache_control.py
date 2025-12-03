# app/utils/cache_control.py

from functools import wraps
from fastapi import Response
from fastapi.responses import JSONResponse


def cache_control(value: str):
    """
    Decorator om eenvoudig een Cache-Control header toe te voegen
    aan responses van je endpoints.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Als de route zelf al een Response teruggeeft (HTML, File, etc.)
            if isinstance(result, Response):
                # Alleen zetten als hij nog niet bestaat
                result.headers.setdefault("Cache-Control", value)
                return result

            # Als het bv. een dict is (JSON), wrap in JSONResponse
            return JSONResponse(content=result, headers={"Cache-Control": value})

        return wrapper

    return decorator
