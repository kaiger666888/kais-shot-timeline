---
phase: 07-cross-shot-re-id-registry-hitl-review-step-reid
reviewed: 2026-07-25T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - analysis/call_reid.py
  - registry/apply_edits.py
  - html/gen_registry_review.py
  - run_pipeline.py
  - scripts/export_asset.py
  - scripts/verify_contract.py
  - scripts/verify_phase7_smoke.py
  - spec/schemas/registry-edits.schema.json
findings:
  critical: 5
  warning: 6
  info: 4
  total: 15
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-07-25
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 7 (Cross-Shot Re-ID Registry + HITL Review) adds the second network-dependent pipeline step (`step_reid`) plus a standalone HITL editor (`apply_edits.py`) that consumes operator-supplied edits. The threat model in `<phase_context>` called out five focus areas; this review empirically reproduced **5 blockers** and **6 warnings** by direct execution plus code reading.

**Headline concerns (verified by running the code, not just reading it):**

- **`apply_edits.py` split is broken** — advertised as "partition one cluster into N", implemented as "clone all members to every split child". Two new clusters end up with byte-identical `appearance_shots`. The `registry-edits.schema.json` `splits` value shape (`string[]` of labels) cannot express member partitioning, so this is a contract-level gap, not just an impl bug.
- **`call_reid.py` crashes on malformed route response** — a single cluster dict missing `cluster_id` (or a poisoned cache containing one) raises an uncaught `KeyError`, exiting with a traceback. This contradicts the file's own graceful-degrade docstring ("畸形条目一律降级为空列表").
- **`apply_edits.py` type_override silently overwrites existing cluster** — changing `char_002 → prop` when `prop_002` already exists **silently destroys** the original `prop_002` data. No error, no warning.
- **`gen_registry_review.py` XSS** — `mask_quality` (and other route-controlled strings) are interpolated into both the HTML body (`<span class="quality-chip">{mq}</span>`) and an inlined `<script>const DRAFT = {...}</script>` block without any HTML-escaping. A route returning `mask_quality: "</script><script>alert(1)</script>"` produces an HTML file that executes the script when opened.
- **`apply_edits.py` merge silently drops a confirmed cluster** — when an operator's `merge_groups` and `confirm_ids` overlap (entirely legal per `registry-edits.schema.json`), the merged-away ID is dropped from canonical output despite being confirmed, violating the documented "ID 保留以维护引用完整性" reference-integrity rule.

**What works correctly (spot-confirmed):**

- ffmpeg subprocess invocations are all arg-list form (no `shell=True`) — T-07-13 mitigation holds.
- cluster_id pattern `^(char|prop)_[0-9]{3}$` enforced at schema boundary → no path traversal via `representative_image`.
- confirmed-only hard gate at `_build_*_entry` time is genuine (review_state is hard-coded to `"confirmed"` in the constructed entry dict).
- Counter `[N/8]` is exactly 24 occurrences; `step_reid` is in slot 6 (`run_pipeline.py:267,285,295,312`).
- Pipeline `--force` correctly clears Phase-7 artifacts (`registry_draft`, `.video-stamp`, `review_html`, `route_cache/`).
- Conditional `data.characters` / `media.characters[]` emission in `export_asset.py` is correctly omitted when canonical files are absent (verified via local dict + append pattern).
- Non-fatal PNG assert in `export_asset.py` correctly degrades to warning instead of `sys.exit`.
- Atomic write (temp + `os.replace`) used uniformly across `call_reid.py`, `apply_edits.py`, `gen_registry_review.py`, `export_asset.py`.

---

## Critical Issues

### CR-01: `apply_edits.py` split clones members to every child — feature is broken

**File:** `registry/apply_edits.py:347-357`
**Issue:**
The HITL HTML prompts the operator with `拆分 char_001 为 N 个新簇` and accepts N labels (e.g., `少年, 老年`), implying the source cluster's members will be partitioned among the resulting child clusters. The implementation instead **copies the entire `members` list** to every split child:

```python
for label in sorted(new_labels):
    new_id = _next_id(prefix, clusters.keys())
    new_cluster = {
        "cluster_id": new_id,
        ...
        "members": list(src.get("members", [])),   # <-- ALL members cloned
        "name_hint": label,
    }
    clusters[new_id] = new_cluster
```

