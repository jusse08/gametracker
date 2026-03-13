from datetime import UTC, datetime

from app.core.time import as_utc_aware, as_utc_naive, utc_now, utc_now_aware


def test_utc_now_returns_naive_utc_datetime():
    current = utc_now()

    assert current.tzinfo is None


def test_utc_now_aware_returns_aware_utc_datetime():
    current = utc_now_aware()

    assert current.tzinfo == UTC


def test_as_utc_aware_marks_naive_values_as_utc():
    value = datetime(2026, 3, 13, 12, 30, 0)

    normalized = as_utc_aware(value)

    assert normalized == datetime(2026, 3, 13, 12, 30, 0, tzinfo=UTC)


def test_as_utc_naive_converts_aware_values_back_to_naive_utc():
    value = datetime(2026, 3, 13, 15, 30, 0, tzinfo=UTC)

    normalized = as_utc_naive(value)

    assert normalized == datetime(2026, 3, 13, 15, 30, 0)
    assert normalized.tzinfo is None
