---
phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
fixed_at: 2026-07-24T19:41:18Z
review_path: .planning/phases/07-cross-shot-re-id-registry-hitl-review-step-reid/07-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-07-24T19:41:18Z
**Source review:** `.planning/phases/07-cross-shot-re-id-registry-hitl-review-step-reid/07-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 11 (5 BLOCKER + 6 WARNING; 4 INFO deferred per default scope)
- Fixed: 11
- Skipped: 0

**Final gate (all 5 green):**
- `python3 spec/validate.py` → exit 0
- `python3 scripts/verify_phase7_smoke.py` → 5/5 green
- `python3 scripts/verify_phase6_smoke.py` → 4/4 green (no regression)
- `PHASE4_ASSET_DIR=<ep01> python3 scripts/verify_contract.py --mode=producer` → exit 0
- `PHASE4_ASSET_DIR=<ep01> PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` → exit 0

## Fixed Issues

### CR-01: `apply_edits.py` split clones members to every child — feature is broken

**Files modified:** `spec/schemas/registry-edits.schema.json`, `registry/apply_edits.py`, `html/gen_registry_review.py`, `spec/fixtures/v1.1/registry.edits.json`, `scripts/verify_phase7_smoke.py`
**Commit:** `6ef2057`
**Reproduction closed:** source `char_001` (3 members) split into 2 children now produces `char_002=[1,2]` + `char_003=[3]` (PARTITIONED), not both `[1,2,3]`.

**Applied fix:** Schema reshape + partition logic.
- **Schema:** `registry-edits.schema.json#splits` reshaped from `{cid: string[] of labels}` to `{cid: [{label, member_indexes: int[>=0]}]}` — the new shape can express which source members go to which child (`member_indexes` are 0-based indexes into the source cluster's `members[]`). `minItems:2` retained; `member_indexes` has `minItems:1` + `uniqueItems:true`. Controlled reshape is allowed because registry-edits is NEW in Phase 7 (not shipped). Schema stays strict (`additionalProperties:false` throughout).
- **apply_edits.py:** split loop now (a) validates **complete partition** — union of all children's `member_indexes` must equal `{0..len(members)-1}`; incomplete/overlap/out-of-range → `sys.exit` FAIL (documented: operator must account for every source member; no silent data loss, consistent with CR-03/CR-05 theme); (b) partitions `src.members[i]` per child's `member_indexes` instead of cloning all; (c) sorts children by `label` for deterministic ID binding (idempotency).
- **gen_registry_review.py:** `splitCluster` UX reworked — prompts for labels then per-label member indexes (last label auto-collects remainder, guaranteeing a complete partition); `exportEdits` already passes `state.splits[k]` through verbatim so it emits the new `[{label, member_indexes}]` shape automatically.
- **Fixture:** `spec/fixtures/v1.1/registry.edits.json` updated to demonstrate the partitioned shape (char_001 → `[{day, [0,1]}, {night, [2]}]`); `confirm_ids`/`renames` adjusted to the resulting `char_003`/`char_004` IDs. Smoke scenario 4 comment updated; the dynamic count now reads "3 chars + 1 props" (the split produces 2 children from char_001).

### CR-02: `call_reid.py` crashes on cluster dict missing `cluster_id` — violates graceful-degrade

**Files modified:** `analysis/call_reid.py`, `registry/apply_edits.py`
**Commit:** `e1af4a8`
**Reproduction closed:** `normalize_clusters({"clusters":[{"review_state":"proposed",...}]})` (no `cluster_id`) now returns `[]` instead of raising `KeyError`.

