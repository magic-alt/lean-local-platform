# ETF rotation real-execution certification campaign

Issue #67 is closed only by real platform evidence. The campaign runner coordinates existing authoritative LEAN, experiment, Paper, admission, resource and artifact services; it does not create a shadow executor or enable Live/P9.

## Immutable U.S. ETF DataRelease

The campaign requires the governed composite profile `us-etf-daily-certification-v1`. The normal `publish_data_release()` path enforces `assetClass=equity`, `market=usa`, and freezes all of these components:

- `bars`;
- `adjustment_factors`;
- `corporate_actions`;
- `security_master`;
- `trading_calendar`;
- `benchmark`.

The `bars.componentReleaseId` is not descriptive metadata: it must identify the executable certified dataset release that LEAN actually resolves. Every canonical, deterministic-rerun, baseline, and walk-forward child backtest must persist that exact value in `backtest_runs.dataset_release_id`, otherwise the campaign fails with a dataset-release lineage mismatch.

## Frozen input

Create a JSON configuration with an explicit immutable `dataReleaseId`. The runner never selects a mutable `latest` release.

```json
{
  "projectId": "<project created from etf_rotation>",
  "dataReleaseId": "<immutable us-etf-daily-certification-v1 DataRelease id>",
  "symbols": ["SPY", "QQQ", "IWM", "IEF", "GLD"],
  "symbol": "SPY",
  "benchmarkSymbol": "SPY",
  "start": "2020-01-02",
  "end": "2025-12-31",
  "cash": 100000,
  "parameters": {
    "lookback": 63,
    "rebalanceDays": 21,
    "selectionCount": 2,
    "volatilityLookback": 60,
    "targetVolatility": 0.10,
    "maxWeight": 0.60,
    "maxTurnover": 0.25,
    "commissionPerOrder": 1.0,
    "slippageBps": 2.0,
    "costModelId": "lean-constant-fee-slippage-v1"
  },
  "walkForward": {
    "universeVersion": "us-etf-core-v1",
    "adjustmentContract": "lean-adjusted-v1",
    "featurePipelineVersion": "etf-rotation-v2",
    "trainYears": 3,
    "validationMonths": 6,
    "testYears": 1,
    "stepYears": 1,
    "parameterGrid": {}
  },
  "gates": {
    "maximumDrawdown": 0.30,
    "maximumTurnover": 1.0,
    "minimumTradeCount": 1
  },
  "paperSessionId": null
}
```

`paperSessionId` must identify an authoritative Paper-v2 session. Do not substitute fixture data or a second ledger. The current canonical ETF template is U.S.-market scoped; until U.S. daily ETF Paper-v2 is certified, the campaign intentionally stops at `waiting_paper_evidence`.

## Run and resume

```bash
python scripts/run_etf_rotation_certification_campaign.py start --config campaign.json
python scripts/run_etf_rotation_certification_campaign.py run --campaign-id <campaign-id>
python scripts/run_etf_rotation_certification_campaign.py status --campaign-id <campaign-id>
```

When LEAN/walk-forward evidence is already complete but the campaign is waiting for a real Paper-v2 session, attach the authoritative session without restarting the earlier work:

```bash
python scripts/run_etf_rotation_certification_campaign.py attach-paper \
  --campaign-id <campaign-id> \
  --session-id <paper-v2-session-id>
python scripts/run_etf_rotation_certification_campaign.py run --campaign-id <campaign-id>
```

The campaign is resumable because step state and child resource IDs are stored as append-only `workflow_events`. Real trading facts remain in their existing canonical tables. An already-certified campaign is immutable and refuses Paper replacement.

## Stages

The state machine executes or verifies, in order:

1. explicit active `us-etf-daily-certification-v1` DataRelease pin and coverage check;
2. composite `bars.componentReleaseId` ↔ actual LEAN `dataset_release_id` binding;
3. canonical ETF rotation LEAN run;
4. deterministic rerun from the canonical strategy snapshot;
5. independent `etf_static_equal_weight` LEAN baseline;
6. post-run execution attribution persisted through `backtest_repository.save_result`;
7. formal `experiment_batches` walk-forward using Train → Validation → OOS and the same composite/executable release identities;
8. authoritative Paper-v2 evidence with worker constraint decisions, ACCEPT and REJECT cases, fills, ledger and reconciliation;
9. duplicate finalization replay proving ledger count/digest stability;
10. before/after runtime resource envelope plus persisted LEAN duration;
11. `certify_etf_rotation_execution` and immutable artifact registration.

A child backtest or batch is created once. Re-running the CLI reads the persisted IDs and continues instead of creating duplicate work.

## Execution attribution

`etf_rotation_execution_attribution.py` materializes these fields into `backtest_results.performance.executionAttribution`:

- `fees`: actual LEAN `Total Fees` / OrderEvent fee evidence;
- `slippage`: the frozen constant-slippage assumption applied to actual filled notional;
- `cashDrag`: average cash fraction derived from the strategy's real `GrossExposure` chart;
- `capacityImpact`: initial capital divided by LEAN `Estimated Strategy Capacity`.

Missing source evidence remains `null`. No value is replaced by synthetic zero, so the certification gate fails closed.

## Paper and Live boundary

The campaign never submits a live broker order. It only accepts Paper-v2 records produced by the existing execution pipeline. A rejected worker constraint decision must have no fill. Duplicate replay calls the existing terminal Paper finalizer and requires unchanged ledger entry count and digest.

The existing authoritative `lean_walkforward_v2` Paper implementation is currently China/Hong Kong daily-equity scoped. U.S. ETF support must be added inside that same Paper-v2 pipeline—with USD/cost semantics and the existing worker risk/ledger writers—before a real U.S. ETF campaign can pass this stage. The campaign deliberately does not create a parallel simulator to bypass that gap.

The `ETF_EXECUTION_CERTIFICATION / LEAN_VALIDATED` artifact is registered only when every gate returns `certified=true`. Live/P9 stays disabled.
