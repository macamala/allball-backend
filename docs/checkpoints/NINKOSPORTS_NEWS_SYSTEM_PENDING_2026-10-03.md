# Football News combined release — 3 October 2026

Tested clean candidate: `2e1a2d8bf72879953403ec9ff989a17839ba8764` on `audit/news-system-release-20261003`, based on deployed `f22e5b603317a12839e123e62b487dbee740fbd5`.

GitHub Actions 37103443217: SUCCESS, 1,914 News/text/deduplication tests on Python 3.12, zero failures/errors. All 23 production files were byte-checked against the tested local files before and after the Git commit. Aggregate checksum: f6bf48ff4f9b6e1f7d3004c25a407a80b17630004c6307c37ad874043c929a78.

Actual-source replay at 06:35 UTC: 10 eligible inputs, not publications. Known menus Brazil Serie B, Croatia HNL, Hungary NB I/NB II, Sweden Allsvenskan. Hungary mixed-tier friendly kept its primary Kisvarda club rather than its NB II opponent. Brazil's bare Serie B reference no longer becomes Italian Serie B. Unknown stories stay unknown.

Actual 60-article public replay identified only duplicate draw-report IDs 22751 and 22770; reaction/interview IDs 22759, 22710, 22731 and 22714 were not selected. Candidate repair holds a duplicate's public classification, without deleting its original row or changing its date/text.

This is a pre-deployment recovery anchor. Do not claim production deployment, new publication gains or 100% coverage from this record. The new source branch is safe to fast-forward only after rechecking current production and Railway state. Shared API/results-worker/frontend remain outside the release.
