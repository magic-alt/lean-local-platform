from __future__ import annotations

import json
import re
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "config" / "contracts" / "research-api-surface.json"
FRONTEND_SRC = ROOT / "web" / "frontend" / "src"
API_LITERAL = re.compile(r"(?P<quote>[\"'`])(?P<path>/api/research[^\"'`]*)(?P=quote)")
TS_INTERPOLATION = re.compile(r"\$\{[^}]+\}")
PATH_PARAMETER = re.compile(r"\{[^}]+\}")


def _contract() -> set[tuple[str, str]]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return {(str(item["method"]).upper(), str(item["path"])) for item in payload["routes"]}


def _normalize(path: str) -> str:
    path = path.split("?", 1)[0]
    path = TS_INTERPOLATION.sub("{}", path)
    path = PATH_PARAMETER.sub("{}", path)
    return path.rstrip("/") or "/"


def _frontend_research_paths() -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        for match in API_LITERAL.finditer(path.read_text(encoding="utf-8")):
            result.setdefault(_normalize(match.group("path")), set()).add(str(path.relative_to(ROOT)))
    return result


def test_research_openapi_surface_matches_frozen_contract():
    schema = app.openapi()
    actual: set[tuple[str, str]] = set()
    for path, operations in schema["paths"].items():
        if not path.startswith("/api/research"):
            continue
        for method in operations:
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                actual.add((method.upper(), path))

    assert actual == _contract()


def test_frontend_research_routes_are_part_of_openapi_surface():
    allowed = {_normalize(path) for _, path in _contract()}
    frontend = _frontend_research_paths()
    stale = {shape: files for shape, files in frontend.items() if shape not in allowed}

    assert stale == {}
