# Research and execution boundary

`platform` owns the canonical market-data control plane, immutable composite
DataRelease publication, LEAN validation, portfolio construction, hard risk,
Paper, OMS, broker integration, ledgers and every lifecycle state after
`RESEARCH_PROMOTED`.

`qlib-platform` owns Qlib materialisation, features, factors, model training,
walk-forward research, research-only portfolio screening and publication of
ModelRelease, StrategyPolicy, SignalSnapshot, TargetPortfolio and research
ValidationResult artifacts.

The integration boundary is an immutable DataRelease plus Artifact Contract v2.
Qlib may never publish order intents, broker orders, fills or the
`LEAN_VALIDATED`, `PAPER`, `PRODUCTION` and `RETIRED` states.

P3 migration starts at the broker edge: the loopback-only, GET-only MiniQMT
query gateway is now owned by `platform` under `app/broker/qmt_gateway`.
It publishes raw broker observations only. PnL, risk, reconciliation, intents,
orders, fills and ledger projections remain platform-owned; the gateway does
not maintain a parallel SQLite ledger or expose any broker write operation.

The existing `app/research/` implementation, `services/ml_research.py` and the
isolated ML dependency lock are grandfathered pending migration. They must not
grow into a second feature store or model-training platform. Architecture tests
hold this allowlist and the canonical SQL-writer boundaries.

## P4–P9 control-plane progression

P4 freezes new `ml-cross-sectional-ranker` jobs in `platform`: historical runs
remain readable, but the Research Control Center no longer advertises or creates
the legacy training template. Qlib remains the only model-training and
walk-forward engine.

P5 binds every new imported Qlib `TARGET_PORTFOLIO` snapshot to its immutable
artifact ID. A LEAN validation draft carries that ID, the source `DataRelease`
ID and the canonical target-weight SHA-256 as server-owned bindings.

P6 is fail-closed. A Qlib target can advance from `RESEARCH_PROMOTED` to
`LEAN_VALIDATED` only after a successful LEAN backtest records exactly the same
DataRelease ID and target-weight hash and passes the existing execution
validation gate. `platform` stores a hash-addressed `VALIDATION_RESULT` and
records its lineage back to the target.

P7 requires that recorded LEAN validation before creating a Paper deployment.
The deployment then records the target's `PAPER` promotion event; this does not
start an account, schedule a run or submit an order by itself.

P8 remains restricted to the existing read-only QMT observation gateway. No
broker-write, OMS-write or live order endpoint is introduced by this work.

P9 remains intentionally unavailable. There is no API path from `PAPER` to
`PRODUCTION`; live activation still requires the separately governed broker,
reconciliation, secret-hardening, canary, kill-switch and rollback acceptance
evidence.