Empirically verified: source `char_001` with `members` spanning `shot_id` ∈ {1,2,3} produces two new clusters `char_002` and `char_003`, **both** with `appearance_shots = [1, 2, 3]`. The output is semantically wrong — downstream prompt attachment (`prompts.json#character_refs[]`, Phase 8) would treat both characters as appearing in every shot the source did.

The root cause is contract-level: `registry-edits.schema.json#splits` only allows `{cid: string[]}`, with no way to express "label X gets members [a,b]". The implementation chose clone-all because partition was unspecified.

**Fix (minimal, non-schema-breaking):** Empty the members on split-children and document that the operator must manually assign via a follow-up flow, OR (preferred) extend the schema:

```json
"splits": {
  "patternProperties": {
    "^(char|prop)_[0-9]{3}$": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["label", "member_indexes"],
        "properties": {
          "label": {"type": "string", "minLength": 1},
          "member_indexes": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1}
        }
      },
      "minItems": 2
    }
  }
}
```

Then partition by `member_indexes` into the source's `members` array. At minimum, raise `sys.exit` on `len(new_labels) > 1` until the contract is resolved — silent cloning is the worst outcome.

---

### CR-02: `call_reid.py` crashes on cluster dict missing `cluster_id` — violates graceful-degrade

**File:** `analysis/call_reid.py:187` (also reached via cache-hit path through `normalize_clusters`)
**Issue:**
The module docstring explicitly promises: *"非 dict / clusters 非 list / 畸形条目一律降级为空列表（defense-in-depth）"*. The implementation only honors this for non-dict entries:

```python
for r in raw:
    if not isinstance(r, dict):
        continue
    ...
    clusters.append({
        "cluster_id": r["cluster_id"],   # <-- KeyError if cluster dict lacks this key
        ...
    })
```

Empirically reproduced: a cache file containing `clusters: [{"review_state": "proposed", ...}]` (no `cluster_id`) produces:

```
Traceback (most recent call last):
  File ".../analysis/call_reid.py", line 422, in <module>
    sys.exit(main())
  File ".../analysis/call_reid.py", line 384, in main
    clusters = normalize_clusters(route_data)
  File ".../analysis/call_reid.py", line 187, in normalize_clusters
    "cluster_id": r["cluster_id"],
KeyError: 'cluster_id'
```

The pipeline wrapper `run_step` sees non-zero exit → `CalledProcessError` → entire pipeline crashes. This is reachable via: (a) compromised/malformed route response, (b) cache-poisoning scenario (see WR-02), (c) operator-supplied draft.

**Fix:** Use `.get()` + skip:

```python
cid = r.get("cluster_id")
if not (isinstance(cid, str)
        and re.match(r"^(char|prop)_[0-9]{3}$", cid)):
    continue   # malformed cluster_id — degrade, don't crash
clusters.append({
    "cluster_id": cid,
    ...
})
```

The same pattern is present in `apply_edits.py:300` (`cid = c["cluster_id"]`) — also crashes on malformed draft (separately verified). Apply the same fix there.

---

### CR-03: `apply_edits.py` type_override silently overwrites existing cluster (data loss)

**File:** `registry/apply_edits.py:366-384`
**Issue:**
When an operator requests `type_overrides: {"char_002": "prop"}` and `prop_002` already exists in the draft (from a different cluster), the code computes `new_id = "prop_002"` and **unconditionally overwrites** the existing entry:

```python
new_id = f"{new_type}_{num_part}"
if new_id == cid:
    continue
cl = clusters.pop(cid)        # remove char_002
clusters[new_id] = cl          # silently OVERWRITES prop_002 if present
```

Empirically verified: draft with `char_002` (`appearance_shots=[1]`) and `prop_002` (`appearance_shots=[2]`), plus `type_overrides: {char_002: prop}`, produces final `props.json` with one entry `prop_002` having `appearance_shots=[1]` — the original prop's `[2]` data is **gone**, no warning, no error, schema-valid output.

The schema cannot catch this (both input and output are schema-valid). Operator typo or unexpected ID collision → silent data loss.

**Fix:** Detect collision and fail loud:

```python
if new_id in clusters:
    sys.exit(
        f"[apply-edits] FAIL: type_override {cid} → {new_id} "
        f"collides with existing cluster (data loss prevented)")
cl = clusters.pop(cid)
cl["cluster_id"] = new_id
clusters[new_id] = cl
```

