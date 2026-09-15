# Post-Migration Release Certification

This runbook defines the evidence path for the PostgreSQL/RabbitMQ-era release. It does **not** change the current release status by itself. The repository remains **NOT CERTIFIED** until the machine-readable bundle passes against one concrete release identity and the required operational evidence has actually been collected.

The policy is versioned in [`config/certification/post-migration-v1.json`](../config/certification/post-migration-v1.json). `scripts/release_certification.py` is the fail-closed evaluator.

## Safety boundary

Certification is evidence only. It never enables production broker writes, Live Trading, or P9. `/api/health/authorization` continues to report those scopes as disabled even if a Backtest or Paper evidence bundle eventually reaches `CERTIFIED`.

The status surfaces are intentionally separate:

- `/api/health` — service health;
- `/api/health/readiness` — runtime readiness and dependency checks;
- `/api/health/certification` — evidence-bundle status bound to the current release identity;
- `/api/health/authorization` — execution authorization boundary.

If the runtime Git SHA, release ID, migration revision/checksum, OpenAPI digest, or frontend digest differs from the bundle, the certification endpoint returns `NOT_CERTIFIED` with a machine-readable `certification_identity_mismatch` reason.

## Evidence set

The post-migration evaluator binds:

- Git SHA and release ID;
- PostgreSQL migration revision and checksum;
- PostgreSQL/RabbitMQ runtime readiness;
- generated OpenAPI SHA-256 and frontend asset SHA-256;
- Python dependency locks, frontend lock, Docker/runtime locks, DataRelease and Research contracts, SLO/repository policy, and release-signing policy;
- immutable DataRelease ID and manifest SHA-256;
- isolated restore evidence and measured RPO/RTO;
- fault-injection matrix;
- supply-chain/SBOM/signature evidence;
- runtime-specific Windows certification when certifying `windows-native`;
- for Paper certification only: real-time production-shape soak evidence and a persisted third-party webhook observation.

Missing files, malformed JSON, missing fields, failed checks, or identity mismatches are certification blockers.

## 1. Release convergence

Generate production-shape PostgreSQL/RabbitMQ release identity evidence from the managed Compose stack:

```bash
python scripts/verify_release_convergence.py \
  --manage-stack \
  --evidence web/runtime/audit/release-convergence.json
```

The evidence must report `managedStack: true`, PostgreSQL and RabbitMQ ready, a versioned release ID/Git SHA, aligned migration state, and matching source/runtime OpenAPI and release identity.

## 2. Immutable DataRelease certification

Run the existing local-data certification against the frozen DataRelease used by the release. Do not certify mutable `current` data as if it were a frozen release.

```bash
python scripts/local_data_certification.py \
  --data-dir /absolute/path/to/data \
  --data-release-id <DATA_RELEASE_ID> \
  --evidence web/runtime/audit/local-data-certification.json
```

The final certificate requires the real frozen DataRelease → LEAN smoke path to pass. A skip-only smoke result is not sufficient.

## 3. Independent restore drill

Create a PostgreSQL backup using the supported deployment/operations backup path, then restore that backup into an isolated database namespace. Bind the drill to the exact release and DataRelease:

```bash
export LEAN_RELEASE_ID=<CURRENT_RELEASE_ID>
python scripts/run_restore_drill.py \
  --backup <POSTGRES_BACKUP_PATH> \
  --target-prefix lean_restore_issue61 \
  --confirm RESTORE_ISOLATED_DATABASE \
  --data-release-id <DATA_RELEASE_ID> \
  --data-release-manifest-sha256 <64_HEX_SHA256> \
  --verify-paper-projections \
  --evidence web/runtime/audit/restore-drill.json
```

The drill verifies canonical table row counts and content digests, records RPO/RTO, and—when Paper certification is in scope—rebuilds and verifies Paper projections inside the isolated restored database. The source database is not rewritten.

## 4. Fault matrix

Run the production-shape service restart acceptance first:

```bash
python scripts/run_service_restart_fault_acceptance.py \
  --confirm RESTART_LOCAL_SERVICES \
  --output web/runtime/audit/service-restart-faults.json
```

This produces structured evidence for PostgreSQL short disconnect, RabbitMQ outage, and worker crash, including recovery samples and before/after state invariants.

Collect dedicated JSON evidence for the remaining policy scenarios:

- duplicate delivery;
- runner timeout/cancel;
- disk full;
- object corruption;
- lease expiry/stale worker;
- missing PIT/benchmark;
- notification failure.

