from app.lean import docker_command
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

    command = docker_command(config_path, results_dir, image="quantconnect/lean:test", algorithm_path=algorithm_path)

    assert command[0] == "/usr/bin/docker"
    assert "run" in command
    assert "--rm" in command
    assert "quantconnect/lean:test" in command
    assert any(str(config_path) in item for item in command)
    assert all(";" not in item for item in command)
