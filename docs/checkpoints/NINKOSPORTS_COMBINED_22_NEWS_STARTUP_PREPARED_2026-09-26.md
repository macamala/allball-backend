# Prepared checkpoint 22 — News startup safeguards, 26 September 2026

## Status and ownership

**Prepared and jointly tested, NOT deployed. C20 remains the production release.** This is the latest prepared News startup follow-up to C21, not a new production checkpoint or a claim that News/Football is complete. This primary chat remains sole integration/deployment owner; backend issues6 and8 stay open.

User asked to continue after News03 integration preparation. Review found real startup/history gaps in C21, and this pass corrected them without starting News, modifying production flags, buying resources or touching Live Scores source.

## Exact refs

- Production backend main, freshly read at start and end: `ba0b70017fa2d96717ce4c4f8e40e2ac95ec3726` (C20).
- Production frontend master, freshly read at start and end: `7183733e5eed7dae566aeaf1632fc757c547cc4c` (unchanged).
- Prepared C21 tested candidate: `39b49492fe38fdac50a7320673d4c7e244c6dae2`; C21 documentation/base for this branch: `833d24c354fe326da64ed2a4a9478eaa3b56ea92`.
- **New exact tested C22 candidate: `e844681d794d8303623e48a2b079fdcd33dc545d`.**
- Branch: `fix/news03-startup-c22-20260926`.
- This later checkpoint commit changes documentation only.
- Original News03 `f08633d0221fbf9d9850f291dbab4ffe927c11c7` remains integrated in the prepared ancestry; C22 intentionally strengthens its budget configuration and the previously retained scheduler/preflight.

Before work, current main/master, issues6/8 and C21/source were read. Latest observed parallel News04 notice is issue8 comment5844711180: its separate branch `news/sources-identity-20260926-04` also starts from C21 and reserves source/identity work, not scheduler/preflight. News04 was NOT merged or altered in this pass. Later integration must reconcile the two deltas on then-current main.

## Defects corrected in the prepared code

### Explicit request approval is no longer inferred from defaults

C21 configured_budget inherited the accepted-article allowance for per-run requests and defaulted to40daily. The configured production path now requires BOTH explicit valid NEWS_AI_MAX_REQUESTS_PER_RUN and NEWS_AI_MAX_REQUESTS_PER_DAY. Missing/invalid settings produce a disabled budget; zero stops processing. Out-of-range/non-ASCII/float/negative settings are rejected rather than silently clamped.

The existing hard maximums20/run and200/day are validation ceilings, NOT user spending approval. No actual quota was configured. Direct constructor values used by fixtures are not production approval. Request counts still are not a monetary/token/account-wide cap. Failed and retry requests keep consuming reservations under the retained News03 accounting.

### Guard before database-bound imports and direct startup

News02 preflight keeps the existing service identity, explicit News enablement, disabled results flags, PostgreSQL syntax, interval/article bounds and legacy acknowledgement checks. It now additionally validates explicit request/history/expansion settings, nonempty AI-key presence without logging its value, and ledger-under-volume paths. Before --run exec it checks actual storage metadata.

`bot.scheduler` no longer imports database-bound News/public modules merely when imported. Both explicit job() and direct `python -m bot.scheduler` validate first. An unconfigured direct module invocation refuses startup with exit78 before database import/ingestion. The normal Docker startup also exits78 when configuration is absent. No guard or acknowledgement was removed.

### History disabled means the scheduler skips its old index lane too

C21 repair functions defaulted off, but scheduler still ran an unconditional index_missing loop over old articles. C22 places summary repair, old-index work and contaminated repair behind the explicit historical flag. With NEWS_HISTORICAL_REPAIR_ENABLED=0 they are not invoked by the scheduler and the historical SessionLocal is not opened.

Even a future explicitly approved history run is bounded: one summary page, one index batch with limit400, one contaminated-repair page. There is no unbounded old-index loop. Historical AI work and new articles share ONE actual-request context in the cycle. This does not certify the factuality/originality of existing articles or authorize historical repair; required eventual production value remains0.

The initial collection path and each scheduled cycle recheck flags. Exhausted, zero or unavailable budgets stop before its ingestion/history IO. Idle no-article cycles do not unnecessarily invalidate public cache. Exception logs use exception class names, not potentially credential-bearing URL strings.

