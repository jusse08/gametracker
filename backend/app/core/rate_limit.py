import time
import threading
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request, status


class RateLimiter:
    """Simple in-memory rate limiter for API endpoints."""

    def __init__(self, requests: int = 100, window: int = 60):
        """
        Initialize rate limiter.

        Args:
            requests: Maximum number of requests allowed
            window: Time window in seconds
        """
        self._requests = requests
        self._window = window
        self._storage: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _get_client_key(self, request: Request) -> str:
        """Extract client identifier from request."""
        forwarded = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        # Include path to allow different limits per endpoint if needed
        return f"{client_ip}:{request.url.path}"

    def _cleanup_old_requests(self, timestamps: Deque[float], now: float) -> None:
        """Remove timestamps outside the current window."""
        while timestamps and now - timestamps[0] > self._window:
            timestamps.popleft()

    def check_rate_limit(self, request: Request) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit.

        Returns:
            Tuple of (is_allowed, remaining_requests, retry_after_seconds)
        """
        now = time.time()
        key = self._get_client_key(request)
        with self._lock:
            timestamps = self._storage[key]

            self._cleanup_old_requests(timestamps, now)

            current_count = len(timestamps)

            if current_count >= self._requests:
                # Rate limit exceeded
                oldest = timestamps[0] if timestamps else now
                retry_after = int(self._window - (now - oldest)) + 1
                return False, 0, retry_after

            # Allow request
            timestamps.append(now)
            remaining = self._requests - len(timestamps)
            return True, remaining, 0

    async def __call__(self, request: Request) -> None:
        """Middleware callable to check rate limits."""
        allowed, remaining, retry_after = self.check_rate_limit(request)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )


# Global rate limiter instance
# 100 requests per minute per IP per endpoint
global_rate_limiter = RateLimiter(requests=100, window=60)
