# Native deployment

Linux is the production native target. macOS is supported as a workstation
using the local process manager; Windows remains experimental.

1. Configure private values from `config/deployment/native.env.example`.
2. Run `python scripts/platformctl.py --mode native doctor`.
3. Run `python scripts/platformctl.py --mode native bootstrap --install-deps`.
4. Install the pinned runtime with `python scripts/platformctl.py --mode native runtime install`.
5. For Linux production, review the units and run
   `python scripts/platformctl.py --mode native install --system`.

The installer never invokes a system package manager. Production native
backtests fail closed unless the pinned runtime, signature, SBOM, dotnet
runtime, and bubblewrap sandbox are ready.
