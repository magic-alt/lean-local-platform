import pytest

from app.lean_engine.symbols import parse_date


def test_parse_date_normalizes_single_digit_month_and_day():
    assert parse_date("2026-6-31").isoformat() == "2026-06-30"


def test_parse_date_keeps_padded_isoformat():
    assert parse_date("2026-06-30").isoformat() == "2026-06-30"


def test_parse_date_rejects_invalid_month():
    with pytest.raises(Exception, match="Invalid date"):
        parse_date("2026-13-01")

