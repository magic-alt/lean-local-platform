# Repository Governance

This document defines the intended GitHub-side governance for `magic-alt/platform`. Repository files are version controlled; GitHub Rulesets and repository settings are server-side controls and must be kept in sync with `.github/repository-policy.json`.

## Current target

The repository is a public, single-maintainer project today. The baseline therefore requires pull requests and automated checks without requiring an approval that the pull-request author cannot provide to their own change.

When a second maintainer with write access is established, raise the approval requirement from `0` to `1` and enable required CODEOWNERS review.

## Security prerequisite: Dependency Graph

GitHub Dependency Review depends on the repository Dependency Graph. Enable it **before** making `Dependency Review` a required status check:

1. Open **Settings → Security → Advanced Security**.
2. Enable **Dependency graph**.
3. Open or update a pull request and verify that the `Dependency Review` workflow runs the actual review step rather than the explicit unavailable warning.
4. Only then apply the `Protect main` required-check list below.

The workflow intentionally distinguishes these states. When Dependency Graph is unavailable, the stable `Dependency Review` job completes with a visible warning so a bootstrap PR is not deadlocked. Once Dependency Graph is enabled, the same check fails closed when a pull request introduces a dependency with a `high` or `critical` known vulnerability.

## Default-branch ruleset

Create an **active branch ruleset** named `Protect main` targeting the default branch.

Required rules:

- block branch deletion;
- block force pushes / non-fast-forward updates;
- require linear history;
- require a pull request before merging;
- require all review conversations to be resolved;
- require `0` approving reviews while the repository has only one maintainer;
- do not require CODEOWNERS approval until another eligible maintainer exists;
- require status checks `Governance` and, after Dependency Graph is enabled and verified, `Dependency Review`;
- require the branch to be up to date before merging.

`Governance` is intentionally small and always-on. `Dependency Review` is the supply-chain merge gate after its server-side prerequisite is active. CodeQL is initially advisory rather than a required status check so its code-scanning rollout can stabilize independently and external fork PRs are not deadlocked.

GitHub supports a pull-request requirement with zero mandatory approvals, which fits a single-maintainer repository while still preventing direct pushes through the ordinary path. Strict required status checks keep the topic branch current with the protected target before merge.

## Release-tag ruleset

Create an **active tag ruleset** named `Protect release tags` targeting `refs/tags/v*`.

Required rules:

- block deletion;
- block force/non-fast-forward updates.

Release tags are immutable evidence. A correction after publication uses a new version; an existing release tag is never moved to another commit.

## Repository merge settings

Use these repository-level settings:

| Setting | Target |
| --- | --- |
| Squash merge | enabled |
| Rebase merge | enabled |
| Merge commits | disabled |
| Automatically delete head branches | enabled |
| Allow update branch | enabled |
| Auto-merge | optional; leave disabled initially |

Linear history plus squash/rebase keeps the default branch easier to audit and makes release boundaries unambiguous.

## Security automation

The repository uses:

- Dependabot for GitHub Actions, npm, Docker and Docker Compose version updates;
- Dependabot security monitoring for Python while the hash-lock regeneration process remains manual;
- Dependency Review on every pull request, with Dependency Graph as its server-side prerequisite;
- CodeQL for Python and JavaScript/TypeScript on `main`, internal pull requests and a weekly schedule.

Do not enable Renovate at the same time as Dependabot. Choose one dependency-update authority to avoid duplicate PRs and lockfile churn.

## Applying the server-side settings

The connected automation surface may not be allowed to mutate Rulesets or repository merge settings. When server-side writes are unavailable, apply the policy in GitHub in this order:

1. Enable **Dependency graph** under **Settings → Security → Advanced Security**.
2. Verify one real `Dependency Review` run.
3. Open **Settings → Rules → Rulesets**.
4. Create the `Protect main` branch ruleset using the default branch target and the rules above.
5. Create the `Protect release tags` tag ruleset for `refs/tags/v*`.
6. Open **Settings → General → Pull Requests** and align merge methods, head-branch deletion and update-branch behavior with the table above.
7. Apply the Description and Topics from `.github/repository-metadata.yml` if they are not already synchronized.
8. Run the remote audit below.

```bash
python scripts/audit_repository_settings.py --repository magic-alt/platform
```

Set `GITHUB_TOKEN` when unauthenticated GitHub API rate limits or protected-setting visibility require authentication. The script only reads settings and never prints the token.

## Promotion of additional required checks

Do not add a check to the Ruleset merely because a workflow exists. Promote a check to required only after it has been stable on representative pull requests and cannot deadlock external contributors.

Recommended progression:

1. `Governance` — required immediately.
2. `Dependency Review` — required after Dependency Graph is enabled and one real review run succeeds.
3. `Backend` / `Frontend` — require when hosted execution is enabled consistently rather than repository-variable skipped.
4. CodeQL merge protection — enable after code scanning has a stable baseline and alert triage policy.
5. Native/Windows/LEAN integration — retain as specialized release or architecture gates unless hosted cost and runtime reliability justify making them universal.

## Emergency changes

Avoid permanent maintainer bypass rules. If a broken required workflow blocks all changes, a repository administrator may temporarily place the ruleset in evaluate/disabled mode, repair the workflow through a pull request, verify the required checks, and immediately restore active enforcement. Record such an exception in the pull request or incident evidence.
