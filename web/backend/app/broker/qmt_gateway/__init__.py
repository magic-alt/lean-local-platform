"""Loopback-only, read-only MiniQMT broker gateway."""

from .app import create_app
from .config import GatewaySettings

__all__ = ["GatewaySettings", "create_app"]
