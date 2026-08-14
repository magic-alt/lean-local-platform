from __future__ import annotations

import argparse
import ipaddress

from .app import create_app
from .config import GatewaySettings


def _loopback_host(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("QMT gateway host must be a loopback IP address") from exc
    if not address.is_loopback:
        raise argparse.ArgumentTypeError("QMT gateway host must be loopback-only")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Platform-owned read-only QMT Broker Gateway")
    parser.add_argument("serve", nargs="?", default="serve", choices=["serve"])
    parser.add_argument("--host", type=_loopback_host, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    settings = GatewaySettings.from_environment()
    import uvicorn

    uvicorn.run(create_app(settings), host=args.host, port=args.port, workers=1)
    return 0