---

### CR-04: `html/gen_registry_review.py` — XSS via unescaped route-controlled strings

**File:** `html/gen_registry_review.py:191-193` (HTML body) and `html/gen_registry_review.py:281,448` (inline `<script>` JSON)

**Issue:**
Three route-controlled string fields are interpolated into the generated HTML without HTML-escaping:

1. **HTML body context** — `mask_quality` rendered into a `<span>`:
```python
member_lis.append(
    f'<li>shot {m.get("shot_id", "?")} · {m.get("frame_pos", "?")} '
    f'· <span class="quality-chip">{mq}</span></li>'
)
```
If `mask_quality` contains `<script>...</script>`, the script executes when the operator opens the HTML in a browser.

2. **Inline `<script>` block** — the entire `draft` is inlined via `json.dumps` without escaping `<`:
```python
draft_json = json.dumps(draft, ensure_ascii=False)
...
const DRAFT = {draft_json};
```
Per HTML parsing rules, a literal `</script>` inside a `<script>` block **always** terminates the block, regardless of JS string context. Any string field (`mask_quality`, `frame_pos`, `generated_at`, `model`) containing `</script>` breaks out and the following `<script>` tag executes.

Empirically verified: a draft containing `mask_quality: "</script><script>alert(1)</script>"` produces an HTML file where:
```
<li>shot 1 · first · <span class="quality-chip"></script><script>alert(1)</script></span></li>
```
and the inline `const DRAFT = {...}` is also broken at the first `</script>`.

**Threat model:** The `<phase_context>` explicitly lists "operator-supplied input trust" as a focus. `mask_quality` is route-controlled (`character-reid` route), operator-editable, and `NOT enum-constrained` per `registry.schema.json:67-69` ("刻不锁 enum"). Defense-in-depth is the project pattern (see `_safe_error` masking URLs that httpx already masks). If a route compromise, cache poisoning, or shared HITL HTML file flows an attacker-controlled string in, scripts execute in the operator's browser with access to the draft JSON and any same-origin data.

**Fix:** Escape every interpolation of route/operator-controlled strings, and escape `<` in the inlined JSON:

```python
from html import escape as _esc
# Body context:
member_lis.append(
    f'<li>shot {_esc(str(m.get("shot_id", "?")))} · {_esc(str(m.get("frame_pos", "?")))} '
    f'· <span class="quality-chip">{_esc(str(mq))}</span></li>'
)
# Inline JSON — replace `</` with `<\/` (standard JSON-in-HTML defense):
draft_json = json.dumps(draft, ensure_ascii=False).replace("</", "<\\/")
```

Apply to `cid`, `default_name`, `tier`, `mean_cosine` rendering too — schema constraints are defense-in-depth, not a substitute for output escaping.

---

### CR-05: `apply_edits.py` merge silently drops a cluster the operator confirmed

**File:** `registry/apply_edits.py:308-334`
**Issue:**
When an operator's edits contain `merge_groups: [["char_001", "char_002"]]` AND `confirm_ids: ["char_001", "char_002"]` (a legal combination per `registry-edits.schema.json` — the schema does not require these to be disjoint), the merged-away ID is dropped despite being confirmed:

```python
canonical_id = group[0]                  # char_001
for cid in group:
    cl = clusters.get(cid)
    ...
    if cid != canonical_id:
        clusters.pop(cid, None)          # char_002 popped, even though confirm_ids set its state
canonical = clusters.get(canonical_id)
...
# Step 4e confirm_ids runs AFTER merge — but char_002 is already gone:
for cid in edits.get("confirm_ids", []) or []:
    if cid in clusters:                  # False for char_002
        clusters[cid]["review_state"] = "confirmed"
```

Empirically verified: with `merge_groups=[[char_001,char_002]]` + `confirm_ids=[char_001,char_002]`, final `characters.json` contains only `char_001`. `char_002` is silently lost.

This violates the documented reference-integrity contract (`apply_edits.py:14-15`: *"reject_ids — 软删除，ID 保留以维护引用完整性"*) and Pitfall 17 (cluster ID immutability). Phase 8's `prompts.json#character_refs[]` will dangle if it references a confirmed-but-merged-away ID.

