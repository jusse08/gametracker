from datetime import UTC, datetime


def utc_now_aware() -> datetime:
    return datetime.now(UTC)


def as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def as_utc_naive(value: datetime) -> datetime:
    return as_utc_aware(value).replace(tzinfo=None)


def utc_now() -> datetime:
    # Keep UTC semantics without using deprecated datetime.utcnow().
    # The project still stores DB timestamps as naive UTC values, so we
    # normalize back to naive datetime for compatibility with existing rows.
    return as_utc_naive(utc_now_aware())
