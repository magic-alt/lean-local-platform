from __future__ import annotations

import gzip
import json


def _rows(dates=("2005-04-29", "2005-05-31"), members=300):
    return [
        {
            "universe_code": "CSI300",
            "symbol": f"{600000 + member:06d}",
            "trade_date": snapshot_date,
            "weight": 100.0 / members,
            "source": "tushare:index_weight",
        }
        for snapshot_date in dates
        for member in range(members)
    ]


def test_snapshot_validation_and_intervals_are_no_lookahead():
    from app.services.tushare_csi300_pit import build_snapshot_intervals, validate_snapshot_rows

    rows = _rows()
    report = validate_snapshot_rows(rows, weight_sum_tolerance=0.01)
    intervals = build_snapshot_intervals(rows, batch_id="unit")

    assert report["snapshotCount"] == 2
    assert report["coverageStart"] == "2005-04-29"
    assert report["coverageEnd"] == "2005-05-31"
    assert report["isOfficialSource"] is False
    first = next(item for item in intervals if item["start_date"] == "2005-04-29")
    second = next(item for item in intervals if item["start_date"] == "2005-05-31")
    assert first["end_date"] == "2005-05-30"
    assert first["announce_date"] == "2005-04-29"
    assert second["end_date"] is None


def test_snapshot_validation_rejects_incomplete_or_gapped_series():
    import pytest

    from app.services.tushare_csi300_pit import validate_snapshot_rows

    with pytest.raises(ValueError, match="Incomplete CSI300 snapshots"):
        validate_snapshot_rows(_rows(members=299))
    with pytest.raises(ValueError, match="coverage gaps"):
        validate_snapshot_rows(_rows(dates=("2005-04-29", "2005-08-31")))


def test_governed_import_can_explicitly_quarantine_an_incomplete_snapshot():
    from app.services.tushare_csi300_pit import import_tushare_csi300_snapshots

    rows = [
        *_rows(dates=("2005-04-29",)),
        *_rows(dates=("2005-05-31",), members=299),
        *_rows(dates=("2005-06-30",)),
    ]

    class Adapter:
        def index_weight_rows(self, index_code, start_date, end_date):
            return rows

    result = import_tushare_csi300_snapshots(
        end_date="2005-06-30",
        adapter=Adapter(),
        dry_run=True,
        quarantine_incomplete=True,
    )

    assert result["snapshotCount"] == 2
    assert result["providerRowCount"] == 899
    assert result["quarantinedRows"] == 299
    assert result["quarantinedSnapshots"] == {"2005-05-31": 299}


def test_governed_import_writes_archive_and_shadow_only(tmp_path, monkeypatch):
    from tests.test_csi300_pit import configure_temp_db

    configure_temp_db(tmp_path, monkeypatch)
    rows = _rows()

    class Adapter:
        def index_weight_rows(self, index_code, start_date, end_date):
            assert index_code == "000300"
            return rows

    from app.db import db
    from app.services.db_object_store import read_bytes
    from app.services.tushare_csi300_pit import import_tushare_csi300_snapshots

    result = import_tushare_csi300_snapshots(
        start_date="2005-01-01",
        end_date="2005-05-31",
        adapter=Adapter(),
    )

    assert result["promotionStatus"] == "shadow_only"
    assert result["canonicalRows"] == 600
    assert result["membershipRows"] == 600
    with db() as connection:
        archive = connection.execute(
            "select * from provider_raw_archives where run_id=? and dataset_key='index_weight'",
            (result["batchId"],),
        ).fetchone()
        stored = connection.execute("select * from stored_objects where id=?", (archive["object_id"],)).fetchone()
        raw_payloads = connection.execute(
            "select count(*) as count from provider_raw_records where dataset_key='index_weight' and payload_json<>''"
        ).fetchone()["count"]
        official_members = connection.execute(
            "select count(*) as count from universe_membership where universe_code='CSI300'"
        ).fetchone()["count"]
        shadow_members = connection.execute(
            "select count(*) as count from universe_membership where universe_code='CSI300_TUSHARE'"
        ).fetchone()["count"]
    assert archive["archive_sha256"] == stored["sha256"]
    assert json.loads(gzip.decompress(read_bytes(stored["id"])))
    assert raw_payloads == 0
    assert official_members == 0
    assert shadow_members == 600
