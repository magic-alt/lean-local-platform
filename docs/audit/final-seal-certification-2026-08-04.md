# Historical Final-seal Certification — 2026-08-04

> Applies to the architecture before the PostgreSQL/RabbitMQ migration.
> Superseded for current-release certification purposes; see
> [Current Release Status](../release-status.md).

## Decision

`NOT_CERTIFIED` / `LEVEL5_FAIL`.

The existing issue ledger has **P0=0, P1=3, P2=1**. Under the release rule that
only P0=0, P1=0 and P2=0 permits `CERTIFIED`, this release cannot be signed as
certified. `CODE_DONE` is not treated as `CLOSED`. The machine-readable
certificate under `web/runtime/audit/releases/<release_id>/release-certificate.json`
binds the final deployed Git SHA, release ID, migration revision/checksum,
OpenAPI digest and path count, frontend digest, worker generation and evidence
hashes after the documentation commit is deployed.

This review is iteration 5 of the preserved 2026-08-02 actual-environment audit.
It does not add findings or widen the audit. It uses only the existing P0/P1/P2
ledger in:

- `actual-environment-system-review-2026-08-02.md`
- `actual-environment-remediation-checklist-2026-08-02.md`
- `actual-environment-feature-matrix-2026-08-02.md`
- `actual-environment-api-contract-review-2026-08-02.md`
- `actual-environment-data-review-2026-08-02.md`
- `web/runtime/audit/actual-environment-system-review-2026-08-02.json`

## Frozen release boundary

| Capability | Final classification |
| --- | --- |
| Local single-machine A-share daily Research | production scope |
| LEAN Backtest | production scope; LEAN is the only production engine |
| Optimization and Reports | production scope |
| Paper Account | production scope; trusted backtest seed required |
| Cross-asset | `research_only` / `preview_only` |
| Live trading | `disabled` |
| Minute/Tick | `disabled` |
| Incomplete PIT dates | fail-closed |
| Unattended operation without delivered external alert | fail-closed / not operationally ready |

No strategy, data asset, page, API or business capability was added.

## Gate results

| Gate | Result | Evidence |
| --- | --- | --- |
| Repository hygiene | PASS | `scripts/check_repository_hygiene.py` |
| Full backend | PASS | 606 passed, 2 skipped after the gate-limited repairs |
| Migration verify | PASS | revision `0043_p1_lineage_query_index`, checksum aligned, 43 applied and 0 pending |
| OpenAPI reference | PASS | 233 paths; generated help reference check passed |
| Frontend production build | PASS | Vite production build; final digest is certificate-bound |
| Level 3 execute | PASS | `web/runtime/audit/final-seal-level3.json` |
| Level 4 execute | FAIL | `web/runtime/audit/final-seal-level4.json` |
| Paper two-account 21-session | PASS | existing cohort `2da80404-a54d-411c-8fba-d1866b1ad43f`; both accounts retained 23 sessions |
| Level 5 constraints | PASS | seven constraint reasons in the fresh Level 3 evidence |
| Level 5 fault | PARTIAL PASS | worker restart recovered with all five row-count invariants stable; full MySQL/Redis injection was not stacked on an already unstable database |
| Browser matrix | NOT VERIFIED | Browser runtime reported no controllable browser instance |

The Level 4 execution created and retained all batch facts. Rolling passed
(`c29bc955-3de8-440d-9435-c5e6f930d15d`). Parameter grid became partial
(`7c65d429-1c2f-4b4e-94be-36c755e6a692`) and Walk-Forward was cancelled only
after the audit client had already failed and the remaining work threatened to
keep the environment non-quiescent (`c97b0d79-25b7-4a8f-8932-9983d4797fe9`);
all database rows and artifacts were preserved. Dynamic PIT correctly rejected a
window without complete fundamentals. During the run, MySQL repeatedly exited
with code 137 and restarted, resetting both stability observations.

## Required negative coverage

Focused acceptance tests covered research/screening Paper seed rejection, stale
dataset trust, missing benchmark, PIT gaps, duplicate/idempotent requests,
ledger digest divergence, worker outage reporting, Webhook delivery failure and
payload drift. The actual environment additionally exposed a mixed-version
state before release rollout: repository SHA `535e768fa9e3c6c1d7a734fe41f91f9fbfba2d63`
versus deployed SHA `2ebbd099499f916b67a4904166720087d431a9db`.
The final certificate may bind only a converged post-commit deployment; a
pre-deployment convergence check cannot close the release.

## Existing open ledger only

| Existing ID | Severity | Final status | Current evidence |
| --- | --- | --- | --- |
| ACT-P1-002 | P1 | `OPEN_OBSERVATION_PENDING` | MySQL 2013/refused connections and exit 137 reset the required seven-day maintenance window |
| ACT-P1-007 | P1 | `OPEN_EXTERNAL_CHANNEL_AND_24H` | Webhook remains dead-lettered with no persisted successful delivery; no approved external endpoint was probed |
| ACT-P1-008 | P1 | `OPEN_24H_CAPACITY_OBSERVATION` | repeated MySQL restarts and worker heartbeat drift reset the 24-hour capacity window |
| ACT-P2-002 | P2 | `OPEN_BROWSER_NOT_VERIFIED` | no Browser instance was available for the four-viewport and cursor-log journeys |

No resolved issue was reopened as a new identifier. The Level 4 and runtime
failures map to ACT-P1-002/ACT-P1-008; the Webhook result maps to ACT-P1-007;
the missing interactive matrix maps to ACT-P2-002.

## Gate-limited repairs

Two narrow repairs were made only after fresh Level 3 failures:

1. The acceptance shadow replay stopped calling the retired `/api/paper` routes
   and now invokes the already-existing internal replay service. The retired API
   was not restored.
2. The max-position acceptance case now places both test symbols in the existing
   watchlist so it reaches the intended `max_positions` rejection instead of an
   earlier `not_in_watchlist` rejection.

Regression tests were added for both repairs. Any release manifest and
certificate are regenerated after these code changes and the final commit.

## Closure rule

The release may become `CERTIFIED` only after the same existing ledger reaches
P0=0, P1=0 and P2=0 with a new certificate: seven continuous days of maintenance
stability, a real external Webhook 2xx plus bounded 24-hour delivery evidence,
24 continuous hours of capacity stability, and the actual Browser matrix. A
score, unit test, production build or old release evidence cannot substitute for
those facts.
