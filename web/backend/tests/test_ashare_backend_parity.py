from __future__ import annotations

import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

if os.environ.get("RUN_LEAN_BACKEND_PARITY") != "1":
    pytest.skip("Set RUN_LEAN_BACKEND_PARITY=1 to run Docker/native parity.", allow_module_level=True)


def test_certified_docker_native_results_are_equivalent():
    from app.services.backend_parity import compare_results

    docker_result = Path(os.environ.get("LEAN_DOCKER_PARITY_RESULT", ""))
    native_result = Path(os.environ.get("LEAN_NATIVE_PARITY_RESULT", ""))
    if not docker_result.is_file() or not native_result.is_file():
        pytest.fail("LEAN_DOCKER_PARITY_RESULT and LEAN_NATIVE_PARITY_RESULT are required")

    report = compare_results(docker_result, native_result, tolerance=1e-8)

    assert report["passed"], report
