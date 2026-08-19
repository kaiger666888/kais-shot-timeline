# Phase 18 Deferred Items

Out-of-scope discoveries logged during execution (not fixed by executors — surface to orchestrator/verifier).

| # | Found | Item | Impact |
|---|-------|------|--------|
| 1 | 18-01 execution (2026-08-19) | Working tree carries uncommitted deletion of 5 v1.2-era research files (`.planning/research/{ARCHITECTURE,FEATURES,PITFALLS,STACK,audio-spike-report}.md`) — content already archived under `.planning/milestones/v1.2-research/`; deletion itself never committed by the milestone transition. | Cosmetic/git-hygiene only. Left untouched by 18-01 (scope boundary). Whichever agent commits next should either commit the deletions or restore the files; do not lose track of them. |