**Fix:** Either emit merged-away IDs as `review_state: "rejected"` in canonical (preserving the registry), or fail loud:

```python
# After merge_groups processing, before confirm_ids:
for cid in edits.get("confirm_ids", []) or []:
    if cid not in clusters:
        # Was it merged away?
        merged = any(cid in g[1:] for g in edits.get("merge_groups", []) or [])
        if merged:
            sys.exit(
                f"[apply-edits] FAIL: confirm_ids references {cid} which was "
                f"merged away. Remove from confirm_ids or split the merge first.")
```

Or change merge to emit soft-retired entries:
```python
# Keep merged-away IDs as rejected stubs:
for cid in group:
    if cid != canonical_id:
        clusters[cid] = {"cluster_id": cid, "review_state": "rejected",
                         "tier": "review", "mean_cosine": 0.0, "members": []}
```
Note: the latter requires `characters.schema.json` to accept `review_state: "rejected"` in canonical (it already does per the enum), and the hard-gate `if cl.get("review_state") != "confirmed": continue` would correctly filter them out at canonical-build time.

---

## Warnings

### WR-01: `call_reid.py` warnings sidecar accumulates duplicates on re-run

**File:** `analysis/call_reid.py:302-414`
**Issue:**
The READ-merge-write pattern appends this step's new warnings to whatever is in the sidecar:

```python
all_warnings = existing_warnings + reid_warnings
with open(warnings_sidecar, "w", encoding="utf-8") as f:
    json.dump({"warnings": all_warnings}, f, ...)
```

