from pathlib import Path


def test_factor_file_smooths_one_day_reversal_and_writes_reference_price(tmp_path, monkeypatch):
    import app.lean_engine.data_paths as data_paths

    monkeypatch.setattr(data_paths, "DATA_DIR", tmp_path / "Data")
    monkeypatch.setattr(data_paths, "REPO_ROOT", tmp_path)
    factors = [
        {"trade_date": "2024-06-24", "adj_factor": 14.953},
        {"trade_date": "2024-06-25", "adj_factor": 14.9525},
        {"trade_date": "2024-06-26", "adj_factor": 14.953},
        {"trade_date": "2025-06-30", "adj_factor": 14.9772},
    ]
    prices = [
        {"trade_date": "2024-06-24", "close": 18.08},
        {"trade_date": "2024-06-25", "close": 17.34},
        {"trade_date": "2024-06-26", "close": 17.69},
        {"trade_date": "2025-06-27", "close": 24.72},
        {"trade_date": "2025-06-30", "close": 24.83},
    ]

    metadata = data_paths.write_equity_factor_file(
        "600460",
        factors,
        market="china",
        price_rows=prices,
        require_reference_prices=True,
    )
    path = tmp_path / "Data" / "equity" / "china" / "factor_files" / "600460.csv"
    text = path.read_text(encoding="utf-8")

    assert "20240625" not in text
    assert "20240626" not in text
    assert "20250630,1.0000000000,1,24.7200000000" in text
    assert metadata["sanitized_transient_dates"] == ["2024-06-25"]
    assert metadata["event_dates"] == ["2025-06-30"]
    assert data_paths.validate_equity_factor_file(path)["passed"] is True


def test_factor_file_validation_rejects_zero_reference_price_on_change(tmp_path):
    from app.lean_engine.data_paths import validate_equity_factor_file

    path = Path(tmp_path) / "600460.csv"
    path.write_text(
        "20240624,0.9983842107,1,0\n"
        "20240625,0.9983508266,1,0\n"
        "20501231,1,1,0\n",
        encoding="utf-8",
    )

    validation = validate_equity_factor_file(path)

    assert validation["passed"] is False
    assert validation["errors"] == ["20240625:zero_reference_price"]
