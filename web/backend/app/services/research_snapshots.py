from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..core.config import RESEARCH_DIR
from ..db import json_dump, utc_now
from ..domain.data_scope import DataScope
from . import data_gateway


SDK_SOURCE = '''"""Read-only access to a frozen LEAN Research snapshot."""
import json
from pathlib import Path


class ResearchData:
    def __init__(self, root):
        self.root = Path(root)
        self.manifest = json.loads((self.root / "manifest.json").read_text())

    @classmethod
    def open(cls, snapshot_id):
        return cls(Path("/Lean/Snapshots") / snapshot_id)

    def history(self):
        import duckdb
        return duckdb.sql(f"select * from read_parquet('{self.root / 'bars.parquet'}')")

    def dataset(self, name="bars"):
        if name != "bars":
            raise KeyError(name)
        return self.history()

    def universe(self):
        return sorted({row[0] for row in self.history().project("symbol").fetchall()})
'''


def create_snapshot(scope: DataScope | dict[str, Any]) -> dict[str, Any]:
    payload = data_gateway.query(scope, limit=1000)
    manifest_seed = {
        "schemaVersion": "1.0",
        "scope": payload["scope"],
        "scopeHash": payload["scopeHash"],
        "dataFingerprint": payload["dataFingerprint"],
        "source": payload["source"],
        "count": payload["count"],
    }
    snapshot_id = hashlib.sha256(
        json.dumps(manifest_seed, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    root = RESEARCH_DIR / "snapshots" / snapshot_id
    root.mkdir(parents=True, exist_ok=True)
    parquet_path = root / "bars.parquet"
    if not parquet_path.exists():
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("duckdb is required to create Research snapshots") from exc
        rows = payload["items"]
        connection = duckdb.connect()
        connection.execute(
            """
            create table bars (
                symbol varchar, trade_date varchar, open double, high double, low double,
                close double, settle double, volume double, amount double,
                turnover_rate double, open_interest double, pct_change double, source varchar
            )
            """
        )
        connection.executemany(
            "insert into bars values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [
                    row.get("symbol"), row.get("trade_date"), row.get("open"), row.get("high"),
                    row.get("low"), row.get("close"), row.get("settle"), row.get("volume"),
                    row.get("amount"), row.get("turnover_rate"), row.get("open_interest"),
                    row.get("pct_change"), row.get("source"),
                ]
                for row in rows
            ],
        )
        connection.execute("copy bars to ? (format parquet, compression zstd)", [str(parquet_path)])
        connection.close()
    parquet_hash = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    manifest = {
        **manifest_seed,
        "snapshotId": snapshot_id,
        "createdAt": utc_now(),
        "files": [{"path": "bars.parquet", "sha256": parquet_hash, "rows": payload["count"]}],
        "readOnly": True,
        "network": "none",
    }
    (root / "manifest.json").write_text(json_dump(manifest), encoding="utf-8")
    (root / "lean_research.py").write_text(SDK_SOURCE, encoding="utf-8")
    return manifest
