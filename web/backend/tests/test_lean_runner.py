import json

import pytest

from app.lean import base_config, docker_command
from app.core.config import DEFAULT_DOCKER_IMAGE
from app.runners.lean_runner import LeanRunner


def test_container_name_is_stable_and_bounded():
    run_id = "SPY-20260101-20260201-" + "x" * 120
    name = LeanRunner.container_name_for(run_id)
    assert name.startswith("lean-SPY")
    assert len(name) <= 60


def test_worker_project_resolution_rejects_legacy_projectless_task():
    from app.lean_engine.errors import LeanPlatformError
    from app.tasks.worker import _task_project

    with pytest.raises(LeanPlatformError, match="project_required"):
        _task_project({"project_id": None, "parameters": {}})


def test_docker_command_uses_argument_list_and_expected_mounts(tmp_path, monkeypatch):
    import app.lean as lean

    monkeypatch.setattr(lean.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    config_path = tmp_path / "run" / "config.json"
    results_dir = tmp_path / "run" / "results"
    algorithm_path = tmp_path / "algo.py"
    project_dir = tmp_path / "project"
    config_path.parent.mkdir()
    results_dir.mkdir()
    algorithm_path.write_text("# test", encoding="utf-8")
    project_dir.mkdir()
    project_algorithm = project_dir / "main.py"
    project_algorithm.write_text("# test", encoding="utf-8")

    support_dir = tmp_path / "run"
    command = docker_command(
        config_path,
        results_dir,
        image=DEFAULT_DOCKER_IMAGE,
        project_dir=project_dir,
        support_dir=support_dir,
    )

    assert command[0] == "/usr/bin/docker"
    assert "run" in command
    assert "--rm" in command
    assert DEFAULT_DOCKER_IMAGE in command
    assert "--network" in command and "none" in command
    assert "--read-only" in command
    assert "--cap-drop" in command and "ALL" in command
    assert "no-new-privileges:true" in command
    assert any(str(config_path) in item for item in command)
    assert f"{support_dir}:/Lean/Run:ro" in command
    assert all(";" not in item for item in command)


def test_docker_command_maps_container_paths_to_host_paths(tmp_path, monkeypatch):
    import app.lean as lean

    container_root = tmp_path / "container" / "repo"
    host_root = tmp_path / "host" / "repo"
    host_data = tmp_path / "host" / "Data"
    container_data = container_root / "Data"
    config_path = container_root / "web" / "runtime" / "runs" / "job" / "config.json"
    results_dir = container_root / "web" / "runtime" / "runs" / "job" / "results"
    project_dir = container_root / "web" / "runtime" / "projects" / "project-1"
    support_dir = container_root / "web" / "runtime" / "runs" / "job"

    monkeypatch.setattr(lean.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(lean, "PLATFORM_DIR", container_root)
    monkeypatch.setattr(lean, "HOST_PLATFORM_DIR", host_root)
    monkeypatch.setattr(lean, "DATA_DIR", container_data)
    monkeypatch.setattr(lean, "HOST_DATA_DIR", host_data)
    monkeypatch.setattr(lean, "OBJECT_STORE_DIR", container_root / "web" / "runtime" / "object-store")
    monkeypatch.setenv("LEAN_HOST_PLATFORM_DIR", str(host_root))
    monkeypatch.setenv("LEAN_HOST_DATA_DIR", str(host_data))

    command = docker_command(
        config_path,
        results_dir,
        image=DEFAULT_DOCKER_IMAGE,
        project_dir=project_dir,
        support_dir=support_dir,
    )

    assert f"{host_root / 'web' / 'runtime' / 'runs' / 'job' / 'config.json'}:/Lean/Launcher/bin/Debug/config.json:ro" in command
    assert f"{host_data}:/Lean/Data:ro" in command
    assert f"{host_root / 'web' / 'runtime' / 'runs' / 'job' / 'results'}:/Lean/Results" in command
    assert f"{host_root / 'web' / 'runtime' / 'projects' / 'project-1'}:/Lean/Project:ro" in command


def test_base_config_adds_python_path_for_ashare_rules():
    config = base_config(
        "job-1",
        {"ticker": "600519", "assetClass": "equity", "ashareRules": True},
        algorithm_class="Algorithm",
        algorithm_location="/Lean/Project/main.py",
        language="Python",
    )

    assert config["python-additional-paths"] == ["/Lean/Run"]


def test_lean_runner_mounts_hongkong_execution_support(tmp_path, monkeypatch):
    import app.runners.lean_runner as runner_module

    captured = {}

    def fake_docker_command(*args, **kwargs):
        captured.update(kwargs)
        return ["docker", "run", "unit"]

    monkeypatch.setattr(runner_module, "docker_command", fake_docker_command)
    run_dir = tmp_path / "hk-run"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    algorithm_path = project_dir / "custom.py"
    algorithm_path.write_text("class Custom: pass\n", encoding="utf-8")
    workspace = LeanRunner().prepare(
        "hk-job",
        {
            "ticker": "00700",
            "assetClass": "equity",
            "market": "hongkong",
            "hkRules": True,
        },
        run_dir,
        algorithm_path=algorithm_path,
        algorithm_class="Custom",
        language="Python",
        project_dir=project_dir,
    )

    assert (run_dir / "hk_execution.py").is_file()
    assert captured["support_dir"] == run_dir
    assert workspace.algorithm_container_path == "/Lean/Project/custom.py"
    assert json.loads(workspace.config_path.read_text(encoding="utf-8"))["python-additional-paths"] == ["/Lean/Run"]


def test_lean_runner_writes_artifact_manifest_without_result_json(tmp_path, monkeypatch):
    import json
    import app.runners.lean_runner as runner_module
    from app.runners.docker_runner import DockerRunResult

    monkeypatch.setattr(runner_module, "docker_command", lambda *args, **kwargs: ["docker", "run", "unit"])

    class DummyDockerRunner:
        def __init__(self, timeout_seconds):
            self.timeout_seconds = timeout_seconds

        def run(self, command, output_callback, container_name=None):
            output_callback("unit docker output")
            results_dir = tmp_path / "run" / "results"
            (results_dir / "log.txt").write_text("lean log", encoding="utf-8")
            return DockerRunResult(exit_code=1, error="unit failure")

    monkeypatch.setattr(runner_module, "DockerRunner", DummyDockerRunner)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    algorithm_path = project_dir / "main.py"
    algorithm_path.write_text("class Algorithm: pass\n", encoding="utf-8")

    output = LeanRunner(timeout_seconds=10).run_backtest(
        "job-1",
        {
            "ticker": "SPY",
            "assetClass": "equity",
            "market": "usa",
            "start": "2024-01-01",
            "end": "2024-01-31",
        },
        tmp_path / "run",
        output_callback=lambda line: None,
        algorithm_path=algorithm_path,
        algorithm_class="Algorithm",
        language="Python",
        project_dir=project_dir,
    )

    manifest_path = output["artifact_manifest_path"]
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())

    assert output["exit_code"] == 1
    assert output["stdout_log_path"].endswith("stdout.log")
    assert manifest["runId"] == "job-1"
    assert manifest["exitCode"] == 1
    assert {item["name"] for item in manifest["artifacts"]} >= {"config.json", "log.txt", "stdout.log"}
    assert "unit docker output" in open(output["stdout_log_path"], encoding="utf-8").read()