When the pipeline is re-run with the route still down (no cache hit possible because route-down doesn't write the per-video cache), the previous run's reid warnings are still in the sidecar and get re-appended:

Empirically verified:
- Run 1: `["preflight route unreachable: ConnectError: ...", "character-reid: offline/cache-miss → empty draft"]` (2 warnings)
- Run 2: same 2 + same 2 appended = 4 warnings
- Run N: 2N warnings

These duplicates flow into `asset.json#generator.warnings` via `export_asset.py`, producing misleading noise that obscures real signal. The plan's intent ("non-destructive merge") is correct for the *cross-step* case (step_semantic then step_reid), but the implementation also merges *self across runs*.

**Fix:** Deduplicate by content, or tag each warning with a stable step name and replace prior entries from the same step:

```python
# Strip prior warnings emitted by THIS step (recognized by prefix), then append fresh:
STEP_TAG = "[reid]"
prior = [w for w in existing_warnings if not w.startswith(STEP_TAG)]
all_warnings = prior + [f"{STEP_TAG} {w}" for w in reid_warnings]
```

---

### WR-02: `call_reid.py` writes cache BEFORE schema validation — bad cache survives

**File:** `analysis/call_reid.py:366-409`
**Issue:**
The cache write happens immediately after `call_route` returns, but the `Draft202012Validator(registry_schema).iter_errors(registry_draft)` schema check happens ~30 lines later. If the route returns malformed data (e.g., `mean_cosine: 2.5` out of `[-1, 1]` range, or `cluster_id` violating pattern), the data is cached, THEN schema validation fails, THEN the process exits non-zero. On the next run the cache hits, the same malformed data is loaded, and schema validation fails again — the cache is permanently poisoned.

Empirically verified: a cache file with `mean_cosine: 2.5` produces `registry.draft.json schema validation failed (1 errors): clusters/0/mean_cosine: 2.5 is greater than the maximum of 1` and exits 1; the cache file remains; subsequent runs hit cache and fail identically. The operator must manually `rm route_cache/character_reid/video_*.json` to recover.

**Fix:** Either validate before caching, or invalidate cache on validation failure:

```python
# Option A: validate before caching
errors = list(Draft202012Validator(registry_schema).iter_errors(route_data))
if errors:
    # Don't cache malformed data
    reid_warnings.append(f"route returned malformed data ({len(errors)} schema errors); degrading")
    route_data = None
else:
    # cache write
    ...

# Option B: invalidate on failure
try:
    errors = list(Draft202012Validator(registry_schema).iter_errors(registry_draft))
    if errors:
        if os.path.exists(cache_file):
            os.unlink(cache_file)   # poison cleanup
        sys.exit(...)
except Exception:
    if os.path.exists(cache_file):
        os.unlink(cache_file)
    raise
```

---

### WR-03: `call_reid.py` does not clamp `mean_cosine` to schema range

**File:** `analysis/call_reid.py:185-192`
**Issue:**
`normalize_clusters` projects `mean_cosine` as `float(mc) if isinstance(mc, (int, float)) else 0.0` but does not clamp to the schema range `[-1, 1]` (`registry.schema.json:46-47`). Route returning `2.5` or `-1.7` flows straight through to draft, which then fails the schema check (see WR-02). This is reachable even without cache poisoning — a fresh route response with a bug returns out-of-range cosine, the schema validation crashes the pipeline.

**Fix:**

```python
mc_raw = r.get("mean_cosine")
if isinstance(mc_raw, (int, float)):
    mc = max(-1.0, min(1.0, float(mc_raw)))   # clamp to schema range
else:
    mc = 0.0
```

Or, more conservatively, skip the cluster entirely if `mc_raw` is out of range (signal of a route bug worth investigating).

---

### WR-04: `verify_contract.py` `_producer_registry_integrity` second-line check only catches "proposed"

**File:** `scripts/verify_contract.py:554-558`
**Issue:**
The Pitfall 7 second-line assert checks only for `review_state == "proposed"`:

```python
if entry.get("review_state") == "proposed":
    failures.append(...)
```

But `apply_edits.py`'s hard gate is `if cl.get("review_state") != "confirmed": continue`, which filters out BOTH `proposed` AND `rejected`. If a future bug ever emits a `rejected` entry into canonical, this second-line check would miss it. The schema (`characters.schema.json:38`) accepts `["proposed", "confirmed", "rejected"]`, so a `rejected` leak would not be caught by schema validation either.

**Fix:** Tighten to "must be confirmed":

```python
if entry.get("review_state") != "confirmed":
    failures.append(
        f"{name} {eid}: review_state={entry.get('review_state')!r} "
        f"in canonical (must be 'confirmed' — Pitfall 7)")
```

---

### WR-05: `apply_edits.py` does not validate the DRAFT against `registry.schema.json` before processing

**File:** `registry/apply_edits.py:287-302`
**Issue:**
The docstring claims "永不信任未校验的操作员输入" (T-07-02 mitigation) and applies this to `registry.edits.json` (validated at line 295 against `registry-edits.schema.json`). But the draft — equally operator-reachable (`registry.draft.json` is a JSON file on disk, editable by hand, and reachable from a corrupted cache or compromised route) — is NOT validated. The very next line:

```python
for c in draft.get("clusters", []):
    cid = c["cluster_id"]      # <-- KeyError if cluster dict missing cluster_id
```

Empirically verified: draft with `clusters: [{"review_state": "proposed", ...}]` (no `cluster_id`) raises uncaught `KeyError` with traceback. The downstream `_validate(CHARACTERS_SCHEMA, chars)` catches invalid OUTPUT but cannot catch the upstream-malformed INPUT that may produce surprising intermediate state.

**Fix:** Add a draft pre-validation step:

```python
# 2b. validate draft pre-apply (T-07-02 mitigation extends to ALL operator inputs)
REGISTRY_SCHEMA = REPO_ROOT / "spec" / "schemas" / "registry.schema.json"
_validate(REGISTRY_SCHEMA, draft)
```

---

### WR-06: `_resolve_frame_ts` treats string-encoded numbers as keywords

**File:** `registry/apply_edits.py:94-98` (and the duplicated copy in `html/gen_registry_review.py:90-93`)
**Issue:**
The registry schema allows `frame_pos` to be either `string` or `number`. The resolver:

```python
if isinstance(frame_pos, (int, float)):
    return float(frame_pos)
fraction = _FRAME_POS_FRACTIONS.get(str(frame_pos), 0.5)
```

correctly handles `frame_pos: 1.5` (number → absolute sec) and `frame_pos: "first"` (keyword). But for `frame_pos: "1.5"` (string-encoded number — a plausible route bug or hand-edit), the `isinstance` check fails, the keyword lookup misses, and it silently defaults to `0.5` (mid-shot). ffmpeg then extracts the wrong frame, producing a misleading thumbnail with no error.

**Fix:** Attempt numeric parse first:

```python
if isinstance(frame_pos, (int, float)):
    return float(frame_pos)
try:
    return float(frame_pos)   # string-encoded number → absolute sec
except (TypeError, ValueError):
    pass
fraction = _FRAME_POS_FRACTIONS.get(str(frame_pos), 0.5)
return float(start) + float(end - start) * fraction
```

---

## Info

### IN-01: `apply_edits.py:355` — `name_hint` is dead code; comment is misleading

**File:** `registry/apply_edits.py:355`
**Issue:**
The splits loop adds `"name_hint": label` to each new cluster, with the comment *"临时字段，build-entry 时若 renames 没覆盖则用作 name"*. But `_build_char_entry` / `_build_prop_entry` never read `name_hint` — they only consult `renames.get(cid, default_name)`. The field is set, never read, then implicitly dropped when `_build_*_entry` constructs the schema-constrained output dict. The comment lies about the field's purpose.

**Fix:** Either honor the comment (use `name_hint` as fallback when `renames` doesn't cover the new ID), or delete the field and fix the comment. The former is the operator-friendlier choice:

```python
# In _build_char_entry:
default_name = cluster.get("name_hint") or f"角色 {cid[-3:]}"
name = renames.get(cid, default_name)
```

---

### IN-02: `apply_edits.py` `merge_groups` creates orphan placeholder when canonical target doesn't exist

**File:** `registry/apply_edits.py:327-332`
**Issue:**
If an operator typo makes `merge_groups[0]` reference a non-existent cluster_id (e.g., `["char_999", "char_001"]` where `char_999` doesn't exist), the code creates a placeholder cluster with `review_state="proposed"` for `char_999`, copies `char_001`'s members into it, and pops `char_001`. The result is an orphan `char_999` cluster that won't flow to canonical unless the operator also adds `char_999` to `confirm_ids` (unlikely, since it's a typo). No warning is emitted; the merge is accepted silently.

**Fix:** Warn or fail when the canonical target is absent:

```python
canonical = clusters.get(canonical_id)
if canonical is None and not any(cid in clusters for cid in group):
    sys.exit(f"[apply-edits] FAIL: merge group {group} references no existing clusters")
```

---

### IN-03: Duplicated `_FRAME_POS_FRACTIONS` / `_QUALITY_RANK` between `apply_edits.py` and `gen_registry_review.py`

**File:** `registry/apply_edits.py:61-67,58` and `html/gen_registry_review.py:67-72`
**Issue:**
Both files define the same constants with a "mirror" comment justifying the duplication (`"mirror apply_edits.py — small enough to inline; no cross-module dep"`). The duplication is intentional (standalone-script convention), but if the fraction map or quality rank ever diverges, the HITL preview will extract a different frame than apply_edits writes — the operator reviews one thumbnail and ships another. The current values match, but the contract is fragile.

**Fix:** Accept the duplication (per the standalone-script convention) but add a regression assertion in `verify_phase7_smoke.py`:

```python
# Cross-module constant parity check (apply_edits <-> gen_registry_review)
import importlib.util
spec_a = importlib.util.spec_from_file_location('ae', REPO/'registry/apply_edits.py')
spec_g = importlib.util.spec_from_file_location('grr', REPO/'html/gen_registry_review.py')
ae = importlib.util.module_from_spec(spec_a); spec_a.loader.exec_module(ae)
grr = importlib.util.module_from_spec(spec_g); spec_g.loader.exec_module(grr)
assert ae._FRAME_POS_FRACTIONS == grr._FRAME_POS_FRACTIONS
assert ae.QUALITY_RANK == grr._QUALITY_RANK
```

---

### IN-04: `gen_registry_review.py:521` `toggleType` uses `alert()` for feedback; no card visual update

**File:** `html/gen_registry_review.py:508-522`
**Issue:**
The `toggleType` handler records the override in `state.typeOverrides[cid]` and shows an `alert()`, but does NOT call `applyVisualState()` and does not mutate the card's visual state (no badge, no class toggle). The operator gets a modal dialog but no persistent indicator that the override is active — easy to forget on export. Other handlers (`toggleConfirm`, `toggleReject`) do call `applyVisualState()`. Inconsistent UX.

**Fix:** Add a visual indicator (e.g., a `state-type-override` class on the card) and update on toggle:

```js
function toggleType(cid) {
    ...
    applyVisualState();   // or a dedicated applyTypeVisualState()
}
```

---

_Reviewed: 2026-07-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
