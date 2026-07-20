import pytest

from app.lean_engine.data_writers import normalize_rows, rows_from_csv
from app.lean_engine.errors import LeanPlatformError


def test_normalize_rows_clamps_provider_float_noise_at_ohlc_boundary():
    rows = normalize_rows(
        [
            {
                "date": "2024-03-11",
                "open": "271.2",
                "high": "278.6",
                "low": "271.2",
                "close": "278.60001",
                "volume": "17866889",
            }
        ]
    )

    assert rows[0][2] == pytest.approx(278.60001)


def test_normalize_rows_still_rejects_material_ohlc_violation():
    with pytest.raises(LeanPlatformError, match="violates high/low bounds"):
        normalize_rows(
            [
                {
                    "date": "2024-03-11",
                    "open": "271.2",
                    "high": "278.6",
                    "low": "271.2",
                    "close": "279.0",
                    "volume": "17866889",
                }
            ]
        )


def test_rows_from_csv_reports_all_missing_template_columns(tmp_path):
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text("date,price\n2026-07-17,10.5\n", encoding="utf-8")

    with pytest.raises(LeanPlatformError, match="Required columns: timestamp, open, high, low, close, volume"):
        rows_from_csv(csv_path)
