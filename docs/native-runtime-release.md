# Native LEAN runtime release contract

Native execution never follows LEAN master and production hosts do not build
LEAN. CI must build the exact commit in `config/runtime/lean-native.lock.json`
for each supported RID, package the Release launcher and its dedicated Python
3.11.11 environment, generate a CycloneDX SBOM, and sign the archive with the
release key corresponding to `config/release-signing-public.pem`.

The lock artifact entry requires immutable HTTPS URLs for the archive,
detached Ed25519 signature, and SBOM plus the archive SHA-256. The SBOM metadata
must contain:

```text
lean.runtime.id=<runtimeId>
lean.runtime.sha256=<archive sha256>
```

`supported` remains `false` in the checked-in bootstrap lock until release
engineering publishes those immutable artifacts and fills every identity and
digest. The installer and runner fail closed while it is false.
