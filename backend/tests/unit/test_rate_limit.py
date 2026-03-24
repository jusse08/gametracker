from starlette.requests import Request

from app.core.rate_limit import RateLimiter


def _request(path: str, *, client_ip: str = "127.0.0.1", forwarded_for: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for:
        headers.append((b"x-forwarded-for", forwarded_for.encode("utf-8")))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers,
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_rate_limiter_blocks_after_limit_for_same_ip_and_path():
    limiter = RateLimiter(requests=2, window=60)
    request = _request("/api/games")

    assert limiter.check_rate_limit(request) == (True, 1, 0)
    assert limiter.check_rate_limit(request) == (True, 0, 0)

    allowed, remaining, retry_after = limiter.check_rate_limit(request)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


def test_rate_limiter_uses_forwarded_for_header():
    limiter = RateLimiter(requests=1, window=60)
    first = _request("/api/games", client_ip="10.0.0.10", forwarded_for="198.51.100.7")
    second = _request("/api/games", client_ip="10.0.0.10", forwarded_for="198.51.100.7")
    third = _request("/api/games", client_ip="10.0.0.10", forwarded_for="203.0.113.9")

    assert limiter.check_rate_limit(first) == (True, 0, 0)
    assert limiter.check_rate_limit(second)[0] is False
    assert limiter.check_rate_limit(third) == (True, 0, 0)


def test_rate_limiter_tracks_each_path_separately():
    limiter = RateLimiter(requests=1, window=60)

    assert limiter.check_rate_limit(_request("/api/games")) == (True, 0, 0)
    assert limiter.check_rate_limit(_request("/api/settings")) == (True, 0, 0)
