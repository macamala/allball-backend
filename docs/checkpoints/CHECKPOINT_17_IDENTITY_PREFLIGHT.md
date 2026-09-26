# C17 identity/date release preflight — 26 September 2026

This record is a preflight, not final production acceptance.

## Exact current and tested refs

Fresh backend main: `6a849ddbbaa0b7e3d4c44b4bb713978cf094a5e0` (C17B). Frontend remains already deployed/tested `9a9d1cc996f746a63d4716043b849a7b12e57538`.

Combined backend candidate: `b221c579387704e12e8a000414d97102b28e9b6c` on `fix/football-c17-team-categories`. It includes date candidate `0d20c7c5c8a83cd4653ab756519a12d9353eb971`. Normal compare is ahead 8, behind 0. Eight files total: two isolated CI workflows, four runtime files and two test files. Runtime modifications are read-side profiles only, not score writes or scheduler changes.

## Real defects reproduced

1. Actual native player `1090170`, Katarina Dybvik Sunde, supplied Unix millisecond career start/end dates. String slicing raised TypeError and discarded otherwise valid club, birth date, position, career and season facts. The date helper now accepts explicit ISO and Unix seconds/milliseconds; invalid/empty dates remain null. It does not invent values or match appearances.
2. Public team `4500`, requested as Aalesund, correctly resolved to Aalesund (W), but its history also contained male Aalesund ID `8404` in `norway-eliteserien`. Native team 4500 explicitly identifies female/Toppserien. Exact category anchors now exclude opposite-category namesakes, retain same-category provider joins, fail closed on contradictory anchors, and retain unknown rows only when exact IDs justify them. Legacy women's competition links use the verified public key. No stored record is deleted.

Actual read-only team probe: run `36216190708`, artifact `10897990765`, ZIP SHA256 `bc657eb12236402397725f85186aec695a71627bb6423a34ce3565dfc035b987`.

## Actual gates and independently checked artifacts

Date gate `36216131295`: SUCCESS, 997 backend tests, no failures/errors/skips, plus captured native male/female player replay. Artifact `10897078334`, SHA256 `cd423e042393ab2c743edec3aa130fe6b6653a3ec40e8e95c4e8bc3d5493f883`.

Combined gate `36216465434`: SUCCESS. Downloaded JUnit contains **1004 tests, zero failures/errors/skips**. Artifact `10897442078`, ZIP SHA256 `14f136bc0442633543ce9643db2fbaff12e3a4555e38547563af53d0a6bc07da`. Source patch SHA256 `68d98d7348d422dab236955e40164f0fef01f958baaa0dab5768560e3ecb181e`. Every runtime/test file checksum matches the reviewed local files. Actual captured club replay retains all three DB rows unchanged, while women's public history correctly returns only `ninko-evt-502d99d773c36f1850cd` and `ninko-evt-99b63e4a2de717c9139b`, category women, Toppserien only. Local focused suite 61 passed.

C17B actual public run `36215852994` already passed retained live/mobile and rich/home/existing-profile checks. Category/scorer API checks preserved all 912 control IDs, matched 838 native category identities with no mismatches and separated 18 women's MX hub records from 151 men's records; new female profile enrichment still failed due the date defect above. That run is NOT an overall pass.

Two final QA assumptions are strengthened, not runtime defects: full women's season fixtures must be checked against the full hub rather than a four-day cohort; player source says current club Aalesund while actual native club says Aalesund (W), so browser must match exact native club ID/name/gender. Final preparation adds native club checks, no cross-category events, and actual female fixture-to-match navigation.

## Release boundary

Release only this exact tested backend candidate by nonforce main fast-forward; frontend stays unchanged. Confirm actual matching terminal API/worker deploys. Then run final production API and real Chromium 1440/390/320 acceptance using both audit preparation scripts, retain the 912-ID baseline, and inspect screenshots. No Railway Agent, settings changes, staged patches, services, database resets, manual result writes, or force pushes.

Remaining global backlog is unchanged: source-only season rich details, remaining tables and old links, complete transfers, globally complete scorers/brackets/assets and other sports/news. Save final checkpoint and issue #6 evidence after actual acceptance; do not claim global completion.
