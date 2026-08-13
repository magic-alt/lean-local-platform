from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from .common import dispatch_task, paged_items
from ..core.config import DEFAULT_DOCKER_IMAGE
from ..core.errors import NotFoundError
from ..lean_engine.errors import LeanPlatformError
from ..lean_engine.results import extract_chart_data, infer_holdings_from_orders
from ..domain.data_scope import DataScope
from ..repositories.backtest_repository import get_backtest
from ..services.backtest_service import (
    backtest_status,
    cancel_backtest,
    create_failed_backtest_job,
    create_backtest_job,
    count_query_backtests,
    enrich_strategy_backtest_request,
    fail_backtest_queue,
    mark_backtest_queued,
    query_backtests,
)
from ..services.backtest_preflight import prepare_backtest_request
from ..services.experiments import get_experiment_versions
from ..services.history_resources import delete_backtest
from ..services.result_service import result_for_job
from ..services.run_paths import run_directory, run_file
from ..services.screening_results import load_screening_result
from ..services.security_identity import (
    canonical_security_symbol,
    enrich_symbol_records,
    resolve_security_identities,
)
from ..services.projects import get_project
from ..services.strategy_admission import admission_for_run
from ..services.tasks import log_window, task_log_window
from ..services import data_gateway
from ..services import research_runs
from ..services.strategies import get_template
from ..services.workflow_lineage import record_edge
from ..services.reproducibility import certificate_for_run, golden_pairs
from ..tasks.worker import run_backtest_task

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    name: str | None = None
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    start: str
    end: str
    fast: int | None = Field(default=None, ge=1)
    slow: int | None = Field(default=None, ge=1)
    cash: float = Field(default=100000, gt=0)
    dockerImage: str = DEFAULT_DOCKER_IMAGE
    projectId: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    dataScope: DataScope | None = None
    sourceResearchRunId: str | None = None


def _shared_scope_payload(request: BacktestRequest) -> dict[str, Any]:
    payload = request.model_dump()
    payload["extra"] = request.model_extra or {}
    if request.sourceResearchRunId and request.dataScope is None:
        raise ValueError("sourceResearchRunId requires the research dataScope.")
    if request.dataScope is None:
        return payload
    resolved = data_gateway.resolve(request.dataScope)
    if request.sourceResearchRunId:
        source = research_runs.get_run(request.sourceResearchRunId)
        if source["status"] != "success":
            raise ValueError("Only a successful research run can seed a backtest.")
        source_scope_hash = data_gateway.scope_hash(source["scope"])
        if source_scope_hash != resolved["scopeHash"]:
            raise ValueError("The submitted dataScope does not match the source research run.")
        source_fingerprint = source.get("data_fingerprint")
        if source_fingerprint and source_fingerprint != resolved["dataFingerprint"]:
            raise ValueError("Research data has changed since the source run; rerun research before backtesting.")
    scope = resolved["scope"]
    asset = scope["asset"]
    time = scope["time"]
    values = scope["selection"]["values"]
    if values:
        payload["symbol"] = values[0]
    payload.update(
        {
            "assetClass": asset["assetClass"],
            "market": asset["market"],
            "venue": asset["venue"],
            "resolution": asset["resolution"],
            "dataType": asset["dataType"],
            "start": time.get("startDate") or payload["start"],
            "end": time.get("endDate") or payload["end"],
        }
    )
    payload["parameters"] = {
        **payload.get("parameters", {}),
        "source": resolved["source"],
        "adjust": scope["price"]["adjust"],
        "allowResearchSource": scope["provider"]["allowResearchSource"],
        "dataScope": scope,
        "scopeHash": resolved["scopeHash"],
        "dataFingerprint": resolved["dataFingerprint"],
        "sourceResearchRunId": request.sourceResearchRunId,
    }
    return payload


def _with_artifacts(run: dict[str, Any]) -> dict[str, Any]:
    run["job_id"] = run["id"]
    path = run_directory(run["id"], run.get("results_dir"), relative="results")
    run["artifacts"] = sorted(child.name for child in path.iterdir() if child.is_file()) if path.exists() else []
    return run


@router.get("")
def backtests(
    name: str | None = None,
    status: str | None = None,
    projectId: str | None = None,
    symbol: str | None = None,
    market: str | None = None,
    fromDate: str | None = None,
    toDate: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    paged: bool = True,
):
    filters = {
            "name": name,
            "status": status,
            "project_id": projectId,
            "symbol": symbol,
            "market": market,
            "from_date": fromDate,
            "to_date": toDate,
    }
    if not paged:
        return query_backtests({**filters, "limit": limit, "offset": offset})
    return {
        "items": query_backtests({**filters, "limit": limit, "offset": offset}),
        "count": count_query_backtests(filters),
        "limit": limit,
        "offset": offset,
    }


