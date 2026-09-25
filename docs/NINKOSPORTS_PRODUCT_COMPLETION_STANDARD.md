# NinkoSports product completion standard

User direction,25 September2026: deliver the depth of a serious live-results service in an original NinkoSports design, not a collection of disconnected widgets. No public launch declaration before the core is stable, complete and tested. Existing public deployment is a verification surface, not proof that this gate is met.

## One connected journey
Live Scores -> competition -> match -> team/player -> back to the same match tab/date/filter. Scores, statuses, kickoff, identifiers and artwork must agree on every step. Canonical old links remain useful. No navigation dead ends, misleading clickable placeholders, invented lineup shapes or made-up results. Data availability differs by competition and must be measured, not concealed with fake content.

## Score Centre
Date navigation in the viewer's timezone; live/upcoming/finished/favorites filters; correct sport-scoped sidebar/counts; real competition and team/participant identity; grouped competitions and group-specific tables; robust updates after reconnect/tab visibility; no disappearing fixtures after details, cache rebuild or restart. Each new change reruns preservation checks and selected actual match-source comparisons.

## Match Centre
Overview: source-backed score, status, periods, venue/referee and readable chronological incidents. Statistics: meaningful categories, full/first/second half as supplied, zero versus unknown distinguished. Lineups: real starters/bench/coach, supplied formations or coordinates, player photos where available, substitutions linked to their people. Player statistics: source-backed metrics with clear column labels. Shots: individual supplied records, team/outcome filters; a graphical shot map only when verified coordinates and orientation exist. Head-to-head and recent form must link correct identities and competitions, without claiming historical completeness from a small sample. Standings preserve exact group/season context. Relevant news remains sport/competition-safe.

## Team, player and competition pages
Team: identity, results/fixtures, squad and relevant table. Player: identity, nationality/role, appearances and supplied performance; return path to origin. Competition: fixtures/results, season/group selector, standings and leaders when supplied. Real routes with useful available content, not buttons opening empty pages. Cross-provider IDs require evidence before merging.

## Sport-specific depth
Football prioritised until score and identity stability. Tennis needs sets, tie-breaks, doubles identities and supplied point history. Basketball needs periods, team/player box scores. Cricket needs innings/scorecards and wickets. Ice hockey/baseball need actual periods/innings and incidents. Motorsport/racing/meets need entries, sessions, classification, gaps/times/positions rather than forced home/away templates. Esports needs series/maps/games and players when available. Never label a sport complete just because one event or its list row works.

## Visual and interaction acceptance
Consistent spacing, type scale, contrast, aligned numbers and restrained accents. Clear score hierarchy, one active navigation level, readable names, deliberate section grouping and no empty cards. Responsive desktop1440, mobile390/320 checks with no page overflow, clipped controls or accidental horizontal scrolling. Keyboard focus and tab selection visible; touch controls usable. Review actual screenshots, not only passing DOM tests. Maintain main-page sets/periods even when compact sidebar omits them.

## Definition of done
A feature is complete only after: verified source example -> parser/storage/public response -> usable UI -> negative/regression tests -> observed successful deployment -> actual production data/browser acceptance -> durable checkpoint. Record remaining gaps and provider/competition scope. Unit tests and successful deployments are necessary, not sufficient. Source availability, licensing and affordability remain constraints; no new paid services or agents without user approval.

C13 begins the connected Match Centre work: real substitution names/goal timeline/added time, cached detail correction, shots and filter controls, evidence-only formation layout and canonical/player navigation. It is not a declaration that every item above is implemented.
