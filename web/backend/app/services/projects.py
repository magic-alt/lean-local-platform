import json
import hashlib
import re
import shutil
import time
from pathlib import Path
from typing import Any

from ..core.config import PROJECTS_DIR
from ..core.errors import LeanWebError, NotFoundError
from ..core.files import ensure_child_path, slugify
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from .strategies import render_python_template

COPY_SUFFIX = re.compile(r"\s+\(copy\s+\d{8}-\d{6}\)$", re.IGNORECASE)


def _class_name(name: str) -> str:
    parts = [part for part in slugify(name).split("-") if part]
    return "".join(part.capitalize() for part in parts) + "Algorithm"


def _project_root(project: dict[str, Any]) -> Path:
    stored_path = Path(project.get("project_path") or "")
    if stored_path.exists():
        return stored_path
    return PROJECTS_DIR / str(project["id"])


def _normalize_project(project: dict[str, Any] | None) -> dict[str, Any] | None:
    if project is None:
        return None
    normalized = dict(project)
    normalized["project_path"] = str(_project_root(normalized))
    normalized["display_name"] = clean_project_name(str(normalized.get("name") or ""))
    return normalized


def clean_project_name(name: str) -> str:
    cleaned = str(name or "").strip()
    while COPY_SUFFIX.search(cleaned):
        cleaned = COPY_SUFFIX.sub("", cleaned).strip()
    return cleaned or "Project"


def _project_manifest(project: dict[str, Any]) -> str:
    root = _project_root(project)
    digest = hashlib.sha256()
    if not root.exists():
        return ""
    paths = (
        item
        for item in root.rglob("*")
        if item.is_file()
        and item.suffix != ".pyc"
        and not any(part.startswith(".") or part == "__pycache__" for part in item.relative_to(root).parts)
    )
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _config_hash(project: dict[str, Any]) -> str:
    payload = json.dumps(project.get("config") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _copy_project_directory(source_root: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=False)
    for child in sorted(source_root.rglob("*")):
        if any(part.startswith(".") for part in child.relative_to(source_root).parts):
            continue
        target = target_root / child.relative_to(source_root)
        if child.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if child.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)


def _render_template_change(
    project_root: Path,
    *,
    language: str,
    algorithm_class: str,
    main_file: str,
    previous_template: str | None,
    next_template: str | None,
) -> None:
    if language != "Python" or not next_template or next_template == previous_template:
        return
    (project_root / main_file).write_text(
        render_python_template(algorithm_class, next_template),
        encoding="utf-8",
    )


