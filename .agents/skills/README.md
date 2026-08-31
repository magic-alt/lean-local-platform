# Repository Skills

This directory contains repository-scoped Agent Skills for `magic-alt/platform`.
Codex discovers root skills from `.agents/skills` when it runs inside the
repository. Keep each skill narrow, explicit, and aligned with the platform's
architecture and safety boundaries.

## Skill catalog

| Skill | Use when |
| --- | --- |
| `repo-audit` | Tracing unfamiliar cross-layer behavior or reviewing a broad platform change. |
| `ci-validation` | Choosing proportionate local and hosted validation before handoff. |
| `data-release-change` | Changing market-data ingestion, PIT semantics, source gates, DataRelease identity, or checksums. |
| `lean-validation-change` | Changing authoritative LEAN validation, evidence, or promotion gates. |
| `paper-execution-change` | Changing Paper accounts, orders, fills, ledgers, schedules, or reconciliation. |
| `broker-gateway-change` | Reviewing broker observation, credentials, gateway exposure, or the broker read/write boundary. |
| `qlib-handoff-review` | Reviewing Artifact Contract v2, TARGET_PORTFOLIO, lineage, or lifecycle handoff from `qlib-platform`. |
| `repository-governance-review` | Changing `.agents`, `.codex`, `.githooks`, `.github`, `AGENTS.md`, repository policy, or release/developer automation. |

## Shared contract

Every repository skill should make the following unambiguous:

1. **Trigger** — when the skill should and should not be used.
2. **Scope** — the smallest files, symbols, or control-plane surfaces to inspect.
3. **Invariants** — architecture, data, execution, security, or governance rules that must remain true.
4. **Forbidden actions** — operations that normal implementation or verification must not perform.
5. **Validation** — the narrowest useful checks, plus broader gates when the change warrants them.
6. **Output** — findings, changed behavior, commands run, skipped gates, and unresolved risks.
7. **Escalation** — when a task stops being ordinary feature work and becomes an architecture/security change.

Descriptions in the YAML front matter are routing metadata. Keep them specific
enough that an agent can decide whether to invoke the skill without reading the
body first.

## Safety baseline

The repository side-effect classes are:

```text
READ_ONLY
LOCAL_TEST_WRITE
DATA_CONTROL_PLANE_WRITE
PAPER_STATE_WRITE
BROKER_OBSERVATION
BROKER_WRITE
LIVE_ACTIVATION
```

`BROKER_WRITE` and `LIVE_ACTIVATION` are not ordinary implementation or
verification surfaces. P9/live activation remains disabled.

Repository automation changes must not weaken:

- fail-closed research and execution validation;
- credential or secret isolation;
- broker read/write boundaries;
- immutable DataRelease and release evidence;
- required repository governance checks;
- command safety rules merely to make automation convenient.

## Validation

For skill, Codex, hook, or GitHub-governance changes run:

```bash
python scripts/check_repository_hygiene.py
python scripts/check_developer_governance.py
python scripts/check_oss_governance.py
```

GitHub-hosted CodeQL and Dependency Review are remote PR gates. They are not
substitutes for the repository-local checks above.

## References

- Root agent policy: [`AGENTS.md`](../../AGENTS.md)
- Codex project configuration: [`.codex/README.md`](../../.codex/README.md)
- Local Git hooks: [`.githooks/README.md`](../../.githooks/README.md)
- GitHub governance: [`.github/README.md`](../../.github/README.md)
