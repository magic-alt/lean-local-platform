---
name: repository-governance-review
description: Review or change repository developer automation and governance under .agents, .codex, .githooks, .github, AGENTS.md, contribution metadata, or release policy; do not use for ordinary product-code implementation.
---

# Repository Governance Review

Use this skill for developer-control-plane changes rather than normal product
features.

## Workflow

1. Read `AGENTS.md` and the nearest relevant governance file before editing.
2. Inventory the affected `.agents`, `.codex`, `.githooks`, `.github`, or
   repository-policy files.
3. Separate **version-controlled desired state** from **GitHub server-side
   settings**. Never claim a Ruleset, security feature, repository topic, or
   branch-protection setting is active unless it was actually verified.
4. For Codex configuration, rules, subagents, or skills, verify
   version-sensitive syntax against current official OpenAI documentation
   before introducing new keys or assumptions.
5. Preserve least privilege:
   - project sandbox defaults stay constrained;
   - network access is not enabled incidentally;
   - secret-like environment variables are filtered from child shells;
   - reviewer/explorer subagents remain behaviorally read-only even when a
     parent session applies broader live runtime permissions.
6. Preserve repository security gates and release immutability. Do not weaken a
   required check, vulnerability threshold, CODEOWNERS surface, release tag
   protection, or destructive-command rule merely to get a PR green.
7. Run the local governance checks and report remote gates separately.

## Required local validation

```bash
python scripts/check_repository_hygiene.py
python scripts/check_developer_governance.py
python scripts/check_oss_governance.py
```

If a change touches release/version policy, also run the appropriate
`check_release_version.py` mode. If it changes a GitHub workflow, verify the
actual Actions run after opening the PR.

## Output

Report:

- files inspected and changed;
- concrete drift or risk found;
- security/permission implications;
- local commands and results;
- remote checks and whether they actually executed or were intentionally
  skipped;
- remaining server-side settings that cannot be changed from repository files.

This skill is `READ_ONLY` by default when asked to audit. Only edit when the
user explicitly requests a repair or implementation.
