from __future__ import annotations

from pathlib import Path

from app.services.fundamental_release import (
    PIT_FUNDAMENTAL_V2_FIELDS,
    build_pit_fundamentals_v2,
    export_pit_fundamentals_v2,
)


def _report(value: float, *, ann_date: str, f_ann_date: str | None = None, update: str = "0"):
    return {
        "instrument": "SZ000001",
        "end_date": "2026-03-31",
        "ann_date": ann_date,
        "f_ann_date": f_ann_date,
        "update_flag": update,
        "observed_at": f"2026-04-{value:02.0f}T12:00:00+08:00",
        "payload_hash": str(value),
        **{field: value for field in PIT_FUNDAMENTAL_V2_FIELDS},
    }


def test_pit_v2_uses_next_open_after_final_announcement_and_revision():
    calendar = ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-06"]
    frame = build_pit_fundamentals_v2(
        [
            _report(1.0, ann_date="2026-04-01"),
            _report(2.0, ann_date="2026-04-01", f_ann_date="2026-04-02", update="1"),
        ],
        calendar,
    )

    assert frame.select("trade_date").to_series().to_list() == [
        "2026-04-02",
        "2026-04-03",
        "2026-04-06",
    ]
    assert frame.select("total_assets_pit").to_series().to_list() == [1.0, 2.0, 2.0]
    assert frame.row(0, named=True)["source_ann_date"] == "2026-04-01"
    assert frame.row(1, named=True)["source_ann_date"] == "2026-04-02"


def test_pit_v2_export_is_hashed_and_schema_complete(tmp_path: Path):
    component = export_pit_fundamentals_v2(
        [_report(1.0, ann_date="2026-04-01")],
        ["2026-04-01", "2026-04-02", "2026-04-03"],
        tmp_path / "pit-v2.parquet",
    )
    assert component["role"] == "pit_fundamentals"
    assert component["schemaVersion"] == "2"
    assert component["files"][0]["rowCount"] == 2
    assert Path(component["files"][0]["path"]).is_file()
