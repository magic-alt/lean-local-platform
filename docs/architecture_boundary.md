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