@router.post("")
def create_backtest(request: BacktestRequest):
    get_project(request.projectId)
    try:
        payload = _shared_scope_payload(request)
        run = create_backtest_job(payload)
    except LeanPlatformError as exc:
        payload = request.model_dump()
        run = create_failed_backtest_job(payload, str(exc))
        return detail(run["id"])
    if request.sourceResearchRunId:
        record_edge(
            parent_type="research_run",
            parent_id=request.sourceResearchRunId,
            child_type="backtest_run",
            child_id=run["id"],
            relation="validated_by",
            contract=request.dataScope.model_dump(mode="json") if request.dataScope else None,
            details={
                "scopeHash": (payload.get("parameters") or {}).get("scopeHash"),
                "dataFingerprint": (payload.get("parameters") or {}).get("dataFingerprint"),
            },
        )

    try:
        dispatch_task(run_backtest_task.s(run["task_id"], run["id"]), run["task_id"])
        mark_backtest_queued(run["id"])
    except HTTPException as exc:
        fail_backtest_queue(run["id"], str(exc.detail))
        raise
    return detail(run["id"])


@router.post("/preflight")
def preflight_backtest(request: BacktestRequest):
    try:
        get_project(request.projectId)
        payload = _shared_scope_payload(request)
        payload = enrich_strategy_backtest_request(payload)
        return prepare_backtest_request(payload, repair=True)["preflight"]
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "stage": "preflight",
                "code": str(exc).split(":", 1)[0].lower().replace(" ", "_"),
                "message": str(exc),
                "retryable": True,
            },
        ) from exc


