# Native deployment

Linux is the production native target. macOS is supported as a workstation
using the local process manager. The Windows architecture and implementation
are feature complete, but Dockerless Core is not accepted until a signed
`windows-x64` runtime and clean-host Golden Acceptance exist; Windows
production remains uncertified until the separate 12-hour fault matrix passes.

1. Configure private values from `config/deployment/native.env.example`. On
   Windows use `config/deployment/windows-native.env.example` instead.
2. Run `python scripts/platformctl.py --mode native doctor`.
3. Run `python scripts/platformctl.py --mode native bootstrap --install-deps`.
4. Install the pinned runtime with `python scripts/platformctl.py --mode native runtime install`.
5. For Linux production, review the units and run
   `python scripts/platformctl.py --mode native install --system`.

The installer never invokes a system package manager. Production native
backtests fail closed unless the pinned runtime, signature, SBOM, dotnet
runtime, and bubblewrap sandbox are ready.
