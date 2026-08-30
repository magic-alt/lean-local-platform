from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


from app.db import db, init_db, json_dump, utc_now
from app.main import app
from app.services import research_runs


SCOPE = {
    "asset": {
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "dataType": "trade",
    },
    "selection": {"type": "universe", "values": ["CSI300"]},
    "time": {
        "startDate": "2020-01-01",
        "endDate": "2025-12-31",
        "asOfDate": "2025-12-31",
    },
    "price": {"adjust": "raw"},
    "provider": {"source": "tushare", "mode": "strict", "allowResearchSource": False},
}


def test_service_refuses_new_and_retried_legacy_ml_jobs():
    init_db()
    operations = (
        lambda: research_runs.preview("ml-cross-sectional-ranker", SCOPE, {}),
        lambda: research_runs.create_run(
            template_key="ml-cross-sectional-ranker",
            name="retired",
            scope=SCOPE,
            parameters={},
        ),
    )
    for operation in operations:
        with pytest.raises(ValueError, match="Legacy platform ML training is retired"):
            operation()
    with db() as connection:
        assert (
            connection.execute("select count(*) count from research_runs").fetchone()[
                "count"
            ]
            == 0
        )
        connection.execute(
            """insert into research_runs
               (id,template_key,name,status,scope_json,parameters_json,cancel_requested,created_at)
               values ('legacy-run','ml-cross-sectional-ranker','legacy','failed',?,?,0,?)""",
            (json_dump(SCOPE), json_dump({}), utc_now()),
        )
    with db() as connection:
        assert (
            connection.execute("select count(*) count from research_runs").fetchone()[
                "count"
            ]
            == 1
        )
    with pytest.raises(ValueError, match="Legacy platform ML training is retired"):
        research_runs.retry_run("legacy-run")
    assert research_runs.get_run("legacy-run")["id"] == "legacy-run"


def test_http_api_removes_legacy_research_execution_routes():
    init_db()
    client = TestClient(app)
    request = {
        "template": "ml-cross-sectional-ranker",
        "name": "retired",
        "scope": SCOPE,
        "parameters": {},
    }

    preview = client.post("/api/research/runs/preview", json=request)
    create = client.post("/api/research/runs", json=request)
    assert preview.status_code == 404
    assert create.status_code == 404

    with db() as connection:
        connection.execute(
            """insert into research_runs
               (id,template_key,name,status,scope_json,parameters_json,cancel_requested,created_at)
               values ('legacy-api-run','ml-cross-sectional-ranker','legacy','failed',?,?,0,?)""",
            (json_dump(SCOPE), json_dump({}), utc_now()),
        )

    retry = client.post("/api/research/runs/legacy-api-run/retry")
    assert retry.status_code == 404
    detail = client.get("/api/research/runs/legacy-api-run")
    assert detail.status_code == 404
