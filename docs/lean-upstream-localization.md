# LEAN upstream and localization strategy

Last reviewed: 2026-09-06.

## Design principle

`lean-local-platform` uses QuantConnect LEAN as the upstream execution engine and adds local data, market metadata, orchestration, validation and Web control-plane adapters around it. The repository must not maintain a divergent private LEAN core.

```text
QuantConnect LEAN upstream
  -> pinned Docker or qualified native runtime
  -> local runner/orchestration boundary
  -> market localization adapters
  -> validation/evidence
  -> Web control plane
```

The Web application is a curated operator interface. It may expose only a subset of LEAN configuration as first-class forms, while project source and configuration continue to use upstream LEAN APIs. A capability not surfaced in the Web UI must not be interpreted as removed from the upstream engine.

## Machine-readable contract

`app/architecture/platform_contract.py` defines the compatibility policy and `GET /api/research/capabilities` exposes it.

The invariant is:

- engine authority: QuantConnect LEAN upstream;
- integration mode: delegate to LEAN;
- core policy: no divergent local core fork;
- extension points: market data, exchange/symbol metadata, local adapters, orchestration, validation/governance and Web UX;
- non-goal: reimplement LEAN algorithm, order, portfolio or brokerage engines.

Upstream upgrades should therefore update the pinned runtime, run compatibility/regression gates and fix adapters rather than replaying local patches against a private engine fork.

## Capability inheritance versus certification

Preserving upstream capabilities and certifying every platform workflow are different statements. The runner/project boundary should remain compatible with upstream LEAN, but only workflows backed by platform acceptance evidence may be advertised as production-ready. `docs/release-status.md` remains the certification source of truth.

## Localization ownership

`web/backend/app/localization/` owns local market facts. `web/backend/app/lean_engine/` consumes those facts to build LEAN-compatible data and metadata; it does not own source market policy.

| Market | Status | Execution scope | Local requirements |
| --- | --- | --- | --- |
| US equity | upstream | upstream | upstream LEAN semantics |
| China A-share | implemented | daily_localized | CNY, Shanghai timezone, split sessions, board-lot defaults, PIT/QA/reference gates |
| Hong Kong equity | partial | preview_only | HKD, HK sessions, per-security board lot and tick metadata, complete calendar and independent validation evidence |

### China A-share

The localization profile explicitly models the 09:30–11:30 and 13:00–15:00 sessions. Existing adapters continue to normalize symbols and generate LEAN-compatible data. Platform-specific data lineage, point-in-time inputs, benchmark/reference coverage and quality checks remain local prerequisites around the upstream engine.

### Hong Kong equity

Hong Kong remains `partial` / `preview_only`. Symbol normalization and data layout are available, but authoritative execution must not be claimed until per-security board-lot and price-tier metadata, complete exchange-calendar coverage, cost-model inputs and independent LEAN validation evidence are available.

## Research Plane

```text
DataRelease (lean-local-platform)
  -> qlib-platform research
  -> Artifact Contract v2
  -> lean-local-platform import + preview
  -> authoritative LEAN validation
  -> governed execution lifecycle
```

`qlib-platform` owns feature engineering, factor/model research, training, walk-forward research, selection and diagnostics. `lean-local-platform` owns DataRelease identity, artifact verification, imported-result preview, LEAN validation and the execution control plane.

Legacy local Research code may remain temporarily for historical evidence or migration compatibility, but it must not receive new UI, API, Example Catalog or Experiment Batch entrypoints.

## API layering

```text
/api/data/*                 data/control plane
/api/projects/*             LEAN project/source management
/api/backtests/*            authoritative LEAN execution
/api/optimizations/*        LEAN-backed experiment execution
/api/research/capabilities  ownership/localization contract
/api/research/imports*      qlib import and read-only preview
/api/paper/*                governed simulation/control plane
```

Routes validate HTTP input and delegate to services. Services own business rules; repositories own persistence; runners own LEAN process boundaries. Market policy should not migrate back into route modules or UI constants.

## Upgrade checklist

For an upstream LEAN upgrade:

1. update the pinned Docker/native runtime identity;
2. run project/runner contract tests;
3. run deterministic Backend/Frontend CI and PostgreSQL/RabbitMQ Web E2E;
4. run explicit LEAN Docker/native/parity gates on a runtime-capable host;
5. run system verification and the required local-data certification evidence;
6. review A/HK adapter assumptions and generated market metadata;
7. keep certification status unchanged until the required evidence bundle is complete.