def get_project(project_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from projects where id = ?", (project_id,)).fetchone()
    project = _normalize_project(row_to_dict(row))
    if project is None:
        raise NotFoundError("Project not found.")
    return project


def list_projects() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from projects order by updated_at desc").fetchall()
        counts = connection.execute(
            """
            select project_id, count(*) as run_count, max(created_at) as latest_run_at
            from backtest_runs
            where project_id is not null
            group by project_id
            """
        ).fetchall()
        latest = connection.execute(
            """
            select project_id, status
            from backtest_runs
            where project_id is not null
            order by created_at desc
            """
        ).fetchall()
    count_by_id = {row["project_id"]: dict(row) for row in counts}
    latest_by_id: dict[str, str] = {}
    for row in latest:
        latest_by_id.setdefault(row["project_id"], row["status"])
    result = []
    for item in rows_to_dicts(rows):
        project = _normalize_project(item) or item
        stats = count_by_id.get(project["id"], {})
        project["run_count"] = int(stats.get("run_count") or 0)
        project["latest_run_at"] = stats.get("latest_run_at")
        project["latest_run_status"] = latest_by_id.get(project["id"])
        result.append(project)
    return result


def _merge_admissions(connection, source_id: str, target_id: str) -> None:
    rows = connection.execute(
        "select * from strategy_admissions where strategy_id = ?",
        (source_id,),
    ).fetchall()
    for row in rows:
        existing = connection.execute(
            """
            select id from strategy_admissions
            where strategy_id = ? and parameters_sha256 = ? and profile_name = ? and profile_version = ?
            """,
            (target_id, row["parameters_sha256"], row["profile_name"], row["profile_version"]),
        ).fetchone()
        if existing:
            connection.execute(
                "update strategy_admission_events set admission_id = ? where admission_id = ?",
                (existing["id"], row["id"]),
            )
            connection.execute("delete from strategy_admissions where id = ?", (row["id"],))
        else:
            connection.execute("update strategy_admissions set strategy_id = ? where id = ?", (target_id, row["id"]))


def _merge_project(source: dict[str, Any], target: dict[str, Any]) -> None:
    source_id = str(source["id"])
    target_id = str(target["id"])
    with db() as connection:
        for table in ("backtest_runs", "tasks", "optimization_runs", "research_sessions", "paper_sessions", "strategy_versions"):
            connection.execute(f"update {table} set project_id = ? where project_id = ?", (target_id, source_id))
        _merge_admissions(connection, source_id, target_id)
        connection.execute("delete from projects where id = ?", (source_id,))
    _remove_path(str(_project_root(source)))


def consolidate_automatic_copies() -> dict[str, Any]:
    projects = list_projects()
    groups: dict[str, list[dict[str, Any]]] = {}
    for project in projects:
        clean_name = clean_project_name(str(project.get("name") or ""))
        groups.setdefault(clean_name.casefold(), []).append(project)
    merged: list[dict[str, str]] = []
    renamed: list[dict[str, str]] = []
    for group in groups.values():
        if len(group) < 2 or not any(COPY_SUFFIX.search(str(item.get("name") or "")) for item in group):
            continue
        clean_name = clean_project_name(str(group[0].get("name") or ""))
        base = next((item for item in group if str(item.get("name")) == clean_name), None)
        if base is None:
            base = min(group, key=lambda item: str(item.get("created_at") or ""))
            update_project(base["id"], name=clean_name)
            base = get_project(base["id"])
        base_signature = (_config_hash(base), _project_manifest(base))
        variants = []
        for candidate in sorted(group, key=lambda item: str(item.get("created_at") or "")):
            if candidate["id"] == base["id"]:
                continue
            signature = (_config_hash(candidate), _project_manifest(candidate))
            if signature == base_signature:
                _merge_project(candidate, base)
                merged.append({"source": candidate["id"], "target": base["id"]})
            else:
                variants.append(candidate)
        for index, variant in enumerate(variants, start=1):
            next_name = f"{clean_name} · variant {index}"
            update_project(variant["id"], name=next_name)
            renamed.append({"project": variant["id"], "name": next_name})
    return {"merged": merged, "renamed": renamed}


def create_project(
    name: str,
    language: str = "Python",
    algorithm_class: str | None = None,
    template_key: str | None = None,
    market: str = "usa",
    asset_class: str = "equity",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    language = language or "Python"
    if language not in {"Python", "CSharp"}:
        raise LeanWebError("Only Python and CSharp projects are supported.")

    base_slug = slugify(name)
    project_id = f"{base_slug}-{time.strftime('%Y%m%d%H%M%S')}"
    project_path = PROJECTS_DIR / project_id
    project_path.mkdir(parents=True, exist_ok=False)

    if language == "Python":
        algorithm_class = algorithm_class or _class_name(name)
        main_file = "main.py"
        (project_path / main_file).write_text(render_python_template(algorithm_class, template_key), encoding="utf-8")
    else:
        algorithm_class = algorithm_class or _class_name(name)
        main_file = "Main.cs"
        (project_path / main_file).write_text(
            "using QuantConnect.Algorithm;\n\n"
            f"public class {algorithm_class} : QCAlgorithm\n"
            "{\n    public override void Initialize() { }\n}\n",
            encoding="utf-8",
        )

    config = {
        "language": language,
        "algorithmClass": algorithm_class,
        "mainFile": main_file,
        "templateKey": template_key or "ema_cross",
        "assetClass": asset_class,
        "market": market,
        "venue": venue or market,
        "resolution": resolution,
        "dataType": data_type,
        "parameters": parameters or {},
    }
    (project_path / "project.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into projects
                (id, name, language, algorithm_class, project_path, main_file, config_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, name, language, algorithm_class, str(project_path), main_file, json_dump(config), now, now),
        )
    return get_project(project_id)


def clone_project(
    source_project_id: str,
    name: str | None = None,
    config_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = get_project(source_project_id)
    source_root = _project_root(source)
    if not source_root.exists():
        raise LeanWebError("Source project path not found.")

    source_name = name or f"{source['name']} Clone"
    base_slug = slugify(source_name)
    clone_project_id = f"{base_slug}-{time.strftime('%Y%m%d%H%M%S')}"
    clone_project_path = PROJECTS_DIR / clone_project_id
    _copy_project_directory(source_root, clone_project_path)

    source_config = dict(source.get("config") or {})
    previous_template = source_config.get("templateKey")
    if config_updates:
        source_config.update({key: value for key, value in config_updates.items() if value is not None})

    main_file = source.get("main_file") or "main.py"
    source_main_file = source_root / main_file
    if not source_main_file.exists():
        files = sorted([path.name for path in clone_project_path.glob("*") if path.is_file()])
        if files:
            main_file = files[0]

    _render_template_change(
        clone_project_path,
        language=source["language"],
        algorithm_class=source["algorithm_class"],
        main_file=main_file,
        previous_template=previous_template,
        next_template=source_config.get("templateKey"),
    )

    (clone_project_path / "project.json").write_text(json.dumps(source_config, indent=2), encoding="utf-8")

    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into projects
                (id, name, language, algorithm_class, project_path, main_file, config_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clone_project_id,
                source_name,
                source["language"],
                source["algorithm_class"],
                str(clone_project_path),
                main_file,
                json_dump(source_config),
                now,
                now,
            ),
        )
    return get_project(clone_project_id)


def _remove_path(path: str | None) -> None:
    if not path:
        return
    target = Path(path)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    elif target.exists():
        target.unlink()


def delete_project(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    deleted = {"runs": 0, "tasks": 0, "reports": 0, "project": project_id}
    with db() as connection:
        active_runs = connection.execute(
            "select count(*) as count from backtest_runs where project_id = ? and status in ('created','queued','checking','running')",
            (project_id,),
        ).fetchone()
        active_tasks = connection.execute(
            "select count(*) as count from tasks where project_id = ? and status in ('created','queued','running')",
            (project_id,),
        ).fetchone()
        if int(active_runs["count"] or 0) or int(active_tasks["count"] or 0):
            raise ValueError("Cancel active project runs and tasks before deleting the project.")
        runs = connection.execute("select * from backtest_runs where project_id = ?", (project_id,)).fetchall()
        run_ids = [row["id"] for row in runs]
        for row in runs:
            _remove_path(Path(row["results_dir"]).parent.as_posix() if row["results_dir"] else None)
            deleted["runs"] += 1
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            reports = connection.execute(f"select * from reports where run_id in ({placeholders})", run_ids).fetchall()
            for row in reports:
                _remove_path(row["report_path"])
                deleted["reports"] += 1
            connection.execute(f"delete from reports where run_id in ({placeholders})", run_ids)
            connection.execute(f"delete from experiments where run_id in ({placeholders})", run_ids)
            connection.execute(f"delete from backtest_results where job_id in ({placeholders})", run_ids)
            connection.execute(f"delete from backtest_runs where id in ({placeholders})", run_ids)

        tasks = connection.execute("select * from tasks where project_id = ?", (project_id,)).fetchall()
        for row in tasks:
            _remove_path(row["log_path"])
            deleted["tasks"] += 1
        connection.execute("delete from tasks where project_id = ?", (project_id,))
        connection.execute("delete from optimization_runs where project_id = ?", (project_id,))
        connection.execute("delete from research_sessions where project_id = ?", (project_id,))
        connection.execute("delete from projects where id = ?", (project_id,))
    _remove_path(str(_project_root(project)))
    return deleted


def file_tree(project_id: str) -> list[dict[str, Any]]:
    project = get_project(project_id)
    root = _project_root(project)
    items = []
    for path in sorted(root.rglob("*")):
        if path.name.startswith("."):
            continue
        relative = path.relative_to(root).as_posix()
        items.append({"path": relative, "name": path.name, "type": "directory" if path.is_dir() else "file"})
    return items


def read_file(project_id: str, relative_path: str) -> dict[str, Any]:
    project = get_project(project_id)
    target = ensure_child_path(_project_root(project), relative_path)
    if not target.exists() or not target.is_file():
        raise NotFoundError("Project file not found.")
    return {"path": relative_path, "content": target.read_text(encoding="utf-8")}


def write_file(project_id: str, relative_path: str, content: str) -> dict[str, Any]:
    project = get_project(project_id)
    target = ensure_child_path(_project_root(project), relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    now = utc_now()
    with db() as connection:
        connection.execute("update projects set updated_at = ? where id = ?", (now, project_id))
    return {"path": relative_path, "size": target.stat().st_size, "updated_at": now}


def update_project(project_id: str, name: str | None = None, config_updates: dict[str, Any] | None = None) -> dict[str, Any]:
    project = get_project(project_id)
    config = dict(project.get("config") or {})
    previous_template = config.get("templateKey")
    if config_updates:
        config.update({key: value for key, value in config_updates.items() if value is not None})
    next_name = name or project["name"]
    now = utc_now()
    project_path = _project_root(project)
    _render_template_change(
        project_path,
        language=project["language"],
        algorithm_class=project["algorithm_class"],
        main_file=project["main_file"],
        previous_template=previous_template,
        next_template=config.get("templateKey"),
    )
    (project_path / "project.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    with db() as connection:
        connection.execute(
            "update projects set name = ?, config_json = ?, updated_at = ? where id = ?",
            (next_name, json_dump(config), now, project_id),
        )
    return get_project(project_id)
