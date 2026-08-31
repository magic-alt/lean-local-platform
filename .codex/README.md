# Codex Project Configuration

This directory defines repository-scoped Codex defaults, custom read-only
reviewers, and command safety rules for `magic-alt/platform`.

Project `.codex` configuration is active only when the repository/config layer
is trusted by the local Codex environment. It is a developer guardrail, not a
replacement for GitHub review, CI, sandboxing, or platform runtime controls.

## Layout

```text
.codex/
├── config.toml
├── agents/
│   ├── code-explorer.toml
│   ├── contract-test-reviewer.toml
│   ├── data-lineage-reviewer.toml
│   ├── execution-safety-reviewer.toml
│   └── repository-governance-reviewer.toml
└── rules/
    └── safety.rules
```

## Project defaults

`config.toml` deliberately uses:

- `approval_policy = "on-request"`;
- `sandbox_mode = "workspace-write"` for the primary implementation session;
- no sandbox network access by default;
- `allow_login_shell = false` to avoid importing uncontrolled login-shell startup behavior;
- automatic secret-like environment-variable exclusions for child shells;
- a bounded subagent concurrency limit.

Do not enable network access, broad environment inheritance, or more permissive
approval defaults as an incidental workaround.

## Custom agents

The custom agents are specialized reviewers/explorers. They use
`sandbox_mode = "read-only"` and must also remain **behaviorally read-only**.

This behavioral requirement matters because a parent Codex session can apply
live sandbox or approval overrides when spawning a child. A reviewer must not
start editing merely because the effective runtime happens to permit writes.

| Agent | Primary responsibility |
| --- | --- |
| `code_explorer` | Trace execution/data paths and side effects. |
| `contract_test_reviewer` | Review API, Artifact Contract, schema compatibility, and tests. |
| `data_lineage_reviewer` | Review PIT, provider provenance, DataRelease identity, and lineage. |
| `execution_safety_reviewer` | Review Paper/OMS/broker lifecycle and execution safety. |
| `repository_governance_reviewer` | Review skills, Codex, hooks, GitHub, release, and repository governance. |

Use subagents for independent read-heavy investigation. Avoid parallel writers
to overlapping files; the primary thread should own integration and edits.

## Command rules

`rules/safety.rules` is project-local defense in depth. Destructive operations
are either prompted or forbidden, and every rule carries inline `match` /
`not_match` examples so rule loading can validate the intended prefix.

Rules do not make a destructive command safe. They complement sandbox and
approval policy, GitHub Rulesets and required checks, CODEOWNERS/review,
backup/recovery procedures, and the platform's live-execution boundary.

## Skills

Repository workflows live under [`.agents/skills`](../.agents/skills/README.md).
Skills describe task-specific invariants and verification. Codex configuration
controls the session and reviewer surface; these layers should not duplicate
large blocks of instructions.

## Validation

After changing `.codex`, `.agents`, hooks, or GitHub governance:

```bash
python scripts/check_repository_hygiene.py
python scripts/check_developer_governance.py
python scripts/check_oss_governance.py
```

Then open a PR and inspect the actual `Governance`, `Dependency Review`, and
CodeQL outcomes when relevant.

## Upstream documentation

Codex configuration formats are version-sensitive. Verify new or changed fields
against current OpenAI documentation before merging:

- https://developers.openai.com/codex/config-reference/
- https://developers.openai.com/codex/rules/
- https://developers.openai.com/codex/subagents/
- https://developers.openai.com/codex/skills/
