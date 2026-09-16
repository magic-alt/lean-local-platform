#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
APP_ROOT = BACKEND / "app"
sys.path.insert(0, str(BACKEND))

from app.architecture.module_boundaries import (  # noqa: E402
    HOTSPOT_MODULES,
    architecture_violations,
)


BRANCH_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.Match,
    ast.BoolOp,
    ast.IfExp,
    ast.comprehension,
    ast.ExceptHandler,
)


def _python_files() -> list[Path]:
    return sorted(APP_ROOT.rglob("*.py"))


def _module_name(path: Path) -> str:
    relative = path.relative_to(BACKEND).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _known_target(candidate: str, known: set[str]) -> str | None:
    current = candidate.strip(".")
    while current:
        if current in known:
            return current
        if "." not in current:
            break
        current = current.rsplit(".", 1)[0]
    return None


def _relative_base(module: str, path: Path, level: int) -> list[str]:
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    parts = package.split(".") if package else []
    up = max(0, level - 1)
    return parts[: max(0, len(parts) - up)]


def _import_targets(
    path: Path,
    module: str,
    tree: ast.AST,
    known: set[str],
) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        candidates: list[str] = []
        if isinstance(node, ast.Import):
            candidates.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _relative_base(module, path, int(node.level))
                module_parts = (node.module or "").split(".") if node.module else []
                prefix = ".".join(base + module_parts)
            else:
                prefix = node.module or ""
            if node.module:
                candidates.append(prefix)
                candidates.extend(f"{prefix}.{alias.name}" for alias in node.names)
            else:
                candidates.extend(".".join([*base, alias.name]) for alias in node.names)
        for candidate in candidates:
            resolved = _known_target(candidate, known)
            if resolved and resolved != module:
                targets.add(resolved)
    return targets


def _branch_points(node: ast.AST) -> int:
    return sum(1 for child in ast.walk(node) if isinstance(child, BRANCH_NODES))


def _module_metrics(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=str(path))
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    function_rows = [
        {
            "name": node.name,
            "line": node.lineno,
            "lines": max(1, int(getattr(node, "end_lineno", node.lineno)) - node.lineno + 1),
            "branchPoints": _branch_points(node),
        }
        for node in functions
    ]
    function_rows.sort(key=lambda item: (-item["lines"], -item["branchPoints"], item["line"], item["name"]))
    return {
        "bytes": len(raw),
        "lines": len(text.splitlines()),
        "functionCount": len(functions),
        "classCount": len(classes),
        "branchPoints": _branch_points(tree),
        "maxFunctionLines": max((item["lines"] for item in function_rows), default=0),
        "maxFunctionBranchPoints": max((item["branchPoints"] for item in function_rows), default=0),
        "largestFunctions": function_rows[:5],
    }


def _strongly_connected_components(
    modules: set[str], edges: set[tuple[str, str]]
) -> list[list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in sorted(edges):
        adjacency[source].append(target)

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in adjacency.get(node, []):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == node:
                break
        if len(component) > 1:
            components.append(sorted(component))

    for module in sorted(modules):
        if module not in indices:
            visit(module)
    return sorted(components, key=lambda item: (len(item), item))


def build_report() -> dict[str, Any]:
    paths = _python_files()
    module_by_path = {path: _module_name(path) for path in paths}
    known = set(module_by_path.values())
    metrics: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str]] = set()

    for path in paths:
        relative = path.relative_to(BACKEND).as_posix()
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        metrics[relative] = _module_metrics(path)
        source = module_by_path[path]
        edges.update((source, target) for target in _import_targets(path, source, tree, known))

    hotspots = {
        relative: metrics.get(relative, {"missing": True})
        for relative in HOTSPOT_MODULES
    }
    total_bytes = sum(int(item["bytes"]) for item in metrics.values())
    total_lines = sum(int(item["lines"]) for item in metrics.values())
    top_by_bytes = sorted(
        (
            {"path": path, "bytes": int(item["bytes"]), "lines": int(item["lines"])}
            for path, item in metrics.items()
        ),
        key=lambda item: (-item["bytes"], item["path"]),
    )[:20]
    cycles = _strongly_connected_components(known, edges)
    return {
        "schemaVersion": "1.0",
        "scope": "web/backend/app",
        "totals": {
            "moduleCount": len(paths),
            "pythonBytes": total_bytes,
            "pythonLines": total_lines,
        },
        "hotspots": hotspots,
        "topModulesByBytes": top_by_bytes,
        "dependencyGraph": {
            "edgeCount": len(edges),
            "cycleCount": len(cycles),
            "cycles": cycles,
            "edges": [list(edge) for edge in sorted(edges)],
        },
        "boundaryViolations": architecture_violations(APP_ROOT),
        "complexityDefinition": {
            "branchPoints": "AST If/loop/Try/Match/BoolOp/IfExp/comprehension/ExceptHandler count",
            "maxFunctionLines": "largest FunctionDef/AsyncFunctionDef source span",
        },
    }


