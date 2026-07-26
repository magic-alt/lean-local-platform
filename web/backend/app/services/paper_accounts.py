from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..repositories.backtest_repository import get_backtest
from ..repositories.market_data_repository import (
    MarketDataUnavailable,
    benchmark_return as market_benchmark_return,
    close_price,
)
from . import paper as legacy_paper
from .alerts import delivery_succeeded, emit_alert, external_alert_channel_configured
from .experiments import get_experiment_versions
from .run_paths import run_directory


ACCOUNT_STATES = {"draft", "active", "paused", "error", "archived"}
DEPLOYMENT_STATES = {"active", "paused", "disabled", "error"}
CYCLE_STATES = {
    "scheduled",
    "waiting_data",
    "queued",
    "running",
    "finalizing",
    "succeeded",
    "skipped",
    "failed",
}
TERMINAL_CYCLE_STATES = {"succeeded", "skipped", "failed"}
MONEY_FIELDS = {
    "initial_cash",
    "cash",
    "available_cash",
    "frozen_cash",
    "market_value",
    "total_equity",
    "realized_pnl",
    "unrealized_pnl",
    "daily_pnl",
    "opening_cash",
    "quantity",
    "sellable_quantity",
    "frozen_quantity",
    "average_cost",
    "certified_price",
    "commission",
    "stamp_duty",
    "transfer_fee",
    "precise_slippage",
    "precise_quantity",
    "precise_price",
    "precise_amount",
}
RATE_FIELDS = {
    "cumulative_return",
    "benchmark_return",
    "excess_return",
    "gross_exposure",
    "net_exposure",
    "turnover",
    "account_weight",
    "max_position_weight",
    "max_daily_turnover",
    "target_weight",
    "previous_weight",
    "confidence",
}

PAPER_ACCOUNT_DATA_TRUST = {
    "valuationTrusted": False,
    "reason": "historical_recertification_pending",
}


class CanonicalStateDivergence(RuntimeError):
    """Raised when an immutable ledger checkpoint no longer reproduces."""


def _data_trust() -> dict[str, Any]:
    """Return a fresh response payload so callers cannot mutate shared state."""
    return dict(PAPER_ACCOUNT_DATA_TRUST)


