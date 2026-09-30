# NinkoSports News football continuation — 30 September 2026

## Scope and release

- User requested News only; continue football first. No Live Scores changes.
- No Railway Agent calls. Direct GitHub and Railway tools only.
- Production News branch: `ops/news-free-probe-20260926`.
- Code release: `95443dc5fed911b89318c0853c7c493724cb0590`; initial release `42599a1ccae84f3147f2e047b41c36db2ff901ab`.
- Tested tree: `1d995b507ecf93284efb4ab9c963baf4bfda03e3` (identical local/GitHub tree).
- News service: `hopeful-blessing` / `be857be7-a029-4663-81c7-bcde75efc482`.
- Project/environment: `17f6ebff-0f6b-42dd-be86-35ca9ca40301` / `cb27d851-9198-47c8-a733-8356e8b6cf63`.
- Final deployment: `dc1b817b-cc56-4660-b610-eca80889141a`, reported SUCCESS with exact final release SHA. Initial deployment: `2658e6c1-e8bc-43a2-bc55-65ebc8da0169`.
- Final runtime began at 04:21 UTC; scheduled interval remains ten minutes. The 04:25 UTC maintenance job completed successfully at 04:26:17 UTC. First writer cycle after this final deploy is scheduled for 04:30 UTC (not yet observed at acceptance).

## Changes and evidence

1. Reject online body-double/alien conspiracy stories at source admission and again after rewriting. French source headlines and softened English headlines are covered. Formal sporting sanctions, legitimate club appeals and normal social announcements remain admissible.
2. Recognize the audited England/Czechia Nations League recap family across four substantially different headlines, requiring the winner, competition, five named participants and dismissal context. Source timestamps must be within 24 hours. Coach reaction, injury, youth/women, different-score and preview stories do not match. This is a narrow confirmed incident repair, not a general solution to all cross-source duplicates.
3. Accept equivalent German score formatting only in explicit sporting grammar, including the parenthesized half-time score before `-Erfolg`, `nach dem ... zum Auftakt gegen`, and `mit ... gegen ... verloren/gewonnen`. No clock, ratio or score reversal is authorized.
4. Public repairs create durable incidents and retain article/source rows. Reindexing must not resurrect held duplicates.

Observed before release: public 22262 and 22274 were conspiracy stories; 22267/22272/22277 repeated the same recap; 22264 was a distinct Czech coach reaction and must remain public. A fourth pre-release duplicate, 22280, had the same source time as 22272 and used the verb defeats. The follow-up accepts that verb under the same evidence requirements. Newest public row policy keeps 22280 in that tie. Public 22242/22230 are separate commission/club-response reporting and must remain.

## Validation

- 350 focused News tests passed; News artifact preflight passed.
- Cases cover source and rewritten conspiracy leads, protected formal sporting events, numeric equivalence and non-equivalence, duplicate intake, public repair, archive retention, durable incidents, repeated maintenance and the 24-hour date boundary.
- Only changed runtime paths: `bot/dedupe.py`, `bot/news_policy.py`, `public_index.py`; one new News test file.
- Backend API and results-worker were not deployed or reconfigured.

## Operational deployment lesson

A direct Railway `redeploy` reused the old e947e27 code. Setting only `NEWS_DEPLOY_REV` on the News service with `skipDeploys=false` built the current branch SHA. Always verify deployment metadata and runtime source hashes; SUCCESS alone is insufficient. Do not redeploy the API or results-worker for News changes.

CLI Git push has no HTTPS credentials in this environment. The connected GitHub account is `macamala`, admin of the already-public `macamala/allball-backend` repository. Blob/tree/commit/ref operations were used; the resulting tree was checked against the tested local tree. No secrets were placed in commits, logs or this record.

## Remaining football work

- News is NOT complete. Continue major European leagues, UEFA/FIFA and Crvena zvezda first.
- New originals are being written automatically, but provider quotas still limit throughput. Gemini successfully wrote articles and another provider validated them; Groq and Mistral quota rejections were observed. Do not claim 500 originals/day proven.
- DeepL translation hit the configured daily character allowance (`requested=11082`); six-language coverage is not complete. Do not silently raise quotas or enable paid modes.
- Several explicit Nations League News cards still have no competition label. The News taxonomy catalog lacks the matching competition entry; fix with category/source evidence and verify the already-deployed API/frontend can display it, without changing Live Scores.
- Sources disagree on some match minutes. Deduplication is not fact verification; avoid merging their numbers into one invented account.
- Other Manchester City articles contain distinct verdict details, club responses and sanctions procedure. Do not collapse these solely because the club name repeats.

## Production acceptance

- Initial release recorded conspiracy holds for 22262/22274 at 04:18 UTC and duplicate holds for 22267/22277 at 04:20 UTC.
- Final release regular maintenance recorded `held duplicate article=22272 kept_article=22280`, then `changed=1 images=0 taxonomy=0 gossip=0 duplicates=1`; scheduled job completed successfully at 04:26:17 UTC.
- Final public API checks passed: 22262, 22274, 22267, 22272 and 22277 are absent from the current public cards; 22280, coach reaction 22264, commission report 22242, club response 22230 and Zvezda 22217 remain present.
- Hidden detail URLs for 22262/22274/22267/22272/22277 return 404; coach reaction detail 22264 returns 200. Holds preserve source/article records in storage by design; no deletion code was added or executed.
- The 100-card football sample has no missing image URL; startup image audit also reported 160 checks and zero failed images on the initial release.
- Backend API deployment is still `a6018808-ec70-44a9-8ddc-5a65b30f9c57`; results-worker still `25287c7e-08a8-46f8-aa3b-0d85ba6eaf53`, both from September 27. Neither was restarted, deployed or reconfigured.
- New writing was observed before deployment (e.g. articles 22273–22280); do not describe a completed post-final-deploy writer cycle as verified. The runtime scheduler and the final periodic maintenance job are verified.