@router.get("/{run_id}/optimization-draft")
def optimization_draft(run_id: str):
    run = get_backtest(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    if run.get("status") != "success":
        raise HTTPException(status_code=409, detail="Only a successful backtest can seed an optimization.")
    parameters = run.get("parameters") or {}
    scope = parameters.get("dataScope") or {
        "asset": {
            "assetClass": parameters.get("assetClass") or run.get("asset_class") or "equity",
            "market": parameters.get("market") or run.get("venue") or "usa",
            "venue": parameters.get("venue") or run.get("venue"),
            "resolution": parameters.get("resolution") or run.get("resolution") or "daily",
            "dataType": parameters.get("dataType") or run.get("data_type") or "trade",
        },
        "selection": {"type": "symbols", "values": [run.get("symbol")]},
        "time": {"startDate": parameters.get("start"), "endDate": parameters.get("end")},
        "price": {"adjust": parameters.get("adjust") or "raw"},
        "provider": {
            "source": parameters.get("source") or "tushare",
            "mode": "strict",
            "allowResearchSource": bool(parameters.get("allowResearchSource")),
        },
    }
    project = get_project(str(run["project_id"]))
    template_key = str((project.get("config") or {}).get("templateKey") or "")
    try:
        schema = get_template(template_key).get("parameters") or []
    except ValueError:
        schema = []
    fixed = {
        str(field["key"]): parameters.get(field["key"], field.get("default"))
        for field in schema
        if field.get("key")
    }
    return {
        "sourceBacktestRunId": run_id,
        "name": f"{run.get('name') or run.get('symbol')} · optimization",
        "projectIds": [run["project_id"]],
        "dataScope": scope,
        "execution": {
            "cash": parameters.get("cash") or parameters.get("initialCash") or 100000,
            "benchmarkSymbol": parameters.get("benchmarkSymbol"),
            "feeModel": parameters.get("feeModel"),
            "slippageModel": parameters.get("slippageModel"),
            "dockerImage": run.get("docker_image") or DEFAULT_DOCKER_IMAGE,
        },
        "fixedParametersByProject": {run["project_id"]: fixed},
        "parameterSchemas": {run["project_id"]: schema},
        "objective": "sharpe",
        "scopeHash": parameters.get("scopeHash") or data_gateway.scope_hash(scope),
        "dataFingerprint": parameters.get("dataFingerprint"),
    }


@router.get("/{run_id}")
def detail(run_id: str):
    run = get_backtest(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return _with_artifacts(run)


@router.get("/{run_id}/reproducibility-certificate")
def reproducibility_certificate(run_id: str):
    item = certificate_for_run(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Reproducibility certificate not found.")
    return item


@router.get("/reproducibility/golden-pairs")
def reproducibility_golden_pairs(limit: int = 100):
    return golden_pairs(limit)


@router.delete("/{run_id}")
def delete(run_id: str):
    try:
        return delete_backtest(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{run_id}/status")
def status(run_id: str):
    try:
        return backtest_status(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found.") from exc


@router.get("/{run_id}/result")
def result(run_id: str):
    run = detail(run_id)
    result_record = result_for_job(run_id)
    if not result_record:
        raise HTTPException(status_code=404, detail="Backtest result not found.")
    orders = result_record.get("orders")
    if not result_record.get("holdings"):
        fallback_orders = orders if isinstance(orders, list) else []
        price_series: list[dict[str, Any]] = []
        if not isinstance(fallback_orders, list) or not fallback_orders:
            result_path = run.get("result_json_path")
            if result_path:
                try:
                    resolved_result_path = run_file(
                        run_id,
                        result_path,
                        f"results/{run_id}.json",
                    )
                    chart_data = extract_chart_data(
                        resolved_result_path,
                        symbol=run.get("symbol"),
                        benchmark_symbol=(run.get("parameters") or {}).get("benchmarkSymbol"),
                        market=(run.get("parameters") or {}).get("market"),
                        benchmark_market=(run.get("parameters") or {}).get("benchmarkMarket"),
                        start=(run.get("parameters") or {}).get("start"),
                        end=(run.get("parameters") or {}).get("end"),
                        asset_class=(run.get("parameters") or {}).get("assetClass"),
                        venue=(run.get("parameters") or {}).get("venue"),
                        resolution=(run.get("parameters") or {}).get("resolution"),
                        data_type=(run.get("parameters") or {}).get("dataType"),
                    )
                    fallback_orders = chart_data.get("orders") or []
                    series = chart_data.get("series") or {}
                    price_series = series.get("price") or []
                except Exception:
                    fallback_orders = []
        try:
            if fallback_orders:
                result_record["holdings"] = infer_holdings_from_orders(fallback_orders, price_series)
            elif not result_record.get("holdings"):
                result_record["holdings"] = []
        except Exception:
            result_record["holdings"] = []
    if not result_record.get("holdings"):
        result_record["holdings"] = []
    parameters = run.get("parameters") or {}
    market = parameters.get("market") or run.get("venue")
    asset_class = str(parameters.get("assetClass") or run.get("asset_class") or "equity")
    result_orders = result_record.get("orders")
    order_symbols = {
        canonical_security_symbol(row.get("symbol"), market)
        for row in result_orders or []
        if isinstance(row, dict) and row.get("symbol")
    } if isinstance(result_orders, list) else set()
    if len(order_symbols) > 1 and run.get("result_json_path"):
        try:
            corrected_chart = extract_chart_data(
                run_file(
                    run_id,
                    run.get("result_json_path"),
                    f"results/{run_id}.json",
                ),
                symbol=run.get("symbol"),
                benchmark_symbol=parameters.get("benchmarkSymbol"),
                market=market,
                benchmark_market=parameters.get("benchmarkMarket"),
                start=parameters.get("start"),
                end=parameters.get("end"),
                asset_class=parameters.get("assetClass"),
                venue=parameters.get("venue"),
                resolution=parameters.get("resolution"),
                data_type=parameters.get("dataType"),
            )
            result_record["holdings"] = corrected_chart.get("holdings") or []
        except Exception:
            pass
    for key in ("orders", "trades", "holdings"):
        rows = result_record.get(key)
        if isinstance(rows, list):
            result_record[key] = enrich_symbol_records(
                [row for row in rows if isinstance(row, dict)],
                market=market,
                asset_class=asset_class,
            )
    return {"job": run, "result": result_record}


@router.get("/{run_id}/results", include_in_schema=False)
def results(run_id: str):
    return RedirectResponse(
        url=f"/api/backtests/{run_id}/result",
        status_code=308,
        headers={"Deprecation": "true", "Sunset": "Sun, 26 Jan 2027 00:00:00 GMT"},
    )


@router.get("/{run_id}/validation")
def validation(run_id: str):
    run = detail(run_id)
    return {
        "job_id": run["id"],
        "validation": run.get("validation"),
        "experiment": run.get("experiment"),
        "fingerprint": run.get("fingerprint"),
    }


@router.get("/{run_id}/admission")
def admission(run_id: str, profile: str = "institutional"):
    try:
        return admission_for_run(run_id, profile)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{run_id}/versions")
def versions(run_id: str):
    run = detail(run_id)
    version_record = get_experiment_versions(run_id)
    if version_record is None:
        raise HTTPException(status_code=404, detail="Experiment versions not found.")
    return {"job_id": run["id"], **version_record}


@router.post("/{run_id}/cancel")
def cancel(run_id: str):
    try:
        return _with_artifacts(cancel_backtest(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found.") from exc


@router.get("/{run_id}/logs")
def logs(run_id: str, offset: int | None = None, cursor: str | None = None, limit: int = 65536):
    run = detail(run_id)
    try:
        if run.get("task_id"):
            return task_log_window(run["task_id"], offset=offset, cursor=cursor, limit=limit)
        return log_window(
            Path(run.get("log_path") or ""),
            offset=offset,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "field": "cursor"}) from exc


@router.get("/{run_id}/chart-data")
def chart_data(run_id: str, symbol: str | None = None):
    run = detail(run_id)
    result_path = run_file(
        run_id,
        run.get("result_json_path"),
        f"results/{run_id}.json",
    )
    if not result_path.is_file():
        raise HTTPException(status_code=404, detail="Result JSON not found.")
    parameters = run.get("parameters") or {}
    market = parameters.get("market") or run.get("venue")
    raw_available_symbols = parameters.get("universeSymbols")
    available_values = raw_available_symbols if isinstance(raw_available_symbols, list) else []
    available_symbols = [
        canonical_security_symbol(value, market)
        for value in available_values
        if str(value).strip()
    ]
    requested_symbol = canonical_security_symbol(symbol, market) if symbol else None
    try:
        payload = extract_chart_data(
            result_path,
            symbol=canonical_security_symbol(run.get("symbol"), market),
            benchmark_symbol=parameters.get("benchmarkSymbol"),
            market=market,
            benchmark_market=parameters.get("benchmarkMarket"),
            start=parameters.get("start"),
            end=parameters.get("end"),
            asset_class=parameters.get("assetClass"),
            venue=parameters.get("venue"),
            resolution=parameters.get("resolution"),
            data_type=parameters.get("dataType"),
            selected_symbol=requested_symbol,
            available_symbols=available_symbols,
            filter_orders=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    metadata = payload.get("metadata") or {}
    discovered = [
        canonical_security_symbol(value, market)
        for value in metadata.get("availableSymbols") or []
    ]
    identities = resolve_security_identities(
        discovered,
        market=market,
        asset_class=str(parameters.get("assetClass") or "equity"),
    )
    order_counts = metadata.get("orderCounts") or {}
    assets = [
        {
            **(identities.get(asset_symbol) or {
                "symbol": asset_symbol,
                "name": None,
                "market": market,
                "exchange": None,
                "display": asset_symbol,
            }),
            "orderCount": int(order_counts.get(asset_symbol) or 0),
        }
        for asset_symbol in discovered
    ]
    selected = canonical_security_symbol(metadata.get("selectedSymbol"), market)
    payload["metadata"] = {
        **metadata,
        "availableAssets": assets,
        "selectedAsset": identities.get(selected) or {
            "symbol": selected,
            "name": None,
            "market": market,
            "exchange": None,
            "display": selected,
        },
    }
    payload["orders"] = enrich_symbol_records(
        payload.get("orders") or [],
        market=market,
        asset_class=str(parameters.get("assetClass") or "equity"),
    )
    payload["orderMarkers"] = enrich_symbol_records(
        payload.get("orderMarkers") or [],
        market=market,
        asset_class=str(parameters.get("assetClass") or "equity"),
    )
    return payload


@router.get("/{run_id}/screening")
def screening(run_id: str):
    run = detail(run_id)
    parameters = run.get("parameters") or {}
    template_key = str(parameters.get("strategyTemplateKey") or "")
    if template_key != "ashare_index_screening":
        raise HTTPException(status_code=404, detail="Screening result is not available for this run.")
    results_dir = run_directory(run_id, run.get("results_dir"), relative="results")
    path = results_dir / "screening-report.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Screening result JSON not found.")
    try:
        return load_screening_result(
            path,
            market=str(parameters.get("market") or "china"),
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{run_id}/artifacts/{name}")
def artifact(run_id: str, name: str):
    run = detail(run_id)
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid artifact name.")
    results_dir = run_directory(run_id, run.get("results_dir"), relative="results")
    path = results_dir / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(path)
