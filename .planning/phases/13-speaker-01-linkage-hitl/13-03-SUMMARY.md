---
phase: 13-speaker-01-linkage-hitl
plan: 03
subsystem: speaker-linkage-hitl-e2e-proof
tags: [end-to-end-proof, sc5-round-trip, idempotency-proof, xss-regression, smoke-harness, fixture, speaker-01, dia-02, dia-03]
requires:
  - 13-01 (registry/link_speakers.py confirmed-only apply gate)
  - 13-02 (html/gen_speaker_review.py HITL review HTML)
  - 13-CONTEXT (SC#5 round-trip composition lock)
  - spec/fixtures/v1.2/{audio_semantic,characters,shots,speakers}.json
  - spec/schemas/{speaker-edits,speakers}.schema.json
  - scripts/verify_contract.py:_producer_registry_integrity (Plan 01 Task 2 extension)
provides:
  - tests/fixtures/speaker_edits_phase13_smoke.json (frozen operator-decision surrogate — the SC#5 shape)
  - scripts/verify_phase13_smoke.sh (regression gate for future Phase 14/15/16 changes — any drift in canonical shape or schemas breaks the assertions)
  - PHASE13_ROUND_TRIP_PASS marker (proves SC#5 end-to-end on the canonical v1.2 fixture set)
affects: []
tech-stack:
  added: []
  patterns:
    - bash smoke orchestration mirroring tests/run_audio_analysis_smoke.sh (no stub server — both Plan 01 + Plan 02 CLIs are file-in/file-out)
    - trap-cleanup workdir isolation ($WORK = /tmp/p13-smoke-$$; rm -rf on EXIT)
    - READ-ONLY canonical-fixture discipline + git diff guard (T-13-14 mitigation)
    - 5-scenario PASS/FAIL pattern with helper functions (assert_grep / assert_not_grep / assert_py / assert_schema)
key-files:
  created:
    - tests/fixtures/speaker_edits_phase13_smoke.json
    - scripts/verify_phase13_smoke.sh
  modified: []
decisions:
  - SC#5 round-trip proven by composition — Plan 01 + Plan 02 CLIs wired together on the canonical v1.2 fixture, NOT a new code path. The smoke replays the operator's single-shot HITL decision deterministically (frozen fixture = the human review surrogate).
  - Confirmed-only gate proven via synthetic spk_003 augmentation (copy-to-/tmp, not canonical mutation) — keeps the canonical 2-speaker fixture pristine while still exercising reject_ids semantics end-to-end.
  - XSS regression proof strengthened (Rule 1 deviation) — added a valid-speaker shot alongside the malformed-spk_id poison shot so the dropdown actually renders and _esc is provably exercised on the poisoned char name.
metrics:
  duration: ~1m39s
  completed: 2026-07-26
  tasks: 1/1
  files_created: 2
  scenarios_passing: 5/5
---

# Phase 13 Plan 03: SPEAKER-01 Linkage HITL — SC#5 End-to-End Round-Trip Smoke Summary

Frozen operator-decision fixture + 5-scenario bash smoke harness proving the full SPEAKER-01 HITL round-trip (audio_semantic + characters → gen_speaker_review HTML → frozen speaker-edits → link_speakers → canonical speakers.json) is schema-valid, byte-identical across re-applies, confirmed-only-gated, XSS-hardened, and accepted by the producer-side integrity check.

## What Was Built (SC#5 proof of composition)

Two test artifacts, **zero production code changes** (Plan 01 + Plan 02 already delivered the production code in waves 1; Plan 03 wires the e2e proof that they COMPOSE correctly — the same composition Phase 14 will wire into run_pipeline.py).

### 1. `tests/fixtures/speaker_edits_phase13_smoke.json`

The frozen operator-decision surrogate representing a clean HITL pass on the v1.2 fixture speakers:

- `confirm_ids`: `[spk_001, spk_002]` — both acoustic IDs confirmed
- `reject_ids`: `[]` — no rejections on the happy path
- `link_mappings`: `{spk_001: char_001}` — link shot-1 voice to 少女; spk_002 stays unlinked (旁白/群杂 → null char_id)
- `merge_groups` / `splits`: empty (single-turn speakers)

Schema-validates against `spec/schemas/speaker-edits.schema.json` (Draft202012Validator). The human review happened once; the smoke replays the apply deterministically.

### 2. `scripts/verify_phase13_smoke.sh` (332 lines)

Bash smoke orchestration mirroring `tests/run_audio_analysis_smoke.sh` structure (simpler — no stub server, since both Plan 01 + Plan 02 CLIs are file-in/file-out). Runs 5 scenarios on the canonical v1.2 fixture set + prints `PHASE13_ROUND_TRIP_PASS` on success.

## 5-Scenario Results (all PASS, exit 0)

| # | Scenario | What it proves | Key assertion |
|---|----------|----------------|----------------|
| 1 | **Happy-path round-trip** | SC#5 main composition: gen HTML → frozen edits → link_speakers → canonical speakers.json | 2 confirmed speakers; spk_001→char_001; spk_002→null; schema-valid (Draft202012Validator) |
| 2 | **Idempotency** | Pitfall 5 deterministic-apply guard — 3× re-apply produces byte-identical output | sha256 `6379c727...` identical across runs 1/2/3 |
| 3 | **Confirmed-only gate** | Pitfall 7 — reject_ids excludes speaker from canonical (synthetic spk_003 augment, copy-to-/tmp) | spk_003 NOT in canonical; canonical = {spk_001, spk_002} |
| 4 | **XSS regression** | _esc + JSON bootstrap `.replace("</","<\\/")` neutralize poison `<script>` payloads | No raw `<script>` in HTML; `&lt;script&gt;` present (proves _esc fired); exactly 1 literal `</script>` (no breakout) |
| 5 | **Producer integrity extension** | Plan 01 Task 2 — `_producer_registry_integrity` accepts canonical shape AND rejects Pitfall 7 leak | 0 failures on canonical; `review_state='proposed'` → `'must be confirmed — Pitfall 7'` failure |

### Bonus observation (not a deviation)

The Scenario 1 round-trip output is semantically identical to the canonical reference `spec/fixtures/v1.2/speakers.json` (same spk_ids, char_ids, turns, review_states — schema validates both). The only difference is cosmetic: the reference uses inline `{"shot_id":1,...}` turn formatting, while the producer follows the standard `json.dump(indent=2)` convention used across all Phase 11/12/13 producers (nested objects expanded). This is a documentation/hand-curation vs. producer-formatting distinction, not a correctness gap.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Scenario 4 poison spec didn't actually exercise `_esc`**

- **Found during:** Task 1 (writing the smoke)
- **Issue:** The plan's exact poison spec for Scenario 4 used `<script>x</script>` as the `spk_id` for ALL poison shots. `_aggregate_speakers` correctly skips these via `SPK_PATTERN` defense-in-depth — but this produces 0 speakers, so the speaker-card+dropdown template never renders. The plan's secondary assertion `grep -q '&lt;script&gt;'` (T-13-15's "meaningful proof that _esc fired on the poisoned char name") silently never fires. The test technically passes (raw `<script>` absent), but it's a **false-pass risk**: it would also pass if `_esc` were completely removed from the codebase, because the dropdown where `_esc` runs never gets rendered.
- **Fix:** Added a SECOND poison shot with a VALID `spk_id` (spk_001) alongside the malformed one. The malformed shot still proves `SPK_PATTERN` defense-in-depth (skipped silently). The valid shot forces a card + dropdown to render, so `_esc` is now actually invoked on the poisoned char name and the `&lt;script&gt;` marker appears in the HTML. Added a `</script>` breakout check (exactly 1 literal close tag — the real block terminator) as defense-in-depth for the JSON-bootstrap `.replace("</","<\\/")` mitigation.
- **Files modified:** `scripts/verify_phase13_smoke.sh` (Scenario 4 block; inline comment documents the Rule 1 fix).
- **Commit:** `ef26887`
- **Result:** Scenario 4 now logs `S4 _esc active on poison (char name → &lt;script&gt; in dropdown option)` AND `S4 no </script> breakout (found 1 literal close tag(s), ≤1 expected)` — both defenses meaningfully proven.

No other deviations. Plan executed as written otherwise — artifact shapes, scenario structure, and assertion targets all match the plan spec line-for-line.

## Authentication Gates

None.

## Known Stubs

None. This plan produces test artifacts only (no production code), and both artifacts are fully wired:
- The frozen fixture carries real operator decisions on real v1.2 fixture speakers.
- The smoke harness invokes the actual Plan 01 + Plan 02 CLIs and the actual `_producer_registry_integrity` extension — no mocks, no stubs.

## Threat Flags

None. The smoke exercises existing mitigations (T-13-01 XSS `_esc`, T-13-09 JSON bootstrap, T-13-10 confirmed-dropdown-filter, Pitfall 5/7/17 guards) but introduces no new network endpoints, auth paths, file access patterns, or schema changes. All threat-register entries for Plan 03 (T-13-13/14/15/SC) are `accept` or `mitigate`-via-test-design and are covered by the harness behavior:

- **T-13-13 (Tampering — fixture deviates from schema):** mitigated — frozen fixture schema-validated at smoke start.
- **T-13-14 (Repudiation — smoke mutates canonical fixtures):** mitigated — trap cleanup + READ-ONLY discipline + explicit `git diff --quiet -- spec/fixtures/v1.2/` guard at smoke tail.
- **T-13-15 (Tampering — XSS false-pass):** mitigated (and strengthened by the Rule 1 fix above).
- **T-13-SC (Supply Chain — no new packages):** accept — zero pip/npm installs (bash + python3 stdlib + jsonschema 4.26.0 already in v1.0 deps).

## Requirements Coverage

| Req | Status | Evidence |
|-----|--------|----------|
| SPEAKER-01 | ✅ exercised | Scenario 1 happy-path round-trip + Scenario 5 producer integrity acceptance |
| SPEAKER-02 | ✅ exercised | Scenario 1 canonical speakers.json schema-validates against speakers.schema.json |
| DIA-02 | ✅ exercised | Input audio_semantic.json carries `dialogue.spk_id` (Phase 12 WhisperX diarization output) consumed end-to-end |
| DIA-03 | ✅ exercised | Operator `link_mappings` (spk→char) in frozen fixture → resolved `char_id` in canonical speakers.json |

## Self-Check: PASSED

- `tests/fixtures/speaker_edits_phase13_smoke.json`: FOUND (8 lines, schema-valid)
- `scripts/verify_phase13_smoke.sh`: FOUND (332 lines; plan min_lines: 130 — exceeded)
- Commit `ef26887`: FOUND in `git log --all`
- `bash scripts/verify_phase13_smoke.sh` post-commit re-run: prints `PHASE13_ROUND_TRIP_PASS`, exits 0
- Canonical v1.2 fixtures: `git diff --quiet -- spec/fixtures/v1.2/` clean (untouched)
- `/tmp/p13-smoke-*` workdirs: cleaned by trap on smoke exit (zero leftovers)
