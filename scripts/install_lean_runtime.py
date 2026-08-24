#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import LEAN_NATIVE_LOCK_PATH, LEAN_RUNTIME_ROOT  # noqa: E402
from app.runners.runtime_registry import RuntimeRegistry, native_platform_key  # noqa: E402


PUBLIC_KEY = ROOT / "config" / "release-signing-public.pem"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    if not url.startswith("https://"):
        raise RuntimeError("runtime_download_requires_https")
    request = urllib.request.Request(url, headers={"User-Agent": "magic-alt-platform-runtime-installer/1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _verify_signature(artifact: Path, signature: Path) -> None:
    openssl = shutil.which("openssl")
    if not openssl or not PUBLIC_KEY.is_file():
        raise RuntimeError("runtime_signature_verifier_unavailable")
    completed = subprocess.run(
        [
            openssl,
            "pkeyutl",
            "-verify",
            "-rawin",
            "-pubin",
            "-inkey",
            str(PUBLIC_KEY),
            "-in",
            str(artifact),
            "-sigfile",
            str(signature),
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("runtime_signature_invalid")


def _safe_member(name: str) -> None:
    normalized = PurePosixPath(name.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise RuntimeError("runtime_archive_path_traversal")


def _extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as handle:
            for item in handle.infolist():
                _safe_member(item.filename)
                if item.is_dir():
                    continue
                mode = item.external_attr >> 16
                if mode & 0o170000 == 0o120000:
                    raise RuntimeError("runtime_archive_symlink_forbidden")
            handle.extractall(destination)
        return
    try:
        with tarfile.open(archive, mode="r:*") as handle:
            for item in handle.getmembers():
                _safe_member(item.name)
                if item.issym() or item.islnk() or item.isdev():
                    raise RuntimeError("runtime_archive_link_or_device_forbidden")
            handle.extractall(destination, filter="data")
        return
    except tarfile.ReadError:
        pass
    tar = shutil.which("tar")
    if not tar:
        raise RuntimeError("runtime_archive_format_unsupported")
    listed = subprocess.run([tar, "-tf", str(archive)], capture_output=True, text=True, check=False)
    if listed.returncode != 0:
        raise RuntimeError("runtime_archive_invalid")
    names = listed.stdout.splitlines()
    verbose = subprocess.run([tar, "-tvf", str(archive)], capture_output=True, text=True, check=False)
    if verbose.returncode != 0 or len(verbose.stdout.splitlines()) != len(names):
        raise RuntimeError("runtime_archive_listing_invalid")
    for name, detail in zip(names, verbose.stdout.splitlines(), strict=True):
        _safe_member(name)
        if not detail or detail[0] not in {"-", "d"}:
            raise RuntimeError("runtime_archive_link_or_device_forbidden")
    extracted = subprocess.run(
        [tar, "--no-same-owner", "--no-same-permissions", "-xf", str(archive), "-C", str(destination)],
        check=False,
    )
    if extracted.returncode != 0:
        raise RuntimeError("runtime_archive_extract_failed")


def _verify_sbom(path: Path, *, runtime_id: str, artifact_sha256: str) -> str:
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("runtime_sbom_invalid") from exc
    if payload.get("bomFormat") != "CycloneDX":
        raise RuntimeError("runtime_sbom_not_cyclonedx")
    properties = {
        str(item.get("name")): str(item.get("value"))
        for item in ((payload.get("metadata") or {}).get("properties") or [])
        if isinstance(item, dict)
    }
    if properties.get("lean.runtime.id") != runtime_id:
        raise RuntimeError("runtime_sbom_identity_mismatch")
    if properties.get("lean.runtime.sha256") != artifact_sha256:
        raise RuntimeError("runtime_sbom_digest_mismatch")
    return _sha256(path)


def install() -> int:
    registry = RuntimeRegistry()
    lock = registry.read_lock()
    platform_key = native_platform_key()
    artifact_meta = registry.artifact(platform_key)
    runtime_id = str(lock["runtimeId"])
    destination = (LEAN_RUNTIME_ROOT / runtime_id).resolve()
    if destination.exists():
        try:
            resolved = registry.resolve()
        except Exception as exc:
            raise RuntimeError("runtime_destination_exists_but_is_not_ready") from exc
        print(f"Runtime already ready: {resolved.identity.runtime_id} ({resolved.identity.platform})")
        return 0
    LEAN_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lean-runtime-download-") as temporary_name:
        temporary = Path(temporary_name)
        archive = temporary / "runtime.archive"
        signature = temporary / "runtime.sig"
        sbom = temporary / "runtime.cyclonedx.json"
        _download(artifact_meta["url"], archive)
        actual_sha = _sha256(archive)
        if actual_sha != artifact_meta["sha256"].lower():
            raise RuntimeError("runtime_artifact_digest_mismatch")
        _download(artifact_meta["signatureUrl"], signature)
        _verify_signature(archive, signature)
        _download(artifact_meta["sbomUrl"], sbom)
        sbom_sha = _verify_sbom(sbom, runtime_id=runtime_id, artifact_sha256=actual_sha)
        staging = LEAN_RUNTIME_ROOT / f".{runtime_id}.{os.getpid()}.staging"
        try:
            _extract(archive, staging)
            launcher_relative = Path(str(lock["launcher"]))
            launcher = (staging / launcher_relative).resolve()
            if not launcher.is_relative_to(staging.resolve()) or not launcher.is_file():
                raise RuntimeError("runtime_launcher_missing")
            launcher_sha = _sha256(launcher)
            marker = {
                "schemaVersion": 1,
                "runtimeId": runtime_id,
                "platform": platform_key,
                "leanCommit": lock["leanCommit"],
                "artifactSha256": actual_sha,
                "launcherSha256": launcher_sha,
                "sbomSha256": sbom_sha,
                "signatureVerified": True,
                "sbomVerified": True,
            }
            (staging / ".ready.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
            shutil.copy2(sbom, staging / "runtime.cyclonedx.json")
            staging.replace(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    resolved = registry.resolve()
    print(f"Installed runtime: {resolved.identity.runtime_id} ({resolved.identity.platform})")
    return 0


def status() -> int:
    try:
        runtime = RuntimeRegistry().resolve()
    except Exception as exc:
        print(f"NOT_READY: {exc}")
        return 2
    print(json.dumps(runtime.identity.as_dict(), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install and verify a pinned signed native LEAN runtime.")
    parser.add_argument("command", choices=("install", "status"))
    args = parser.parse_args()
    try:
        return install() if args.command == "install" else status()
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
