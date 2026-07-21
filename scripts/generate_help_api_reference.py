#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
OUTPUT = ROOT / "docs" / "help" / "api-reference.md"
sys.path.insert(0, str(BACKEND))


def _schema_name(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "-"
    ref = str(schema.get("$ref") or "")
    if ref:
        return f"`{ref.rsplit('/', 1)[-1]}`"
    if schema.get("type") == "array":
        return f"array[{_schema_name(schema.get('items'))}]"
    if schema.get("oneOf"):
        return " / ".join(_schema_name(item) for item in schema["oneOf"])
    if schema.get("anyOf"):
        return " / ".join(_schema_name(item) for item in schema["anyOf"])
    return f"`{schema.get('type') or 'object'}`"


def _request(operation: dict[str, Any]) -> str:
    parameters = operation.get("parameters") or []
    parts = [
        f"`{parameter.get('name')}` ({parameter.get('in')}{', required' if parameter.get('required') else ''})"
        for parameter in parameters
    ]
    body = operation.get("requestBody") or {}
    content = body.get("content") or {}
    if content:
        media_type = "application/json" if "application/json" in content else next(iter(content))
        parts.append(f"body {_schema_name(content[media_type].get('schema'))}")
    return "<br>".join(parts) or "-"


def _response(operation: dict[str, Any]) -> str:
    responses = operation.get("responses") or {}
    statuses = sorted((status for status in responses if str(status).startswith("2")), key=str)
    if not statuses:
        return "-"
    status = statuses[0]
    content = responses[status].get("content") or {}
    if not content:
        return f"`{status}`"
    media_type = "application/json" if "application/json" in content else next(iter(content))
    return f"`{status}` {_schema_name(content[media_type].get('schema'))}"


def generate() -> str:
    from app.main import app

    schema = app.openapi()
    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            tag = str((operation.get("tags") or ["other"])[0])
            grouped.setdefault(tag, []).append((method.upper(), path, operation))
    count = sum(len(items) for items in grouped.values())
    lines = [
        "# 完整 API 端点索引",
        "",
        "> 本文由 `scripts/generate_help_api_reference.py` 根据 FastAPI OpenAPI 确定性生成。",
        "> 业务语义、完整示例和错误处理请参阅 [API 使用指南](../api.md)。",
        "",
        f"当前共收录 **{count}** 个公开业务操作。交互式 Schema 以 `/docs` 和 `/openapi.json` 为准。",
        "",
    ]
    for tag in sorted(grouped):
        lines.extend([f"## {tag}", "", "| Method | Path | Summary | Input | Success |", "| --- | --- | --- | --- | --- |"])
        for method, path, operation in sorted(grouped[tag], key=lambda item: (item[1], item[0])):
            summary = str(operation.get("summary") or operation.get("operationId") or "-").replace("|", "\\|")
            if operation.get("deprecated"):
                summary = f"Deprecated · {summary}"
            lines.append(f"| `{method}` | `{path}` | {summary} | {_request(operation)} | {_response(operation)} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the in-app FastAPI endpoint index.")
    parser.add_argument("--check", action="store_true", help="Fail when the checked-in document is stale.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable result.")
    args = parser.parse_args()
    content = generate()
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    changed = current != content
    if not args.check and changed:
        OUTPUT.write_text(content, encoding="utf-8")
    result = {"path": str(OUTPUT.relative_to(ROOT)), "changed": changed, "ok": not (args.check and changed)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif args.check and changed:
        print(f"Stale generated API reference: {OUTPUT.relative_to(ROOT)}", file=sys.stderr)
    elif not args.check:
        print(f"{'Updated' if changed else 'Unchanged'} {OUTPUT.relative_to(ROOT)}")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
