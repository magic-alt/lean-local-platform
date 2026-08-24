from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

if os.environ.get("RUN_LEAN_NATIVE_INTEGRATION") != "1":
    pytest.skip("Set RUN_LEAN_NATIVE_INTEGRATION=1 to run native LEAN integration.", allow_module_level=True)


def test_native_lean_runs_pinned_acceptance_spec(tmp_path):
    from app.runners.lean_runner import LeanRunner

    spec_path = Path(os.environ.get("LEAN_NATIVE_ACCEPTANCE_SPEC", ""))
    if not spec_path.is_file():
        pytest.fail("LEAN_NATIVE_ACCEPTANCE_SPEC must identify the fixed certified acceptance JSON")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    project_dir = Path(spec["projectDir"]).resolve()
    algorithm_path = (project_dir / spec["mainFile"]).resolve()
    output = LeanRunner(timeout_seconds=int(spec.get("timeoutSeconds") or 300)).run_backtest(
        str(spec["runId"]),
        dict(spec["parameters"]),
        tmp_path / "native-run",
        output_callback=lambda _line: None,
        algorithm_path=algorithm_path,
        algorithm_class=str(spec["algorithmClass"]),
        language="Python",
        project_dir=project_dir,
    )

    assert output["execution_backend"] == "native"
    assert output["exit_code"] == 0
    assert output["timed_out"] is False
    assert output["result_json_path"]
    assert output["runtime_identity"]["artifactSha256"]
