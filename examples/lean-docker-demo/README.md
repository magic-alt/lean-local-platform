# LEAN Docker Demo

This directory contains the standalone EMA-cross example that previously lived
in the repository root. It is not used by the Web API or production workers.

Run the direct Docker example:

```bash
./examples/lean-docker-demo/run.sh
```

Use the legacy teaching CLI:

```bash
python3 examples/lean-docker-demo/local_platform.py --help
```

Market data defaults to the workspace-level `Data` directory and can be
overridden with `LEAN_DATA_DIR`. Generated files are written under
`web/runtime/examples/lean-docker-demo/` and are intentionally excluded from
Git.
