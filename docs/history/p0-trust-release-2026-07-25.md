# P0 trust and data-coverage release — 2026-07-25

This acceptance closes the four P0 items in the living roadmap. It does not
change the historical conclusions recorded by earlier audits and does not
promote Level 4 or Level 5.

## Result

Overall result: `PASS`.

- The independent Source/QA/reference matrix passed against certified TuShare
  production data. The positive path passed ten gates; uncertified provider
  labels, a forged certification flag, a Critical QA report and an injected
  PIT/reference gap were all rejected.
- The official CSI300 chain now covers 2005-04-08 onward. It contains 1,850
  official membership events, 1,225 intervals and 70 persisted source
  artifacts. Launch membership is reconstructed from the official 2005-07-01
  300-member snapshot and official early events; current constituents are not
  used as a historical seed.
- The retained official bundle contains 124 files. Its bundle SHA-256 is
  `309f2f3a24510add6d6d3f5023b48c35b51a913edd3806d20b95403b87c2dc31`.
  Independent SQL checks returned exactly 300 members on the launch date,
  2005-07-01 and every sampled year-end trading date through 2017.
- Real LEAN runs `600519-20260601-20260722-20260725062226` and
  `600519-20260601-20260722-20260725062337` share input fingerprint
  `ba9473993680043d8b8b96ef3a0b8d4d7e855a41c6cc74b552250dc760ee41a6`
  and canonical result digest
  `e0e620a87c7206a815945b8b7046a3f07da10daff7df0b26e31bcab8584b28c5`.
  The digest was recomputed from each raw result file. Ending equity, fill
  count and completed date also match; raw digests differ as expected because
  run-local metadata is excluded from the canonical result.
- Ten-dataset run `b15c8791-1e35-499d-9730-6b4d4e42164b` passed every
  manifest/watermark/archive item and active stored-object integrity. All 37
  historical quarantined references remain in the issue ledger: 36 are
  superseded by verified archives and one by lossless canonical evidence.
  Remaining open issue count is zero.

## Evidence and reproduction

- `audit-output/p0-trust-2026-07-25/release-trust-evidence.json`
- `audit-output/p0-trust-2026-07-25/archive-reconciliation.json`
- `audit-output/p0-trust-2026-07-25/SHA256SUMS`
- `config/data-sources/csi300_pit_sources.json`

```bash
web/backend/.venv/bin/python scripts/import_csindex_csi300_pit.py --dry-run
web/backend/.venv/bin/python scripts/import_csindex_csi300_pit.py \
  --offline --dry-run
web/backend/.venv/bin/python scripts/reconcile_provider_archives.py
web/backend/.venv/bin/python scripts/run_p0_trust_release.py
```
