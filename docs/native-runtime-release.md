# Native LEAN runtime release contract

Native execution never follows LEAN master and production hosts do not build
LEAN. Release engineering builds an exact QuantConnect/Lean commit for each
supported RID, packages the Release launcher with the dedicated Python runtime,
generates a CycloneDX SBOM, and signs the archive with the private key matching
`config/release-signing-public.pem`.

The checked-in runtime lock is intentionally fail-closed. `supported` must remain
`false` until the immutable artifact, detached signature, SBOM, and SHA-256 have
all been produced and independently reviewed.

## Validation policy

GitHub Actions are optional evidence only. Repository or Actions quota limits
must not block Windows Native development or release acceptance. A change may be
merged when the equivalent local Windows validation passes and its JSON evidence
is retained with the review notes.

Run the local contract gate from Windows PowerShell:

```powershell
.\deploy\windows\run_local_native_validation.ps1
```

The local gate validates locked Python dependencies, `pip check`, `platformctl`,
PowerShell syntax, JSON contracts, Python compilation, RuntimeRegistry,
Restricted Runner, Windows sandbox/Job Object/Supervisor contracts,
certification contracts, repository hygiene, and `git diff --check`. It writes
host/commit-bound evidence to:

```text
C:\ProgramData\LeanPlatform\evidence\windows-native-local-validation.json
```

A green GitHub Actions run may supplement this evidence but is not required.
This relaxation changes the execution venue only; it does not relax runtime
signature, Dockerless Golden Acceptance, backend parity, or production
certification gates.

## Windows x64 candidate flow

The preferred release path is local Windows release engineering:

```powershell
.\deploy\windows\run_local_native_runtime_release.ps1 `
  -LeanCommit 81a62a1eb4d4e0a96bb7c3d183b4083c47d2b600 `
  -RuntimeId lean-81a62a1-windows-x64-r1 `
  -PythonRoot C:\path\to\Python311 `
  -SigningPrivateKeyPath C:\secure\lean-runtime-signing.pem `
  -PublishDraft
```

This path requires local `git`, .NET 10, Python 3.11.11, OpenSSL, and, only when
`-PublishDraft` is used, an authenticated GitHub CLI. The script:

1. checks out the exact requested QuantConnect/Lean commit;
2. builds `Launcher/QuantConnect.Lean.Launcher.csproj` in Release mode;
3. packages the complete launcher output plus Python 3.11.11;
4. computes the archive SHA-256;
5. generates a file-level CycloneDX 1.5 SBOM;
6. creates an Ed25519 detached signature and verifies it against the checked-in
   public key;
7. optionally publishes all files to a **draft** GitHub release; and
8. emits `lean-native.lock.generated.json` for review when the draft release is
   published.

The repository also keeps `.github/workflows/native-runtime-release.yml` as an
optional convenience path for environments with Actions quota. Its output and
trust requirements are equivalent to the local release path; it is not a
required merge or release gate.

The default candidate is currently pinned to QuantConnect/Lean commit
`81a62a1eb4d4e0a96bb7c3d183b4083c47d2b600`. This is a release candidate
anchor, not automatic approval. Change it only through explicit release review.

For a private repository, a Windows host may set `LEAN_RUNTIME_DOWNLOAD_TOKEN`
to a token allowed to read the release assets. The installer sends it only as an
HTTPS bearer token and still verifies SHA-256, signature, and SBOM before making
the runtime ready.

## Lock contract

The artifact entry requires immutable HTTPS URLs for the archive, detached
signature, and SBOM plus the archive SHA-256. Platform-specific entries may
override `launcher`, `pythonHome`, and `pythonLibrary`; this is required because
Windows uses `python/python311.dll` while Linux uses a shared-object path.

The SBOM metadata must contain:

```text
lean.runtime.id=<runtimeId>
lean.runtime.sha256=<archive sha256>
```

Do not copy the generated lock into `config/runtime/lean-native.lock.json` until
all of the following are true:

- local Windows Native validation passed for the candidate commit;
- the draft release assets and hashes were reviewed;
- the detached signature verifies against the checked-in public key;
- the Windows clean-host Dockerless Golden Acceptance passes using that exact
  runtime;
- Docker/native result parity is accepted for the selected regression case; and
- the release is made immutable/published.

After those gates pass, replace the bootstrap lock with the reviewed generated
lock and rerun `platformctl --mode native runtime install`, `doctor`, and the
clean-host Golden Acceptance. Production support remains a separate gate and
still requires the Windows 12-hour fault/soak certification.
