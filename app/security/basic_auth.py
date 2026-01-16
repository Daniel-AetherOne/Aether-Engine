import base64
import hmac
import os
from typing import Optional

from fastapi import Request
from fastapi.responses import Response


def _unauthorized() -> Response:
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="sales"'},
        content="Unauthorized",
    )


def _parse_basic_auth(header: str) -> Optional[tuple[str, str]]:
    # header: "Basic base64(user:pass)"
    try:
        scheme, b64 = header.split(" ", 1)
        if scheme.lower() != "basic":
            return None
        raw = base64.b64decode(b64).decode("utf-8")
        user, pwd = raw.split(":", 1)
        return user, pwd
    except Exception:
        return None


class BasicAuthMiddleware:
    """
    Minimal Basic Auth middleware.
    Protects configurable path prefixes.
    """

    def __init__(self, app, protected_prefixes: list[str]):
        self.app = app
        self.protected_prefixes = protected_prefixes
        self.user = os.getenv("SALES_BASIC_AUTH_USER", "")
        self.pwd = os.getenv("SALES_BASIC_AUTH_PASS", "")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if not any(path.startswith(p) for p in self.protected_prefixes):
            await self.app(scope, receive, send)
            return

        req = Request(scope, receive=receive)
        auth = req.headers.get("authorization")
        if not auth:
            resp = _unauthorized()
            await resp(scope, receive, send)
            return

        parsed = _parse_basic_auth(auth)
        if not parsed:
            resp = _unauthorized()
            await resp(scope, receive, send)
            return

        user, pwd = parsed

        # constant-time compare
        ok_user = hmac.compare_digest(user, self.user)
        ok_pwd = hmac.compare_digest(pwd, self.pwd)
        if not (ok_user and ok_pwd):
            resp = _unauthorized()
            await resp(scope, receive, send)
            return

        await self.app(scope, receive, send)
