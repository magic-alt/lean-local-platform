import json
import shutil
import time
from pathlib import Path
from typing import Any

from ..core.config import PROJECTS_DIR
from ..core.errors import LeanWebError, NotFoundError
from ..core.files import ensure_child_path, slugify
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from .strategies import render_python_template


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
    return normalized


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
    return [_normalize_project(project) or project for project in rows_to_dicts(rows)]


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
    if config_updates:
        source_config.update({key: value for key, value in config_updates.items() if value is not None})

    main_file = source.get("main_file") or "main.py"
    source_main_file = source_root / main_file
    if not source_main_file.exists():
        files = sorted([path.name for path in clone_project_path.glob("*") if path.is_file()])
        if files:
            main_file = files[0]

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
    if config_updates:
        config.update({key: value for key, value in config_updates.items() if value is not None})
    next_name = name or project["name"]
    now = utc_now()
    project_path = _project_root(project)
    (project_path / "project.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    with db() as connection:
        connection.execute(
            "update projects set name = ?, config_json = ?, updated_at = ? where id = ?",
            (next_name, json_dump(config), now, project_id),
        )
    return get_project(project_id)
