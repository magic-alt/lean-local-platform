from app.lean import base_config, docker_command
from app.runners.lean_runner import LeanRunner


def test_container_name_is_stable_and_bounded():
    run_id = "SPY-20260101-20260201-" + "x" * 120
    name = LeanRunner.container_name_for(run_id)
    assert name.startswith("lean-SPY")
    assert len(name) <= 60


def test_docker_command_uses_argument_list_and_expected_mounts(tmp_path, monkeypatch):
    import app.lean as lean

    monkeypatch.setattr(lean.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    config_path = tmp_path / "run" / "config.json"
    results_dir = tmp_path / "run" / "results"
    algorithm_path = tmp_path / "algo.py"
    config_path.parent.mkdir()
    results_dir.mkdir()
    algorithm_path.write_text("# test", encoding="utf-8")

    support_dir = tmp_path / "run"
    command = docker_command(
        config_path,
        results_dir,
        image="quantconnect/lean:test",
        algorithm_path=algorithm_path,
        support_dir=support_dir,
    )

    assert command[0] == "/usr/bin/docker"
    assert "run" in command
    assert "--rm" in command
    assert "quantconnect/lean:test" in command
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
    algorithm_path = container_root / "DockerDemoAlgorithm.py"
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
        image="quantconnect/lean:test",
        algorithm_path=algorithm_path,
        support_dir=support_dir,
    )

    assert f"{host_root / 'web' / 'runtime' / 'runs' / 'job' / 'config.json'}:/Lean/Launcher/bin/Debug/config.json:ro" in command
    assert f"{host_data}:/Lean/Data:ro" in command
    assert f"{host_root / 'web' / 'runtime' / 'runs' / 'job' / 'results'}:/Lean/Results" in command
    assert f"{host_root / 'DockerDemoAlgorithm.py'}:/Lean/DockerDemoAlgorithm.py:ro" in command


def test_base_config_adds_python_path_for_ashare_rules():
    config = base_config("job-1", {"ticker": "600519", "assetClass": "equity", "ashareRules": True})

    assert config["python-additional-paths"] == ["/Lean/Run"]
