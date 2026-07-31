from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..core.config import PLATFORM_DIR
from ..core.errors import NotFoundError
from .projects import create_project, update_project, write_file
from .settings import get_settings


CATALOG_PATH = PLATFORM_DIR / "examples" / "catalog.json"
KINDS = {"backtest", "optimization", "research"}


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, Any], ...]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Example catalog must be a JSON array.")
    seen: set[tuple[str, str]] = set()
    items: list[dict[str, Any]] = []
    for raw in payload:
        item = dict(raw)
        kind = str(item.get("kind") or "").strip().lower()
        key = str(item.get("key") or "").strip()
        identity = (kind, key)
        if kind not in KINDS or not key or identity in seen:
            raise ValueError(f"Invalid or duplicate example catalog entry: {identity}")
        seen.add(identity)
        item.setdefault("version", 1)
        item.setdefault("tags", [])
        item.setdefault("defaults", {})
        items.append(item)
    return tuple(items)


def list_examples(kind: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
    normalized_kind = str(kind or "").strip().lower()
    needle = str(query or "").strip().casefold()
    result = []
    for item in _catalog():
        if normalized_kind and item["kind"] != normalized_kind:
            continue
        haystack = " ".join(
            [str(item.get("name") or ""), str(item.get("description") or ""), *map(str, item.get("tags") or [])]
        ).casefold()
        if needle and needle not in haystack:
            continue
        result.append(dict(item))
    return result


def get_example(kind: str, key: str) -> dict[str, Any]:
    normalized = str(kind).strip().lower()
    item = next((candidate for candidate in _catalog() if candidate["kind"] == normalized and candidate["key"] == key), None)
    if item is None:
        raise NotFoundError("Example not found.")
    return dict(item)


def _research_notebook(example: dict[str, Any]) -> str:
    title = str(example["name"])
    description = str(example.get("description") or "")
    defaults = repr(example.get("defaults") or {})
    if example.get("key") == "ashare-swing-candidates":
        cells = [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# 全A有序回调候选研究\n",
                    "\n该案例读取研究运行生成的只读快照，复核 A/B/C/Reject 漏斗。筛选结果是研究候选，不是买入建议。\n",
                    "\n先在研究工作台运行 `全A有序回调候选`，点击运行历史中的“快照”，再用该快照启动本项目的 Notebook Workspace。\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from pathlib import Path\n",
                    "import json\n",
                    "import pandas as pd\n",
                    "\n",
                    "snapshot_id_file = Path('/Lean/Project/.lean-research-snapshot-id')\n",
                    "if not snapshot_id_file.is_file():\n",
                    "    raise RuntimeError('工作区没有绑定研究快照')\n",
                    "snapshot_id = snapshot_id_file.read_text(encoding='utf-8').strip()\n",
                    "snapshot_root = Path('/Lean/Snapshots') / snapshot_id\n",
                    "manifest = json.loads((snapshot_root / 'manifest.json').read_text(encoding='utf-8'))\n",
                    "manifest\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "audit = pd.read_parquet(snapshot_root / 'screen-audit.parquet')\n",
                    "audit.groupby('bucket').size().reindex(['A', 'B', 'C', 'Reject'], fill_value=0)\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "columns = ['bucket', 'ts_code', 'name', 'spot_close', 'score', 'entry_ready', 'triggered', 'first_rejection']\n",
                    "audit.loc[audit['bucket'] != 'Reject', columns].sort_values(['bucket', 'score'], ascending=[True, False]).head(30)\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "case_symbols = ['600036','601166','000651','600690','600030','601088','300059','601766','601985','601899','600938','601600','603993','600111']\n",
                    "audit.loc[audit['ts_code'].astype(str).str.zfill(6).isin(case_symbols), columns + ['worst_5d', 'current_drawdown_60', 'atr20_pct']]\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## 可继续研究\n",
                    "\n可以在不改写冻结数据的前提下调整分数、比较拒绝原因分布，或把 A/B 候选送入基本面尽调和含费用回测。若要修改均线周期或回调定义，应重新运行研究模板，不要从快照推断未保存的价格路径。\n",
                ],
            },
        ]
    else:
        cells = [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    f"# {title}\n",
                    f"\n{description}\n",
                    "\n此 Notebook 由 LEAN Local 案例目录生成，可直接修改并保存到当前 Research 工作区。\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from pathlib import Path\n",
                    "import json\n",
                    "import pandas as pd\n",
                    "\n",
                    f"defaults = {defaults}\n",
                    "defaults\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# LEAN数据只读挂载在 /Lean/Data，Parquet研究数据只读挂载在 /Lean/Parquet。\n",
                    "data_root = Path('/Lean/Data')\n",
                    "parquet_root = Path('/Lean/Parquet')\n",
                    "print('LEAN data:', data_root.exists(), 'Parquet:', parquet_root.exists())\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## 下一步\n",
                    "在网页案例的快捷表单中可生成同口径摘要；Notebook适合继续做自定义图表和假设检验。\n",
                ],
            },
        ]
    return json.dumps(
        {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}}, "nbformat": 4, "nbformat_minor": 5},
        ensure_ascii=False,
        indent=2,
    )


def instantiate_example(kind: str, key: str, *, name: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    example = get_example(kind, key)
    defaults = {**(example.get("defaults") or {}), **(overrides or {})}
    settings = get_settings()
    market = str(defaults.get("market") or settings["defaultMarket"])
    project = create_project(
        name or str(example["name"]),
        "Python",
        template_key=str(example.get("templateKey") or "blank"),
        asset_class=str(defaults.get("assetClass") or settings["defaultAssetClass"]),
        market=market,
        venue=str(defaults.get("venue") or market),
        resolution=str(defaults.get("resolution") or settings["defaultResolution"]),
        data_type=str(defaults.get("dataType") or settings["defaultDataType"]),
        parameters=dict(defaults.get("parameters") or {}),
    )
    project = update_project(
        project["id"],
        config_updates={
            "exampleKey": example["key"],
            "exampleKind": example["kind"],
            "exampleVersion": example["version"],
            "exampleDefaults": defaults,
        },
    )
    if example["kind"] == "research":
        write_file(project["id"], f"notebooks/{example['key']}.ipynb", _research_notebook(example))
        write_file(
            project["id"],
            "RESEARCH.md",
            f"# {example['name']}\n\n{example.get('description') or ''}\n\n打开 `notebooks/{example['key']}.ipynb` 开始分析。\n",
        )
    route = "/backtests" if example["kind"] == "backtest" else "/optimization" if example["kind"] == "optimization" else "/research"
    return {"example": example, "project": project, "launch": {"route": route, "defaults": defaults}}
