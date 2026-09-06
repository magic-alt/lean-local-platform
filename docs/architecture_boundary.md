# Research and execution boundary

## Upstream LEAN is the execution authority

`lean-local-platform` is a local control plane and localization layer **over** QuantConnect LEAN. It is not a replacement implementation of the LEAN algorithm, order, portfolio, brokerage or execution engines, and it must not maintain a divergent local LEAN core fork.

Local development belongs at explicit adapter boundaries: market data, symbol/exchange metadata, broker adapters, orchestration, validation/governance and Web control-plane UX. A curated Web surface may expose fewer controls than upstream LEAN, but that does not redefine or remove upstream engine capabilities. See [LEAN upstream and localization strategy](lean-upstream-localization.md).

## Research Plane ownership

`platform` owns the canonical market-data control plane, immutable composite DataRelease publication, LEAN validation, portfolio construction, hard risk, Paper, OMS, broker integration, ledgers and every lifecycle state after `RESEARCH_PROMOTED`.

`qlib-platform` owns Qlib materialisation, features, factors, model training, walk-forward research, research-only portfolio screening and publication of ModelRelease, StrategyPolicy, SignalSnapshot, TargetPortfolio and research ValidationResult artifacts.

The integration boundary is an immutable DataRelease plus Artifact Contract v2. Qlib may never publish order intents, broker orders, fills or the `LEAN_VALIDATED`, `PAPER`, `PRODUCTION` and `RETIRED` states.

The public platform Research surface is intentionally narrow:

```text
GET  /api/research/capabilities
GET  /api/research/imports
GET  /api/research/imports/{import_id}
POST /api/research/imports/qlib
POST /api/research/runs/{run_id}/lean-validation
```

The GET routes are read-only projections for Web/API preview. The POST import route verifies Artifact Contract v2. LEAN validation verifies the exact imported DataRelease and TargetPortfolio hash against an authoritative LEAN run.

Legacy `app/research/`, `services/ml_research.py`, detached Research container code and historical Celery tasks remain compatibility/history debt only. They may be retained while old evidence and migrations need them, but **no new API, Example Catalog, Experiment Batch or Web entrypoint may create local Research work**. New model research must go through qlib-platform.

## A-share and Hong Kong localization

Market-specific behavior is owned by `app/localization/`, not by a forked LEAN engine. `app/lean_engine/` consumes those profiles to build LEAN-compatible data/market metadata.

- **China A-share**: daily localization is implemented, including explicit morning/afternoon sessions, CNY, board-lot defaults with security overrides, existing PIT/QA/benchmark gates and A-share symbol normalization. Production certification remains a separate evidence decision.
- **Hong Kong equity**: symbol normalization and data layout are available, but the profile is `partial` / `preview_only`. Per-security board lot, price-tier tick size, exchange-calendar completeness, fees and independent execution-validation evidence are required before authoritative execution is claimed.

The localization capability matrix is machine-readable at `GET /api/research/capabilities`; it must not advertise a market as certified merely because a symbol can be parsed or a LEAN data file can be generated.

## P3 broker edge

P3 migration starts at the broker edge: the loopback-only, GET-only MiniQMT query gateway is owned by `platform` under `app/broker/qmt_gateway`.
It publishes raw broker observations only. PnL, risk, reconciliation, intents, orders, fills and ledger projections remain platform-owned; the gateway does not maintain a parallel SQLite ledger or expose any broker write operation.

## P4–P9 control-plane progression

P4 freezes new `ml-cross-sectional-ranker` jobs in `platform`: historical runs remain readable, but the platform no longer advertises or creates local model-training jobs. Qlib remains the only model-training and walk-forward engine.

P5 binds every new imported Qlib `TARGET_PORTFOLIO` snapshot to its immutable artifact ID. A LEAN validation draft carries that ID, the source `DataRelease` ID and the canonical target-weight SHA-256 as server-owned bindings.

P6 is fail-closed. A Qlib target can advance from `RESEARCH_PROMOTED` to `LEAN_VALIDATED` only after a successful LEAN backtest records exactly the same DataRelease ID and target-weight hash and passes the existing execution validation gate. `platform` stores a hash-addressed `VALIDATION_RESULT` and records its lineage back to the target.

P7 requires that recorded LEAN validation before creating a Paper deployment. The deployment then records the target's `PAPER` promotion event; this does not start an account, schedule a run or submit an order by itself.

P8 remains restricted to the existing read-only QMT observation gateway. No broker-write, OMS-write or live order endpoint is introduced by this work.

P9 remains intentionally unavailable. There is no API path from `PAPER` to `PRODUCTION`; live activation still requires the separately governed broker, reconciliation, secret-hardening, canary, kill-switch and rollback acceptance evidence.
