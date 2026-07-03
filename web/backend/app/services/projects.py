import json
import time
from pathlib import Path
from typing import Any

from ..core.config import PROJECTS_DIR
from ..core.errors import LeanWebError, NotFoundError
from ..core.files import ensure_child_path, slugify
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


PYTHON_TEMPLATE = '''from AlgorithmImports import *
from datetime import datetime


class {class_name}(QCAlgorithm):
    def initialize(self):
        ticker = self.get_parameter("ticker", "SPY").upper()
        start = datetime.strptime(self.get_parameter("start", "2013-01-01"), "%Y-%m-%d")
        end = datetime.strptime(self.get_parameter("end", "2013-06-30"), "%Y-%m-%d")
        cash = float(self.get_parameter("cash", 100000))
        fast_period = int(self.get_parameter("fast", 10))
        slow_period = int(self.get_parameter("slow", 30))

        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_cash(cash)

        equity = self.add_equity(ticker, Resolution.DAILY, data_normalization_mode=DataNormalizationMode.RAW)
        self.symbol = equity.symbol
        self.fast = self.ema(self.symbol, fast_period, Resolution.DAILY)
        self.slow = self.ema(self.symbol, slow_period, Resolution.DAILY)
        self.set_warm_up(max(fast_period, slow_period), Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up or not self.fast.is_ready or not self.slow.is_ready:
            return

        invested = self.portfolio[self.symbol].invested
        if self.fast.current.value > self.slow.current.value and not invested:
            self.set_holdings(self.symbol, 1)
        elif self.fast.current.value < self.slow.current.value and invested:
            self.liquidate(self.symbol)

        self.plot("EMA", "Fast", self.fast.current.value)
        self.plot("EMA", "Slow", self.slow.current.value)
'''


def _class_name(name: str) -> str:
    parts = [part for part in slugify(name).split("-") if part]
    return "".join(part.capitalize() for part in parts) + "Algorithm"


def get_project(project_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from projects where id = ?", (project_id,)).fetchone()
    project = row_to_dict(row)
    if project is None:
        raise NotFoundError("Project not found.")
    return project


def list_projects() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from projects order by updated_at desc").fetchall()
    return rows_to_dicts(rows)


def create_project(name: str, language: str = "Python", algorithm_class: str | None = None) -> dict[str, Any]:
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
        (project_path / main_file).write_text(PYTHON_TEMPLATE.format(class_name=algorithm_class), encoding="utf-8")
    else:
        algorithm_class = algorithm_class or _class_name(name)
        main_file = "Main.cs"
        (project_path / main_file).write_text(
            "using QuantConnect.Algorithm;\n\n"
            f"public class {algorithm_class} : QCAlgorithm\n"
            "{\n    public override void Initialize() { }\n}\n",
            encoding="utf-8",
        )

    config = {"language": language, "algorithmClass": algorithm_class, "mainFile": main_file}
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


def delete_project(project_id: str) -> None:
    project = get_project(project_id)
    path = Path(project["project_path"])
    if path.exists():
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    with db() as connection:
        connection.execute("delete from projects where id = ?", (project_id,))


def file_tree(project_id: str) -> list[dict[str, Any]]:
    project = get_project(project_id)
    root = Path(project["project_path"])
    items = []
    for path in sorted(root.rglob("*")):
        if path.name.startswith("."):
            continue
        relative = path.relative_to(root).as_posix()
        items.append({"path": relative, "name": path.name, "type": "directory" if path.is_dir() else "file"})
    return items


def read_file(project_id: str, relative_path: str) -> dict[str, Any]:
    project = get_project(project_id)
    target = ensure_child_path(Path(project["project_path"]), relative_path)
    if not target.exists() or not target.is_file():
        raise NotFoundError("Project file not found.")
    return {"path": relative_path, "content": target.read_text(encoding="utf-8")}


def write_file(project_id: str, relative_path: str, content: str) -> dict[str, Any]:
    project = get_project(project_id)
    target = ensure_child_path(Path(project["project_path"]), relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    now = utc_now()
    with db() as connection:
        connection.execute("update projects set updated_at = ? where id = ?", (now, project_id))
    return {"path": relative_path, "size": target.stat().st_size, "updated_at": now}