### Storage and one shared-ledger owner

New stdlib-only news_runtime.py checks absolute paths, actual Linux mountinfo, the declared mount as the deepest covering mount, existing parent directories, symlink/hardlink/regular-file conditions, read-only mounts and obvious ephemeral filesystems. It does not create a mount, directory or ledger during inspection and does not pretend an ordinary directory is durable storage.

A nonblocking exclusive lock on the ledger's stable .worker.lock inode prevents a second cooperating scheduler on the SAME shared ledger from starting. The file is not unlinked. Ownership stays held until running scheduler jobs have shut down, and is released on close/error.

**Boundaries:** filesystem metadata is not operator approval, proof of Railway deployment persistence, backup, or proof no unrelated News process exists. Separate ledgers/workers/hosts do not become one global cap through this lock. Production still requires actual approved durable storage, source/DB/config verification and a single News owner. No new storage or remote probe was created.

## Scope and preservation

Compared with the C21 documentation base, tested C22 is ahead11/behind0 with10files:

Runtime/deployment (4): new news_runtime.py; modified bot/news_budget.py, bot/scheduler.py and deploy/news/preflight.py.
Tests (3): new tests/test_c22_news_runtime.py and tests/test_c22_news_scheduler.py; existing tests/test_news_deploy_contract.py success fixture now supplies the new mandatory values and isolates its exec-target unit from real mount checks.
Audit/gate (3): audit/c22_apply_review.py, audit/c22_image_storage_probe.py, .github/workflows/c22-news-startup.yml.

**537 other tracked C21 paths are byte-identical**, including all collector/results/identity/alias/category/delta protections, app.py, models/database/schema, News03 article/source policies, public editorial/read/index logic, requirements and deploy/news/Dockerfile. The unchanged Docker recipe already copies root *.py, including the new helper. No frontend source or deployment changed. Tests/test_auth.py was NOT weakened or modified.

Seven final reviewed runtime/test hashes, and all537 protected hashes, were verified against the downloaded actual tested-source archive and reviewed local files. Source patch SHA256: `b9dd623c252a684eebb64c38779c89a450340fe06169af482b572c1c1823a7ca`.

## Actual final validation

**GitHub Actions run36231550050 / job108375535822: all steps SUCCESS.** Workflow head040ce552f70eead0120df7a991caa86a54d6f2ac; final source candidate is e844681d... above.

- **1,395 selected combined backend cases,0failures,0errors,0skips**, across82files. Includes C21's1327 cases,67new C22 cases and one additional parameterized required-file case. This is the combined retained selection, not every unrelated repository test.
- Five representative new assertions against unchanged C21 each failed by assertion, with no collection errors. These reproduce implicit run/day allowance, missing-cap preflight acceptance, early database import/direct startup, and unconditional historical indexing.
- The actual unchanged News Docker recipe built from the combined source; Python3.12.14; inspection preflight passed.
- Actual default image invocation and explicit python -m bot.scheduler each refused unconfigured startup with exit78. Diagnostics contain fixed codes, not fixture secrets.
- A real CI bind-mounted directory was reused by two separate Docker containers. The first reserved2 fixture attempts, the second could reserve only1more then was denied at3. A container without that mount rejected storage and created no ledger. **These were fixture reservations,0realAIcalls; this is NOT a Railway restart/deploy persistence test.**
- Real child-process tests cover exclusive ownership, release after exception and rejection of symlinked lock files. Retained C21 multi-process same-ledger accounting tests remain in the combined run.
- Runtime test containers used --network none, ephemeral data and mocked source/AI; ordinary dependency downloads occurred during image build. No production credentials or DB were used.
- Local focused131-case suite passed. An additional local attempt including test_auth could not collect because this container lacks feedparser; it is NOT reported as a passed full gate. The real dependency-compatible CI result above is the full selected-suite evidence.

No new frontend suite/build/browser run was needed for this backend-only continuation. Last frontend329tests/build belong to C21, not a new C22 result. No production mobile/desktop/asset validation or real source-to-public article is claimed.

### Downloaded evidence

