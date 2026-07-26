from __future__ import annotations

import csv
from io import BytesIO, StringIO
import json
from typing import Any
from xml.sax.saxutils import escape


REPORT_LAYOUT_VERSION = "report-layout-v2"


def report_payload(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result") or {}
    parameters = item.get("parameters") or {}
    symbol = item.get("symbol") or parameters.get("ticker") or parameters.get("symbol")
    asset_class = item.get("asset_class") or parameters.get("assetClass") or "equity"
    title = parameters.get("name") or (f"Local {asset_class} {symbol} Backtest" if symbol else "LEAN Backtest Report")
    return {
        "id": item.get("id"),
        "runId": item.get("run_id"),
        "source": item.get("source"),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
        "finishedAt": item.get("finished_at"),
        "error": item.get("error"),
        "title": title,
        "symbol": symbol,
        "market": item.get("venue") or parameters.get("market") or parameters.get("venue"),
        "provider": parameters.get("providerSource") or parameters.get("source"),
        "startDate": parameters.get("start"),
        "endDate": parameters.get("end"),
        "initialCash": parameters.get("initialCash") or parameters.get("initial_cash") or parameters.get("cash"),
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
        f"<!-- {REPORT_LAYOUT_VERSION} -->",
        "",
        f"# {payload.get('title') or 'LEAN Backtest Report'}",
        "",
        f"> QUANTCONNECT LEAN · 回测分析 · 运行编号 `{payload.get('runId') or payload.get('id')}`",
        "",
        "## Summary",
        "",
        f"- Symbol: {payload.get('symbol') or '-'}",
        f"- Market: {payload.get('market') or '-'}",
        f"- Period: {payload.get('startDate') or '-'} to {payload.get('endDate') or '-'}",
        f"- Provider: {payload.get('provider') or '-'}",
        f"- Initial Cash: {payload.get('initialCash') or '-'}",
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


def json_report(payload: dict[str, Any]) -> str:
    """Return a deterministic, human-readable structured report."""
    return json.dumps(
        {"layoutVersion": REPORT_LAYOUT_VERSION, **payload},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"


def csv_report(payload: dict[str, Any]) -> str:
    """Flatten report metadata, metrics and artifacts into a portable ledger."""
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["section", "key", "value"])
    summary_fields = (
        ("title", "title"),
        ("run_id", "runId"),
        ("symbol", "symbol"),
        ("market", "market"),
        ("period_start", "startDate"),
        ("period_end", "endDate"),
        ("provider", "provider"),
        ("initial_cash", "initialCash"),
        ("status", "status"),
        ("created_at", "createdAt"),
        ("finished_at", "finishedAt"),
        ("error", "error"),
    )
    for key, payload_key in summary_fields:
        writer.writerow(["summary", key, _csv_value(payload.get(payload_key))])
    for key, value in sorted((payload.get("metrics") or {}).items(), key=lambda item: str(item[0])):
        writer.writerow(["metric", key, _csv_value(value)])
    validation = payload.get("validation") or {}
    for key in ("passed", "severity"):
        if key in validation:
            writer.writerow(["validation", key, _csv_value(validation.get(key))])
    for index, gate in enumerate(validation.get("gates") or [], start=1):
        writer.writerow(["validation_gate", str(index), _csv_value(gate)])
    experiment = payload.get("experiment") or {}
    for key, value in (
        ("strategy_sha256", (experiment.get("strategy") or {}).get("sha256")),
        ("parameters_sha256", (experiment.get("parameters") or {}).get("sha256")),
        ("docker_image", (experiment.get("environment") or {}).get("dockerImage")),
    ):
        if value not in (None, ""):
            writer.writerow(["experiment", key, _csv_value(value)])
    for item in payload.get("storedObjects") or []:
        key = item.get("object_key") or item.get("key") or "-"
        writer.writerow(
            [
                "artifact",
                key,
                _csv_value(
                    {
                        "sha256": item.get("sha256"),
                        "size": item.get("size"),
                        "contentType": item.get("content_type"),
                    }
                ),
            ]
        )
    for section in ("orders", "trades", "holdings"):
        for index, item in enumerate(payload.get(section) or [], start=1):
            writer.writerow([section[:-1], str(index), _csv_value(item)])
    for key, value in sorted((payload.get("performance") or {}).items(), key=lambda item: str(item[0])):
        writer.writerow(["performance", key, _csv_value(value)])
    # Excel recognizes the UTF-8 BOM and does not corrupt Chinese labels.
    return "\ufeff" + stream.getvalue()


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def pdf_report(payload: dict[str, Any]) -> bytes:
    """Render a compact, Unicode-safe PDF from the canonical report payload."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("reportlab is required for PDF report export.") from exc

    font_name = "STSong-Light"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))

    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=str(payload.get("title") or "LEAN Backtest Report"),
        author="LEAN Local",
        subject=f"Backtest report {payload.get('runId') or payload.get('id') or ''}",
    )
    sample = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=sample["Title"],
        fontName=font_name,
        fontSize=20,
        leading=25,
        textColor=colors.HexColor("#102A43"),
        alignment=TA_CENTER,
        spaceAfter=6 * mm,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=sample["Normal"],
        fontName=font_name,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#627D98"),
        alignment=TA_CENTER,
        spaceAfter=7 * mm,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=sample["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0B7285"),
        spaceBefore=4 * mm,
        spaceAfter=2.5 * mm,
    )
    cell_style = ParagraphStyle(
        "ReportCell",
        parent=sample["BodyText"],
        fontName=font_name,
        fontSize=8.2,
        leading=11,
        textColor=colors.HexColor("#243B53"),
    )
    small_style = ParagraphStyle(
        "ReportSmall",
        parent=cell_style,
        fontSize=7.2,
        leading=9.5,
        textColor=colors.HexColor("#486581"),
    )

    def paragraph(value: Any, style=cell_style) -> Any:
        return Paragraph(escape("-" if value in (None, "") else str(value)), style)

    def table(rows: list[list[Any]], widths: list[float], *, header: bool = True) -> Any:
        output = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BCCCDC")),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
        ]
        if header:
            commands.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF0")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#102A43")),
                ]
            )
        output.setStyle(TableStyle(commands))
        return output

    story: list[Any] = [
        Paragraph(escape(str(payload.get("title") or "LEAN Backtest Report")), title_style),
        Paragraph(
            "QUANTCONNECT LEAN · 回测分析 · 运行编号 "
            + escape(str(payload.get("runId") or payload.get("id") or "-")),
            subtitle_style,
        ),
        Paragraph("Summary", heading_style),
    ]
    summary_rows = [
        [paragraph("Field"), paragraph("Value")],
        [paragraph("Symbol"), paragraph(payload.get("symbol"))],
        [paragraph("Market"), paragraph(payload.get("market"))],
        [paragraph("Period"), paragraph(f"{payload.get('startDate') or '-'} to {payload.get('endDate') or '-'}")],
        [paragraph("Provider"), paragraph(payload.get("provider"))],
        [paragraph("Initial Cash"), paragraph(payload.get("initialCash"))],
        [paragraph("Status"), paragraph(payload.get("status"))],
        [paragraph("Created"), paragraph(payload.get("createdAt"))],
        [paragraph("Finished"), paragraph(payload.get("finishedAt"))],
    ]
    if payload.get("error"):
        summary_rows.append([paragraph("Error"), paragraph(payload.get("error"))])
    story.extend([table(summary_rows, [42 * mm, 132 * mm]), Spacer(1, 2 * mm), Paragraph("Metrics", heading_style)])

    metric_rows = [[paragraph("Metric"), paragraph("Value")]]
    metrics = payload.get("metrics") or {}
    if metrics:
        metric_rows.extend([paragraph(key), paragraph(value)] for key, value in sorted(metrics.items(), key=lambda item: str(item[0])))
    else:
        metric_rows.append([paragraph("-"), paragraph("-")])
    story.append(table(metric_rows, [92 * mm, 82 * mm]))

    validation = payload.get("validation") or {}
    if validation:
        story.extend(
            [
                Paragraph("Validation", heading_style),
                table(
                    [
                        [paragraph("Passed"), paragraph(validation.get("passed"))],
                        [paragraph("Severity"), paragraph(validation.get("severity"))],
                        [paragraph("Gate Count"), paragraph(len(validation.get("gates") or []))],
                    ],
                    [42 * mm, 132 * mm],
                    header=False,
                ),
            ]
        )

    experiment = payload.get("experiment") or {}
    if experiment:
        story.extend(
            [
                Paragraph("Experiment", heading_style),
                table(
                    [
                        [paragraph("Strategy SHA256"), paragraph((experiment.get("strategy") or {}).get("sha256"), small_style)],
                        [paragraph("Parameters SHA256"), paragraph((experiment.get("parameters") or {}).get("sha256"), small_style)],
                        [paragraph("Docker Image"), paragraph((experiment.get("environment") or {}).get("dockerImage"), small_style)],
                    ],
                    [42 * mm, 132 * mm],
                    header=False,
                ),
            ]
        )

    story.extend([Paragraph("Artifacts", heading_style)])
    artifact_rows = [[paragraph("Object"), paragraph("SHA256"), paragraph("Size")]]
    objects = payload.get("storedObjects") or []
    if objects:
        artifact_rows.extend(
            [
                paragraph(item.get("object_key") or item.get("key"), small_style),
                paragraph(item.get("sha256"), small_style),
                paragraph(item.get("size"), small_style),
            ]
            for item in objects
        )
    else:
        artifact_rows.append([paragraph("-"), paragraph("-"), paragraph("-")])
    story.append(table(artifact_rows, [72 * mm, 82 * mm, 20 * mm]))

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(font_name, 7)
        canvas.setFillColor(colors.HexColor("#829AB1"))
        canvas.drawString(18 * mm, 9 * mm, REPORT_LAYOUT_VERSION)
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
