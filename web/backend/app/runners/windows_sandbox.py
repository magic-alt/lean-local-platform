from __future__ import annotations

import ctypes
import getpass
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..core.config import DATA_DIR, LEAN_RUNTIME_ROOT, RUNTIME_DIR


DEFAULT_POLICY_PATH = Path(
    os.environ.get(
        "LEAN_WINDOWS_SANDBOX_POLICY_FILE",
        r"C:\ProgramData\LeanPlatform\sandbox-policy.json",
    )
)


@dataclass(frozen=True)
class WindowsSandboxStatus:
    ready: bool
    detail: str
    checks: dict[str, bool]


class WindowsSandboxVerifier:
    def __init__(
        self,
        policy_path: Path = DEFAULT_POLICY_PATH,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.policy_path = Path(policy_path)
        self.runner = runner

    def _policy(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _firewall(self, display_name: str) -> bool:
        completed = self.runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "$rule=Get-NetFirewallRule -DisplayName '"
                    + display_name.replace("'", "''")
                    + "' -ErrorAction Stop; "
                    "$ok=($rule.Enabled -eq 'True' -and $rule.Direction -eq 'Outbound' "
                    "-and $rule.Action -eq 'Block'); if(-not $ok){exit 2}"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return completed.returncode == 0

    def _acl(self, path: Path, account: str) -> bool:
        completed = self.runner(
            ["icacls.exe", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return completed.returncode == 0 and account.casefold() in completed.stdout.casefold()

    def verify(self, *, require_current_account: bool = True) -> WindowsSandboxStatus:
        if os.name != "nt":
            return WindowsSandboxStatus(False, "windows_sandbox_requires_windows", {})
        policy = self._policy()
        account = str(policy.get("runnerAccount") or "").strip()
        firewall_rule = str(policy.get("firewallRule") or "").strip()
        current = getpass.getuser().split("\\")[-1].casefold()
        expected = account.split("\\")[-1].casefold()
        required_roots = {
            Path(str(policy.get("dataRoot") or DATA_DIR)).resolve(),
            Path(str(policy.get("runtimeRoot") or LEAN_RUNTIME_ROOT)).resolve(),
            Path(str(policy.get("workRoot") or RUNTIME_DIR)).resolve(),
        }
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
        checks = {
            "policy": policy.get("schemaVersion") == 1,
            "serviceAccount": bool(account) and (not require_current_account or current == expected),
            "restrictedTokenApi": bool(getattr(advapi32, "CreateRestrictedToken", None)),
            "jobObjectApi": all(
                bool(getattr(kernel32, name, None))
                for name in (
                    "CreateJobObjectW",
                    "SetInformationJobObject",
                    "AssignProcessToJobObject",
                    "TerminateJobObject",
                )
            ),
            "firewall": bool(firewall_rule) and self._firewall(firewall_rule),
            "acl": bool(account)
            and all(path.exists() and self._acl(path, account) for path in required_roots),
            "runtimeRoot": LEAN_RUNTIME_ROOT.resolve().is_relative_to(
                Path(str(policy.get("runtimeRoot") or LEAN_RUNTIME_ROOT)).resolve()
            ),
        }
        failed = [name for name, passed in checks.items() if not passed]
        return WindowsSandboxStatus(
            not failed,
            "windows sandbox verified" if not failed else "LEAN_RUNNER_UNSAFE:" + ",".join(failed),
            checks,
        )


class WindowsJobObject:
    """Kill-on-close process-tree and bounded-resource Job Object."""

    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _ExtendedLimitInformation(ctypes.Structure):
        pass

    _ExtendedLimitInformation._fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

    def __init__(self, *, memory_bytes: int, active_process_limit: int) -> None:
        if os.name != "nt":
            raise RuntimeError("windows_job_object_requires_windows")
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        self.handle = handle
        limits = self._ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | self.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | self.JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | self.JOB_OBJECT_LIMIT_JOB_MEMORY
        )
        limits.BasicLimitInformation.ActiveProcessLimit = max(1, active_process_limit)
        limits.ProcessMemoryLimit = max(256 * 1024**2, memory_bytes)
        limits.JobMemoryLimit = max(256 * 1024**2, memory_bytes)
        if not kernel32.SetInformationJobObject(
            handle,
            self.JobObjectExtendedLimitInformation,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def assign(self, process_handle: int) -> None:
        if not ctypes.windll.kernel32.AssignProcessToJobObject(self.handle, process_handle):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def terminate(self, exit_code: int = 1) -> None:
        ctypes.windll.kernel32.TerminateJobObject(self.handle, exit_code)

    def close(self) -> None:
        handle, self.handle = self.handle, None
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