Final artifact10902766045 / c22-news-startup-evidence:1,381,112bytes, ZIP SHA256 **91c474b2717cbcf2d2ef54d0433885216939c61ff988602491054a36a0671ef3**. ZIP integrity, actual baseline/final JUnit, candidate marker, default/direct reports, three container storage JSONs and seven reviewed+537protected source hashes were independently checked. Archive includes exact committed source and diff. Artifacts have30-day retention; committed source/tests/checkpoint remain durable records, not database backups.

Initial run36231281729 is retained as FAILURE:1394passed/1failed of1395. Its sole failing old architecture check required the documented phrase `never mass-rewrite historical articles`; the rewrite had omitted that phrase. It was restored truthfully in the scheduler docstring, its checksum updated, and the entire gate rerun. No old assertion was deleted or relaxed. Later container startup/mount steps had not executed in the failed run and were only accepted after the final successful run. Failed artifact10901648993 ZIP SHA2561ec08505ba48af65482cf2889dcc263fd1389338b5d70c556e4736caba360041 was downloaded/integrity-checked too.

## Current production and activation blockers

Main/master remain C20/frontend7183733..., verified again after the final gate. This pass performed0deployments,0externalAIrequests,0newconfirmedpublicNews03articles,0manualscorewrites and0historicalproductionrewrites.

Direct Railway status in this continuation still reports no News volume and the same existing deployments:
- API b9d2539c-b8cc-49b9-bd31-68e39bb50039, C20.
- results-worker98ceeeb2-9762-4686-81da-fc9e0c44521a, C20.
- existing News hopeful-blessing/be857be7-a029-4663-81c7-bcde75efc482 remains deployment79f761eb-3afc-457a-b222-15c1a5c63088 from20September; volumes:[]. Its old Node/Python mismatch is not fixed by saving this candidate.

No approved persistent ledger path, explicit spending/request allowance, verified backend binding/root, non-secret database identity, actual flags or independent single-owner evidence has been established. Previous variable redaction remains an access boundary, not a reason to expose credentials through another route. No new storage/subscription/resource was purchased and no acknowledgement/enablement flag was imposed. The unrelated staged Railway patch for audit-scheduler-lease remains untouched.

No Railway Agent or TinyFish used this pass; no screenshots/images sent and no plugin chores requested from the user. No production DB reset, main/master rewrite, forced ref, service replacement or frontend redeploy.

## Exact continuation and release boundary

1. Read this prepared checkpoint, current issues6/8 and current refs. Do not reset main to prepared News branches or reapply C18/C20. C22 already contains prepared C21+News03; production still contains C20. News04 is a separate parallel source/identity delta, not automatically included.
2. Obtain the user's explicit spending ceiling and approved actual-request allowances, and establish an approved persistent ledger location on the EXISTING News service. Code ceilings and fixture2/3 are not approval. No new paid resource before explicit consent.
3. Confirm correct backend source/root/approved revision, actual non-secret configuration and one News owner via authorized access. Preserve existing service identities/results-disabled flags and News02 legacy review. Do not use Agent as a secret-redaction workaround.
4. Verify the ledger survives an actual approved Railway restart/deployment without an AI call, and record retention/backup/single-owner evidence. The CI mount proof is not a substitute.
5. Keep historical0; leave expanded feeds disabled until selected source extraction, factual/source attribution and image rights/credit review. Required credits/public sanitizer behavior remain separately unresolved, not repaired by C22.
6. Reconcile any newer Live Scores/News04 changes on current main, run joint gates for the exact release, save current-ref/config rollback preflight, then deploy only necessary services. No frontend changes implies no automatic frontend redeploy.
7. Only then run a bounded approved source->extraction->originaldraft->DB->publicarticle check with original dates, internal link, suitable photo/credits, duplicates and real desktop/mobile review, plus retained Live Scores before/after checks.
8. On future News failure, stop only its process via authorized service-specific action, preserve ledger/articles/results, and use a reviewed forward revert of only offending News code. Never reset DB or roll back completed football changes. No rollback executed here.

Still open: News actual activation/fresh production content,14missing source adapters/stale alternatives, credit/image/factuality checks, stale homepage selection; C20's remaining current/future source conflicts and complete rich MatchCentres/tables/oldlinks/transfers/scorers/brackets/assets. Their historical counts are not new C22 production measurements.
