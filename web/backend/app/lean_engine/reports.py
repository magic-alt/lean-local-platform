from pathlib import Path

from ..reporting.html_report import render_report_file

def render_report(result_json: Path, report_html: Path) -> None:
    render_report_file(result_json, report_html)
