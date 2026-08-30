from __future__ import annotations

import json

import pytest

from scripts import platformctl


def test_auto_mode_requires_one_unambiguous_source(tmp_path, monkeypatch):
    monkeypatch.setattr(platformctl, "DEPLOYMENT_STATE", tmp_path / "state.json")
    monkeypatch.delenv("LEAN_DEPLOYMENT_MODE", raising=False)

    with pytest.raises(platformctl.PlatformCtlError, match="auto_mode_ambiguous"):
        platformctl.resolve_selection("auto", None)


def test_cli_mode_precedes_config_and_persisted_state(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"mode": "native", "profile": "core"}), encoding="utf-8")
    monkeypatch.setattr(platformctl, "DEPLOYMENT_STATE", state)
    monkeypatch.setenv("LEAN_DEPLOYMENT_MODE", "native")

    selection = platformctl.resolve_selection("docker", "dev")

    assert selection.mode == "docker"
    assert selection.profile == "dev"


def test_auto_mode_rejects_conflicting_config_and_state(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"mode": "docker", "profile": "full"}), encoding="utf-8")
    monkeypatch.setattr(platformctl, "DEPLOYMENT_STATE", state)
    monkeypatch.setenv("LEAN_DEPLOYMENT_MODE", "native")

    with pytest.raises(platformctl.PlatformCtlError, match="auto_mode_ambiguous"):
        platformctl.resolve_selection("auto", None)


def test_windows_scm_manager_is_opt_in(monkeypatch):
    monkeypatch.delenv("LEAN_NATIVE_MANAGER", raising=False)
    monkeypatch.delenv("LEAN_WINDOWS_PRODUCTION_MODE", raising=False)

    assert platformctl._windows_scm_requested() is False

    monkeypatch.setenv("LEAN_NATIVE_MANAGER", "windows-scm")
    assert platformctl._windows_scm_requested() is True


def test_windows_local_stop_does_not_call_scm(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {"mode": "native", "profile": "core", "manager": "local", "processes": []}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(platformctl, "DEPLOYMENT_STATE", state)
    monkeypatch.setattr(platformctl.os, "name", "nt")
    monkeypatch.setattr(
        platformctl,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("local stop must not call sc.exe"),
    )

    assert platformctl.stop(platformctl.Selection("native", "core")) == 0
