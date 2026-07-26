from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..services import paper_accounts as service


router = APIRouter(prefix="/api/paper", tags=["paper-accounts"])


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=191)
    description: str | None = Field(default=None, max_length=1024)
    marketScope: str = "china"
    baseCurrency: str = "CNY"
    initialCash: str
    benchmarkSymbol: str = "000300"
    riskConfig: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=191)
    description: str | None = Field(default=None, max_length=1024)
    benchmarkSymbol: str | None = None
    metadata: dict[str, Any] | None = None


class AccountClone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=191)
    description: str | None = None
    initialCash: str | None = None


class DeploymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    projectId: str
    sourceBacktestId: str
    scheduleType: str = "market_daily"
    scheduleExpression: str = "after_close+00:45"
    marketTimezone: str = "Asia/Shanghai"
    executionTiming: str = "next_open"
    signalMode: str = "paper_execute"
    universeConfig: dict[str, Any] = Field(default_factory=dict)
    isPrimary: bool = True


class DeploymentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    projectId: str | None = None
    sourceBacktestId: str | None = None
    scheduleType: str | None = None
    scheduleExpression: str | None = None
    marketTimezone: str | None = None
    executionTiming: str | None = None
    signalMode: str | None = None
    universeConfig: dict[str, Any] | None = None


class RunNowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tradingDate: str | None = None