Each scenario must contain a pass/fail result plus non-empty `trace` and `invariants`. Assemble the final matrix:

```bash
python scripts/build_fault_matrix.py \
  --service-restart web/runtime/audit/service-restart-faults.json \
  --scenario duplicate_delivery=<PATH> \
  --scenario runner_timeout_cancel=<PATH> \
  --scenario disk_full=<PATH> \
  --scenario object_corruption=<PATH> \
  --scenario lease_expiry_stale_worker=<PATH> \
  --scenario missing_pit_benchmark=<PATH> \
  --scenario notification_failure=<PATH> \
  --output web/runtime/audit/fault-matrix.json
```

The matrix exits non-zero until every required scenario is present, passed, and has structured trace/invariant evidence.

## 5. Supply chain

Generate current SBOM/vulnerability/signature evidence using the repository's existing supply-chain tools, then evaluate it:

```bash
python scripts/check_supply_chain.py \
  --output web/runtime/audit/supply-chain.json
```

A passing certification requires digest-pinned runtime dependencies, hash-locked Python dependencies, the frontend lock, SBOM/vulnerability policy evidence, and the release signature gate required by `check_supply_chain.py`.

## 6. Real Paper soak

`scripts/run_paper_accounts_acceptance.py` is useful functional acceptance, but it rapidly replays historical trading dates. It is **not** real 21-day elapsed evidence and cannot satisfy the final Paper gate.

Start the real-time observer only after the release/DataRelease identity is frozen:

```bash
python scripts/paper_soak_observer.py start \
  --account-id <PAPER_ACCOUNT_ID> \
  --data-release-id <DATA_RELEASE_ID> \
  --data-release-manifest-sha256 <64_HEX_SHA256>
```

Take at least one observation on each production-shape observation day:

```bash
python scripts/paper_soak_observer.py sample
```

After at least 21 elapsed calendar days and at least 21 distinct Asia/Shanghai observation dates, finalize against the completed fault matrix:

```bash
python scripts/paper_soak_observer.py finalize \
  --fault-matrix web/runtime/audit/fault-matrix.json \
  --evidence web/runtime/audit/paper-soak-evidence.json
```

The observer uses current timestamps only, maintains a hash chain over samples, validates Paper projection history on every sample, rejects release-identity drift, and requires database/RabbitMQ/worker interruption-recovery evidence. Same-day accelerated samples cannot pass.

## 7. Third-party alert observation

Run the existing external webhook acceptance against a real third-party endpoint for the required observation window:

```bash
python scripts/run_external_webhook_acceptance.py --help
```

Final Paper certification requires `thirdPartyCertified: true`, at least 24 observed hours, and persisted successful delivery evidence. A local endpoint is not sufficient.

## 8. Build the certificate

Backtest profile:

```bash
python scripts/release_certification.py \
  --profile backtest \
  --runtime linux-docker \
  --release-convergence web/runtime/audit/release-convergence.json \
  --local-data-certification web/runtime/audit/local-data-certification.json \
  --restore-drill web/runtime/audit/restore-drill.json \
  --fault-matrix web/runtime/audit/fault-matrix.json \
  --supply-chain web/runtime/audit/supply-chain.json \
  --output web/runtime/audit/release-certification.json
```

Paper profile additionally requires real soak and external webhook evidence:

```bash
python scripts/release_certification.py \
  --profile paper \
  --runtime linux-docker \
  --release-convergence web/runtime/audit/release-convergence.json \
  --local-data-certification web/runtime/audit/local-data-certification.json \
  --restore-drill web/runtime/audit/restore-drill.json \
  --fault-matrix web/runtime/audit/fault-matrix.json \
  --supply-chain web/runtime/audit/supply-chain.json \
  --paper-soak web/runtime/audit/paper-soak-evidence.json \
  --external-webhook web/runtime/audit/external-webhook-acceptance.json \
  --output web/runtime/audit/release-certification.json
```

For `windows-native`, pass the actual Windows certificate with `--windows-certificate`; a Linux/Docker pass is not inherited by Windows.

## Closure rule for Issue #61

Issue #61 is not complete merely because the code and CI pass. Close it only after the current release has a complete, identity-matched evidence bundle and the operational activities above have actually executed. In particular, a historical replay or one-day accelerated simulation must never be relabeled as the required 21-day production-shape Paper observation.
