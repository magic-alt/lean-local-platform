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