**Applied fix:** Per-cluster normalization wrapped in broad defense.
- `call_reid.py` `normalize_clusters`: explicit `cluster_id` validation via `r.get("cluster_id")` + regex `^(char|prop)_[0-9]{3}$` (skip if missing/non-str/pattern-mismatch) **plus** broad `try/except (KeyError, TypeError, ValueError, IndexError)` around the per-cluster body so any unforeseen malformation degrades to a skip (honors the file's "畸形条目一律降级为空列表" docstring).
- `apply_edits.py` cluster-build loop: `cid = c["cluster_id"]` → `c.get("cluster_id")` + `isinstance(cid, str)` skip (defense-in-depth; WR-05's pre-apply schema validation is the primary gate, this is the belt-and-suspenders).

### CR-03: `apply_edits.py` type_override silently overwrites existing cluster (data loss)

**Files modified:** `registry/apply_edits.py`
**Commit:** `15b244c`
**Reproduction closed:** `type_overrides: {char_002: prop}` with existing `prop_002` now exits non-zero with `[apply-edits] FAIL: type_override char_002 → prop_002 collides with an existing cluster (data loss prevented)`; non-colliding override (`char_005 → prop_005`) still works.

**Applied fix:** Collision detection before the `clusters.pop`/re-insert. `if new_id in clusters: sys.exit(...)` — refuses to silently destroy the existing cluster's data. Operator must resolve the conflict (rename or merge the colliding target) before retrying. Consistent with the project's fails-loud pattern (`_validate`, schema exit).

### CR-04: `html/gen_registry_review.py` — XSS via unescaped route-controlled strings

**Files modified:** `html/gen_registry_review.py`
**Commit:** `336d04f`
**Reproduction closed:** draft with `mask_quality: "</script><script>alert(1)</script>"` produces HTML where the body span is `<span class="quality-chip">&lt;/script&gt;...` (escaped) and the inline `const DRAFT = {...}` no longer contains a raw `</script>` (replaced with `<\/script>`).

**Applied fix:** Output escaping for every interpolation of route/operator-controlled strings + JSON-in-script defense.
- Added self-contained `_esc()` helper (5-char HTML escape: `& < > " '`). Self-contained inline impl rather than `from html import escape` to avoid the local `html/` namespace-package shadowing ambiguity and match the standalone-script convention.
- **Body context:** `mask_quality`, `frame_pos`, `shot_id` (all route-controlled, NOT pattern-locked) are the primary vector — now `_esc()`-wrapped in `member_lis`. `cid`, `tier`, `default_name`, `asset_name` also wrapped (defense-in-depth; they are schema-constrained but escaping is harmless).
- **Inline `<script>` JSON:** `draft_json = json.dumps(draft, ensure_ascii=False).replace("</", "<\\/")` — the standard JSON-in-HTML defense. `\/` is a valid JS escape for `/`, so client-side `DRAFT` data round-trips correctly while `</script>` can no longer terminate the script block.

### CR-05: `apply_edits.py` merge silently drops a cluster the operator confirmed

**Files modified:** `registry/apply_edits.py`
**Commit:** `4c3491e`
**Reproduction closed:** `merge_groups=[[char_001,char_002]]` + `confirm_ids=[char_001,char_002]` now produces `char_001` confirmed with `appearance_shots=[1,2]` (char_002's confirm intent forwarded to the canonical target; no silent drop).

**Applied fix:** Merge-state forwarding (documented choice: **the merge target inherits the merged-away ID's confirm/reject state**).
- Merge loop builds a `merge_map: {merged_away_id: canonical_target_id}` as it pops non-canonical IDs.
- `confirm_ids`/`reject_ids` processing consults `merge_map`: if a cid was merged away (not in `clusters`), its review state is applied to `merge_map[cid]` (the canonical target) instead of being silently skipped. This honors the operator's confirm intent (merge + confirm = "these are the same entity, confirm it") with no silent data loss. The merged-away ID does not appear as a separate canonical entry (correctly — its members moved to the canonical target), so no duplication.

---

## Warning Fixes (WR-01 .. WR-06)

### WR-01: `call_reid.py` warnings sidecar accumulates duplicates on re-run

**Files modified:** `analysis/call_reid.py`
**Commit:** `24fb5a8`
**Reproduction closed:** 3 consecutive route-down runs now produce 2 warnings (not 6); a `[semantic]` warning injected from another step survives re-runs (cross-step merge preserved).

**Applied fix:** Step-tag dedup. `reid_warnings` are tagged with `[reid] ` prefix at sidecar-merge time; prior `[reid]`-tagged entries are stripped from `existing_warnings` before appending fresh ones. Cross-step warnings (e.g. `[semantic]` from step_semantic) are left untouched (non-destructive cross-step merge retained). The smoke scenario-1 keyword check (`preflight`/`ConnectError`/`character-reid`) still matches because the tag is a prefix.

### WR-02: `call_reid.py` writes cache BEFORE schema validation — bad cache survives

**Files modified:** `analysis/call_reid.py`
**Commit:** `23a9d48`
**Reproduction closed:** a cache containing a member with `frame_pos: [1,2]` (list — survives `normalize_clusters` but fails the draft schema) now logs `[reid] invalidated poisoned cache: ...`, deletes the cache file, and the next run degrades cleanly (exit 0, empty clusters) instead of failing identically.

**Applied fix:** Invalidate-on-failure. On draft schema validation failure, `os.unlink(cache_file)` (best-effort, wrapped in `try/except OSError`) runs before `sys.exit`. Covers both the fresh-route-response-cached-then-fail path and the stale-poisoned-cache-hit path. After WR-03 (clamp) + CR-02 (skip malformed) most route malformations are normalized away, so this is defense-in-depth for malformations normalization cannot fix (e.g. `frame_pos` of wrong type).

### WR-03: `call_reid.py` does not clamp `mean_cosine` to schema range

**Files modified:** `analysis/call_reid.py`
**Commit:** `4f5836c`
**Reproduction closed:** `normalize_clusters(mean_cosine=2.5)` → `1.0`; `=-1.7` → `-1.0`; `=0.72` → `0.72` (in-range preserved); `="high"` → `0.0`. Draft with the clamped value is schema-valid.

**Applied fix:** `mc = max(-1.0, min(1.0, float(mc_raw)))` when `mc_raw` is numeric; else `0.0`. Clamps route bugs (out-of-range cosine) into the schema-legal `[-1, 1]` range so the draft no longer fails validation on a fresh malformed route response.

### WR-04: `verify_contract.py` `_producer_registry_integrity` only catches "proposed"

**Files modified:** `scripts/verify_contract.py`
**Commit:** `fc20f18`
**Reproduction closed:** a `review_state="rejected"` entry leaked into canonical is now flagged (`must be 'confirmed' — Pitfall 7`); a missing `review_state` is also caught; a `confirmed` entry still passes.

**Applied fix:** Tightened the second-line assert from `== "proposed"` to `!= "confirmed"`, matching `apply_edits.py`'s hard gate (`if review_state != "confirmed": continue`). Catches proposed, rejected, and missing states. The schema enum accepts all three, so without this tighten a `rejected` leak would pass schema validation undetected.

### WR-05: `apply_edits.py` does not validate the DRAFT against `registry.schema.json` before processing

**Files modified:** `registry/apply_edits.py`
**Commit:** `d445515`
**Reproduction closed:** a draft with a cluster missing `cluster_id` now exits with `registry.schema.json validation failed (3 errors): clusters/0: 'cluster_id' is a required property ...` (clean schema-validation error, no `KeyError` traceback); a valid draft still processes fine.

**Applied fix:** Added `REGISTRY_SCHEMA` constant + `_validate(REGISTRY_SCHEMA, draft)` call immediately after the edits pre-validation (step 2b, before the cluster-build loop). Extends the T-07-02 "永不信任未校验的操作员输入" mitigation to the draft (equally operator-reachable: a JSON file on disk, editable by hand, reachable from a corrupted cache or compromised route). Works with CR-02's defensive `.get()` as belt-and-suspenders.

### WR-06: `_resolve_frame_ts` treats string-encoded numbers as keywords

**Files modified:** `registry/apply_edits.py`, `html/gen_registry_review.py`
**Commit:** `ed0e133`
**Reproduction closed:** `_resolve_frame_ts(shot=[0,10], frame_pos="7.5")` → `7.5` (absolute sec, was `5.0` mid-shot). Keywords still work: `"first"` → `0.0`, `"50%"` → `5.0`; genuine non-numeric (`"garbage"`) still falls back to mid `5.0` (documented default).

**Applied fix:** Added a `try: return float(frame_pos) except (TypeError, ValueError): pass` between the `isinstance(number)` check and the keyword lookup, in both copies of `_resolve_frame_ts` (apply_edits.py + gen_registry_review.py). String-encoded numbers (`"7.5"`, `"15"`) now parse as absolute seconds; only true non-numeric strings fall through to the keyword map. Applied to both files to keep the duplicated resolver in parity (IN-03 notes the duplication is intentional).

## Skipped Issues

None — all 11 in-scope findings were fixed. The 4 INFO findings (IN-01..IN-04) are out of scope per the default `critical_warning` fix scope and were not addressed in this iteration.

---

_Fixed: 2026-07-24T19:41:18Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
