from __future__ import annotations

from pathlib import Path
import signal
import shlex
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "start_web_single_instance.sh"


def _bash_available() -> bool:
    bash = shutil.which("bash")
    if not bash:
        return False
    try:
        return subprocess.run(
            [bash, "--version"], capture_output=True, timeout=2, check=False
        ).returncode == 0
    except OSError:
        return False


@pytest.mark.skipif(not _bash_available(), reason="a functional bash is required")
def test_start_web_script_is_valid_bash() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not _bash_available(), reason="a functional bash is required")
def test_shutdown_terminates_tracked_log_process_without_waiting_forever(tmp_path: Path) -> None:
    lock_dir = tmp_path / "launcher.lock"
    command = f"""
        source {shlex.quote(str(SCRIPT))}
        START_COMPOSE_SERVICES=0
        COMPOSE_STARTED=0
        LOCK_DIR={shlex.quote(str(lock_dir))}
        mkdir "$LOCK_DIR"
        printf '%s\n' "$$" > "$LOCK_DIR/pid"
        LOCK_ACQUIRED=1
        sleep 300 &
        LOG_STREAM_PID=$!
        shutdown 0
    """
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("收到退出信号") == 1
    assert not lock_dir.exists()


@pytest.mark.skipif(not _bash_available(), reason="a functional bash is required")
def test_sigint_exits_launcher_once_and_releases_lock(tmp_path: Path) -> None:
    lock_dir = tmp_path / "signal.lock"
    command = f"""
        source {shlex.quote(str(SCRIPT))}
        START_COMPOSE_SERVICES=0
        COMPOSE_STARTED=0
        LOCK_DIR={shlex.quote(str(lock_dir))}
        mkdir "$LOCK_DIR"
        printf '%s\n' "$$" > "$LOCK_DIR/pid"
        LOCK_ACQUIRED=1
        trap 'shutdown 130' INT
        trap 'shutdown 143' TERM
        trap 'shutdown $?' EXIT
        sleep 300 &
        LOG_STREAM_PID=$!
        printf 'READY\n'
        wait "$LOG_STREAM_PID"
    """
    process = subprocess.Popen(
        ["bash", "-c", command],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "READY"
    process.send_signal(signal.SIGINT)
    stdout, stderr = process.communicate(timeout=5)

    assert process.returncode == 130, stderr
    assert stdout.count("收到退出信号") == 1
    assert not lock_dir.exists()
