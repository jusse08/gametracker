from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_isoformat() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")
