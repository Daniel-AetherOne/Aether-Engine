import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse


class SimpleRateLimitMiddleware:
    """
    In-memory sliding window limit.
    Good enough for MVP; not multi-worker safe.
    """

    def __init__(self, app, path: str, limit: int, window_seconds: int):
        self.app = app
        self.path = path
        self.limit = limit
        self.window = window_seconds
        self.hits: Dict[str, Deque[float]] = defaultdict(deque)

    def _client_key(self, req: Request) -> str:
        # prefer real client ip if behind proxy you can later use X-Forwarded-For
        return req.client.host if req.client else "unknown"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("path") != self.path:
            await self.app(scope, receive, send)
            return

        req = Request(scope, receive=receive)
        key = self._client_key(req)

        now = time.time()
        q = self.hits[key]

        # drop old
        while q and q[0] <= now - self.window:
            q.popleft()

        if len(q) >= self.limit:
            resp = JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "detail": f"Max {self.limit} per {self.window}s",
                },
            )
            await resp(scope, receive, send)
            return

        q.append(now)
        await self.app(scope, receive, send)
