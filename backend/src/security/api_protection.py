from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response

CallNext = Callable[[Request], Awaitable[Response]]


class ApiProtector:
    """Small in-process guard suitable for a single-instance deployment."""

    def __init__(self, *, api_key: str | None, requests_per_minute: int) -> None:
        self.api_key = api_key
        self.requests_per_minute = max(1, requests_per_minute)
        self._request_times: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, request: Request, call_next: CallNext) -> Response:
        if not self._is_protected_path(request.url.path):
            return await call_next(request)
        if self.api_key and request.headers.get("x-api-key") != self.api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key."})
        if self._rate_limit_exceeded(self._client_id(request), time.monotonic()):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded."},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)

    @staticmethod
    def _is_protected_path(path: str) -> bool:
        return path.startswith("/api/") and path != "/api/health"

    @staticmethod
    def _client_id(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def _rate_limit_exceeded(self, client_id: str, now: float) -> bool:
        recent = self._request_times[client_id]
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= self.requests_per_minute:
            return True
        recent.append(now)
        return False

