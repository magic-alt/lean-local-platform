#!/usr/bin/env python3
"""Refresh the checked-in TuShare stock/index/futures/options contract snapshot.

The generated contract is deliberately independent from account entitlements:
it describes what the provider publishes, while runtime permission probes
describe which endpoints the configured account can currently call.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import re
from pathlib import Path
import time
from typing import Any
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "config" / "tushare_contracts.v1.json"
BASE_URL = "https://tushare.pro"
INDEX_URL = f"{BASE_URL}/document/2?doc_id="
TARGET_CATEGORIES = {
    "股票数据": "equity",
    "指数专题": "index",
    "期货数据": "future",
    "期权数据": "option",
}
DOC_OVERRIDES: dict[str, dict[str, str]] = {
    "109": {"datasetKey": "pro_bar_general", "apiName": "pro_bar", "deliveryMethod": "sdk"},
    "146": {"datasetKey": "pro_bar_equity", "apiName": "pro_bar", "deliveryMethod": "sdk"},
    # TuShare documents this as licensed CSV delivery rather than a Pro API.
    "314": {"datasetKey": "futures_tick_file", "apiName": "file_delivery", "deliveryMethod": "file"},
}
CANONICAL_APIS = {
    "stock_basic", "stock_st", "st", "namechange", "trade_cal", "daily",
    "weekly", "monthly", "adj_factor", "daily_basic", "stk_limit", "suspend_d",
    "income", "balancesheet", "cashflow", "forecast", "express", "dividend",
    "fina_indicator", "fina_audit", "fina_mainbz", "disclosure_date",
    "index_basic", "index_daily", "index_weekly", "index_monthly", "index_weight",
    "index_dailybasic", "index_classify", "index_member_all", "sw_daily",
    "fut_basic", "fut_daily", "fut_mapping", "fut_settle", "ft_limit",
    "opt_basic", "opt_daily",
}
DATE_FIELDS = {
    "date", "trade_date", "cal_date", "ann_date", "end_date", "start_date",
    "list_date", "delist_date", "maturity_date", "last_edate", "last_ddate",
    "pub_date", "imp_date", "record_date", "ex_date", "pay_date", "div_listdate",
    "base_date", "exp_date", "in_date", "out_date", "float_date", "suspend_date",
    "resume_date", "delivery_date", "report_date",
}
DATETIME_TOKENS = ("time", "datetime", "timestamp")


def _fetch(url: str) -> str:
    error: Exception | None = None
    for attempt in range(3):
        request = Request(
            url,
            headers={
                "User-Agent": "lean-platform-contract-audit/1.0",
                "Connection": "close",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - retries transient documentation errors.
            error = exc
            if attempt < 2:
                time.sleep(0.25 * (2**attempt))
    raise RuntimeError(f"Unable to fetch TuShare contract document after retries: {url}") from error


def _doc_id(href: str) -> str:
    match = re.search(r"doc_id=(\d+)", href)
    return match.group(1) if match else ""


def _leaf_documents(index_html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(index_html, "html.parser")
    sidebar = soup.select_one("#jstree")
    if sidebar is None:
        raise RuntimeError("TuShare document sidebar was not found.")
    documents: list[dict[str, str]] = []
    for category_title, asset_class in TARGET_CATEGORIES.items():
        category_link = next(
            (link for link in sidebar.find_all("a") if link.get_text(" ", strip=True) == category_title),
            None,
        )
        if category_link is None:
            raise RuntimeError(f"TuShare category not found: {category_title}")
        category_node = category_link.find_parent("li")
        if category_node is None:
            raise RuntimeError(f"TuShare category node is invalid: {category_title}")
        for node in category_node.find_all("li"):
            # Only terminal menu nodes represent endpoint documents. Parent
            # nodes are organizational headings and do not define contracts.
            if node.find("ul", recursive=False) is not None:
                continue
            link = node.find("a", recursive=False)
            if link is None:
                continue
            href = str(link.get("href") or "")
            identifier = _doc_id(href)
            if not identifier:
                continue
            documents.append(
                {
                    "assetClass": asset_class,
                    "category": category_title,
                    "title": link.get_text(" ", strip=True),
                    "docId": identifier,
                    "documentationUrl": f"{BASE_URL}/document/2?doc_id={identifier}",
                }
            )
    return documents


def _api_names(text: str) -> list[str]:
    names: list[str] = []
    patterns = (
        r"(?:接口|接口名)[：:]\s*`?([A-Za-z][A-Za-z0-9_]*)",
        r"API[：:]\s*`?([A-Za-z][A-Za-z0-9_]*)",
    )
    for pattern in patterns:
        for value in re.findall(pattern, text, flags=re.IGNORECASE):
            name = value.strip().lower()
            if name not in names and name not in {"python", "http", "restful"}:
                names.append(name)
    return names


def _field_name(value: str) -> str:
    cleaned = value.strip().strip("`").lower().replace(" ", "_")
    cleaned = re.sub(r"[^a-z0-9_]", "", cleaned)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"field_{cleaned}"
    return cleaned


def _field_type(name: str, provider_type: str) -> str:
    lowered = provider_type.lower()
    if name in DATE_FIELDS or name.endswith("_date"):
        return "date"
    if any(token in name for token in DATETIME_TOKENS) and name not in {"trade_time_desc"}:
        return "datetime"
    if any(token in lowered for token in ("int", "integer")):
        return "integer"
    if any(token in lowered for token in ("float", "double", "decimal", "number")):
        return "decimal"
    if any(token in lowered for token in ("bool", "boolean")):
        return "boolean"
    return "string"


def _table_fields(content: Tag) -> list[dict[str, Any]]:
    candidates: list[list[dict[str, Any]]] = []
    output_mode = False
    for element in content.find_all(["h1", "h2", "h3", "h4", "h5", "p", "table"]):
        if element.name != "table":
            label = element.get_text(" ", strip=True)
            if "输出参数" in label or "输出字段" in label or "返回字段" in label:
                output_mode = True
            elif "输入参数" in label:
                output_mode = False
            continue
        headers = [cell.get_text(" ", strip=True) for cell in element.select("thead th")]
        if not headers:
            first = element.find("tr")
            headers = [cell.get_text(" ", strip=True) for cell in first.find_all(["th", "td"])] if first else []
        normalized_headers = [header.lower() for header in headers]
        if not any(header in {"名称", "name", "字段", "字段名"} for header in normalized_headers):
            continue
        rows: list[dict[str, Any]] = []
        body_rows = element.select("tbody tr") or element.find_all("tr")[1:]
        for row in body_rows:
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if not cells:
                continue
            values = {headers[index]: cells[index] for index in range(min(len(headers), len(cells)))}
            raw_name = next((values[key] for key in headers if key.lower() in {"名称", "name", "字段", "字段名"}), cells[0])
            name = _field_name(raw_name)
            if not name:
                continue
            provider_type = next((values[key] for key in headers if "类型" in key or key.lower() == "type"), "str")
            description = next((values[key] for key in headers if "描述" in key or "说明" in key), "")
            default_display = next((values[key] for key in headers if "默认" in key or "必选" in key), "")
            rows.append(
                {
                    "name": name,
                    "providerName": raw_name.strip().strip("`"),
                    "providerType": provider_type or "str",
                    "type": _field_type(name, provider_type),
                    "nullable": str(default_display).upper() not in {"Y", "是", "必选"},
                    "description": description,
                }
            )
        if rows:
            if output_mode:
                return rows
            candidates.append(rows)
    return candidates[-1] if candidates else []


def _natural_key(fields: list[dict[str, Any]]) -> list[str]:
    names = {field["name"] for field in fields}
    result: list[str] = []
    for candidate in ("ts_code", "index_code", "con_code", "symbol", "exchange"):
        if candidate in names:
            result.append(candidate)
            break
    for candidate in (
        "trade_time", "timestamp", "trade_date", "cal_date", "ann_date", "end_date",
        "start_date", "pub_date", "imp_date", "in_date", "record_date",
    ):
        if candidate in names:
            result.append(candidate)
            break
    if not result and fields:
        result.append(str(fields[0]["name"]))
    return result


def _storage_tier(title: str, api_name: str) -> str:
    text = f"{title} {api_name}".lower()
    if any(token in text for token in ("分钟", "tick", "实时", "_min", "mins")):
        return "columnar"
    return "canonical" if api_name in CANONICAL_APIS else "typed_source"


def _document_contracts(entry: tuple[int, dict[str, str]]) -> list[dict[str, Any]]:
    index, document = entry
    html = _fetch(document["documentationUrl"])
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("#document .document > .content") or soup.select_one("#document .content")
    if content is None:
        raise RuntimeError(f"TuShare document content was not found: {document['documentationUrl']}")
    text = content.get_text(" ", strip=True)
    override = DOC_OVERRIDES.get(document["docId"])
    names = [override["apiName"]] if override else _api_names(text)
    if not names:
        names = [f"doc_{document['docId']}"]
    fields = _table_fields(content)
    retired = any(token in document["title"] for token in ("（停）", "(停)", "（旧）", "(旧)"))
    contracts = [
        {
            "datasetKey": str(override["datasetKey"]) if override else api_name,
            "apiName": api_name,
            "assetClass": document["assetClass"],
            "category": document["category"],
            "title": document["title"],
            "status": "retired" if retired else "active",
            "documentationUrl": document["documentationUrl"],
            "docId": document["docId"],
            "storageTier": _storage_tier(document["title"], api_name),
            "sourceTable": f"src_tushare_{str(override['datasetKey']) if override else api_name}",
            "deliveryMethod": str(override.get("deliveryMethod", "pro_api")) if override else "pro_api",
            "naturalKey": _natural_key(fields),
            "fields": fields,
            "contractComplete": bool(fields) and (override is not None or not api_name.startswith("doc_")),
            "ordinal": index * 10 + offset,
        }
        for offset, api_name in enumerate(names)
    ]
    return contracts


def _contracts(documents: list[dict[str, str]]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    entries = list(enumerate(documents, start=1))
    with ThreadPoolExecutor(max_workers=24, thread_name_prefix="tushare-contract") as executor:
        document_results = list(executor.map(_document_contracts, entries))
    used_names: set[str] = set()
    for document_contracts in document_results:
        for contract in document_contracts:
            api_name = str(contract["apiName"])
            unique_name = str(contract["datasetKey"])
            if unique_name in used_names:
                unique_name = f"{api_name}_doc_{contract['docId']}"
            used_names.add(unique_name)
            contract["datasetKey"] = unique_name
            contract["sourceTable"] = f"src_tushare_{unique_name}"
            contracts.append(contract)
    return contracts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    args = parser.parse_args()
    documents = _leaf_documents(_fetch(INDEX_URL))
    contracts = _contracts(documents)
    counts: dict[str, int] = {}
    for item in contracts:
        counts[item["assetClass"]] = counts.get(item["assetClass"], 0) + 1
    payload = {
        "schemaVersion": 1,
        "contractVersion": f"{args.as_of}.1",
        "provider": "tushare",
        "documentationUrl": INDEX_URL,
        "asOfDate": args.as_of,
        "assetClasses": sorted(TARGET_CATEGORIES.values()),
        "counts": counts,
        "contracts": sorted(contracts, key=lambda item: (item["ordinal"], item["datasetKey"])),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": counts, "total": len(contracts)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
