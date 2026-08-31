# Versioning and Releases

LEAN Local Platform uses Semantic Versioning for repository releases and keeps **software release** separate from **production certification**.

A GitHub Release or `vX.Y.Z` tag means a source baseline was versioned and published. It does **not** mean the platform has passed the runtime, data, fault, restore, soak, broker or production evidence required by `docs/release-status.md`.

## Version authority

The root `VERSION` file is the source of truth for the next repository release.

```text
0.1.0
```

Release tags use the same version with a `v` prefix:

```text
v0.1.0
```

The repository is currently pre-1.0. During `0.x` development:

- **PATCH** (`0.1.0` → `0.1.1`) is for backward-compatible fixes, documentation, dependency/security maintenance and operational corrections that do not intentionally break public contracts.
- **MINOR** (`0.1.x` → `0.2.0`) is for new capabilities and may carry explicitly documented breaking changes while the project remains pre-1.0.
- **MAJOR** (`1.0.0` and later) follows standard Semantic Versioning: incompatible public contract changes require a major increment.

Do not encode build dates, Git SHAs or certification status into `VERSION`. Those identities belong in release evidence and `docs/release-status.md`.

## Changelog contract

Normal development adds concise entries under `## Unreleased` in `CHANGELOG.md`.

A release-preparation pull request must:

1. choose the release version and update `VERSION`;
2. move the release entries out of `Unreleased` into a dated heading such as:

```markdown
## [0.1.0] - 2026-09-01
```

3. leave a fresh `## Unreleased` section for subsequent work;
4. verify that release notes do not claim certification or live-execution support that is not present in `docs/release-status.md`.

`scripts/check_release_version.py --tag vX.Y.Z --require-changelog` enforces the VERSION/tag match and the dated changelog heading.

## Release gates

Before creating a repository release candidate, run at least:

```bash
python scripts/check_repository_hygiene.py
python scripts/check_oss_governance.py
python scripts/check_release_version.py --tag vX.Y.Z --require-changelog
```

Then run the validation lanes appropriate to the change set. A normal release candidate should have current Backend and Frontend evidence; runtime, native, Windows, LEAN, migration, restore or acceptance evidence is required when those surfaces changed.

The release process must never use a release tag to bypass the production certification rules in `docs/release-status.md`.

## Draft-release workflow

The `Release` GitHub Actions workflow is intentionally manual.

From `main`, dispatch it with the exact version from `VERSION`. The workflow:

1. validates SemVer, `VERSION`, and the dated changelog section;
2. re-runs repository governance checks;
3. refuses to overwrite an existing tag;
4. creates an annotated `vX.Y.Z` tag at the selected `main` commit;
5. pushes the tag;
6. creates a **draft** GitHub Release using generated release notes.

The workflow does not publish the draft automatically. A maintainer reviews the generated notes and evidence before publishing.

If a tag already exists, fix the release by creating a new version. Do not move or delete a published release tag.

## Release notes

`.github/release.yml` groups generated notes by breaking changes, security, features, fixes, documentation and dependencies. Labels improve categorization but are not substitutes for `CHANGELOG.md`, which remains the human-maintained record of observable behavior and architecture changes.

## Native LEAN runtime releases

`Native Runtime Release` is a separate artifact workflow for a pinned upstream LEAN runtime. Its `native-<runtime-id>` tags are not repository SemVer releases and must not be confused with `vX.Y.Z` platform releases.

Native runtime promotion retains its own signing, SBOM, validation, Dockerless Golden Acceptance and backend-parity requirements.

## 1.0 criteria

Do not use `1.0.0` merely because the repository is public. A 1.0 release should coincide with a deliberately stable public contract and documented support policy. Production certification may be part of that decision, but repository SemVer and runtime certification remain separate evidence dimensions.
