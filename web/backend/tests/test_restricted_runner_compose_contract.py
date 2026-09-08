from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_restricted_runner_runtime_mount_preserves_read_only_boundaries() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    runner = compose["services"]["lean-runner"]
    volumes = set(runner["volumes"])

    # The runner lifespan updates interrupted jobs through PostgreSQL. db() also
    # initializes runtime directories, so this mount must remain writable even
    # though the container root and market-data mount stay read-only.
    assert "./web/runtime:/workspace/web/runtime" in volumes
    assert ".:/workspace:ro" in volumes
    assert any(value.endswith(":/workspace/data:ro") for value in volumes)
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes

    assert runner["read_only"] is True
    assert runner["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in runner["security_opt"]
    assert any(
        str(value).startswith("/workspace/web/runtime/secrets:rw,")
        for value in runner["tmpfs"]
    )
