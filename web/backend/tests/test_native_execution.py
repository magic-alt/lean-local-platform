from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.lean_engine.config import base_config
from app.lean_engine.errors import LeanPlatformError
from app.runners.base import LeanPathLayout
from app.runners.runtime_registry import RuntimeRegistry
from app.services.backend_parity import compare_results
from app.services.run_fingerprint import canonical_config_hash


def test_docker_layout_is_posix_even_on_windows():
    layout = LeanPathLayout.docker(include_support=True)

    assert str(layout.data_dir) == "/Lean/Data"
    assert str(layout.support_dir) == "/Lean/Run"


def test_canonical_config_hash_ignores_backend_paths(tmp_path):
    docker_path = tmp_path / "docker.json"
    native_path = tmp_path / "native.json"
    docker = base_config(
        "run",
        {"ticker": "SPY"},
        algorithm_class="Algorithm",
        algorithm_location="/Lean/Project/main.py",
        language="Python",
        path_layout=LeanPathLayout.docker(include_support=True),
    )
    native_layout = LeanPathLayout(
        launcher_dir=tmp_path / "runtime",
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        project_dir=tmp_path / "project",
        storage_dir=tmp_path / "storage",
        support_dir=tmp_path / "support",
    )
    native = base_config(
        "run",
        {"ticker": "SPY"},
        algorithm_class="Algorithm",
        algorithm_location=str(native_layout.project_dir / "main.py"),
        language="Python",
        path_layout=native_layout,
    )
    docker_path.write_text(json.dumps(docker), encoding="utf-8")
    native_path.write_text(json.dumps(native), encoding="utf-8")

    assert canonical_config_hash(docker_path) == canonical_config_hash(native_path)


def test_runtime_registry_rejects_unpublished_lock(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "supported": False,
                "runtimeId": "pending",
                "leanCommit": "0" * 40,
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(LeanPlatformError, match="native_runtime_not_configured"):
        RuntimeRegistry(lock, tmp_path / "runtimes").read_lock()


def test_runtime_registry_verifies_ready_launcher(tmp_path, monkeypatch):
    from app.runners import runtime_registry

    launcher_bytes = b"launcher"
    launcher_sha = hashlib.sha256(launcher_bytes).hexdigest()
    artifact_sha = "a" * 64
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "supported": True,
                "runtimeId": "lean-unit",
                "leanCommit": "b" * 40,
                "launcher": "Launcher/QuantConnect.Lean.Launcher.dll",
                "artifacts": {
                    "linux-x64": {
                        "url": "https://example.invalid/runtime",
                        "sha256": artifact_sha,
                        "signatureUrl": "https://example.invalid/runtime.sig",
                        "sbomUrl": "https://example.invalid/runtime.cdx.json",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "runtimes" / "lean-unit"
    launcher = root / "Launcher" / "QuantConnect.Lean.Launcher.dll"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(launcher_bytes)
    (root / ".ready.json").write_text(
        json.dumps(
            {
                "runtimeId": "lean-unit",
                "platform": "linux-x64",
                "artifactSha256": artifact_sha,
                "launcherSha256": launcher_sha,
                "signatureVerified": True,
                "sbomVerified": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_registry, "native_platform_key", lambda: "linux-x64")

    runtime = RuntimeRegistry(lock, tmp_path / "runtimes").resolve()

    assert runtime.identity.artifact_sha256 == artifact_sha
    assert runtime.launcher == launcher


def test_backend_parity_requires_exact_orders_and_tolerant_metrics(tmp_path):
    left = tmp_path / "docker.json"
    right = tmp_path / "native.json"
    payload = {
        "orders": {"1": {"id": 1, "quantity": 2}},
        "trades": [{"id": 1}],
        "statistics": {"End Equity": "100.0", "Sharpe Ratio": "1.5", "Drawdown": "2%"},
    }
    left.write_text(json.dumps(payload), encoding="utf-8")
    payload["statistics"]["End Equity"] = "100.000000001"
    right.write_text(json.dumps(payload), encoding="utf-8")

    assert compare_results(left, right)["passed"] is True

    payload["orders"]["1"]["quantity"] = 3
    right.write_text(json.dumps(payload), encoding="utf-8")
    report = compare_results(left, right)
    assert report["passed"] is False
    assert report["checks"]["orders"] is False
