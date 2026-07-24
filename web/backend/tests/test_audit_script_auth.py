from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps({"ok": True}).encode("utf-8")


def test_daily_shadow_reads_runtime_token_without_exposing_it(tmp_path, monkeypatch):
    module = _load_script("audit_daily_shadow", "scripts/run_daily_shadow_pipeline.py")
    token_file = tmp_path / "api_token"
    token_file.write_text("audit-secret\n", encoding="utf-8")
    monkeypatch.delenv("LEAN_API_TOKEN", raising=False)
    monkeypatch.setenv("LEAN_API_TOKEN_FILE", str(token_file))
    captured = {}

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    status, payload = module._api("http://localhost", "GET", "/api/health", timeout=7)

    assert status == 200
    assert payload == {"ok": True}
    assert captured == {"authorization": "Bearer audit-secret", "timeout": 7}


def test_level3_shadow_prefers_environment_token(monkeypatch):
    module = _load_script("audit_level3_shadow", "scripts/run_level3_shadow_audit.py")
    monkeypatch.setenv("LEAN_API_TOKEN", "environment-secret")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    status, payload = module._api_json("http://localhost", "/api/health")

    assert status == 200
    assert payload == {"ok": True}
    assert captured == {"authorization": "Bearer environment-secret", "timeout": 20}


def test_daily_shadow_backtest_requires_governed_project(monkeypatch):
    module = _load_script("audit_daily_shadow_contract", "scripts/run_daily_shadow_pipeline.py")
    captured = {}

    def fake_api(base_url, method, path, payload=None, timeout=300):
        captured.update(
            {
                "base_url": base_url,
                "method": method,
                "path": path,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return 400, {"detail": "contract probe"}

    monkeypatch.setattr(module, "_api", fake_api)
    result = module._backtest_smoke(
        "http://localhost",
        "governed-project-id",
        "600519",
        "000300",
        "tushare",
        "2023-01-03",
        "2023-06-30",
        "next_open",
    )

    assert result["status"] == "critical"
    assert captured["payload"]["projectId"] == "governed-project-id"
    assert captured["payload"]["symbol"] == "600519"


def test_level3_audit_redacts_compose_secrets():
    module = _load_script("audit_level3_redaction", "scripts/run_level3_shadow_audit.py")
    rendered = module._redact_text(
        "  TUSHARE_TOKEN: provider-secret\n"
        "  LEAN_DATABASE_URL: mysql://secret\n"
        "  NORMAL_SETTING: visible\n"
    )

    assert "provider-secret" not in rendered
    assert "mysql://secret" not in rendered
    assert rendered.count("<redacted>") == 2
    assert "NORMAL_SETTING: visible" in rendered


def test_level4_audit_authenticates_json_and_csv_requests(tmp_path, monkeypatch):
    from scripts import run_level4_audit as module

    token_file = tmp_path / "api_token"
    token_file.write_text("level4-secret\n", encoding="utf-8")
    monkeypatch.delenv("LEAN_API_TOKEN", raising=False)
    monkeypatch.setenv("LEAN_API_TOKEN_FILE", str(token_file))
    captured = []

    class Response(_Response):
        headers = {}

        def read(self) -> bytes:
            return json.dumps(
                {
                    "withinLimit": True,
                    "expandedCount": 1,
                    "items": [],
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured.append((request.full_url, request.get_header("Authorization"), timeout))
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    payload, status, _ = module._api(
        "http://localhost",
        "POST",
        "/api/experiment-batches/preview",
        {"kind": "backtest"},
        timeout=7,
    )

    assert status == 200
    assert payload["withinLimit"] is True
    assert captured == [
        (
            "http://localhost/api/experiment-batches/preview",
            "Bearer level4-secret",
            7,
        )
    ]


def test_level4_validator_cannot_report_pass_with_failed_invariants():
    from scripts import run_level4_audit as module

    status, _warnings, failures = module._validate_case_result(
        "rolling",
        {"mode": "rolling", "minRollingFolds": 3},
        {
            "status": "success",
            "items": [
                {
                    "id": "only-item",
                    "status": "success",
                    "parameters": {
                        "start": "2023-01-01",
                        "end": "2023-12-31",
                        "parameters": {
                            "experimentMode": "rolling",
                            "experimentFold": 1,
                            "experimentPhase": "rolling",
                        },
                    },
                }
            ],
        },
    )

    assert status == "failed"
    assert any(item.startswith("rolling_folds_below_min") for item in failures)
    # Also retain a hard invalid batch status probe.
    status, _warnings, failures = module._validate_case_result(
        "rolling",
        {"mode": "rolling"},
        {"status": "failed", "items": [{"id": "x", "status": "failed"}]},
    )
    assert status == "failed"
    assert failures


def test_level4_dynamic_pit_reads_nested_strategy_parameters():
    from scripts import run_level4_audit as module

    status, warnings, failures = module._validate_case_result(
        "dynamic_pit",
        {
            "mode": "dynamic_universe",
            "universeCode": "CSI300",
            "start": "2021-01-01",
            "end": "2021-12-31",
        },
        {
            "status": "success",
            "config": {
                "resolvedSelection": {
                    "type": "universe",
                    "universeCode": "CSI300",
                    "symbols": ["000001", "600519"],
                }
            },
            "items": [
                {
                    "id": "dynamic-item",
                    "status": "success",
                    "parameters": {
                        "start": "2021-01-01",
                        "end": "2021-12-31",
                        "parameters": {
                            "universeCode": "CSI300",
                            "dynamicUniverse": True,
                            "universeSchedule": json.dumps(
                                [
                                    {
                                        "symbol": "000001",
                                        "startDate": "2021-01-01",
                                        "endDate": "2021-06-30",
                                    },
                                    {
                                        "symbol": "600519",
                                        "startDate": "2021-07-01",
                                        "endDate": None,
                                    },
                                ]
                            ),
                        },
                    },
                }
            ],
        },
    )

    assert status == "passed"
    assert failures == []
    assert not any(item.startswith("dynamic_universe_code_skew") for item in warnings)


def test_level4_walk_forward_requires_train_validation_and_oos():
    from scripts import run_level4_audit as module

    legacy_items = []
    for phase, start, end in (
        ("train", "2020-01-01", "2020-12-31"),
        ("test", "2021-01-01", "2021-12-31"),
    ):
        legacy_items.append(
            {
                "id": phase,
                "status": "success",
                "parameters": {
                    "start": start,
                    "end": end,
                    "parameters": {
                        "experimentMode": "walk_forward",
                        "experimentFold": 1,
                        "experimentPhase": phase,
                    },
                },
            }
        )

    status, _warnings, failures = module._validate_case_result(
        "walk_forward",
        {"mode": "walk_forward", "minWalkForwardFolds": 1},
        {"status": "success", "items": legacy_items},
    )

    assert status == "failed"
    assert any(item.startswith("walk_forward_fold_phase_invalid") for item in failures)