def _decimal(value: Any, *, positive: bool = False, default: str = "0") -> Decimal:
    try:
        result = Decimal(str(default if value is None or value == "" else value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid decimal value: {value}") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError("Amount must be a positive finite decimal.")
    return result.quantize(Decimal("0.00000001"))


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _public(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    result: dict[str, Any] = {}
    for key, value in item.items():
        if isinstance(value, Decimal) or key in MONEY_FIELDS or key in RATE_FIELDS:
            if value is None:
                result[key] = None
            else:
                precision = Decimal("0.000000000001") if key in RATE_FIELDS else Decimal("0.00000001")
                result[key] = format(Decimal(str(value)).quantize(precision), "f")
        elif key in {"metadata", "config", "parameters", "universe_config", "checkpoint", "projection", "report", "payload", "evidence"}:
            result[key] = value or {}
        else:
            result[key] = value
    return result


def _public_many(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_public(item) or {} for item in items]


def _bounded_page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 200)), max(0, int(offset))


def _paged(items: list[dict[str, Any]], *, total: int, limit: int, offset: int) -> dict[str, Any]:
    return {"items": _public_many(items), "count": int(total), "limit": limit, "offset": offset}


def _market(value: Any) -> str:
    normalized = str(value or "china").strip().lower()
    if normalized not in {"china"}:
        raise ValueError("Paper Accounts v1 supports certified China A-share daily data only.")
    return normalized


def _account_row(connection: Any, account_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        select account.*,projection.cash,projection.available_cash,projection.frozen_cash,
               projection.market_value,projection.total_equity,projection.realized_pnl,
               projection.unrealized_pnl,projection.daily_pnl,projection.cumulative_return,
               projection.benchmark_return,projection.excess_return,projection.position_count,
               projection.gross_exposure,projection.net_exposure,projection.turnover,
               projection.last_valuation_at,projection.quote_data_timestamp,
               projection.source_ledger_sequence,projection.source_checkpoint_digest,
               projection.health_status
        from paper_accounts account
        left join paper_account_projections projection on projection.paper_account_id=account.id
        where account.id=?
        """,
        (account_id,),
    ).fetchone()
    item = row_to_dict(row)
    if not item:
        raise KeyError("Paper account not found.")
    return item


def create_account(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Account name is required.")
    market = _market(payload.get("marketScope") or payload.get("market"))
    currency = str(payload.get("baseCurrency") or "CNY").upper()
    if currency != "CNY":
        raise ValueError("China A-share Paper Accounts require CNY base currency.")
    initial_cash = _decimal(payload.get("initialCash"), positive=True)
    benchmark = str(payload.get("benchmarkSymbol") or "000300").strip().upper()
    account_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    risk_id = str(uuid.uuid4())
    ledger_id = str(uuid.uuid4())
    checkpoint_id = str(uuid.uuid4())
    now = utc_now()
    risk = dict(payload.get("riskConfig") or {})
    risk_fingerprint = _digest({"accountId": account_id, "version": 1, "risk": risk})
    opening_digest = _digest(
        {
            "paperAccountId": account_id,
            "generation": 1,
            "currency": currency,
            "openingCash": format(initial_cash, "f"),
            "ledgerEntryId": ledger_id,
        }
    )
    with db() as connection:
        connection.execute(
            """
            insert into paper_sessions
                (id,project_id,name,status,symbol,asset_class,venue,resolution,cash,equity,
                 parameters_json,created_at,updated_at,mode,legacy_read_only,auto_advance,
                 pipeline_version)
            values (?,null,?,'created',?,'equity',?,'daily',0,0,?,?,?,
                    'lean_walkforward_v2',0,0,2)
            """,
            (
                session_id,
                f"[account] {name}",
                benchmark,
                market,
                json_dump({"paperAccountId": account_id, "accountGeneration": 1}),
                now,
                now,
            ),
        )
        connection.execute(
            """
            insert into paper_accounts
                (id,shadow_session_id,name,description,status,market_scope,base_currency,
                 initial_cash,benchmark_symbol,execution_mode,current_generation,
                 active_risk_profile_id,version,metadata_json,created_at,updated_at)
            values (?,?,?,?,?,?,?,?,?,'paper_execute',1,?,1,?,?,?)
            """,
            (
                account_id,
                session_id,
                name,
                str(payload.get("description") or "").strip() or None,
                "draft",
                market,
                currency,
                initial_cash,
                benchmark,
                risk_id,
                json_dump(payload.get("metadata") or {}),
                now,
                now,
            ),
        )
        connection.execute(
            """
            insert into paper_ledger_entries
                (id,session_id,intent_id,fill_id,entry_type,asset,symbol,quantity,
                 amount,currency,idempotency_key,created_at,paper_account_id,
                 account_generation,ledger_sequence,precise_quantity,precise_amount)
            values (?,?,?,null,'CASH_DEPOSIT','cash',null,0,?,?,?,?,
                    ?,1,1,0,?)
            """,
            (
                ledger_id,
                session_id,
                f"opening:{account_id}:1",
                initial_cash,
                currency,
                f"account:{account_id}:generation:1:opening:cash",
                now,
                account_id,
                initial_cash,
            ),
        )
        connection.execute(
            """
            insert into paper_account_generations
                (id,paper_account_id,generation,opening_cash,opening_ledger_entry_id,
                 opening_checkpoint_digest,reason,created_at)
            values (?,?,1,?,?,?,'account_created',?)
            """,
            (generation_id, account_id, initial_cash, ledger_id, opening_digest, now),
        )
        connection.execute(
            """
            insert into paper_risk_profiles
                (id,paper_account_id,version,status,max_positions,max_position_weight,
                 cash_floor,max_order_amount,max_daily_turnover,config_json,
                 config_fingerprint,created_at)
            values (?,?,1,'active',?,?,?,?,?,?,?,?)
            """,
            (
                risk_id,
                account_id,
                risk.get("maxPositions"),
                _decimal(risk.get("maxPositionWeight")) if risk.get("maxPositionWeight") is not None else None,
                _decimal(risk.get("cashFloor")) if risk.get("cashFloor") is not None else Decimal("0"),
                _decimal(risk.get("maxOrderAmount")) if risk.get("maxOrderAmount") is not None else None,
                _decimal(risk.get("maxDailyTurnover")) if risk.get("maxDailyTurnover") is not None else None,
                json_dump(risk),
                risk_fingerprint,
                now,
            ),
        )
        checkpoint_payload = {
            "paperAccountId": account_id,
            "generation": 1,
            "cash": format(initial_cash, "f"),
            "positions": [],
            "sourceLedgerSequence": 1,
        }
        checkpoint_digest = _digest(checkpoint_payload)
        connection.execute(
            """
            insert into paper_account_checkpoints
                (id,paper_account_id,generation,cycle_id,source_ledger_sequence,digest,
                 checkpoint_json,created_at)
            values (?,?,1,null,1,?,?,?)
            """,
            (checkpoint_id, account_id, checkpoint_digest, json_dump(checkpoint_payload), now),
        )
        connection.execute(
            """
            insert into paper_account_projections
                (paper_account_id,generation,cash,available_cash,frozen_cash,market_value,
                 total_equity,realized_pnl,unrealized_pnl,daily_pnl,cumulative_return,
                 benchmark_return,excess_return,position_count,gross_exposure,net_exposure,
                 turnover,last_valuation_at,quote_data_timestamp,source_ledger_sequence,
                 source_checkpoint_digest,health_status,updated_at)
            values (?,1,?,?,0,0,?,0,0,0,0,0,0,0,0,0,0,?,null,1,?,'healthy',?)
            """,
            (account_id, initial_cash, initial_cash, initial_cash, now, checkpoint_digest, now),
        )
    return get_account(account_id)


def get_account(account_id: str) -> dict[str, Any]:
    with db() as connection:
        item = _account_row(connection, account_id)
    return _public(item) or {}


def list_accounts(
    *,
    status: str | None = None,
    market: str | None = None,
    strategy: str | None = None,
    keyword: str | None = None,
    has_active_deployment: bool | None = None,
    health: str | None = None,
    sort: str = "updated_at",
    direction: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit, offset = _bounded_page(limit, offset)
    clauses = ["1=1"]
    params: list[Any] = []
    if status:
        clauses.append("account.status=?")
        params.append(status)
    if market:
        clauses.append("account.market_scope=?")
        params.append(market)
    if keyword:
        clauses.append("(account.name like ? or account.description like ?)")
        pattern = f"%{keyword.strip()}%"
        params.extend((pattern, pattern))
    if strategy:
        clauses.append(
            "exists(select 1 from paper_strategy_deployments d where d.paper_account_id=account.id and d.name like ?)"
        )
        params.append(f"%{strategy.strip()}%")
    if has_active_deployment is not None:
        predicate = "exists" if has_active_deployment else "not exists"
        clauses.append(
            f"{predicate}(select 1 from paper_strategy_deployments d where d.paper_account_id=account.id and d.status='active')"
        )
    if health:
        clauses.append("projection.health_status=?")
        params.append(health)
    sort_columns = {
        "name": "account.name",
        "status": "account.status",
        "created_at": "account.created_at",
        "updated_at": "account.updated_at",
        "total_equity": "projection.total_equity",
        "cumulative_return": "projection.cumulative_return",
    }
    order_column = sort_columns.get(sort, "account.updated_at")
    order_direction = "asc" if direction.lower() == "asc" else "desc"
    where = " and ".join(clauses)
    with db() as connection:
        total_row = connection.execute(
            f"""
            select count(*) as count from paper_accounts account
            left join paper_account_projections projection on projection.paper_account_id=account.id
            where {where}
            """,
            tuple(params),
        ).fetchone()
        rows = connection.execute(
            f"""
            select account.*,projection.cash,projection.available_cash,projection.market_value,
                   projection.total_equity,projection.daily_pnl,projection.cumulative_return,
                   projection.benchmark_return,projection.excess_return,projection.position_count,
                   projection.health_status,projection.last_valuation_at,
                   (select d.name from paper_strategy_deployments d
                    where d.paper_account_id=account.id and d.is_primary=1
                    order by d.version desc limit 1) as primary_strategy,
                   (select d.last_successful_trading_date from paper_strategy_deployments d
                    where d.paper_account_id=account.id and d.is_primary=1
                    order by d.version desc limit 1) as last_successful_trading_date,
                   (select d.next_scheduled_at from paper_strategy_deployments d
                    where d.paper_account_id=account.id and d.is_primary=1
                    order by d.version desc limit 1) as next_scheduled_at,
                   (select count(*) from paper_strategy_signals paper_signal
                    where paper_signal.paper_account_id=account.id and paper_signal.disposition='next_session_pending') as pending_signal_count,
                   (select count(*) from paper_order_intents intent
                    join paper_order_transitions transition on transition.intent_id=intent.id
                    where intent.paper_account_id=account.id and transition.to_state='ACCEPTED'
                      and not exists(select 1 from paper_order_transitions terminal
                                     where terminal.intent_id=intent.id and terminal.to_state in ('FILLED','REJECTED','CANCELLED','EXPIRED','FAILED'))) as pending_order_count
            from paper_accounts account
            left join paper_account_projections projection on projection.paper_account_id=account.id
            where {where}
            order by {order_column} {order_direction}
            limit ? offset ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
    result = _paged(rows_to_dicts(rows), total=int(total_row["count"] or 0), limit=limit, offset=offset)
    result["dataTrust"] = _data_trust()
    return result


def update_account(account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"name", "description", "benchmarkSymbol", "metadata"}
    unexpected = set(payload) - allowed
    if unexpected:
        raise ValueError(f"Immutable or unsupported account fields: {', '.join(sorted(unexpected))}")
    account = get_account(account_id)
    if account["status"] == "archived":
        raise ValueError("Archived accounts are immutable.")
    assignments: list[str] = []
    params: list[Any] = []
    mapping = {
        "name": ("name", lambda value: str(value).strip()),
        "description": ("description", lambda value: str(value).strip() or None),
        "benchmarkSymbol": ("benchmark_symbol", lambda value: str(value).strip().upper()),
        "metadata": ("metadata_json", json_dump),
    }
    for key, value in payload.items():
        column, convert = mapping[key]
        converted = convert(value)
        if key in {"name", "benchmarkSymbol"} and not converted:
            raise ValueError(f"{key} cannot be empty.")
        assignments.append(f"{column}=?")
        params.append(converted)
    if assignments:
        params.extend((utc_now(), account_id))
        with db() as connection:
            connection.execute(
                f"update paper_accounts set {','.join(assignments)},version=version+1,updated_at=? where id=?",
                tuple(params),
            )
    return get_account(account_id)


def delete_account(account_id: str) -> dict[str, Any]:
    """Delete a stopped Paper account and all of its account-owned records."""
    with db() as connection:
        account = _account_row(connection, account_id)
        if account["status"] == "active":
            raise ValueError("Active Paper accounts must be paused or archived before deletion.")

        active_cycle = connection.execute(
            """
            select id from paper_execution_cycles
            where paper_account_id=?
              and status in ('scheduled','waiting_data','queued','running','finalizing')
            limit 1
            """,
            (account_id,),
        ).fetchone()
        if active_cycle:
            raise ValueError("This Paper account still has an active execution cycle.")

        session_id = str(account["shadow_session_id"])
        deployment_rows = connection.execute(
            "select id from paper_strategy_deployments where paper_account_id=?",
            (account_id,),
        ).fetchall()
        cycle_rows = connection.execute(
            "select id,paper_run_id from paper_execution_cycles where paper_account_id=?",
            (account_id,),
        ).fetchall()
        related_ids = [
            account_id,
            session_id,
            *[str(item["id"]) for item in deployment_rows],
            *[str(item["id"]) for item in cycle_rows],
            *[str(item["paper_run_id"]) for item in cycle_rows if item["paper_run_id"]],
        ]
        placeholders = ",".join("?" for _ in related_ids)
        active_task = connection.execute(
            f"""
            select id from tasks
            where (id in ({placeholders}) or related_id in ({placeholders}))
              and status in ('created','queued','running')
            limit 1
            """,
            tuple(related_ids + related_ids),
        ).fetchone()
        if active_task:
            raise ValueError("This Paper account still has an active task.")

        connection.execute(
            """
            delete from paper_daily_job_events
            where job_id in (select id from paper_daily_jobs where session_id=?)
            """,
            (session_id,),
        )
        connection.execute("delete from paper_daily_jobs where session_id=?", (session_id,))
        connection.execute(
            """
            delete from paper_run_checkpoints
            where paper_run_id in (select id from paper_walkforward_runs where session_id=?)
            """,
            (session_id,),
        )
        connection.execute(
            """
            delete from paper_constraint_decisions
            where intent_id in (
                select id from paper_order_intents
                where paper_account_id=? or session_id=?
            )
            """,
            (account_id, session_id),
        )
        connection.execute(
            """
            delete from paper_order_fills
            where paper_account_id=? or intent_id in (
                select id from paper_order_intents
                where paper_account_id=? or session_id=?
            )
            """,
            (account_id, account_id, session_id),
        )
        connection.execute(
            """
            delete from paper_order_transitions
            where intent_id in (
                select id from paper_order_intents
                where paper_account_id=? or session_id=?
            )
            """,
            (account_id, session_id),
        )
        connection.execute(
            "delete from paper_ledger_entries where paper_account_id=? or session_id=?",
            (account_id, session_id),
        )
        connection.execute(
            "delete from paper_order_intents where paper_account_id=? or session_id=?",
            (account_id, session_id),
        )
        connection.execute("delete from paper_reconciliation_records where session_id=?", (session_id,))

        connection.execute(
            """
            delete from paper_execution_cycle_events
            where cycle_id in (select id from paper_execution_cycles where paper_account_id=?)
            """,
            (account_id,),
        )
        for table in (
            "paper_notification_outbox",
            "paper_account_daily_reports",
            "paper_strategy_signals",
            "paper_account_checkpoints",
            "paper_account_daily_snapshots",
            "paper_account_position_projections",
            "paper_account_projections",
        ):
            connection.execute(f"delete from {table} where paper_account_id=?", (account_id,))
        connection.execute("delete from paper_execution_cycles where paper_account_id=?", (account_id,))
        connection.execute("delete from paper_strategy_deployments where paper_account_id=?", (account_id,))
        connection.execute("delete from paper_risk_profiles where paper_account_id=?", (account_id,))
        connection.execute("delete from paper_account_generations where paper_account_id=?", (account_id,))

        for table in (
            "paper_lean_order_events",
            "paper_walkforward_runs",
            "paper_daily_reports",
            "paper_portfolio_snapshots",
            "paper_positions",
            "paper_orders",
            "paper_signals",
        ):
            connection.execute(f"delete from {table} where session_id=?", (session_id,))
        connection.execute(
            f"delete from tasks where id in ({placeholders}) or related_id in ({placeholders})",
            tuple(related_ids + related_ids),
        )
        connection.execute("delete from paper_accounts where id=?", (account_id,))
        connection.execute("delete from paper_sessions where id=?", (session_id,))
    return {"deleted": True, "id": account_id}


def transition_account(account_id: str, action: str) -> dict[str, Any]:
    transitions = {
        "activate": ({"draft", "paused", "error"}, "active"),
        "pause": ({"active", "error"}, "paused"),
        "resume": ({"paused"}, "active"),
        "archive": ({"paused", "draft", "error"}, "archived"),
    }
    if action not in transitions:
        raise ValueError("Unsupported account action.")
    allowed, target = transitions[action]
    account = get_account(account_id)
    if account["status"] == target:
        return account
    if account["status"] not in allowed:
        if account["status"] == "archived":
            raise ValueError("Archived accounts cannot be resumed or mutated.")
        raise ValueError(f"Cannot {action} account from {account['status']}.")
    if action in {"activate", "resume"}:
        with db() as connection:
            active = connection.execute(
                "select count(*) as count from paper_strategy_deployments where paper_account_id=? and status='active'",
                (account_id,),
            ).fetchone()
        if not active or int(active["count"] or 0) == 0:
            raise ValueError("Activate at least one frozen strategy deployment first.")
    now = utc_now()
    timestamp_column = {"activate": "activated_at", "pause": "paused_at", "resume": "activated_at", "archive": "archived_at"}[action]
    with db() as connection:
        connection.execute(
            f"""
            update paper_accounts set status=?,version=version+1,updated_at=?,{timestamp_column}=?
            where id=?
            """,
            (target, now, now, account_id),
        )
        if target in {"paused", "archived"}:
            connection.execute(
                "update paper_sessions set status='paused',auto_advance=0,updated_at=? where id=?",
                (now, account["shadow_session_id"]),
            )
        elif target == "active":
            connection.execute(
                "update paper_sessions set status='running',auto_advance=0,updated_at=? where id=?",
                (now, account["shadow_session_id"]),
            )
    return get_account(account_id)


def pause_accounts_for_data_trust() -> dict[str, Any]:
    """Pause runnable Paper accounts while their valuation is untrusted.

    Archived accounts remain archived. Draft accounts are included so they
    cannot be activated without an explicit recovery decision.
    """
    now = utc_now()
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select id,shadow_session_id from paper_accounts
                where status in ('draft','active','error')
                """
            ).fetchall()
        )
        account_ids = [str(row["id"]) for row in rows]
        session_ids = [str(row["shadow_session_id"]) for row in rows if row.get("shadow_session_id")]
        if account_ids:
            placeholders = ",".join("?" for _ in account_ids)
            connection.execute(
                f"""
                update paper_accounts
                set status='paused',version=version+1,updated_at=?,paused_at=?
                where id in ({placeholders})
                """,
                tuple([now, now] + account_ids),
            )
        if session_ids:
            placeholders = ",".join("?" for _ in session_ids)
            connection.execute(
                f"""
                update paper_sessions set status='paused',auto_advance=0,updated_at=?
                where id in ({placeholders})
                """,
                tuple([now] + session_ids),
            )
    return {
        "pausedAccountIds": account_ids,
        "pausedCount": len(account_ids),
        "dataTrust": _data_trust(),
    }


def clone_account(account_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    source = get_account(account_id)
    with db() as connection:
        risk = row_to_dict(
            connection.execute(
                "select * from paper_risk_profiles where id=?",
                (source["active_risk_profile_id"],),
            ).fetchone()
        ) or {}
        deployments = rows_to_dicts(
            connection.execute(
                """
                select * from paper_strategy_deployments
                where paper_account_id=? and status!='disabled'
                order by version
                """,
                (account_id,),
            ).fetchall()
        )
    request = dict(payload or {})
    request.setdefault("name", f"{source['name']} Copy")
    request.setdefault("description", source.get("description"))
    request.setdefault("marketScope", source["market_scope"])
    request.setdefault("baseCurrency", source["base_currency"])
    request.setdefault("initialCash", source["initial_cash"])
    request.setdefault("benchmarkSymbol", source["benchmark_symbol"])
    request.setdefault("riskConfig", risk.get("config") or {})
    clone = create_account(request)
    for deployment in deployments:
        create_deployment(
            clone["id"],
            {
                "name": deployment["name"],
                "projectId": deployment["project_id"],
                "sourceBacktestId": deployment["source_backtest_id"],
                "scheduleType": deployment["schedule_type"],
                "scheduleExpression": deployment["schedule_expression"],
                "marketTimezone": deployment["market_timezone"],
                "executionTiming": deployment["execution_timing"],
                "signalMode": deployment["signal_mode"],
                "isPrimary": bool(deployment["is_primary"]),
            },
        )
    return get_account(clone["id"])


def _candidate(project_id: str, source_backtest_id: str) -> dict[str, Any]:
    candidates = legacy_paper.trusted_backtest_candidates(project_id)
    candidate = next((item for item in candidates if str(item["id"]) == source_backtest_id), None)
    if not candidate:
        raise ValueError("Deployment requires a successful, certified, validation-passed frozen backtest candidate.")
    run = get_backtest(source_backtest_id)
    if not run:
        raise ValueError("Source backtest is unavailable.")
    parameters = dict(run.get("parameters") or {})
    fingerprint = dict(run.get("fingerprint") or {})
    certification = dict(fingerprint.get("datasetCertification") or {})
    snapshot_dir = run_directory(source_backtest_id, parameters.get("strategySnapshotDir"), relative="strategy")
    if not snapshot_dir.is_dir():
        raise ValueError("Frozen project snapshot is unavailable.")
    versions = get_experiment_versions(source_backtest_id) or {}
    return {
        "candidate": candidate,
        "run": run,
        "parameters": parameters,
        "fingerprint": fingerprint,
        "certification": certification,
        "versions": versions,
        "snapshotDir": str(snapshot_dir),
    }


def _next_market_close(trading_date: str | None = None) -> str:
    market_now = datetime.now(ZoneInfo("Asia/Shanghai"))
    base = date.fromisoformat(trading_date) if trading_date else market_now.date()
    scheduled = datetime(base.year, base.month, base.day, 18, 45, tzinfo=ZoneInfo("Asia/Shanghai"))
    if scheduled <= market_now:
        scheduled += timedelta(days=1)
    while scheduled.weekday() >= 5:
        scheduled += timedelta(days=1)
    return scheduled.astimezone(timezone.utc).isoformat()


def create_deployment(account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    account = get_account(account_id)
    if account["status"] == "archived":
        raise ValueError("Archived accounts cannot receive deployments.")
    project_id = str(payload.get("projectId") or "").strip()
    source_id = str(payload.get("sourceBacktestId") or "").strip()
    if not project_id or not source_id:
        raise ValueError("projectId and sourceBacktestId are required.")
    frozen = _candidate(project_id, source_id)
    parameters = frozen["parameters"]
    candidate = frozen["candidate"]
    versions = frozen["versions"]
    experiment = dict(versions.get("experiment") or {})
    source_fingerprint = frozen["fingerprint"]
    certification = frozen["certification"]
    with db() as connection:
        risk_profile = row_to_dict(
            connection.execute(
                "select * from paper_risk_profiles where id=?",
                (account["active_risk_profile_id"],),
            ).fetchone()
        ) or {}
    risk_config = dict(risk_profile.get("config") or {})
    risk_parameters = {
        "maxPositions": risk_config.get("maxPositions"),
        "maxPositionWeight": risk_config.get("maxPositionWeight"),
        "minCash": risk_config.get("cashFloor", "0"),
        "maxOrderAmount": risk_config.get("maxOrderAmount"),
        "maxDailyTurnover": risk_config.get("maxDailyTurnover"),
        "blacklist": list(risk_config.get("blacklist") or []),
        "observeOnlySymbols": list(risk_config.get("observeOnly") or []),
    }
    strategy_fingerprint = str(
        parameters.get("strategySnapshotHash")
        or parameters.get("strategyFingerprint")
        or candidate.get("parameterHash")
        or _digest(source_fingerprint)
    )
    dataset_fingerprint = _digest(certification)
    signal_mode = str(payload.get("signalMode") or "paper_execute")
    if signal_mode not in {"paper_execute", "signal_only"}:
        raise ValueError("signalMode must be paper_execute or signal_only.")
    is_primary = bool(payload.get("isPrimary", signal_mode == "paper_execute"))
    with db() as connection:
        version_row = connection.execute(
            "select max(version) as version from paper_strategy_deployments where paper_account_id=?",
            (account_id,),
        ).fetchone()
        version = int(version_row["version"] or 0) + 1
        if signal_mode == "paper_execute":
            conflict = connection.execute(
                """
                select id from paper_strategy_deployments
                where paper_account_id=? and status='active' and signal_mode='paper_execute'
                """,
                (account_id,),
            ).fetchone()
            if conflict:
                raise ValueError("Only one active paper_execute deployment is allowed per account.")
    deployment_id = str(uuid.uuid4())
    project_snapshot_id = str(
        parameters.get("strategySnapshotHash") or parameters.get("strategySnapshotDir") or source_id
    )
    dataset_version = str(
        certification.get("datasetVersion") or certification.get("id") or "UNVERSIONED"
    )
    schedule_type = str(payload.get("scheduleType") or "market_daily")
    schedule_expression = str(payload.get("scheduleExpression") or "after_close+00:45")
    market_timezone = str(payload.get("marketTimezone") or "Asia/Shanghai")
    execution_timing = str(payload.get("executionTiming") or "next_open")
    if market_timezone != "Asia/Shanghai" or execution_timing != "next_open":
        raise ValueError("A-share v1 requires Asia/Shanghai and next_open execution.")
    universe_config = dict(payload.get("universeConfig") or {})
    deployment_fingerprint = _digest(
        {
            "accountId": account_id,
            "generation": account["current_generation"],
            "version": version,
            "sourceBacktestId": source_id,
            "projectSnapshotId": project_snapshot_id,
            "strategyFingerprint": strategy_fingerprint,
            "datasetFingerprint": dataset_fingerprint,
            "parameters": parameters,
            "universe": universe_config,
            "riskConfigVersion": risk_profile.get("version"),
            "riskConfigFingerprint": risk_profile.get("config_fingerprint"),
            "risk": risk_parameters,
            "signalMode": signal_mode,
            "executionTiming": execution_timing,
        }
    )
    start = str(parameters.get("end") or date.today().isoformat())
    next_date = legacy_paper._next_trade_date(account["market_scope"], start)
    now = utc_now()
    signal_shadow_session_id = str(uuid.uuid4()) if signal_mode == "signal_only" else None
    deployment_parameters = {
        **parameters,
        **risk_parameters,
        **({"_deploymentShadowSessionId": signal_shadow_session_id} if signal_shadow_session_id else {}),
    }
    with db() as connection:
        if signal_shadow_session_id:
            connection.execute(
                """
                insert into paper_sessions
                    (id,project_id,name,status,symbol,asset_class,venue,resolution,cash,equity,
                     parameters_json,created_at,updated_at,mode,legacy_read_only,
                     source_backtest_id,strategy_version_id,parameter_hash,start_date,
                     auto_advance,pipeline_version)
                values (?,?,?,'created',?,'equity','china','daily',?,?,?, ?,?,
                        'lean_walkforward',0,?,?,?,?,0,1)
                """,
                (
                    signal_shadow_session_id,
                    project_id,
                    f"[signal-only] {payload.get('name') or candidate.get('name') or 'Strategy'}",
                    str(frozen["run"].get("symbol") or parameters.get("ticker") or account["benchmark_symbol"]),
                    _decimal(account["initial_cash"]),
                    _decimal(account["initial_cash"]),
                    json_dump(
                        {
                            **parameters,
                            "sourceBacktestId": source_id,
                            "strategySnapshotDir": frozen["snapshotDir"],
                            "strategySnapshotHash": strategy_fingerprint,
                            "datasetVersion": dataset_version,
                            "benchmarkSymbol": account["benchmark_symbol"],
                            "paperAccountId": account_id,
                            "signalOnly": True,
                        }
                    ),
                    now,
                    now,
                    source_id,
                    candidate.get("strategyVersionId"),
                    candidate.get("parameterHash"),
                    next_date,
                ),
            )
        connection.execute(
            """
            insert into paper_strategy_deployments
                (id,paper_account_id,generation,supersedes_deployment_id,version,name,status,
                 is_primary,project_id,source_backtest_id,strategy_version_id,project_snapshot_id,
                 dataset_version_id,experiment_version_id,schedule_type,schedule_expression,
                 market_timezone,run_after_market_close,execution_timing,signal_mode,
                 parameters_json,universe_config_json,risk_config_version,strategy_fingerprint,
                 dataset_fingerprint,deployment_fingerprint,next_scheduled_at,created_at,updated_at)
            values (?,?,?,null,?,?,'active',?,?,?,?,?,?,?,?,?,?,1,?,?,?, ?,1,?,?,?, ?,?,?)
            """,
            (
                deployment_id,
                account_id,
                account["current_generation"],
                version,
                str(payload.get("name") or candidate.get("name") or f"Strategy {version}"),
                1 if is_primary else 0,
                project_id,
                source_id,
                candidate.get("strategyVersionId"),
                project_snapshot_id,
                dataset_version,
                experiment.get("id") or experiment.get("experiment_version_id"),
                schedule_type,
                schedule_expression,
                market_timezone,
                execution_timing,
                signal_mode,
                json_dump(deployment_parameters),
                json_dump(universe_config),
                strategy_fingerprint,
                dataset_fingerprint,
                deployment_fingerprint,
                _next_market_close(next_date),
                now,
                now,
            ),
        )
        # The legacy v2 runner remains the only execution engine and fact chain.
        # Only the primary paper_execute deployment owns the account shadow
        # session. signal_only deployments receive isolated non-ledger sessions.
        frozen_parameters = {
            **parameters,
            **risk_parameters,
            "sourceBacktestId": source_id,
            "strategySnapshotDir": frozen["snapshotDir"],
            "strategySnapshotHash": strategy_fingerprint,
            "datasetVersion": dataset_version,
            "benchmarkSymbol": account["benchmark_symbol"],
            "paperAccountId": account_id,
            "deploymentId": deployment_id,
            "cash": account["initial_cash"],
        }
        if signal_mode == "paper_execute":
            connection.execute(
                """
                update paper_sessions
                set project_id=?,name=?,symbol=?,venue='china',resolution='daily',
                    parameters_json=?,source_backtest_id=?,strategy_version_id=?,
                    parameter_hash=?,start_date=?,mode='lean_walkforward_v2',
                    legacy_read_only=0,pipeline_version=2,updated_at=?
                where id=?
                """,
                (
                    project_id,
                    f"[account] {account['name']} / {payload.get('name') or candidate.get('name') or 'Strategy'}",
                    str(frozen["run"].get("symbol") or parameters.get("ticker") or account["benchmark_symbol"]),
                    json_dump(frozen_parameters),
                    source_id,
                    candidate.get("strategyVersionId"),
                    candidate.get("parameterHash"),
                    next_date,
                    now,
                    account["shadow_session_id"],
                ),
            )
    return get_deployment(deployment_id)


def get_deployment(deployment_id: str) -> dict[str, Any]:
    with db() as connection:
        item = row_to_dict(
            connection.execute(
                "select * from paper_strategy_deployments where id=?",
                (deployment_id,),
            ).fetchone()
        )
    if not item:
        raise KeyError("Paper deployment not found.")
    return _public(item) or {}


def list_deployments(account_id: str) -> list[dict[str, Any]]:
    get_account(account_id)
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_strategy_deployments
            where paper_account_id=? order by is_primary desc,version desc
            """,
            (account_id,),
        ).fetchall()
    return _public_many(rows_to_dicts(rows))


def update_deployment(deployment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_deployment(deployment_id)
    immutable_change = any(
        key in payload
        for key in {
            "projectId",
            "sourceBacktestId",
            "parameters",
            "universeConfig",
            "signalMode",
            "executionTiming",
        }
    )
    if immutable_change:
        replacement = {
            "name": payload.get("name", current["name"]),
            "projectId": payload.get("projectId", current["project_id"]),
            "sourceBacktestId": payload.get("sourceBacktestId", current["source_backtest_id"]),
            "scheduleType": payload.get("scheduleType", current["schedule_type"]),
            "scheduleExpression": payload.get("scheduleExpression", current["schedule_expression"]),
            "marketTimezone": payload.get("marketTimezone", current["market_timezone"]),
            "executionTiming": payload.get("executionTiming", current["execution_timing"]),
            "signalMode": payload.get("signalMode", current["signal_mode"]),
            "universeConfig": payload.get("universeConfig", current.get("universe_config") or {}),
            "isPrimary": bool(current["is_primary"]),
        }
        transition_deployment(deployment_id, "disable")
        created = create_deployment(current["paper_account_id"], replacement)
        with db() as connection:
            connection.execute(
                "update paper_strategy_deployments set supersedes_deployment_id=? where id=?",
                (deployment_id, created["id"]),
            )
        return get_deployment(created["id"])
    allowed = {"name", "scheduleType", "scheduleExpression"}
    unexpected = set(payload) - allowed
    if unexpected:
        raise ValueError(f"Unsupported deployment fields: {', '.join(sorted(unexpected))}")
    mapping = {"name": "name", "scheduleType": "schedule_type", "scheduleExpression": "schedule_expression"}
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in payload.items():
        assignments.append(f"{mapping[key]}=?")
        values.append(str(value).strip())
    if assignments:
        values.extend((utc_now(), deployment_id))
        with db() as connection:
            connection.execute(
                f"update paper_strategy_deployments set {','.join(assignments)},updated_at=? where id=?",
                tuple(values),
            )
    return get_deployment(deployment_id)


def transition_deployment(deployment_id: str, action: str) -> dict[str, Any]:
    current = get_deployment(deployment_id)
    transitions = {
        "activate": ({"paused", "error"}, "active"),
        "pause": ({"active", "error"}, "paused"),
        "resume": ({"paused"}, "active"),
        "disable": ({"active", "paused", "error"}, "disabled"),
    }
    if action not in transitions:
        raise ValueError("Unsupported deployment action.")
    allowed, target = transitions[action]
    if current["status"] == target:
        return current
    if current["status"] not in allowed:
        raise ValueError(f"Cannot {action} deployment from {current['status']}.")
    if target == "active" and current["signal_mode"] == "paper_execute":
        with db() as connection:
            conflict = connection.execute(
                """
                select id from paper_strategy_deployments
                where paper_account_id=? and status='active' and signal_mode='paper_execute' and id!=?
                """,
                (current["paper_account_id"], deployment_id),
            ).fetchone()
        if conflict:
            raise ValueError("Only one active paper_execute deployment is allowed per account.")
    now = utc_now()
    timestamp = "disabled_at" if target == "disabled" else "paused_at" if target == "paused" else None
    with db() as connection:
        if timestamp:
            connection.execute(
                f"update paper_strategy_deployments set status=?,{timestamp}=?,updated_at=? where id=?",
                (target, now, now, deployment_id),
            )
        else:
            connection.execute(
                "update paper_strategy_deployments set status=?,paused_at=null,updated_at=? where id=?",
                (target, now, deployment_id),
            )
    return get_deployment(deployment_id)


def _account_checkpoint(connection: Any, account_id: str, generation: int) -> dict[str, Any]:
    item = row_to_dict(
        connection.execute(
            """
            select * from paper_account_checkpoints
            where paper_account_id=? and generation=?
            order by source_ledger_sequence desc limit 1
            """,
            (account_id, generation),
        ).fetchone()
    )
    if not item:
        raise ValueError("Account opening checkpoint is unavailable.")
    return item


def ensure_cycle(deployment_id: str, trading_date: str, *, diagnostic: bool = False) -> dict[str, Any]:
    deployment = get_deployment(deployment_id)
    account = get_account(deployment["paper_account_id"])
    normalized_date = date.fromisoformat(trading_date).isoformat()
    with db() as connection:
        checkpoint = _account_checkpoint(connection, account["id"], int(account["current_generation"]))
        existing = row_to_dict(
            connection.execute(
                "select * from paper_execution_cycles where deployment_id=? and trading_date=?",
                (deployment_id, normalized_date),
            ).fetchone()
        )
        if existing:
            return _public(existing) or {}
        input_fingerprint = _digest(
            {
                "paperAccountId": account["id"],
                "accountGeneration": account["current_generation"],
                "deploymentId": deployment_id,
                "tradingDate": normalized_date,
                "strategyFingerprint": deployment["strategy_fingerprint"],
                "datasetFingerprint": deployment["dataset_fingerprint"],
                "accountOpeningCheckpointDigest": checkpoint["digest"],
                "diagnostic": diagnostic,
            }
        )
        idempotency_key = (
            f"{account['id']}:{account['current_generation']}:{deployment_id}:"
            f"{normalized_date}:{input_fingerprint}"
        )
        cycle_id = str(uuid.uuid4())
        now = utc_now()
        connection.execute(
            """
            insert into paper_execution_cycles
                (id,paper_account_id,account_generation,deployment_id,trading_date,
                 scheduled_at,status,attempt,idempotency_key,input_fingerprint,
                 account_checkpoint_digest,strategy_fingerprint,dataset_fingerprint,
                 created_at,updated_at)
            values (?,?,?,?,?,?,'scheduled',0,?,?,?,?,?,?,?)
            """,
            (
                cycle_id,
                account["id"],
                account["current_generation"],
                deployment_id,
                normalized_date,
                now,
                idempotency_key,
                input_fingerprint,
                checkpoint["digest"],
                deployment["strategy_fingerprint"],
                deployment["dataset_fingerprint"],
                now,
                now,
            ),
        )
        _append_cycle_event(
            connection,
            cycle_id,
            None,
            "scheduled",
            "cycle_created",
            {"diagnostic": diagnostic},
        )
        item = row_to_dict(
            connection.execute("select * from paper_execution_cycles where id=?", (cycle_id,)).fetchone()
        )
    return _public(item) or {}


def _append_cycle_event(
    connection: Any,
    cycle_id: str,
    from_status: str | None,
    to_status: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    sequence_row = connection.execute(
        "select max(sequence) as sequence from paper_execution_cycle_events where cycle_id=?",
        (cycle_id,),
    ).fetchone()
    sequence = int(sequence_row["sequence"] or 0) + 1
    connection.execute(
        """
        insert into paper_execution_cycle_events
            (id,cycle_id,sequence,from_status,to_status,event_type,payload_json,created_at)
        values (?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            cycle_id,
            sequence,
            from_status,
            to_status,
            event_type,
            json_dump(payload or {}),
            utc_now(),
        ),
    )


def transition_cycle(
    cycle_id: str,
    to_status: str,
    *,
    event_type: str,
    expected: set[str] | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if to_status not in CYCLE_STATES:
        raise ValueError("Unknown Paper execution cycle status.")
    with db() as connection:
        current = row_to_dict(
            connection.execute("select * from paper_execution_cycles where id=?", (cycle_id,)).fetchone()
        )
        if not current:
            raise KeyError("Paper execution cycle not found.")
        if expected is not None and current["status"] not in expected:
            return _public(current) or {}
        if current["status"] == to_status:
            return _public(current) or {}
        values = dict(fields or {})
        assignments = ["status=?", "version=version+1", "updated_at=?"]
        parameters: list[Any] = [to_status, utc_now()]
        for key, value in values.items():
            assignments.append(f"{key}=?")
            parameters.append(value)
        parameters.extend((cycle_id, current["version"]))
        cursor = connection.execute(
            f"update paper_execution_cycles set {','.join(assignments)} where id=? and version=?",
            tuple(parameters),
        )
        if getattr(cursor, "rowcount", 1) != 1:
            concurrent = row_to_dict(
                connection.execute("select * from paper_execution_cycles where id=?", (cycle_id,)).fetchone()
            )
            return _public(concurrent) or {}
        _append_cycle_event(
            connection,
            cycle_id,
            str(current["status"]),
            to_status,
            event_type,
            values,
        )
        updated = row_to_dict(
            connection.execute("select * from paper_execution_cycles where id=?", (cycle_id,)).fetchone()
        )
    return _public(updated) or {}


def _is_open_trading_day(trading_date: str, market: str = "china") -> bool:
    with db() as connection:
        row = connection.execute(
            "select is_open from trade_calendar where market=? and trade_date=?",
            (market, trading_date),
        ).fetchone()
    if row is not None:
        return bool(row["is_open"])
    return date.fromisoformat(trading_date).weekday() < 5


def run_now(deployment_id: str, trading_date: str | None = None) -> dict[str, Any]:
    deployment = get_deployment(deployment_id)
    account = get_account(deployment["paper_account_id"])
    if deployment["status"] != "active":
        raise ValueError("Only active deployments can run.")
    if account["status"] != "active":
        raise ValueError("Paper account must be active.")
    if trading_date is None:
        trading_date = str(
            deployment.get("last_successful_trading_date")
            and legacy_paper._next_trade_date("china", deployment["last_successful_trading_date"])
            or (legacy_paper.get_session(account["shadow_session_id"]) or {}).get("start_date")
            or date.today().isoformat()
        )
    cycle = ensure_cycle(deployment_id, trading_date)
    if cycle["status"] in {"queued", "running", "finalizing", "succeeded", "skipped"}:
        return {**cycle, "idempotent": True}
    if not _is_open_trading_day(trading_date):
        return transition_cycle(
            cycle["id"],
            "skipped",
            event_type="non_trading_day",
            expected={"scheduled", "waiting_data"},
            fields={
                "skip_reason": "non_trading_day",
                "result_digest": _digest({"cycleId": cycle["id"], "reason": "non_trading_day"}),
                "finished_at": utc_now(),
            },
        )
    queued = transition_cycle(
        cycle["id"],
        "queued",
        event_type="run_now_queued",
        expected={"scheduled", "waiting_data", "failed"},
    )
    from ..tasks.worker import run_paper_execution_cycle_task

    task = run_paper_execution_cycle_task.apply_async(args=[cycle["id"]])
    return {**queued, "celeryTaskId": task.id, "idempotent": False}


def begin_cycle(cycle_id: str) -> dict[str, Any]:
    cycle = transition_cycle(
        cycle_id,
        "running",
        event_type="worker_started",
        expected={"queued", "scheduled", "waiting_data"},
        fields={"started_at": utc_now(), "attempt": 1},
    )
    deployment = get_deployment(cycle["deployment_id"])
    account = get_account(cycle["paper_account_id"])
    with db() as connection:
        conflicting = connection.execute(
            """
            select id from paper_execution_cycles
            where paper_account_id=? and id!=? and status in ('running','finalizing')
            limit 1
            """,
            (cycle["paper_account_id"], cycle_id),
        ).fetchone()
    if conflicting:
        return transition_cycle(
            cycle_id,
            "waiting_data",
            event_type="account_execution_busy",
            expected={"running"},
            fields={
                "failure_code": "account_busy",
                "failure_detail": f"Account cycle {conflicting['id']} is still mutating account state.",
            },
        )
    session_id = (
        str((deployment.get("parameters") or {}).get("_deploymentShadowSessionId") or "")
        if deployment["signal_mode"] == "signal_only"
        else account["shadow_session_id"]
    )
    if not session_id:
        return fail_cycle(cycle_id, "deployment_session_missing", "Frozen deployment session is unavailable.")
    try:
        paper_run = legacy_paper.create_walkforward_run(session_id, cycle["trading_date"])
    except Exception as exc:
        message = str(exc)
        lower = message.lower()
        if any(token in lower for token in ("data", "qa", "benchmark", "certif", "source", "reference")):
            return transition_cycle(
                cycle_id,
                "waiting_data",
                event_type="readiness_gate_blocked",
                expected={"running"},
                fields={"failure_code": "data_not_ready", "failure_detail": message},
            )
        return fail_cycle(cycle_id, "lean_prepare_failed", message)
    with db() as connection:
        connection.execute(
            """
            update paper_execution_cycles
            set paper_run_id=?,lean_run_id=?,updated_at=?,version=version+1
            where id=?
            """,
            (paper_run["id"], paper_run.get("backtest_run_id"), utc_now(), cycle_id),
        )
    return {
        **get_cycle(cycle_id),
        "paperRun": paper_run,
        "shadowSessionId": session_id,
        "signalMode": deployment["signal_mode"],
    }


def fail_cycle(cycle_id: str, failure_code: str, detail: str) -> dict[str, Any]:
    item = transition_cycle(
        cycle_id,
        "failed",
        event_type="cycle_failed",
        expected=CYCLE_STATES - TERMINAL_CYCLE_STATES,
        fields={
            "failure_code": failure_code,
            "failure_detail": detail,
            "finished_at": utc_now(),
        },
    )
    with db() as connection:
        connection.execute(
            """
            update paper_strategy_deployments
            set consecutive_failures=consecutive_failures+1,status=case
                when consecutive_failures+1>=3 then 'error' else status end,updated_at=?
            where id=?
            """,
            (utc_now(), item["deployment_id"]),
        )
        _enqueue_notification(
            connection,
            item["paper_account_id"],
            item["deployment_id"],
            cycle_id,
            "cycle_failed",
            {"tradingDate": item["trading_date"], "failureCode": failure_code, "detail": detail},
        )
    return item


def get_cycle(cycle_id: str) -> dict[str, Any]:
    with db() as connection:
        item = row_to_dict(
            connection.execute("select * from paper_execution_cycles where id=?", (cycle_id,)).fetchone()
        )
    if not item:
        raise KeyError("Paper execution cycle not found.")
    return _public(item) or {}


def finalize_cycle(cycle_id: str) -> dict[str, Any]:
    cycle = get_cycle(cycle_id)
    if cycle["status"] == "succeeded":
        return cycle
    cycle = transition_cycle(
        cycle_id,
        "finalizing",
        event_type="legacy_pipeline_finalized",
        expected={"running", "queued"},
    )
    account = get_account(cycle["paper_account_id"])
    deployment = get_deployment(cycle["deployment_id"])
    paper_run_id = str(cycle.get("paper_run_id") or "")
    paper_run = legacy_paper.get_walkforward_run(paper_run_id)
    if not paper_run or paper_run.get("status") != "success":
        raise ValueError("LEAN Paper run and six-phase finalization must succeed before cycle finalization.")
    with db() as connection:
        intents = rows_to_dicts(
            connection.execute(
                "select * from paper_order_intents where paper_run_id=?",
                (paper_run_id,),
            ).fetchall()
        )
        intent_ids = [str(item["id"]) for item in intents]
        if intent_ids:
            placeholders = ",".join("?" for _ in intent_ids)
            missing_context = connection.execute(
                f"""
                select count(*) as count from paper_ledger_entries
                where intent_id in ({placeholders})
                  and (paper_account_id is null or account_generation is null
                       or execution_cycle_id is null or ledger_sequence is null
                       or precise_quantity is null or precise_amount is null)
                """,
                tuple(intent_ids),
            ).fetchone()
            if int(missing_context["count"] or 0):
                raise CanonicalStateDivergence(
                    f"ledger_context_missing:{cycle['paper_account_id']}:{cycle_id}"
                )
        fills = rows_to_dicts(
            connection.execute(
                "select * from paper_order_fills where execution_cycle_id=?",
                (cycle_id,),
            ).fetchall()
        )
        rejects = connection.execute(
            """
            select count(*) as count from paper_order_transitions transition
            join paper_order_intents intent on intent.id=transition.intent_id
            where intent.execution_cycle_id=? and transition.to_state='REJECTED'
            """,
            (cycle_id,),
        ).fetchone()
        if deployment["signal_mode"] == "signal_only":
            events = rows_to_dicts(
                connection.execute(
                    """
                    select * from paper_lean_order_events
                    where paper_run_id=? order by created_at,id
                    """,
                    (paper_run_id,),
                ).fetchall()
            )
            signals = _signals_from_signal_only_events(connection, cycle, events)
        else:
            signals = _signals_from_intents(connection, cycle, intents)
    deployment_parameters = dict(deployment.get("parameters") or {})
    projection = rebuild_projection(
        cycle["paper_account_id"],
        cycle["trading_date"],
        source=deployment_parameters.get("source"),
        allow_research_source=bool(deployment_parameters.get("allowResearchSource")),
    )
    report = _write_daily_report(cycle_id, projection)
    executable_signal_count = sum(
        1 for item in signals if item.get("signal_type") != "no_signal"
    )
    result_digest = _digest(
        {
            "cycleId": cycle_id,
            "inputFingerprint": cycle["input_fingerprint"],
            "paperRunId": paper_run_id,
            "signalIds": [item["id"] for item in signals],
            "intentIds": intent_ids,
            "fillFingerprints": [item.get("fill_fingerprint") or item["id"] for item in fills],
            "projectionDigest": projection["account"]["source_checkpoint_digest"],
            "reportDigest": report["result_digest"],
        }
    )
    now = utc_now()
    succeeded = transition_cycle(
        cycle_id,
        "succeeded",
        event_type="cycle_reconciled",
        expected={"finalizing"},
        fields={
            "finished_at": now,
            "result_digest": result_digest,
            "signal_count": executable_signal_count,
            "intent_count": len(intents),
            "order_count": len(intents),
            "fill_count": len(fills),
            "rejected_count": int(rejects["count"] or 0),
            "daily_report_id": report["id"],
            "failure_code": None,
            "failure_detail": None,
        },
    )
    with db() as connection:
        connection.execute(
            """
            update paper_strategy_deployments
            set last_successful_trading_date=?,next_scheduled_at=?,consecutive_failures=0,
                updated_at=?
            where id=?
            """,
            (
                cycle["trading_date"],
                _next_market_close(legacy_paper._next_trade_date("china", cycle["trading_date"])),
                now,
                cycle["deployment_id"],
            ),
        )
        event_type = "new_trade_signal" if executable_signal_count else "cycle_recovered"
        _enqueue_notification(
            connection,
            cycle["paper_account_id"],
            cycle["deployment_id"],
            cycle_id,
            event_type,
            {
                "tradingDate": cycle["trading_date"],
                "signalCount": executable_signal_count,
                "fillCount": len(fills),
                "rejectCount": int(rejects["count"] or 0),
                "deepLink": f"/#/paper/accounts/{cycle['paper_account_id']}?tab=signals",
            },
        )
        if intents:
            _enqueue_notification(
                connection,
                cycle["paper_account_id"],
                cycle["deployment_id"],
                cycle_id,
                "order_created",
                {
                    "tradingDate": cycle["trading_date"],
                    "orderCount": len(intents),
                    "deepLink": f"/#/paper/accounts/{cycle['paper_account_id']}?tab=orders",
                },
            )
        if fills:
            _enqueue_notification(
                connection,
                cycle["paper_account_id"],
                cycle["deployment_id"],
                cycle_id,
                "fill_created",
                {
                    "tradingDate": cycle["trading_date"],
                    "fillCount": len(fills),
                    "deepLink": f"/#/paper/accounts/{cycle['paper_account_id']}?tab=trades",
                },
            )
        if int(rejects["count"] or 0):
            _enqueue_notification(
                connection,
                cycle["paper_account_id"],
                cycle["deployment_id"],
                cycle_id,
                "risk_rejected",
                {
                    "tradingDate": cycle["trading_date"],
                    "rejectCount": int(rejects["count"] or 0),
                    "deepLink": f"/#/paper/accounts/{cycle['paper_account_id']}?tab=signals",
                },
            )
    return succeeded


def _signals_from_intents(
    connection: Any,
    cycle: dict[str, Any],
    intents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    if not intents:
        signal_id = str(uuid.uuid4())
        connection.execute(
            """
            insert into paper_strategy_signals
                (id,paper_account_id,deployment_id,cycle_id,signal_key,signal_type,
                 symbol,signal_timestamp,intended_execution_date,evidence_json,
                 disposition,no_trade_reason,lean_run_id,data_timestamp,created_at)
            values (?,?,?,?,?,'no_signal',null,?,?,?,'observed','no_signal',?,?,?)
            """,
            (
                signal_id,
                cycle["paper_account_id"],
                cycle["deployment_id"],
                cycle["id"],
                f"{cycle['id']}:no_signal",
                f"{cycle['trading_date']}T15:01:00+08:00",
                legacy_paper._next_trade_date("china", cycle["trading_date"]),
                json_dump({"reason": "LEAN produced no executable order for the certified trading day."}),
                cycle.get("lean_run_id"),
                f"{cycle['trading_date']}T15:00:00+08:00",
                utc_now(),
            ),
        )
        return [
            {
                "id": signal_id,
                "signal_type": "no_signal",
                "disposition": "observed",
                "no_trade_reason": "no_signal",
            }
        ]
    for intent in intents:
        terminal = connection.execute(
            """
            select to_state,payload_json from paper_order_transitions
            where intent_id=? order by sequence desc limit 1
            """,
            (intent["id"],),
        ).fetchone()
        state = str(terminal["to_state"] if terminal else "")
        raw_payload = json.loads(terminal["payload_json"] or "{}") if terminal else {}
        reason = raw_payload.get("reason")
        disposition = {
            "FILLED": "filled",
            "REJECTED": "rejected",
            "EXPIRED": "not_executed",
            "ACCEPTED": "next_session_pending",
        }.get(state, state.lower() or "observed")
        signal_id = str(uuid.uuid4())
        signal_key = f"{cycle['id']}:{intent['event_key']}"
        connection.execute(
            """
            insert into paper_strategy_signals
                (id,paper_account_id,deployment_id,cycle_id,signal_key,signal_type,symbol,
                 signal_timestamp,intended_execution_date,target_quantity,previous_quantity,
                 evidence_json,disposition,no_trade_reason,intent_id,lean_run_id,
                 data_timestamp,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                signal_id,
                cycle["paper_account_id"],
                cycle["deployment_id"],
                cycle["id"],
                signal_key,
                str(intent["side"]).lower(),
                intent["symbol"],
                intent.get("signal_time") or utc_now(),
                legacy_paper._next_trade_date("china", cycle["trading_date"]),
                intent.get("precise_quantity") or intent["quantity"],
                Decimal("0"),
                json_dump(intent.get("rawIntent") or {}),
                disposition,
                reason,
                intent["id"],
                cycle.get("lean_run_id"),
                f"{cycle['trading_date']}T15:00:00+08:00",
                utc_now(),
            ),
        )
        created.append(
            {
                "id": signal_id,
                "signal_type": str(intent["side"]).lower(),
                "disposition": disposition,
                "no_trade_reason": reason,
            }
        )
    return created


def _signals_from_signal_only_events(
    connection: Any,
    cycle: dict[str, Any],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not events:
        return _signals_from_intents(connection, cycle, [])
    created: list[dict[str, Any]] = []
    for event in events:
        evidence = dict(event.get("event") or {})
        side = str(evidence.get("side") or evidence.get("direction") or "observe").lower()
        symbol = str(evidence.get("symbol") or "").upper() or None
        signal_key = f"{cycle['id']}:signal-only:{event['event_key']}"
        signal_id = str(uuid.uuid4())
        connection.execute(
            """
            insert into paper_strategy_signals
                (id,paper_account_id,deployment_id,cycle_id,signal_key,signal_type,symbol,
                 signal_timestamp,intended_execution_date,target_quantity,evidence_json,
                 disposition,no_trade_reason,intent_id,lean_run_id,data_timestamp,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,null,?,?,?)
            """,
            (
                signal_id,
                cycle["paper_account_id"],
                cycle["deployment_id"],
                cycle["id"],
                signal_key,
                side,
                symbol,
                str(evidence.get("signalTime") or evidence.get("time") or f"{cycle['trading_date']}T15:01:00+08:00"),
                legacy_paper._next_trade_date("china", cycle["trading_date"]),
                evidence.get("quantity"),
                json_dump(evidence),
                "observed",
                "observe_only",
                cycle.get("lean_run_id"),
                f"{cycle['trading_date']}T15:00:00+08:00",
                utc_now(),
            ),
        )
        created.append(
            {
                "id": signal_id,
                "signal_type": side,
                "disposition": "observed",
                "no_trade_reason": "observe_only",
            }
        )
    return created


def rebuild_projection(
    account_id: str,
    as_of_date: str,
    *,
    source: str | None = None,
    allow_research_source: bool = False,
    benchmark_start_date: str | None = None,
) -> dict[str, Any]:
    valuation_date = date.fromisoformat(str(as_of_date)[:10]).isoformat()
    account = get_account(account_id)
    generation = int(account["current_generation"])
    with db() as connection:
        entries = rows_to_dicts(
            connection.execute(
                """
                select * from paper_ledger_entries
                where paper_account_id=? and account_generation=?
                order by ledger_sequence,id
                """,
                (account_id, generation),
            ).fetchall()
        )
        prior = row_to_dict(
            connection.execute(
                "select * from paper_account_projections where paper_account_id=?",
                (account_id,),
            ).fetchone()
        ) or {}
        if benchmark_start_date is None:
            first_cycle = connection.execute(
                """
                select min(trading_date) as trading_date from paper_execution_cycles
                where paper_account_id=? and account_generation=? and trading_date<=?
                  and status not in ('skipped','failed')
                """,
                (account_id, generation, valuation_date),
            ).fetchone()
            benchmark_start_date = str(first_cycle["trading_date"]) if first_cycle["trading_date"] else None
    cash = sum(
        _decimal(item.get("precise_amount", item.get("amount")))
        for item in entries
        if item.get("asset") == "cash"
    )
    positions: dict[str, Decimal] = {}
    costs: dict[str, Decimal] = {}
    for entry in entries:
        if entry.get("asset") != "equity" or not entry.get("symbol"):
            continue
        symbol = str(entry["symbol"])
        quantity = _decimal(entry.get("precise_quantity", entry.get("quantity")))
        positions[symbol] = positions.get(symbol, Decimal("0")) + quantity
        if quantity > 0:
            costs[symbol] = costs.get(symbol, Decimal("0")) + _decimal(
                entry.get("precise_amount", entry.get("amount"))
            )
    quote_timestamp: str | None = None
    rows: list[dict[str, Any]] = []
    market_value = Decimal("0")
    try:
        for symbol, quantity in sorted(positions.items()):
            if quantity == 0:
                continue
            quote = close_price(
                symbol,
                valuation_date,
                source=source,
                allow_research_source=allow_research_source,
                market=str(account["market_scope"]),
            )
            price = _decimal(quote["close"])
            quote_date = str(quote["tradeDate"])
            quote_timestamp = max(filter(None, [quote_timestamp, quote_date]), default=None)
            value = quantity * price
            market_value += value
            average_cost = costs.get(symbol, Decimal("0")) / quantity if quantity else Decimal("0")
            rows.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "sellable": quantity,
                    "averageCost": average_cost,
                    "price": price,
                    "marketValue": value,
                    "unrealizedPnl": value - costs.get(symbol, Decimal("0")),
                    "quoteDate": quote_date,
                    "dataStatus": "certified_close",
                }
            )
        if benchmark_start_date:
            benchmark = market_benchmark_return(
                str(account["benchmark_symbol"]),
                benchmark_start_date,
                valuation_date,
                source=source,
                allow_research_source=allow_research_source,
                market=str(account["market_scope"]),
            )
            benchmark_value = _decimal(benchmark["return"])
        else:
            benchmark_value = _decimal(prior.get("benchmark_return"))
    except MarketDataUnavailable:
        with db() as connection:
            connection.execute(
                """
                update paper_account_projections
                set health_status='degraded',updated_at=? where paper_account_id=?
                """,
                (utc_now(), account_id),
            )
        raise
    equity = cash + market_value
    initial = _decimal(account["initial_cash"])
    cumulative = (equity / initial - Decimal("1")) if initial else Decimal("0")
    excess = cumulative - benchmark_value
    sequence = max((int(item.get("ledger_sequence") or 0) for item in entries), default=0)
    checkpoint_payload = {
        "paperAccountId": account_id,
        "generation": generation,
        "cash": format(cash, "f"),
        "positions": [
            {"symbol": row["symbol"], "quantity": format(row["quantity"], "f")}
            for row in rows
        ],
        "sourceLedgerSequence": sequence,
    }
    checkpoint_digest = _digest(checkpoint_payload)
    with db() as connection:
        existing_checkpoint = connection.execute(
            """
            select id,digest from paper_account_checkpoints
            where paper_account_id=? and generation=? and source_ledger_sequence=?
            """,
            (account_id, generation, sequence),
        ).fetchone()
    if existing_checkpoint and str(existing_checkpoint["digest"]) != checkpoint_digest:
        with db() as connection:
            connection.execute(
                "update paper_accounts set status='error',updated_at=? where id=?",
                (utc_now(), account_id),
            )
            connection.execute(
                """
                update paper_account_projections
                set health_status='error',updated_at=? where paper_account_id=?
                """,
                (utc_now(), account_id),
            )
        emit_alert(
            "paper_schedule_failed",
            severity="critical",
            title="Paper immutable ledger checkpoint divergence",
            message=f"Account {account_id} generation {generation} sequence {sequence} diverged.",
            source="paper_accounts",
        )
        raise CanonicalStateDivergence(
            f"checkpoint_divergence:{account_id}:{generation}:{sequence}"
        )
    with db() as connection:
        for row in rows:
            weight = row["marketValue"] / equity if equity else Decimal("0")
            connection.execute(
                """
                insert into paper_account_position_projections
                    (paper_account_id,generation,symbol,security_name,market,quantity,
                     sellable_quantity,frozen_quantity,average_cost,certified_price,
                     market_value,account_weight,daily_pnl,unrealized_pnl,realized_pnl,
                     last_buy_date,quote_data_timestamp,data_status,updated_at)
                values (?,?,?,null,'china',?,?,0,?,?,?,?,0,?,0,null,?,?,?)
                on conflict(paper_account_id,generation,symbol) do update set
                    quantity=excluded.quantity,sellable_quantity=excluded.sellable_quantity,
                    average_cost=excluded.average_cost,certified_price=excluded.certified_price,
                    market_value=excluded.market_value,account_weight=excluded.account_weight,
                    unrealized_pnl=excluded.unrealized_pnl,
                    quote_data_timestamp=excluded.quote_data_timestamp,
                    data_status=excluded.data_status,updated_at=excluded.updated_at
                """,
                (
                    account_id,
                    generation,
                    row["symbol"],
                    row["quantity"],
                    row["sellable"],
                    row["averageCost"],
                    row["price"],
                    row["marketValue"],
                    weight,
                    row["unrealizedPnl"],
                    row["quoteDate"],
                    row["dataStatus"],
                    utc_now(),
                ),
            )
        active_symbols = [row["symbol"] for row in rows]
        if active_symbols:
            placeholders = ",".join("?" for _ in active_symbols)
            connection.execute(
                f"""
                delete from paper_account_position_projections
                where paper_account_id=? and generation=? and symbol not in ({placeholders})
                """,
                tuple([account_id, generation] + active_symbols),
            )
        else:
            connection.execute(
                "delete from paper_account_position_projections where paper_account_id=? and generation=?",
                (account_id, generation),
            )
        if not existing_checkpoint:
            connection.execute(
                """
                insert into paper_account_checkpoints
                    (id,paper_account_id,generation,cycle_id,source_ledger_sequence,digest,
                     checkpoint_json,created_at)
                values (?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    account_id,
                    generation,
                    None,
                    sequence,
                    checkpoint_digest,
                    json_dump(checkpoint_payload),
                    utc_now(),
                ),
            )
        unrealized = sum((row["unrealizedPnl"] for row in rows), Decimal("0"))
        available = cash
        gross = market_value / equity if equity else Decimal("0")
        now = utc_now()
        connection.execute(
            """
            insert into paper_account_projections
                (paper_account_id,generation,cash,available_cash,frozen_cash,market_value,
                 total_equity,realized_pnl,unrealized_pnl,daily_pnl,cumulative_return,
                 benchmark_return,excess_return,position_count,gross_exposure,net_exposure,
                 turnover,last_valuation_at,quote_data_timestamp,source_ledger_sequence,
                 source_checkpoint_digest,health_status,updated_at)
            values (?,?,?,?,0,?,?,0,?,0,?,?,?,?,?,?,0,?,?,?,?,?,?)
            on conflict(paper_account_id) do update set
                generation=excluded.generation,cash=excluded.cash,
                available_cash=excluded.available_cash,frozen_cash=excluded.frozen_cash,
                market_value=excluded.market_value,total_equity=excluded.total_equity,
                realized_pnl=excluded.realized_pnl,unrealized_pnl=excluded.unrealized_pnl,
                daily_pnl=excluded.daily_pnl,cumulative_return=excluded.cumulative_return,
                benchmark_return=excluded.benchmark_return,excess_return=excluded.excess_return,
                position_count=excluded.position_count,gross_exposure=excluded.gross_exposure,
                net_exposure=excluded.net_exposure,turnover=excluded.turnover,
                last_valuation_at=excluded.last_valuation_at,
                quote_data_timestamp=excluded.quote_data_timestamp,
                source_ledger_sequence=excluded.source_ledger_sequence,
                source_checkpoint_digest=excluded.source_checkpoint_digest,
                health_status=excluded.health_status,updated_at=excluded.updated_at
            """,
            (
                account_id,
                generation,
                cash,
                available,
                market_value,
                equity,
                unrealized,
                cumulative,
                benchmark_value,
                excess,
                len(rows),
                gross,
                gross,
                now,
                quote_timestamp,
                sequence,
                checkpoint_digest,
                "healthy",
                now,
            ),
        )
    return get_overview(account_id)


def rebuild_current_projection(account_id: str) -> dict[str, Any]:
    with db() as connection:
        deployment_row = connection.execute(
            """
            select id,last_successful_trading_date from paper_strategy_deployments
            where paper_account_id=? and is_primary=1
            order by version desc limit 1
            """,
            (account_id,),
        ).fetchone()
    if deployment_row is None:
        return rebuild_projection(account_id, date.today().isoformat())
    deployment = get_deployment(str(deployment_row["id"]))
    parameters = dict(deployment.get("parameters") or {})
    return rebuild_projection(
        account_id,
        str(deployment_row["last_successful_trading_date"] or date.today().isoformat()),
        source=parameters.get("source"),
        allow_research_source=bool(parameters.get("allowResearchSource")),
    )


def _write_daily_report(cycle_id: str, projection: dict[str, Any]) -> dict[str, Any]:
    cycle = get_cycle(cycle_id)
    account_projection = dict(projection.get("account") or {})
    benchmark_symbol = str(account_projection.get("benchmark_symbol") or "").strip().upper()
    benchmark_return = account_projection.get("benchmark_return")
    source_ledger_sequence = account_projection.get("source_ledger_sequence")
    source_checkpoint_digest = account_projection.get("source_checkpoint_digest")
    if not benchmark_symbol or benchmark_return is None:
        raise CanonicalStateDivergence(f"benchmark_projection_missing:{cycle['paper_account_id']}:{cycle_id}")
    if source_ledger_sequence is None or not source_checkpoint_digest:
        raise CanonicalStateDivergence(f"checkpoint_projection_missing:{cycle['paper_account_id']}:{cycle_id}")
    payload = {
        "accountId": cycle["paper_account_id"],
        "deploymentId": cycle["deployment_id"],
        "cycleId": cycle_id,
        "tradingDate": cycle["trading_date"],
        "status": "succeeded",
        "executionTiming": "next_open",
        "projection": {**projection, "account": account_projection},
    }
    digest = _digest(payload)
    report_id = str(uuid.uuid4())
    with db() as connection:
        existing = row_to_dict(
            connection.execute(
                "select * from paper_account_daily_reports where cycle_id=?",
                (cycle_id,),
            ).fetchone()
        )
        if existing:
            return _public(existing) or {}
        connection.execute(
            """
            insert into paper_account_daily_reports
                (id,paper_account_id,deployment_id,cycle_id,trading_date,report_json,
                 result_digest,created_at)
            values (?,?,?,?,?,?,?,?)
            """,
            (
                report_id,
                cycle["paper_account_id"],
                cycle["deployment_id"],
                cycle_id,
                cycle["trading_date"],
                json_dump(payload),
                digest,
                utc_now(),
            ),
        )
        connection.execute(
            """
            insert into paper_account_daily_snapshots
                (id,paper_account_id,generation,trading_date,projection_json,
                 benchmark_symbol,benchmark_return,source_ledger_sequence,
                 source_checkpoint_digest,created_at)
            values (?,?,?,?,?,?,?,?,?,?)
            on conflict(paper_account_id,generation,trading_date) do update set
                projection_json=excluded.projection_json,
                benchmark_return=excluded.benchmark_return,
                source_ledger_sequence=excluded.source_ledger_sequence,
                source_checkpoint_digest=excluded.source_checkpoint_digest
            """,
            (
                str(uuid.uuid4()),
                cycle["paper_account_id"],
                cycle["account_generation"],
                cycle["trading_date"],
                json_dump(account_projection),
                benchmark_symbol,
                benchmark_return,
                source_ledger_sequence,
                source_checkpoint_digest,
                utc_now(),
            ),
        )
    return {"id": report_id, "result_digest": digest, "report": payload}


def _enqueue_notification(
    connection: Any,
    account_id: str,
    deployment_id: str | None,
    cycle_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    dedupe = f"{event_type}:{account_id}:{deployment_id or ''}:{cycle_id or ''}"
    now = utc_now()
    connection.execute(
        """
        insert into paper_notification_outbox
            (id,paper_account_id,deployment_id,cycle_id,event_type,dedupe_key,payload_json,
             status,attempt,next_attempt_at,created_at,updated_at)
        values (?,?,?,?,?,?,?,'pending',0,?,?,?)
        on conflict(dedupe_key) do update set dedupe_key=excluded.dedupe_key
        """,
        (
            str(uuid.uuid4()),
            account_id,
            deployment_id,
            cycle_id,
            event_type,
            dedupe,
            json_dump(payload),
            now,
            now,
            now,
        ),
    )


def deliver_notifications(limit: int = 100) -> dict[str, Any]:
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select * from paper_notification_outbox
                where status in ('pending','retrying')
                  and (next_attempt_at is null or next_attempt_at<=?)
                order by created_at limit ?
                """,
                (utc_now(), max(1, min(int(limit), 500))),
            ).fetchall()
        )
    delivered: list[str] = []
    failed: list[str] = []
    for item in rows:
        if not external_alert_channel_configured():
            with db() as connection:
                connection.execute(
                    """
                    update paper_notification_outbox
                    set status='failed',attempt=attempt+1,last_error='no_channel_configured',updated_at=?
                    where id=?
                    """,
                    (utc_now(), item["id"]),
                )
            failed.append(item["id"])
            continue
        try:
            alert = emit_alert(
                "paper_schedule_failed" if item["event_type"] in {"cycle_failed", "data_not_ready"} else "paper_reject_spike",
                severity=(
                    "critical"
                    if item["event_type"] == "cycle_failed"
                    else "error"
                    if item["event_type"] == "data_not_ready"
                    else "warning"
                ),
                title=f"Paper account event: {item['event_type']}",
                message=json.dumps(item.get("payload") or {}, ensure_ascii=False, default=str),
                source="paper_accounts",
                related_id=item["paper_account_id"],
                details=item.get("payload") or {},
                dedupe_key=item["dedupe_key"],
            )
            delivery = alert.get("delivery") if isinstance(alert, dict) else None
            if not delivery_succeeded(delivery):
                status = str((delivery or {}).get("status") or "external_delivery_not_acknowledged")
                raise RuntimeError(f"external_delivery_not_acknowledged:{status}")
            with db() as connection:
                connection.execute(
                    """
                    update paper_notification_outbox
                    set status='delivered',attempt=attempt+1,delivered_at=?,updated_at=?
                    where id=?
                    """,
                    (utc_now(), utc_now(), item["id"]),
                )
            delivered.append(item["id"])
        except Exception as exc:
            with db() as connection:
                connection.execute(
                    """
                    update paper_notification_outbox
                    set status='retrying',attempt=attempt+1,last_error=?,updated_at=?
                    where id=?
                    """,
                    (str(exc), utc_now(), item["id"]),
                )
            failed.append(item["id"])
    return {"delivered": delivered, "failed": failed}


def schedule_due_deployments(now: datetime | None = None) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select deployment.*
                from paper_strategy_deployments deployment
                join paper_accounts account on account.id=deployment.paper_account_id
                where deployment.status='active' and account.status='active'
                  and deployment.schedule_type='market_daily'
                  and (deployment.next_scheduled_at is null or deployment.next_scheduled_at<=?)
                order by deployment.next_scheduled_at,deployment.created_at
                """,
                (current.isoformat(),),
            ).fetchall()
        )
    queued: list[str] = []
    waiting: list[str] = []
    for deployment in rows:
        account = get_account(deployment["paper_account_id"])
        session = legacy_paper.get_session(account["shadow_session_id"]) or {}
        next_date = (
            legacy_paper._next_trade_date("china", deployment["last_successful_trading_date"])
            if deployment.get("last_successful_trading_date")
            else session.get("start_date")
        )
        if not next_date or str(next_date) > current.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat():
            continue
        cycle = ensure_cycle(deployment["id"], str(next_date))
        if not _is_open_trading_day(str(next_date)):
            transition_cycle(
                cycle["id"],
                "skipped",
                event_type="calendar_closed",
                expected={"scheduled"},
                fields={
                    "skip_reason": "non_trading_day",
                    "finished_at": utc_now(),
                    "result_digest": _digest({"cycleId": cycle["id"], "reason": "non_trading_day"}),
                },
            )
            continue
        if cycle["status"] == "scheduled":
            from ..tasks.worker import run_paper_execution_cycle_task

            transition_cycle(
                cycle["id"],
                "queued",
                event_type="beat_dispatched",
                expected={"scheduled"},
            )
            run_paper_execution_cycle_task.apply_async(args=[cycle["id"]])
            queued.append(cycle["id"])
        elif cycle["status"] == "waiting_data":
            waiting.append(cycle["id"])
    return {"queued": queued, "waitingData": waiting}


def recover_orphaned_cycles(stale_minutes: int = 15) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max(1, stale_minutes))).isoformat()
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select * from paper_execution_cycles
                where status in ('running','finalizing') and updated_at<?
                order by updated_at
                """,
                (cutoff,),
            ).fetchall()
        )
    recovered: list[str] = []
    failed: list[str] = []
    for cycle in rows:
        paper_run = legacy_paper.get_walkforward_run(str(cycle.get("paper_run_id") or ""))
        try:
            if paper_run and paper_run.get("status") == "success":
                finalize_cycle(cycle["id"])
                recovered.append(cycle["id"])
            elif paper_run and paper_run.get("status") in {"queued", "running"}:
                backtest = get_backtest(str(paper_run.get("backtest_run_id") or "")) or {}
                backtest_status = str(backtest.get("status") or "")
                if backtest_status == "success":
                    legacy_paper.finalize_walkforward_run(str(paper_run["id"]))
                    finalize_cycle(cycle["id"])
                    recovered.append(cycle["id"])
                    continue
                with db() as connection:
                    runner = row_to_dict(
                        connection.execute(
                            """
                            select status,error,timed_out,exit_code
                            from restricted_runner_jobs where run_id=?
                            """,
                            (paper_run.get("backtest_run_id"),),
                        ).fetchone()
                    )
                runner_status = str((runner or {}).get("status") or "")
                if backtest_status in {"failed", "cancelled"} or runner_status == "failed":
                    reason = str(
                        backtest.get("error")
                        or (runner or {}).get("error")
                        or "Underlying LEAN execution failed before canonical finalization."
                    )
                    legacy_paper.fail_walkforward_run(str(paper_run["id"]), reason)
                    fail_cycle(cycle["id"], "orphaned_lean_run", reason)
                    failed.append(cycle["id"])
                    continue
                # A running delegated job may legitimately exceed the cycle
                # stale threshold. Its persisted runner state remains the
                # ownership lease until the runner reaches a terminal state.
                continue
            else:
                fail_cycle(cycle["id"], "orphaned_cycle", "Cycle lease expired without a recoverable LEAN run.")
                failed.append(cycle["id"])
        except Exception as exc:
            fail_cycle(cycle["id"], "recovery_failed", str(exc))
            failed.append(cycle["id"])
    return {"recovered": recovered, "failed": failed}


