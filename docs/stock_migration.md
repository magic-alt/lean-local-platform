# Stock Project Migration Record

Historical record reviewed 2026-07-21. This file intentionally preserves the original migration boundary and source commit; current architecture and Roadmap status live in `docs/architecture.md` and `docs/roadmap.md`.

The former Backtrader platform is frozen as a source archive. LEAN is the only
production backtest engine for this repository.

- Source repository: `/Users/kaermax/stock`
- Source commit: `9f6399fa22d37dcd990e976d0b870329035e5174`
- Source branch at review: `feature/settings-full-configuration`
- Source license: MIT, copyright 2026 magic-alt
- Decision date: 2026-07-15

## Migration boundary

The following concepts are being reimplemented against LEAN-native results and
MySQL persistence: strategy admission and baseline drift, risk/attribution
metrics, run-ID portfolio optimization, risk parity, and turning-point
selection. Tests and formulas may be adapted with the source license retained.

Backtrader/Zipline engines, SQLite caches, the Vue/FastAPI control plane,
JSON/SQLite job stores, broker stubs, plugin/package facades, MLOps adapters,
runtime artifacts, and downloaded data are not migrated.

The source Git history remains the authoritative archive. No new product
features should be developed in that repository unless the product direction
explicitly changes to live brokerage integration.

## LEAN-native replacements

- Strategy admission is persisted in `strategy_admissions` and append-only
  `strategy_admission_events`. A parameter fingerprint progresses through
  `research`, `baseline_registered`, `admission_passed`, and `paper_validated`.
- Baseline and candidate evaluation require successful, trusted runs covering
  bull, bear, range, and high-volatility regimes. The `institutional` profile
  applies absolute quality gates and baseline-drift gates.
- LEAN results now add daily VaR 95%, expected shortfall 95%, tracking error,
  information ratio, market correlation, and end-position concentration.
- Portfolio weight search accepts two to five admitted run IDs, aligns their
  persisted NAV series, and supports Sharpe, return, or drawdown objectives.
- `risk_parity` and `turning_point` are first-class LEAN strategy templates;
  they do not import Backtrader or execute code from the source repository.

Relevant endpoints:

```text
GET  /api/strategies/admission/config
POST /api/strategies/{strategyId}/baselines
POST /api/strategies/{strategyId}/admissions
POST /api/strategies/{strategyId}/paper-validations
GET  /api/strategies/{strategyId}/admission
GET  /api/backtests/{runId}/admission
POST /api/portfolio-optimizations/preview
POST /api/portfolio-optimizations
```

Portfolio optimization deliberately rejects unadmitted runs and short weights.
The migrated multi-asset templates are research templates; an A-share
multi-symbol strategy still has to pass the existing data, benchmark, fee,
price-limit, suspension, and T+1 validation chain before it is trusted.