def _call(callback, *args, **kwargs):
    try:
        return callback(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/accounts/compare")
def compare_accounts(
    accountId: list[str] = Query(default=[]),
    startDate: str | None = None,
    endDate: str | None = None,
):
    return _call(service.compare_accounts, accountId, startDate, endDate)


@router.get("/accounts")
def list_accounts(
    status: str | None = None,
    market: str | None = None,
    strategy: str | None = None,
    keyword: str | None = None,
    hasActiveDeployment: bool | None = None,
    health: str | None = None,
    sort: str = "updated_at",
    direction: str = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(
        service.list_accounts,
        status=status,
        market=market,
        strategy=strategy,
        keyword=keyword,
        has_active_deployment=hasActiveDeployment,
        health=health,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )


@router.post("/accounts", status_code=201)
def create_account(request: AccountCreate):
    return _call(service.create_account, request.model_dump())


@router.get("/accounts/{account_id}")
def get_account(account_id: str):
    return _call(service.get_account, account_id)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: str):
    return _call(service.delete_account, account_id)


@router.patch("/accounts/{account_id}")
def update_account(account_id: str, request: AccountUpdate):
    return _call(service.update_account, account_id, request.model_dump(exclude_none=True))


@router.post("/accounts/{account_id}/activate")
def activate_account(account_id: str):
    return _call(service.transition_account, account_id, "activate")


@router.post("/accounts/{account_id}/pause")
def pause_account(account_id: str):
    return _call(service.transition_account, account_id, "pause")


@router.post("/accounts/{account_id}/resume")
def resume_account(account_id: str):
    return _call(service.transition_account, account_id, "resume")


@router.post("/accounts/{account_id}/archive")
def archive_account(account_id: str):
    return _call(service.transition_account, account_id, "archive")


@router.post("/accounts/{account_id}/clone", status_code=201)
def clone_account(account_id: str, request: AccountClone | None = None):
    return _call(
        service.clone_account,
        account_id,
        request.model_dump(exclude_none=True) if request else {},
    )


@router.get("/accounts/{account_id}/overview")
def account_overview(account_id: str):
    return _call(service.get_overview, account_id)


@router.get("/accounts/{account_id}/positions")
def account_positions(
    account_id: str,
    symbol: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(service.list_positions, account_id, symbol=symbol, limit=limit, offset=offset)


@router.get("/accounts/{account_id}/orders")
def account_orders(
    account_id: str,
    startDate: str | None = None,
    endDate: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    status: str | None = None,
    deploymentId: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(
        service.list_orders,
        account_id,
        start_date=startDate,
        end_date=endDate,
        symbol=symbol,
        side=side,
        status=status,
        deployment_id=deploymentId,
        limit=limit,
        offset=offset,
    )


@router.get("/accounts/{account_id}/trades")
def account_trades(
    account_id: str,
    startDate: str | None = None,
    endDate: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    deploymentId: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(
        service.list_trades,
        account_id,
        start_date=startDate,
        end_date=endDate,
        symbol=symbol,
        side=side,
        deployment_id=deploymentId,
        limit=limit,
        offset=offset,
    )


@router.get("/accounts/{account_id}/signals")
def account_signals(
    account_id: str,
    startDate: str | None = None,
    endDate: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
    deploymentId: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(
        service.list_signals,
        account_id,
        start_date=startDate,
        end_date=endDate,
        symbol=symbol,
        status=status,
        deployment_id=deploymentId,
        limit=limit,
        offset=offset,
    )


@router.get("/accounts/{account_id}/performance")
def account_performance(
    account_id: str,
    startDate: str | None = None,
    endDate: str | None = None,
):
    return _call(service.performance, account_id, startDate, endDate)


@router.get("/accounts/{account_id}/cycles")
def account_cycles(
    account_id: str,
    startDate: str | None = None,
    endDate: str | None = None,
    status: str | None = None,
    deploymentId: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(
        service.list_cycles,
        account_id,
        start_date=startDate,
        end_date=endDate,
        status=status,
        deployment_id=deploymentId,
        limit=limit,
        offset=offset,
    )


@router.get("/accounts/{account_id}/daily-reports")
def account_daily_reports(
    account_id: str,
    startDate: str | None = None,
    endDate: str | None = None,
    deploymentId: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(
        service.list_daily_reports,
        account_id,
        start_date=startDate,
        end_date=endDate,
        deployment_id=deploymentId,
        limit=limit,
        offset=offset,
    )


@router.get("/accounts/{account_id}/audit")
def account_audit(
    account_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(service.audit, account_id, limit, offset)


@router.get("/accounts/{account_id}/deployments")
def list_deployments(account_id: str):
    return _call(service.list_deployments, account_id)


@router.post("/accounts/{account_id}/deployments", status_code=201)
def create_deployment(account_id: str, request: DeploymentCreate):
    return _call(service.create_deployment, account_id, request.model_dump())


@router.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: str):
    return _call(service.get_deployment, deployment_id)


@router.patch("/deployments/{deployment_id}")
def update_deployment(deployment_id: str, request: DeploymentUpdate):
    return _call(service.update_deployment, deployment_id, request.model_dump(exclude_none=True))


@router.post("/deployments/{deployment_id}/activate")
def activate_deployment(deployment_id: str):
    return _call(service.transition_deployment, deployment_id, "activate")


@router.post("/deployments/{deployment_id}/pause")
def pause_deployment(deployment_id: str):
    return _call(service.transition_deployment, deployment_id, "pause")


@router.post("/deployments/{deployment_id}/resume")
def resume_deployment(deployment_id: str):
    return _call(service.transition_deployment, deployment_id, "resume")


@router.post("/deployments/{deployment_id}/run-now")
def run_now(deployment_id: str, request: RunNowRequest | None = None):
    return _call(service.run_now, deployment_id, request.tradingDate if request else None)


@router.get("/deployments/{deployment_id}/next-runs")
def next_runs(deployment_id: str, count: int = Query(default=5, ge=1, le=20)):
    return _call(service.next_runs, deployment_id, count)


@router.get("/signals")
def global_signals(
    accountId: str | None = None,
    deploymentId: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(
        service.global_signals,
        account_id=accountId,
        deployment_id=deploymentId,
        symbol=symbol,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/execution-cycles")
def global_cycles(
    accountId: str | None = None,
    deploymentId: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return _call(
        service.global_cycles,
        account_id=accountId,
        deployment_id=deploymentId,
        status=status,
        limit=limit,
        offset=offset,
    )