def _baseline_errors(report: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(baseline.get("schemaVersion") or "") != "1.0":
        errors.append("architecture baseline schemaVersion must be 1.0")
    expected_hotspots = baseline.get("hotspots") or {}
    actual_hotspots = report["hotspots"]
    for path in HOTSPOT_MODULES:
        expected = expected_hotspots.get(path) if isinstance(expected_hotspots, dict) else None
        actual = actual_hotspots.get(path) or {}
        if not isinstance(expected, dict) or not isinstance(expected.get("bytes"), int):
            errors.append(f"baseline hotspot is missing byte anchor: {path}")
            continue
        if actual.get("bytes") != expected["bytes"]:
            errors.append(
                f"hotspot byte anchor changed: {path}: "
                f"expected={expected['bytes']}, actual={actual.get('bytes')}"
            )
    errors.extend(report.get("boundaryViolations") or [])
    return sorted(set(errors))


def _mermaid(report: dict[str, Any]) -> str:
    edges = report["dependencyGraph"]["edges"]
    modules = sorted({item for edge in edges for item in edge})
    identifiers = {
        module: "m_" + re.sub(r"[^A-Za-z0-9_]", "_", module)
        for module in modules
    }
    lines = ["flowchart LR"]
    for module in modules:
        lines.append(f'  {identifiers[module]}["{module}"]')
    for source, target in edges:
        lines.append(f"  {identifiers[source]} --> {identifiers[target]}")
    return "\n".join(lines) + "\n"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic modular-monolith dependency and complexity evidence."
    )
    parser.add_argument("--baseline", type=Path, help="Tracked hotspot anchor JSON.")
    parser.add_argument("--check", action="store_true", help="Fail on boundary or hotspot-anchor drift.")
    parser.add_argument("--output", type=Path, help="Write full JSON evidence to this path.")
    parser.add_argument("--mermaid-output", type=Path, help="Write the full internal import graph as Mermaid.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args(argv)

    report = build_report()
    errors = list(report["boundaryViolations"])
    if args.baseline:
        baseline_path = args.baseline if args.baseline.is_absolute() else ROOT / args.baseline
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        errors = _baseline_errors(report, baseline)
    report["checkErrors"] = errors
    report["ok"] = not errors

    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        _write(output, rendered)
    if args.mermaid_output:
        graph_path = args.mermaid_output if args.mermaid_output.is_absolute() else ROOT / args.mermaid_output
        _write(graph_path, _mermaid(report))
    if args.json:
        print(rendered, end="")
    elif args.check and errors:
        print("Architecture baseline validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    elif args.check:
        print(
            "Architecture baseline passed: "
            f"{report['totals']['moduleCount']} modules, "
            f"{report['dependencyGraph']['edgeCount']} internal dependency edges."
        )
    else:
        print(rendered, end="")
    return 1 if args.check and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
