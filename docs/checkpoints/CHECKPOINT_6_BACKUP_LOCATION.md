# Checkpoint #6 — saved WIP and validation evidence

The checkpoint status record is `NINKOSPORTS_CHECKPOINT_6_2026-09-25.md` in this directory. No production branch was moved while saving checkpoint #6.

## Durable backup
- Private ChatGPT Library path: `/NinkoSports/Checkpoints/NinkoSports_Checkpoint_6_Backup.zip`.
- Filename: `NinkoSports_Checkpoint_6_Backup.zip`.
- Archive size: 16,925 bytes; 11 members.
- Archive SHA-256: `f77a93bae634800ab7d1299975c1d248c69f43bf6b8d8cc6e84d63ace12b3fb6`.
- Local zip integrity and every member hash in manifest.json were verified before the successful Library upload.
- This is a saved code/evidence backup, NOT a database backup and NOT a production-ready release.

## Contents
- `patches/mobile-responsive.patch`: six frontend files, not deployed. Base `macamala/allball-frontend@93dd66e65231cb36967dcfe43e6355784ae3e8fd`. Patch SHA-256 `80865fce8c15ccfd255face6a7975a12fb4d3c8fe097830f45a67217a49d5f1e`.
- `patches/backend-lineage-wip.patch`: adds only failing maintenance/lineage reproduction tests, not an implementation. Base `macamala/allball-backend@8a17ffa57a2227392d3ff1211fc630f22c2981fd`. Patch SHA-256 `f4ba5bee209ac4f7c25ece4face118a3f42aa96faf9560c94465dc38aa614bca`.
- `tests/test_maintenance_lineage.py`: readable reproduction source.
- Mobile focused-test/build logs, baseline failing lineage-test log, latest failing acceptance JSON, compact old/latest score summaries, manifest and README.

## Safe restore from another chat/session
1. Read the checkpoint issue and this directory before any code or infrastructure changes.
2. Use Files list at the exact Library folder above to resolve the saved ZIP. Materialize the actual returned file reference when container bytes are needed; do not infer a sandbox path.
3. Verify archive SHA-256, unzip into a new directory and verify member hashes against manifest.json.
4. Fetch current repository heads. Inspect/apply the correct patch only on an isolated checkout of the stated base; run `git apply --check` first. If heads changed, reconcile instead of overwriting.
5. Mobile has eight focused local tests/build passed only. Backend has eight selected failing reproductions and nine deselected cases; planned maintenance-policy implementation is absent. Re-run and finish the appropriate suite before publication.
6. Latest archived production acceptance remains FAILED (7/8 finals, Andorra-Malta keeper/alias regression). An earlier 8/8 snapshot is not a current all-clear. Never call this checkpoint a stable production release.

The private Library archive is authoritative for WIP bytes. Do not rely on unreferenced Git objects, expired GitHub Actions artifacts, temporary container paths, or the transcript as the sole backup.
