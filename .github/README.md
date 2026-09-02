# GitHub Repository Governance

This directory contains the version-controlled part of the GitHub control
plane. Read it with `docs/repository-governance.md`: some controls live in
GitHub server-side Settings and cannot be activated by committing files alone.

## Layout

| Surface | Purpose |
| --- | --- |
| `CODEOWNERS` | Review ownership, including agent/Codex/hook governance. |
| `PULL_REQUEST_TEMPLATE.md` | Required review context and validation evidence. |
| `ISSUE_TEMPLATE/` | Structured bug, feature, and documentation intake. |
| `dependabot.yml` | Single dependency-update authority. |
| `repository-metadata.yml` | Canonical Description and Topics desired state. |
| `repository-policy.json` | Machine-readable desired repository/Ruleset/security state. |
| `release.yml` | Generated-release-note categories. |
| `workflows/ci.yml` | Always-on Governance plus opt-in compute-heavy validation. |
| `workflows/dependency-review.yml` | Pull-request dependency vulnerability gate. |
| `workflows/codeql.yml` | Python and JavaScript/TypeScript code scanning. |
| `workflows/release.yml` | Manual, validated draft software-release workflow. |
| `workflows/native-runtime-release.yml` | Separate signed native LEAN runtime artifact flow. |

## Authority boundaries

Repository files declare and validate **desired state**. They do not prove that
server-side settings are enabled. Remote verification is required for branch or
tag Rulesets, Dependency Graph, Description/Topics, merge settings, and secrets.

Use:

```bash
python scripts/audit_repository_settings.py --repository magic-alt/lean-local-platform
```

to detect remote drift where the GitHub API exposes the relevant state.

## Workflow permissions

Use least-privilege `permissions:` blocks. Content-validation workflows should
normally use `contents: read`. Grant `contents: write` or
`security-events: write` only to the narrow workflow/job that requires it.

Do not use `pull_request_target` for untrusted contributor code unless a
specific design has been security-reviewed.

## Required-check discipline

A workflow name is not enough evidence that a control executed. Distinguish:

- passed check with the substantive step executed;
- passed bootstrap/availability check with substantive work skipped;
- intentionally skipped compute-heavy lane;
- failed or cancelled run.

Only promote a check to required after it has a stable, non-deadlocking path for
the repository contribution model.

## Developer automation

Changes under these surfaces require explicit CODEOWNERS ownership:

```text
AGENTS.md
.agents/
.codex/
.githooks/
.github/
scripts/check_developer_governance.py
```

Validate them with:

```bash
python scripts/check_repository_hygiene.py
python scripts/check_developer_governance.py
python scripts/check_oss_governance.py
```
