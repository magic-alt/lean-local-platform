from __future__ import annotations

import sys
from pathlib import Path

import pytest


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


def test_parse_legacy_csindex_html_promotes_embedded_adjustment_headers():
    from app.services.csi300_pit import parse_adjustment_notice

    html = """
    <table><tr><td>关于定期调整的说明</td></tr></table>
    <table>
      <tr><td>调出样本</td><td>调出样本</td><td>调入样本</td><td>调入样本</td></tr>
      <tr><td>股票代码</td><td>股票名称</td><td>证券代码</td><td>证券简称</td></tr>
      <tr><td>000029</td><td>深深房A</td><td>000059</td><td>辽通化工</td></tr>
    </table>
    """

    parsed = parse_adjustment_notice(
        html.encode(),
        index_code="CSI300",
        source_url="https://www.csindex.com.cn/legacy/notice",
        announce_date="2005-06-22",
        effective_date="2005-07-01",
        content_type="html",
    )

    assert sorted((item["action_type"], item["symbol"]) for item in parsed["events"]) == [
        ("add", "000059"),
        ("delete", "000029"),
    ]


def test_parse_legacy_csindex_html_filters_index_matrix_to_csi300():
    from app.services.csi300_pit import parse_adjustment_notice

    html = """
    <table>
      <tr><td>指数名称</td><td>调入</td><td>调入</td><td>调出</td><td>调出</td></tr>
      <tr><td>指数名称</td><td>股票代码</td><td>股票名称</td><td>股票代码</td><td>股票名称</td></tr>
      <tr><td>沪深300指数</td><td>601857</td><td>中国石油</td><td>002025</td><td>航天电器</td></tr>
      <tr><td>中证100指数</td><td>601857</td><td>中国石油</td><td>600270</td><td>外运发展</td></tr>
    </table>
    """

    parsed = parse_adjustment_notice(
        html.encode(),
        index_code="CSI300",
        source_url="https://www.csindex.com.cn/legacy/notice",
        announce_date="2007-11-06",
        effective_date="2007-11-19",
        content_type="html",
    )

    assert sorted((item["action_type"], item["symbol"]) for item in parsed["events"]) == [
        ("add", "601857"),
        ("delete", "002025"),
    ]


def test_parse_legacy_csindex_html_uses_symbol_values_when_delete_headers_are_reversed():
    from app.services.csi300_pit import parse_adjustment_notice

    html = """
    <table>
      <tr><td>指数名称</td><td>调入</td><td>调入</td><td>调出</td><td>调出</td></tr>
      <tr><td>指数名称</td><td>股票名称</td><td>股票代码</td><td>股票名称</td><td>股票代码</td></tr>
      <tr><td>沪深300指数</td><td>大秦铁路</td><td>601006</td><td>000780</td><td>草原兴发</td></tr>
      <tr><td>中证100指数</td><td>大秦铁路</td><td>601006</td><td>600022</td><td>济南钢铁</td></tr>
    </table>
    """

    parsed = parse_adjustment_notice(
        html.encode(),
        index_code="CSI300",
        source_url="https://www.csindex.com.cn/legacy/ipo",
        announce_date="2006-08-02",
        effective_date="2006-08-15",
        content_type="html",
    )

    assert sorted((item["action_type"], item["symbol"]) for item in parsed["events"]) == [
        ("add", "601006"),
        ("delete", "000780"),
    ]


def test_parse_csindex_matrix_does_not_accept_hongkong_security_codes():
    from app.services.csi300_pit import parse_adjustment_notice

    html = """
    <table>
      <tr><td>指数代码</td><td>指数简称</td><td>调出</td><td>调出</td><td>调入</td><td>调入</td></tr>
      <tr><td>指数代码</td><td>指数简称</td><td>股票代码</td><td>股票名称</td><td>股票代码</td><td>股票名称</td></tr>
      <tr><td>000300</td><td>沪深300</td><td>600837</td><td>海通证券</td><td>HK06837</td><td>海通证券H</td></tr>
    </table>
    """

    parsed = parse_adjustment_notice(
        html.encode(),
        index_code="CSI300",
        source_url="https://www.csindex.com.cn/mixed-market",
        announce_date="2025-02-06",
        effective_date="2025-03-04",
        content_type="html",
    )

    assert [(item["action_type"], item["symbol"]) for item in parsed["events"]] == [
        ("delete", "600837"),
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


def test_csindex_effective_date_parses_legacy_adjustment_phrases(monkeypatch):
    import scripts.import_csindex_csi300_pit as importer

    monkeypatch.setattr(importer, "_first_trade_date", lambda year, month: f"{year:04d}-{month:02d}-04")

    assert importer.effective_date_from_content(
        "中证指数有限公司决定自11月19日起进行调整",
        "2007-11-06",
    ) == "2007-11-19"
    assert importer.effective_date_from_content(
        "决定于7月3日调整沪深300指数样本股",
        "2006-06-12",
    ) == "2006-07-03"
    assert importer.effective_date_from_content(
        "决定于2008年1月第一个交易日调整样本股",
        "2007-12-10",
    ) == "2008-01-04"


def test_csindex_offline_download_refuses_missing_attachment(tmp_path):
    import scripts.import_csindex_csi300_pit as importer

    with pytest.raises(RuntimeError, match="absent from the immutable offline bundle"):
        importer._download(
            "https://oss-ch.csindex.com.cn/missing.xlsx",
            tmp_path,
            offline=True,
        )


def test_official_initial_members_use_2005_snapshot_not_current_members():
    import scripts.import_csindex_csi300_pit as importer

    rows = []
    symbols = [f"{index:06d}" for index in range(1, 301)]
    for index in range(0, 300, 3):
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{symbol}</td><td>Name {symbol}</td>"
                for symbol in symbols[index : index + 3]
            )
            + "</tr>"
        )
    detail = {
        "id": 86,
        "publishDate": "2005-07-12",
        "title": "沪深300指数样本股名单（2005年7月1日起生效）",
        "content": (
            "<table><tr><td>代码</td><td>名称</td><td>代码</td><td>名称</td>"
            "<td>代码</td><td>名称</td></tr>"
            + "".join(rows)
            + "</table>"
        ),
    }
    events = [
        {
            "symbol": "000001",
            "action_type": "delete",
            "effective_date": "2005-07-01",
        },
        {
            "symbol": "999999",
            "name": "Replacement",
            "action_type": "add",
            "effective_date": "2005-07-01",
        },
    ]
    detail["content"] = detail["content"].replace(
        "<td>000001</td><td>Name 000001</td>",
        "<td>999999</td><td>Replacement</td>",
    )

    initial, source = importer.official_initial_members([detail], events)

    assert len(initial) == 300
    assert "000001" in {item["symbol"] for item in initial}
    assert "999999" not in {item["symbol"] for item in initial}
    assert source["reconstruction"]["method"].startswith("reverse_official")
