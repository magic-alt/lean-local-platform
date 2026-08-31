from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "contracts" / "research-api-surface.json"
RESEARCH_API_PATH = ROOT / "web" / "backend" / "app" / "api" / "research.py"
FRONTEND_SRC = ROOT / "web" / "frontend" / "src"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
API_LITERAL = re.compile(r"(?P<quote>[\"'`])(?P<path>/api/research[^\"'`]*)(?P=quote)")
TS_INTERPOLATION = re.compile(r"\$\{[^}]+\}")
PATH_PARAMETER = re.compile(r"\{[^}]+\}")
RETIRED_CLIENT_MEMBERS = {
    "researchTemplates",
    "researchRuns",
    "researchRun",
    "previewResearchRun",
    "createResearchRun",
    "deleteResearchRun",
    "retryResearchRun",
    "cancelResearchRun",
    "researchRunExportUrl",
    "researchArtifactUrl",
    "researchBacktestDraft",
    "researchSessions",
    "createResearchSnapshot",
    "startResearch",
    "stopResearch",
    "restartResearch",
    "researchLogs",
    "runResearchChecks",
    "deleteResearch",
}
RETIRED_CLIENT_MEMBER = re.compile(
    rf"\bapi\s*\.\s*(?P<member>{'|'.join(sorted(RETIRED_CLIENT_MEMBERS))})\b"
)


def load_contract() -> set[tuple[str, str]]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise SystemExit("Unsupported research API surface schemaVersion")
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise SystemExit("Research API surface contract must declare at least one route")
    result: set[tuple[str, str]] = set()
    for item in routes:
        if not isinstance(item, dict):
            raise SystemExit("Research API route entries must be objects")
        method = str(item.get("method") or "").upper()
        path = str(item.get("path") or "")
        if method not in {value.upper() for value in HTTP_METHODS} or not path.startswith("/api/research"):
            raise SystemExit(f"Invalid Research API route contract entry: {item!r}")
        result.add((method, path))
    return result


def _router_prefix(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "router" for target in targets):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        if not (isinstance(value.func, ast.Name) and value.func.id == "APIRouter"):
            continue
        for keyword in value.keywords:
            if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                return keyword.value.value
    return ""


def backend_public_routes() -> set[tuple[str, str]]:
    tree = ast.parse(RESEARCH_API_PATH.read_text(encoding="utf-8"), filename=str(RESEARCH_API_PATH))
    prefix = _router_prefix(tree)
    result: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not (isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "router"):
                continue
            method = decorator.func.attr.lower()
            if method not in HTTP_METHODS or not decorator.args:
                continue
            raw_path = decorator.args[0]
            if not isinstance(raw_path, ast.Constant) or not isinstance(raw_path.value, str):
                continue
            include_in_schema = True
            for keyword in decorator.keywords:
                if keyword.arg == "include_in_schema" and isinstance(keyword.value, ast.Constant):
                    include_in_schema = bool(keyword.value.value)
            if not include_in_schema:
                continue
            result.add((method.upper(), f"{prefix}{raw_path.value}"))
    return result


def normalize_path(path: str) -> str:
    path = path.split("?", 1)[0]
    path = TS_INTERPOLATION.sub("{}", path)
    path = PATH_PARAMETER.sub("{}", path)
    return path.rstrip("/") or "/"


def frontend_research_paths() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in API_LITERAL.finditer(text):
            value = match.group("path")
            found.setdefault(normalize_path(value), []).append(str(path.relative_to(ROOT)))
    return found


def frontend_retired_client_members() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in RETIRED_CLIENT_MEMBER.finditer(text):
            found.setdefault(match.group("member"), []).append(str(path.relative_to(ROOT)))
    return found


def main() -> int:
    contract = load_contract()
    backend = backend_public_routes()
    errors: list[str] = []
    if backend != contract:
        missing = sorted(contract - backend)
        extra = sorted(backend - contract)
        if missing:
            errors.append(f"Research API source is missing contracted routes: {missing}")
        if extra:
            errors.append(f"Research API source exposes uncontracted routes: {extra}")

    allowed_shapes = {normalize_path(path) for _, path in contract}
    frontend = frontend_research_paths()
    stale = {shape: files for shape, files in frontend.items() if shape not in allowed_shapes}
    if stale:
        details = "; ".join(f"{shape} -> {sorted(set(files))}" for shape, files in sorted(stale.items()))
        errors.append(f"Frontend references Research routes outside the public OpenAPI surface: {details}")

    retired_members = frontend_retired_client_members()
    if retired_members:
        details = "; ".join(
            f"api.{member} -> {sorted(set(files))}"
            for member, files in sorted(retired_members.items())
        )
        errors.append(f"Frontend references retired Research API client members: {details}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        "Frontend Research API contract OK: "
        f"{len(contract)} public backend routes; {len(frontend)} frontend Research route shape(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