def get_overview(account_id: str) -> dict[str, Any]:
    account = get_account(account_id)
    with db() as connection:
        deployment = row_to_dict(
            connection.execute(
                """
                select * from paper_strategy_deployments
                where paper_account_id=? and is_primary=1
                order by version desc limit 1
                """,
                (account_id,),
            ).fetchone()
        )
        latest_cycle = row_to_dict(
            connection.execute(
                """
                select * from paper_execution_cycles
                where paper_account_id=? order by trading_date desc,created_at desc limit 1
                """,
                (account_id,),
            ).fetchone()
        )
        session = connection.execute(
            "select symbol from paper_sessions where id=?",
            (account["shadow_session_id"],),
        ).fetchone()
        symbol = str(session["symbol"] or "") if session else ""
        watermark = row_to_dict(
            connection.execute(
                """
                select provider,dataset_key,scope_key,last_data_date,validation_status,updated_at
                from provider_dataset_watermarks
                where dataset_key in ('daily','daily_bars','stock_daily')
                  and (scope_key=? or scope_key like ?)
                order by updated_at desc limit 1
                """,
                (symbol, f"%{symbol}%"),
            ).fetchone()
        )
        qa = row_to_dict(
            connection.execute(
                """
                select id,severity,created_at from data_quality_reports
                where symbol=? order by created_at desc limit 1
                """,
                (symbol,),
            ).fetchone()
        )
    return {
        "account": account,
        "deployment": _public(deployment),
        "latestCycle": _public(latest_cycle),
        "dataReadiness": {
            "symbol": symbol,
            "watermark": watermark,
            "qa": qa,
        },
        "dataTrust": _data_trust(),
    }


