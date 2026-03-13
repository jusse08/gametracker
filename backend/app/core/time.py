from datetime import UTC, datetime


def utc_now() -> datetime:
    # Keep UTC semantics without using deprecated datetime.utcnow().
    # The project still stores DB timestamps as naive UTC values, so we
    # normalize back to naive datetime for compatibility with existing rows.
    return datetime.now(UTC).replace(tzinfo=None)
