# Certified ETF Momentum / Risk-Parity Rotation

This template is the canonical ETF acceptance strategy introduced for Issue #67.
It is intentionally conservative and deterministic so the same immutable input
bundle can be replayed in backtest, walk-forward validation, and paper trading.

## Allocation pipeline

For every eligible rebalance session the strategy:

1. advances the rebalance clock only on a fresh, non-fill-forward trading session;
2. requires finite positive adjusted prices and enough history for both momentum
   and volatility windows;
3. ranks positive-momentum ETFs by `momentum DESC, ticker ASC`;
4. selects at most `selectionCount` ETFs;
5. assigns inverse-volatility risk-parity weights;
6. redistributes weights subject to `maxWeight`;
7. scales gross exposure down when the diagonal annualized volatility estimate
   exceeds `targetVolatility`; leverage above 1.0 is not used;
8. preserves non-tradable/suspended holdings and reserves their gross exposure;
9. blends current and requested weights so one-rebalance turnover does not exceed
   `maxTurnover`;
10. submits reductions before increases through LEAN portfolio targets.

A zero-candidate rebalance is a defined risk-off state. The strategy moves toward
cash, but it does not bypass the turnover cap or attempt to force orders in
securities without a fresh tradable bar.

## Determinism and corporate actions

- Ranking ties are resolved by ticker ascending.
- Iterative weight capping processes symbols in ticker order.
- The canonical U.S. ETF pack uses `DataNormalizationMode.ADJUSTED`, so dividend
  and split boundaries do not appear as artificial momentum shocks.
- `rebalanceDays` means **fresh trading sessions**, not calendar days. Weekends,
  holidays, and missing/fill-forward bars do not advance the clock.

## Parameters

| Parameter | Default | Contract |
| --- | ---: | --- |
| `symbols` | `SPY,QQQ,IWM,IEF,GLD` | At least two unique ETFs |
| `lookback` | 63 | 2–504 trading sessions |
| `rebalanceDays` | 21 | 1–126 fresh sessions |
| `selectionCount` | 2 | 1–20 and no greater than symbol count |
| `volatilityLookback` | 60 | 2–252 trading sessions |
| `targetVolatility` | 0.10 | 0.01–1.00 annualized |
| `maxWeight` | 0.60 | 0.01–1.00 |
| `maxTurnover` | 0.25 | 0.01–1.00 one-way turnover |
| `commissionPerOrder` | 1.00 | USD 0–100 |
| `slippageBps` | 2.0 | 0–100 bps |
| `costModelId` | `lean-constant-fee-slippage-v1` | Non-empty identity |

Invalid or non-finite numeric values fail closed with `ValueError`.

## Cost model

The template does not subtract synthetic costs from returns. For U.S. ETFs it
installs LEAN `ConstantFeeModel` and `ConstantSlippageModel` on each security.
The model identity and parameters are carried in the strategy parameters so the
same cost assumptions can be pinned in the certification lineage.

China/Hong Kong execution continues to use the platform execution helpers and is
not certified by this U.S. ETF acceptance pack.

## Certification

The deterministic reference implementation lives in
`web/backend/app/services/etf_rotation_certification.py`.

The machine-readable report requires:

- candidate and static-equal-weight baseline metrics:
  `sharpe`, `maxDrawdown`, `turnover`, `tradeCount`;
- lineage identities:
  `codeVersion`, `dataReleaseId`, `costModelId`;
- at least two equal deterministic replay fingerprints;
- explicit gate thresholds supplied by the certification input.

Example:

```bash
python scripts/certify_etf_rotation.py \
  --input path/to/certification-input.json \
  --regression-fixture web/backend/tests/fixtures/etf_rotation_certification.v1.json \
  --output web/runtime/audit/etf-rotation-certification.json
```

The command exits with status `2` when the metric/lineage/determinism gates fail.
A passing synthetic regression fixture is engineering evidence only; it is not a
production-readiness claim and does not replace live/paper acceptance evidence
required by Issue #67.

## Real-execution certification

The second #67 certification layer is
`web/backend/app/services/etf_rotation_execution_certification.py`. It consumes
existing authoritative platform records instead of creating a parallel executor
or ledger. A real-execution certificate is fail-closed unless all of these are
present and mutually consistent:

- canonical ETF and static-weight baseline LEAN runs bound to the same immutable
  `dataReleaseId`, code version and cost-model identity;
- complete fee, slippage, cash-drag and capacity-impact attribution;
- the existing experiment service's frozen train/validation/OOS walk-forward
  lineage and ordered, fingerprinted folds;
- Paper order intents plus worker constraint decisions, transitions, fills,
  append-only ledger entries, deterministic projection and reconciliation;
- explicit duplicate-replay/idempotency evidence proving the ledger entry count
  and identity do not change on replay;
- an existing strategy admission at `admission_passed` or `paper_validated`;
- real before/after runtime resource snapshots with CPU/RSS evidence and the
  persisted backtest duration.

Build an audit report with:

```bash
python scripts/certify_etf_rotation_execution.py \
  --input path/to/real-execution-evidence.json \
  --output web/runtime/audit/etf-rotation-execution-certification.json
```

A failed report is still useful audit evidence and exits with status `2`, but it
cannot be registered as a platform certification artifact. Only a fully passing
report can be registered as `ETF_EXECUTION_CERTIFICATION / LEAN_VALIDATED` in
the existing immutable `artifact_registry`; this never enables live/P9 trading.
