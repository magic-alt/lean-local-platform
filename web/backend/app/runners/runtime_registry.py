from __future__ import annotations

import hashlib
import json
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.config import LEAN_NATIVE_LOCK_PATH, LEAN_NATIVE_RUNTIME_ID, LEAN_RUNTIME_ROOT
from ..lean_engine.errors import LeanPlatformError
from .base import RuntimeIdentity


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class NativeRuntime:
    root: Path
    launcher: Path
    identity: RuntimeIdentity
    python_home: Path | None
    python_library: Path | None


def native_platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    aliases = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}
    arch = aliases.get(machine, machine)
    if system == "linux" and arch == "x64":
        return "linux-x64"
    if system == "darwin" and arch == "arm64":
        return "macos-arm64"
    if system == "windows" and arch == "x64":
        return "windows-x64"
    raise LeanPlatformError(f"native_runtime_platform_unsupported:{system}-{arch}")


class RuntimeRegistry:
    def __init__(self, lock_path: Path = LEAN_NATIVE_LOCK_PATH, runtime_root: Path = LEAN_RUNTIME_ROOT):
        self.lock_path = Path(lock_path)
        self.runtime_root = Path(runtime_root)

    def read_lock(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LeanPlatformError("native_runtime_lock_unavailable") from exc
        if payload.get("schemaVersion") != 1:
            raise LeanPlatformError("native_runtime_lock_schema_invalid")
        if payload.get("supported") is not True:
            raise LeanPlatformError("native_runtime_not_configured")
        runtime_id = str(payload.get("runtimeId") or "")
        commit = str(payload.get("leanCommit") or "").lower()
        if not runtime_id or not _GIT_SHA.fullmatch(commit):
            raise LeanPlatformError("native_runtime_lock_identity_invalid")
        return payload

    def artifact(self, platform_key: str | None = None) -> dict[str, str]:
        payload = self.read_lock()
        key = platform_key or native_platform_key()
        artifact = (payload.get("artifacts") or {}).get(key)
        if not isinstance(artifact, dict):
            raise LeanPlatformError(f"native_runtime_artifact_missing:{key}")
        required = ("url", "sha256", "signatureUrl", "sbomUrl")
        if any(not str(artifact.get(name) or "") for name in required):
            raise LeanPlatformError("native_runtime_artifact_metadata_incomplete")
        if not _SHA256.fullmatch(str(artifact["sha256"]).lower()):
            raise LeanPlatformError("native_runtime_artifact_sha256_invalid")
        if any(not str(artifact[name]).startswith("https://") for name in ("url", "signatureUrl", "sbomUrl")):
            raise LeanPlatformError("native_runtime_artifact_url_must_use_https")
        result = {name: str(artifact[name]) for name in required}
        for name in ("launcher", "pythonHome", "pythonLibrary"):
            if artifact.get(name) is not None:
                result[name] = str(artifact[name])
        return result

    @staticmethod
    def _relative_path(
        payload: dict[str, Any], artifact: dict[str, str], name: str
    ) -> Path | None:
        value = artifact.get(name)
        if value is None:
            raw = payload.get(name)
            value = str(raw) if raw is not None else None
        if not value:
            return None
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise LeanPlatformError(f"native_runtime_{name.lower()}_path_invalid")
        return relative

    def resolve(self) -> NativeRuntime:
        payload = self.read_lock()
        runtime_id = LEAN_NATIVE_RUNTIME_ID or str(payload["runtimeId"])
        if runtime_id != str(payload["runtimeId"]):
            raise LeanPlatformError("native_runtime_id_not_locked")
        platform_key = native_platform_key()
        artifact = self.artifact(platform_key)
        root = (self.runtime_root / runtime_id).resolve()
        marker_path = root / ".ready.json"
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LeanPlatformError("native_runtime_not_installed") from exc
        if (
            marker.get("runtimeId") != runtime_id
            or marker.get("platform") != platform_key
            or marker.get("artifactSha256") != artifact["sha256"].lower()
            or marker.get("signatureVerified") is not True
            or marker.get("sbomVerified") is not True
        ):
            raise LeanPlatformError("native_runtime_ready_marker_invalid")
        launcher_relative = self._relative_path(payload, artifact, "launcher")
        if launcher_relative is None:
            raise LeanPlatformError("native_runtime_launcher_path_invalid")
        launcher = (root / launcher_relative).resolve()
        if not launcher.is_relative_to(root) or not launcher.is_file():
            raise LeanPlatformError("native_runtime_launcher_missing")
        launcher_sha = str(marker.get("launcherSha256") or "").lower()
        if not _SHA256.fullmatch(launcher_sha):
            raise LeanPlatformError("native_runtime_launcher_digest_missing")
        actual_launcher_sha = hashlib.sha256(launcher.read_bytes()).hexdigest()
        if actual_launcher_sha != launcher_sha:
            raise LeanPlatformError("native_runtime_launcher_digest_mismatch")
        python_relative = self._relative_path(payload, artifact, "pythonHome")
        python_home = (root / python_relative).resolve() if python_relative else None
        if python_home is not None and (
            not python_home.is_relative_to(root) or not python_home.exists()
        ):
            raise LeanPlatformError("native_runtime_python_path_invalid")
        library_relative = self._relative_path(payload, artifact, "pythonLibrary")
        python_library = (root / library_relative).resolve() if library_relative else None
        if python_library is not None and (
            not python_library.is_relative_to(root) or not python_library.is_file()
        ):
            raise LeanPlatformError("native_runtime_python_library_invalid")
        return NativeRuntime(
            root=root,
            launcher=launcher,
            python_home=python_home,
            python_library=python_library,
            identity=RuntimeIdentity(
                backend="native",
                runtime_id=runtime_id,
                artifact_sha256=artifact["sha256"].lower(),
                lean_commit=str(payload["leanCommit"]).lower(),
                platform=platform_key,
            ),
        )
