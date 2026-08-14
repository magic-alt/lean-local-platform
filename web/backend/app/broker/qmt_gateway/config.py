from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GatewaySettings:
    """Configuration for the platform-owned, read-only QMT boundary."""

    userdata_path: Path
    account_id: str
    account_type: str
    session_id: int
    token: str
    xtquant_site_packages: Path | None = None

    @classmethod
    def from_environment(cls) -> "GatewaySettings":
        def required(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise RuntimeError(f"required gateway configuration is missing: {name}")
            return value

        try:
            session_id = int(os.environ.get("QMT_SESSION_ID", "18001"))
        except ValueError as exc:
            raise RuntimeError("QMT_SESSION_ID must be an integer") from exc
        if session_id <= 0:
            raise RuntimeError("QMT_SESSION_ID must be positive")
        site_packages = os.environ.get("QMT_XTQUANT_SITE_PACKAGES", "").strip()
        return cls(
            userdata_path=Path(required("QMT_USERDATA_PATH")),
            account_id=required("QMT_ACCOUNT_ID"),
            account_type=os.environ.get("QMT_ACCOUNT_TYPE", "STOCK").strip() or "STOCK",
            session_id=session_id,
            token=required("QMT_GATEWAY_TOKEN"),
            xtquant_site_packages=Path(site_packages) if site_packages else None,
        )
