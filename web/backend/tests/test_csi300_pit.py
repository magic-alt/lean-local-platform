from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def configure_temp_db(tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()


def test_parse_adjustment_notice_extracts_add_and_delete_events():
    from app.services.csi300_pit import parse_adjustment_notice

    html = """
    <table>
      <tr>
        <th>调入证券代码</th><th>调入证券名称</th>
        <th>调出证券代码</th><th>调出证券名称</th>
      </tr>
      <tr>
        <td>600000</td><td>浦发银行</td>
        <td>000002</td><td>万科A</td>
      </tr>
    </table>
    """

    parsed = parse_adjustment_notice(
        html.encode("utf-8"),
        index_code="CSI300",
        source_url="https://example.test/csi300-adjustment.html",
        announce_date="2024-05-15",
        effective_date="2024-06-01",
        content_type="html",
    )

    assert parsed["parse_status"] == "parsed"
    events = sorted(parsed["events"], key=lambda item: item["action_type"])
    assert [(item["action_type"], item["symbol"]) for item in events] == [("add", "600000"), ("delete", "000002")]
    assert all(item["announce_date"] == "2024-05-15" for item in events)
    assert all(item["effective_date"] == "2024-06-01" for item in events)
    assert all(item["raw_file_hash"] == parsed["raw_file_hash"] for item in events)


def test_parse_csi300_pdf_text_stops_before_next_index_section():
    from app.services.csi300_pit import events_from_csi300_pdf_text

    text = """
    附件：部分指数样本调整名单
    沪深 300 指数样本调整名单：
    调出名单 调入名单
    证券代码 证券名称 证券代码 证券名称
    000661 长春高新 000657 中钨高新
    000786 北新建材 000988 华工科技
    中证 500 指数样本调整名单：
    调出名单 调入名单
    证券代码 证券名称 证券代码 证券名称
    000426 兴业银锡 000661 长春高新
    """

    events = events_from_csi300_pdf_text(
        text,
        index_code="CSI300",
        source_url="unit.pdf",
        raw_file_hash="hash",
        announce_date="2026-05-29",
        effective_date="2026-06-15",
    )

    assert [(item["action_type"], item["symbol"]) for item in events] == [
        ("delete", "000661"),
        ("add", "000657"),
        ("delete", "000786"),
        ("add", "000988"),
    ]


def test_csi300_pit_materialization_respects_effective_date(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.db import db
    from app.services.ashare_repository import universe_as_of
    from app.services.csi300_pit import (
        build_membership_intervals,
        content_hash,
        materialize_membership_intervals,
        upsert_membership_events,
        upsert_source_artifact,
    )

    source_url = "manual:unit"
    raw_hash = content_hash(b"unit")
    upsert_source_artifact(
        index_code="CSI300_TEST",
        source_url=source_url,
        raw_file_hash=raw_hash,
        content_type="json",
        parse_status="parsed",
        metadata={"fixture": True},
    )
    events = [
        {
            "index_code": "CSI300_TEST",
            "symbol": "000002",
            "name": "Vanke A",
            "action_type": "delete",
            "adjustment_type": "regular",
            "announce_date": "2024-05-15",
            "effective_date": "2024-06-01",
            "source_url": source_url,
            "raw_file_hash": raw_hash,
        },
        {
            "index_code": "CSI300_TEST",
            "symbol": "600000",
            "name": "SPDB",
            "action_type": "add",
            "adjustment_type": "regular",
            "announce_date": "2024-05-15",
            "effective_date": "2024-06-01",
            "source_url": source_url,
            "raw_file_hash": raw_hash,
        },
    ]
    upsert_membership_events(events, batch_id="unit-batch")
    built = build_membership_intervals(
        index_code="CSI300_TEST",
        initial_announce_date="2024-01-01",
        initial_effective_date="2024-01-01",
        initial_members=[
            {"symbol": "000001", "name": "Ping An Bank", "listed_date": "1991-04-03"},
            {"symbol": "000002", "name": "Vanke A", "listed_date": "1991-01-29"},
            {"symbol": "600519", "name": "Kweichow Moutai", "listed_date": "2001-08-27"},
        ],
        events=events,
        source="unit",
        batch_id="unit-batch",
        previous_trade_date_fn=lambda effective_date: "2024-05-31",
    )

    assert built["warnings"] == []
    materialize_membership_intervals(
        index_code="CSI300_TEST",
        intervals=built["intervals"],
        source="unit",
        batch_id="unit-batch",
        replace=True,
    )

    assert [item["symbol"] for item in universe_as_of("CSI300_TEST", "2024-05-31")] == [
        "000001",
        "000002",
        "600519",
    ]
    assert [item["symbol"] for item in universe_as_of("CSI300_TEST", "2024-06-01")] == [
        "000001",
        "600000",
        "600519",
    ]
    with db() as connection:
        event_count = connection.execute("select count(*) as count from index_membership_events").fetchone()["count"]
        pit_count = connection.execute("select count(*) as count from index_membership_pit where index_code = 'CSI300_TEST'").fetchone()[
            "count"
        ]
    assert event_count == 2
    assert pit_count == 4


def test_csindex_effective_date_uses_next_trade_date_for_close_after(monkeypatch):
    import scripts.import_csindex_csi300_pit as importer

    monkeypatch.setattr(importer, "_next_trade_date", lambda day: "2021-06-15")

    content = "<p>本次样本调整将于2021年6月11日收盘后生效。</p>"

    assert importer.effective_date_from_content(content, "2021-05-28") == "2021-06-15"
