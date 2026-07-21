# Documentation Audit — 2026-07-21

## Scope

This audit compared repository documentation with current API routes, migrations, Compose configuration, data synchronization policy, example catalog and experiment-batch implementation. It did not delete historical issue descriptions or point-in-time evidence.

## Updated Sources of Truth

| Document | Audit result |
| --- | --- |
| `README.md` | Added current capability snapshot, document index, 10-dataset policy, batches, previews, Docs and report behavior |
| `docs/architecture.md` | Rewritten to match MySQL-only runtime, queue split, data sync, experiment batches, storage ownership and recovery |
| `docs/data_pipeline.md` | Reconciled one-click/on-demand policy, correctness checks, raw archive model, disk safety and previews |
| `docs/api.md` | Added preflight, examples, experiment batches, preview/on-demand/CSV template, report objects/export, help and database outage semantics |
| `docs/deployment.md` | Added full worker/beat profile, build semantics, MySQL memory defaults, bounded retry and OOM diagnostics |
| `docs/roadmap.md` | Marked implemented batch/rolling/walk-forward/Markdown features and retained real remaining gaps |
| `docs/help/*` | Rebuilt as a catalog-driven tutorial/reference center with GFM tables, deep links, screenshots, complete workflow guides and historical labeling |
| Web/backend/frontend READMEs | Updated feature lists and complete Compose worker topology |

The help center now directly serves selected canonical repository documents instead of copying them into a second reference tree. Its generated API index is checked against FastAPI OpenAPI, and `scripts/check_help_docs.py` validates every catalog source, relative Markdown link and screenshot.

## Historical Preservation

- `docs/history/platform-audit-2026-07.md` remains the full 2026-07-04 review and issue register. A dated status delta was added at the top; old issue text, counts, commands and two-week plan remain unchanged.
- `docs/stock_migration.md` remains a historical migration decision record.
- `docs/history/2026-07-platform-fixes.md` records the July sync, storage, Preview, startup, MySQL and report incidents with symptom, root cause, fix and remaining risk.
- Future fixes should update status or add a new dated record, not erase the motivating failure.

## Authoritative Dynamic Interfaces

Some inventories change more frequently than prose. Use these interfaces as authoritative:

- API routes and schemas: `/openapi.json` and `/docs`.
- Strategy templates: `GET /api/strategies/templates`.
- Examples: `GET /api/examples` and `examples/catalog.json`.
- Provider policy and permission: `GET /api/data/catalog`.
- Runtime migrations: `scripts/db_migrate.py --status --json`.
- In-app articles: `GET /api/help/articles` backed by `docs/help/catalog.json`; catalog entries may point to approved Markdown under `docs/`.

## Known Remaining Documentation Work

- Re-capture the tracked E2E screenshots with `npm run docs:screenshots` after material UI layout changes.
- Add a production backup/restore drill transcript after the first scheduled exercise.
- Add exchange-specific futures/options and convertible-bond runbooks when their acceptance gates are complete.
- Keep environment defaults synchronized with `.env.example` and Compose whenever resource tuning changes.