def _list_account_table(
    account_id: str,
    table: str,
    *,
    date_column: str,
    start_date: str | None = None,
    end_date: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
    deployment_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    get_account(account_id)
    limit, offset = _bounded_page(limit, offset)
    clauses = ["paper_account_id=?"]
    params: list[Any] = [account_id]
    if start_date:
        clauses.append(f"{date_column}>=?")
        params.append(start_date)
    if end_date:
        clauses.append(f"{date_column}<=?")
        params.append(end_date)
    if symbol:
        clauses.append("symbol=?")
        params.append(symbol.upper())
    if status:
        status_column = "status" if table != "paper_strategy_signals" else "disposition"
        clauses.append(f"{status_column}=?")
        params.append(status)
    if deployment_id and table in {"paper_strategy_signals", "paper_execution_cycles", "paper_account_daily_reports"}:
        clauses.append("deployment_id=?")
        params.append(deployment_id)
    where = " and ".join(clauses)
    with db() as connection:
        total = connection.execute(f"select count(*) as count from {table} where {where}", tuple(params)).fetchone()
        rows = connection.execute(
            f"select * from {table} where {where} order by {date_column} desc limit ? offset ?",
            tuple(params + [limit, offset]),
        ).fetchall()
    return _paged(rows_to_dicts(rows), total=int(total["count"] or 0), limit=limit, offset=offset)


def list_positions(
    account_id: str,
    *,
    symbol: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    account = get_account(account_id)
    limit, offset = _bounded_page(limit, offset)
    clauses = ["paper_account_id=?", "generation=?"]
    params: list[Any] = [account_id, account["current_generation"]]
    if symbol:
        clauses.append("symbol=?")
        params.append(symbol.upper())
    where = " and ".join(clauses)
    with db() as connection:
        total = connection.execute(
            f"select count(*) as count from paper_account_position_projections where {where}",
            tuple(params),
        ).fetchone()
        rows = connection.execute(
            f"""
            select * from paper_account_position_projections
            where {where} order by market_value desc limit ? offset ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
    return _paged(rows_to_dicts(rows), total=int(total["count"] or 0), limit=limit, offset=offset)


def list_orders(account_id: str, **filters: Any) -> dict[str, Any]:
    get_account(account_id)
    limit, offset = _bounded_page(filters.get("limit", 50), filters.get("offset", 0))
    clauses = ["intent.paper_account_id=?"]
    params: list[Any] = [account_id]
    if filters.get("symbol"):
        clauses.append("intent.symbol=?")
        params.append(str(filters["symbol"]).upper())
    if filters.get("side"):
        clauses.append("intent.side=?")
        params.append(str(filters["side"]).lower())
    if filters.get("deployment_id"):
        clauses.append("intent.deployment_id=?")
        params.append(filters["deployment_id"])
    if filters.get("start_date"):
        clauses.append("intent.trade_date>=?")
        params.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("intent.trade_date<=?")
        params.append(filters["end_date"])
    status_filter = filters.get("status")
    where = " and ".join(clauses)
    sql = f"""
        select intent.*,
               (select transition.to_state from paper_order_transitions transition
                where transition.intent_id=intent.id order by transition.sequence desc limit 1) as status,
               (select fill.quantity from paper_order_fills fill
                where fill.intent_id=intent.id order by fill.created_at desc limit 1) as filled_quantity,
               (select fill.price from paper_order_fills fill
                where fill.intent_id=intent.id order by fill.created_at desc limit 1) as average_fill_price,
               (select fill.fee+fill.tax from paper_order_fills fill
                where fill.intent_id=intent.id order by fill.created_at desc limit 1) as fees,
               (select decision.rule_code from paper_constraint_decisions decision
                where decision.intent_id=intent.id) as reject_reason
        from paper_order_intents intent where {where}
    """
    with db() as connection:
        rows = rows_to_dicts(connection.execute(f"{sql} order by intent.created_at desc", tuple(params)).fetchall())
    if status_filter:
        rows = [item for item in rows if item.get("status") == status_filter]
    total = len(rows)
    return _paged(rows[offset : offset + limit], total=total, limit=limit, offset=offset)


def list_trades(account_id: str, **filters: Any) -> dict[str, Any]:
    get_account(account_id)
    limit, offset = _bounded_page(filters.get("limit", 50), filters.get("offset", 0))
    clauses = ["fill.paper_account_id=?"]
    params: list[Any] = [account_id]
    if filters.get("symbol"):
        clauses.append("intent.symbol=?")
        params.append(str(filters["symbol"]).upper())
    if filters.get("side"):
        clauses.append("intent.side=?")
        params.append(str(filters["side"]).lower())
    if filters.get("start_date"):
        clauses.append("fill.trade_date>=?")
        params.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("fill.trade_date<=?")
        params.append(filters["end_date"])
    where = " and ".join(clauses)
    with db() as connection:
        total = connection.execute(
            f"""
            select count(*) as count from paper_order_fills fill
            join paper_order_intents intent on intent.id=fill.intent_id where {where}
            """,
            tuple(params),
        ).fetchone()
        rows = connection.execute(
            f"""
            select fill.*,intent.symbol,intent.side,intent.deployment_id,
                   (fill.quantity*fill.price) as principal,
                   (case when intent.side='buy' then -1 else 1 end) *
                   (fill.quantity*fill.price) - fill.fee-fill.tax as total_cash_impact
            from paper_order_fills fill
            join paper_order_intents intent on intent.id=fill.intent_id
            where {where} order by fill.trade_date desc,fill.created_at desc
            limit ? offset ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
    return _paged(rows_to_dicts(rows), total=int(total["count"] or 0), limit=limit, offset=offset)


def list_signals(account_id: str, **filters: Any) -> dict[str, Any]:
    return _list_account_table(
        account_id,
        "paper_strategy_signals",
        date_column="signal_timestamp",
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        symbol=filters.get("symbol"),
        status=filters.get("status"),
        deployment_id=filters.get("deployment_id"),
        limit=filters.get("limit", 50),
        offset=filters.get("offset", 0),
    )


def list_cycles(account_id: str, **filters: Any) -> dict[str, Any]:
    return _list_account_table(
        account_id,
        "paper_execution_cycles",
        date_column="trading_date",
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        status=filters.get("status"),
        deployment_id=filters.get("deployment_id"),
        limit=filters.get("limit", 50),
        offset=filters.get("offset", 0),
    )


def list_daily_reports(account_id: str, **filters: Any) -> dict[str, Any]:
    return _list_account_table(
        account_id,
        "paper_account_daily_reports",
        date_column="trading_date",
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        deployment_id=filters.get("deployment_id"),
        limit=filters.get("limit", 50),
        offset=filters.get("offset", 0),
    )


def performance(account_id: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    account = get_account(account_id)
    clauses = ["paper_account_id=?", "generation=?"]
    params: list[Any] = [account_id, account["current_generation"]]
    if start_date:
        clauses.append("trading_date>=?")
        params.append(start_date)
    if end_date:
        clauses.append("trading_date<=?")
        params.append(end_date)
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                f"""
                select * from paper_account_daily_snapshots
                where {' and '.join(clauses)} order by trading_date
                """,
                tuple(params),
            ).fetchall()
        )
    missing_benchmark_dates = [
        str(item["trading_date"])
        for item in rows
        if item.get("benchmark_return") is None
    ]
    if missing_benchmark_dates:
        raise CanonicalStateDivergence(
            f"benchmark_snapshot_missing:{account_id}:{','.join(missing_benchmark_dates)}"
        )
    points = [
        {
            "tradingDate": item["trading_date"],
            **(item.get("projection") or {}),
            "benchmarkReturn": format(Decimal(str(item["benchmark_return"])), "f"),
        }
        for item in rows
    ]
    return {
        "accountId": account_id,
        "currency": account["base_currency"],
        "benchmarkSymbol": account["benchmark_symbol"],
        "startDate": points[0]["tradingDate"] if points else start_date,
        "valuationDate": points[-1]["tradingDate"] if points else None,
        "missingDates": [],
        "points": points,
        "dataTrust": _data_trust(),
    }


def audit(account_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    get_account(account_id)
    limit, offset = _bounded_page(limit, offset)
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select event.*,cycle.trading_date,cycle.deployment_id
                from paper_execution_cycle_events event
                join paper_execution_cycles cycle on cycle.id=event.cycle_id
                where cycle.paper_account_id=?
                order by event.created_at desc limit ? offset ?
                """,
                (account_id, limit, offset),
            ).fetchall()
        )
        total = connection.execute(
            """
            select count(*) as count from paper_execution_cycle_events event
            join paper_execution_cycles cycle on cycle.id=event.cycle_id
            where cycle.paper_account_id=?
            """,
            (account_id,),
        ).fetchone()
    return _paged(rows, total=int(total["count"] or 0), limit=limit, offset=offset)


def compare_accounts(account_ids: list[str], start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(account_ids))
    if not 2 <= len(unique_ids) <= 10:
        raise ValueError("Select between 2 and 10 Paper accounts.")
    accounts = [get_account(account_id) for account_id in unique_ids]
    currencies = sorted({str(item["base_currency"]) for item in accounts})
    comparable = len(currencies) == 1
    valuations = [item.get("last_valuation_at") for item in accounts if item.get("last_valuation_at")]
    common_valuation = min(valuations) if valuations else None
    rows = []
    for account in accounts:
        if account.get("benchmark_return") is None:
            raise CanonicalStateDivergence(f"benchmark_projection_missing:{account['id']}")
        cycles = list_cycles(account["id"], start_date=start_date, end_date=end_date, limit=200)["items"]
        trades = list_trades(account["id"], start_date=start_date, end_date=end_date, limit=200)["items"]
        rejected = sum(int(item.get("rejected_count") or 0) for item in cycles)
        rows.append(
            {
                "accountId": account["id"],
                "name": account["name"],
                "currency": account["base_currency"],
                "benchmarkSymbol": account["benchmark_symbol"],
                "valuationDate": common_valuation,
                "cumulativeReturn": account.get("cumulative_return") or "0",
                "benchmarkReturn": account["benchmark_return"],
                "excessReturn": account.get("excess_return") or "0",
                "maxDrawdown": None,
                "volatility": None,
                "sharpe": None,
                "turnover": account.get("turnover") or "0",
                "tradeCount": len(trades),
                "winRate": None,
                "cashRatio": (
                    format(
                        _decimal(account.get("cash")) / _decimal(account.get("total_equity")),
                        "f",
                    )
                    if _decimal(account.get("total_equity")) > 0
                    else "0"
                ),
                "positionCount": account.get("position_count") or 0,
                "riskRejectCount": rejected,
                "lastRunDate": max(
                    (str(item["trading_date"]) for item in cycles if item["status"] == "succeeded"),
                    default=None,
                ),
            }
        )
    return {
        "comparable": comparable,
        "reason": None if comparable else "currency_mismatch",
        "currencies": currencies,
        "comparisonStart": start_date,
        "valuationDate": common_valuation,
        "missingData": [item["id"] for item in accounts if not item.get("last_valuation_at")],
        "accounts": rows,
        "dataTrust": _data_trust(),
    }


def global_signals(**filters: Any) -> dict[str, Any]:
    limit, offset = _bounded_page(filters.get("limit", 50), filters.get("offset", 0))
    clauses = ["1=1"]
    params: list[Any] = []
    for key, column in (
        ("account_id", "paper_account_id"),
        ("deployment_id", "deployment_id"),
        ("symbol", "symbol"),
        ("status", "disposition"),
    ):
        if filters.get(key):
            clauses.append(f"{column}=?")
            value = filters[key].upper() if key == "symbol" else filters[key]
            params.append(value)
    where = " and ".join(clauses)
    with db() as connection:
        total = connection.execute(
            f"select count(*) as count from paper_strategy_signals where {where}",
            tuple(params),
        ).fetchone()
        rows = connection.execute(
            f"""
            select * from paper_strategy_signals where {where}
            order by signal_timestamp desc limit ? offset ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
    return _paged(rows_to_dicts(rows), total=int(total["count"] or 0), limit=limit, offset=offset)


def global_cycles(**filters: Any) -> dict[str, Any]:
    limit, offset = _bounded_page(filters.get("limit", 50), filters.get("offset", 0))
    clauses = ["1=1"]
    params: list[Any] = []
    for key, column in (
        ("account_id", "paper_account_id"),
        ("deployment_id", "deployment_id"),
        ("status", "status"),
    ):
        if filters.get(key):
            clauses.append(f"{column}=?")
            params.append(filters[key])
    where = " and ".join(clauses)
    with db() as connection:
        total = connection.execute(
            f"select count(*) as count from paper_execution_cycles where {where}",
            tuple(params),
        ).fetchone()
        rows = connection.execute(
            f"""
            select * from paper_execution_cycles where {where}
            order by trading_date desc,created_at desc limit ? offset ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()
    return _paged(rows_to_dicts(rows), total=int(total["count"] or 0), limit=limit, offset=offset)


def next_runs(deployment_id: str, count: int = 5) -> dict[str, Any]:
    deployment = get_deployment(deployment_id)
    session_account = get_account(deployment["paper_account_id"])
    current = str(
        deployment.get("last_successful_trading_date")
        or (legacy_paper.get_session(session_account["shadow_session_id"]) or {}).get("start_date")
        or date.today().isoformat()
    )
    dates: list[str] = []
    if not deployment.get("last_successful_trading_date"):
        dates.append(current)
    while len(dates) < max(1, min(int(count), 20)):
        current = legacy_paper._next_trade_date("china", current)
        dates.append(current)
    return {
        "deploymentId": deployment_id,
        "marketTimezone": deployment["market_timezone"],
        "scheduleExpression": deployment["schedule_expression"],
        "runs": [
            {"tradingDate": item, "scheduledAt": _next_market_close(item), "executionTiming": "next_open"}
            for item in dates
        ],
    }
