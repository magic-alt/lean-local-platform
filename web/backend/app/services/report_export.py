from __future__ import annotations

import csv
import io
import json
import textwrap
from typing import Any


def report_payload(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result") or {}
    return {
        "id": item.get("id"),
        "runId": item.get("run_id"),
        "source": item.get("source"),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
        "finishedAt": item.get("finished_at"),
        "error": item.get("error"),
        "metrics": result.get("summary_metrics") or result.get("statistics") or {},
        "performance": result.get("performance") or {},
        "orders": result.get("orders") or [],
        "trades": result.get("trades") or [],
        "holdings": result.get("holdings") or [],
        "validation": item.get("validation") or (result.get("performance") or {}).get("validation"),
        "experiment": item.get("experiment") or (result.get("performance") or {}).get("experiment"),
        "storedObjects": item.get("storedObjects") or [],
        "rawResultObjectId": item.get("raw_result_object_id"),
        "summaryObjectId": item.get("summary_object_id"),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Backtest Report: {payload.get('runId') or payload.get('id')}",
        "",
        "## Summary",
        "",
        f"- Status: {payload.get('status') or '-'}",
        f"- Created: {payload.get('createdAt') or '-'}",
        f"- Finished: {payload.get('finishedAt') or '-'}",
        f"- Error: {payload.get('error') or '-'}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    metrics = payload.get("metrics") or {}
    if metrics:
        lines.extend(f"| {key} | {value} |" for key, value in metrics.items())
    else:
        lines.append("| - | - |")
    validation = payload.get("validation") or {}
    if validation:
        lines.extend(
            [
                "",
                "## Validation",
                "",
                f"- Passed: {validation.get('passed')}",
                f"- Severity: {validation.get('severity')}",
                f"- Gates: {len(validation.get('gates') or [])}",
            ]
        )
    experiment = payload.get("experiment") or {}
    if experiment:
        lines.extend(
            [
                "",
                "## Experiment",
                "",
                f"- Strategy SHA256: {((experiment.get('strategy') or {}).get('sha256')) or '-'}",
                f"- Parameters SHA256: {((experiment.get('parameters') or {}).get('sha256')) or '-'}",
                f"- Docker Image: {((experiment.get('environment') or {}).get('dockerImage')) or '-'}",
            ]
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "| Key | SHA256 | Size |",
            "| --- | --- | --- |",
        ]
    )
    objects = payload.get("storedObjects") or []
    if objects:
        lines.extend(f"| {item.get('object_key') or item.get('key') or '-'} | {item.get('sha256') or '-'} | {item.get('size') or '-'} |" for item in objects)
    else:
        lines.append("| - | - | - |")
    return "\n".join(lines) + "\n"


def csv_report(payload: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "key", "value"])
    for key in ("id", "runId", "source", "status", "createdAt", "finishedAt", "error"):
        writer.writerow(["summary", key, payload.get(key) or ""])
    for key, value in (payload.get("metrics") or {}).items():
        writer.writerow(["metrics", key, value])
    validation = payload.get("validation") or {}
    for key in ("passed", "severity"):
        if key in validation:
            writer.writerow(["validation", key, validation.get(key)])
    experiment = payload.get("experiment") or {}
    for section in ("strategy", "parameters", "data", "environment"):
        for key, value in (experiment.get(section) or {}).items():
            writer.writerow([f"experiment.{section}", key, value])
    return output.getvalue()


def json_report(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _pdf_text(value: str) -> str:
    safe = value.encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_report(payload: dict[str, Any]) -> bytes:
    raw_lines = markdown_report(payload).replace("|", " ").replace("#", "").splitlines()
    lines: list[str] = []
    for line in raw_lines:
        wrapped = textwrap.wrap(line, width=96) or [""]
        lines.extend(wrapped)
    chunks = [lines[index : index + 54] for index in range(0, len(lines), 54)] or [[]]

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    page_ids = []
    next_id = 4
    for chunk in chunks:
        content = "BT\n/F1 10 Tf\n50 780 Td\n14 TL\n"
        for line in chunk:
            content += f"({_pdf_text(line)}) Tj\nT*\n"
        content += "ET\n"
        content_bytes = content.encode("latin-1", errors="replace")
        content_id = next_id
        page_id = next_id + 1
        next_id += 2
        objects[content_id] = b"<< /Length " + str(len(content_bytes)).encode() + b" >>\nstream\n" + content_bytes + b"endstream"
        objects[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents "
            + f"{content_id} 0 R".encode()
            + b" >>"
        )
        page_ids.append(page_id)
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids).encode()
    objects[2] = b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(page_ids)).encode() + b" >>"

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for object_id in sorted(objects):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(output)
