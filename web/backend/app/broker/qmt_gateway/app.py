from __future__ import annotations

import secrets
from typing import Callable

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import GatewaySettings
from .service import QmtGatewayService
from .xtquant_client import QmtReadOnlyClient, XtQuantReadOnlyClient


def create_app(settings: GatewaySettings, *, client: QmtReadOnlyClient | None = None) -> FastAPI:
    """Create a GET-only broker observation service for the local MiniQMT process."""

    service = QmtGatewayService(client or XtQuantReadOnlyClient(settings))
    bearer = HTTPBearer(auto_error=False)

    def require_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
        if not secrets.compare_digest(credentials.credentials, settings.token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")

    app = FastAPI(title="Platform QMT Read-only Broker Gateway", version="2.0.0")

    def gateway_call(call: Callable[[], object]) -> object:
        try:
            return call()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    @app.get("/v1/health")
    def health() -> dict[str, object]:
        value = service.health()
        if value["status"] != "ready":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=value["reason"])
        return value

    @app.get("/v1/account", dependencies=[Depends(require_token)])
    def account(trade_date: str) -> dict[str, object]:
        return gateway_call(lambda: service.account(trade_date))  # type: ignore[return-value]

    @app.get("/v1/positions", dependencies=[Depends(require_token)])
    def positions(trade_date: str) -> list[dict[str, object]]:
        return gateway_call(lambda: service.positions(trade_date))  # type: ignore[return-value]

    @app.get("/v1/orders", dependencies=[Depends(require_token)])
    def orders(trade_date: str) -> list[dict[str, object]]:
        return gateway_call(lambda: service.orders(trade_date))  # type: ignore[return-value]

    @app.get("/v1/fills", dependencies=[Depends(require_token)])
    def fills(trade_date: str) -> list[dict[str, object]]:
        return gateway_call(lambda: service.fills(trade_date))  # type: ignore[return-value]

    @app.get("/v1/quotes", dependencies=[Depends(require_token)])
    def quotes(trade_date: str, instruments: str) -> list[dict[str, object]]:
        requested = [item.strip().upper() for item in instruments.split(",") if item.strip()]
        if not requested:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="instruments is required")
        return gateway_call(lambda: service.quotes(trade_date, requested))  # type: ignore[return-value]

    return app
