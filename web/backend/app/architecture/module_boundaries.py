from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path


DOMAIN_FORBIDDEN_EXTERNAL_IMPORT_PREFIXES: tuple[str, ...] = (
    "adata",
    "akshare",
    "baostock",
    "celery",
    "docker",
    "duckdb",
    "fastapi",
    "jqdatasdk",
    "kombu",
    "longbridge",
    "psycopg",
    "pymysql",
    "sqlalchemy",
    "starlette",
    "tqsdk",
    "tushare",
    "xtquant",
)

# The domain package may depend on stable core contracts and other domain
# modules, but it must not reach upward into use cases or outward into runtime
# adapters. Relative imports such as ``from ..services import ...`` are checked
# independently from third-party imports above.
DOMAIN_FORBIDDEN_INTERNAL_ROOTS: frozenset[str] = frozenset(
    {
        "api",
        "lean_engine",
        "repositories",
        "runners",
        "services",
        "tasks",
    }
)

ENTRYPOINT_DIRS: tuple[str, ...] = ("api", "tasks")

HOTSPOT_MODULES: tuple[str, ...] = (
    "app/services/data_sync.py",
    "app/services/experiment_batches.py",
    "app/db.py",
    "app/runner_service.py",
)


def _matches_prefix(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def _imports(path: Path) -> list[tuple[int, str, int]]:
    """Return ``(line, module, relative_level)`` imports for one Python file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.lineno, node.module or "", int(node.level or 0)))
    return imports


def domain_import_violations(app_root: Path) -> list[str]:
    violations: list[str] = []
    domain_root = app_root / "domain"
    if not domain_root.is_dir():
        return ["app/domain: domain package is missing"]

    for path in sorted(domain_root.rglob("*.py")):
        relative = path.relative_to(app_root.parent).as_posix()
        try:
            imports = _imports(path)
        except SyntaxError as exc:
            violations.append(f"{relative}:{exc.lineno or 0}: syntax error blocks boundary analysis")
            continue
        for line, module, level in imports:
            if level:
                root = module.split(".", 1)[0] if module else ""
                if root in DOMAIN_FORBIDDEN_INTERNAL_ROOTS:
                    violations.append(
                        f"{relative}:{line}: domain import crosses inward boundary: "
                        f"{'.' * level}{module}"
                    )
                continue
            if any(
                _matches_prefix(module, prefix)
                for prefix in DOMAIN_FORBIDDEN_EXTERNAL_IMPORT_PREFIXES
            ):
                violations.append(
                    f"{relative}:{line}: domain import crosses adapter/framework boundary: {module}"
                )
            if any(
                _matches_prefix(module, f"app.{root}")
                for root in DOMAIN_FORBIDDEN_INTERNAL_ROOTS
            ):
                violations.append(
                    f"{relative}:{line}: domain import crosses inward boundary: {module}"
                )
    return sorted(set(violations))


def _write_pattern(table: str) -> re.Pattern[str]:
    escaped = re.escape(table)
    return re.compile(
        rf"\b(?:insert\s+into|update|delete\s+from)\s+[`\"]?{escaped}[`\"]?\b",
        re.IGNORECASE,
    )


def sql_writers(app_root: Path, table: str) -> set[str]:
    pattern = _write_pattern(table)
    writers: set[str] = set()
    for path in sorted(app_root.rglob("*.py")):
        if pattern.search(path.read_text(encoding="utf-8")):
            writers.add(path.relative_to(app_root.parent).as_posix())
    return writers


def ownership_violations(
    app_root: Path,
    owners: Mapping[str, str],
) -> list[str]:
    violations: list[str] = []
    backend_root = app_root.parent
    for table, owner in sorted(owners.items()):
        owner_path = backend_root / owner
        if not owner_path.is_file():
            violations.append(f"{table}: declared owner does not exist: {owner}")
        actual = sorted(sql_writers(app_root, table))
        if actual != [owner]:
            violations.append(
                f"{table}: canonical writer mismatch; expected={owner}; actual={actual}"
            )
    return violations


def entrypoint_sql_write_violations(
    app_root: Path,
    tables: set[str] | frozenset[str],
) -> list[str]:
    violations: list[str] = []
    for directory in ENTRYPOINT_DIRS:
        root = app_root / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            relative = path.relative_to(app_root.parent).as_posix()
            for table in sorted(tables):
                if _write_pattern(table).search(text):
                    violations.append(
                        f"{relative}: entrypoint performs direct SQL write to {table}"
                    )
    return sorted(set(violations))


def architecture_violations(app_root: Path) -> list[str]:
    from .state_ownership import CANONICAL_TABLE_WRITERS, ORCHESTRATION_STATE_BOUNDARIES

    protected_tables = set(CANONICAL_TABLE_WRITERS) | set(ORCHESTRATION_STATE_BOUNDARIES)
    violations = domain_import_violations(app_root)
    violations.extend(ownership_violations(app_root, CANONICAL_TABLE_WRITERS))
    violations.extend(entrypoint_sql_write_violations(app_root, protected_tables))
    return sorted(set(violations))
