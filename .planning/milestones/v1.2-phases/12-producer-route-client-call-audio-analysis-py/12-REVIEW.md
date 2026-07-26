---
phase: 12-producer-route-client-call-audio-analysis-py
reviewed: 2026-07-26T00:00:00Z
depth: quick
files_reviewed: 5
files_reviewed_list:
  - analysis/call_audio_analysis.py
  - tests/audio_analysis_stub_server.py
  - tests/run_audio_analysis_smoke.sh
  - tests/fixtures/audio_analysis_stub_response_nonempty.json
  - tests/fixtures/audio_analysis_stub_response_empty.json
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-07-26
**Depth:** quick
**Files Reviewed:** 5 (1 producer client + 4 test artifacts)
**Status:** issues_found (0 blockers, 4 warnings, 3 info)

## Summary

`analysis/call_audio_analysis.py` (827 lines) is the third sibling of the v1.1
route-pattern family (`call_shot_analysis.py`, `call_reid.py`). It faithfully
mirrors the proven patterns: per-shot httpx POST, 4-tuple cache,
poisoned-cache schema-invalidated cleanup, byte-identical-absent
graceful-degrade, non-destructive `[audio]` warnings read-merge-write.

Threat model T-12-01..05 mitigations verified present and correct:
- **T-12-01 (route auth)**: no auth header, internal-only route (mirror sibling).
- **T-12-02 (poisoned cache)**: schema-validate on hit (`call_audio_analysis.py:647-667`) AND pre-write (`:759-784`); both paths unlink offending cache files.
- **T-12-03 (path traversal)**: cache filename `shot_{sid:03d}.json` via `:03d` format spec genuinely rejects non-int sid (raises TypeError/ValueError before file IO); output path is trusted `--output` flag.
- **T-12-04 (info disclosure)**: `_safe_error` regex applied on every URL-bearing error path in `call_route`/`preflight` (lines 359-394, 422-426). Verified: no httpx-exception string reaches `audio_warnings` without redaction.
- **ROUTE_PATH correctness**: `/api/production/audio-analysis` (NO `/v1/`, line 120) — matches Phase 10 mount-path flag; `rsplit("/api/production", 1)` anchor (lines 415, 613) is consistent between preflight and main client.

Correctness invariants confirmed by tracing code (smoke already proved at runtime):
- poisoned-cache invalidation on hit unlinks + marks `cache_stale=True` + leaves `route_shot=None` → triggers re-POST in the `not route_down` branch (refetch path is real, not dead).
- byte-identical-absent when `has_any_data=False` (line 740): `args.output` is NOT written, prior artifact NOT unlinked, sidecar warning emitted.
- `[audio]`/`[semantic]`/`[reid]` read-merge-write: `prior = [w for w in existing_warnings if not w.startswith("[audio]")]` (line 800) preserves cross-step tags; only same-step tag self-dedups.

Findings below are real quality/robustness gaps the smoke harness does NOT
cover (single-shot fixture, all-happy-path or all-degrade scenarios — no
malformed-shots, no multi-shot, no route-up + poisoned-cache).

## Warnings

### WR-01: `poisoned_cache_files` list is dead code — silent poisoned-cache event when route is UP

**File:** `analysis/call_audio_analysis.py:628, 664`
**Issue:** The variable is declared with comment "命中时校验失败 → 累积，结束时统一警告"
(accumulate on hit-failure; summarize at end of loop) and populated at line 664
inside the poisoned-cache invalidation branch. But it is **never read after
the loop** — grep confirms only 2 hits (decl + append). The promised summary
warning is never emitted.

Concrete impact: when route is UP, poisoned cache is detected, and the
refetch SUCCEEDS, the operator gets only a stdout `print` (line 661). No
entry flows into `route_cache/warnings.json` → `asset.json#generator.warnings`.
The smoke catches this only because Scenario 3 uses `--offline` (refetch
skipped, `cache_stale=True` triggers the offline/stale-cache branch at line
702-704). The route-up + refetch-success path is untested and silently loses
the poisoned-cache signal.

**Fix:**
```python
# After the per-shot loop, before decision (around line 729):
if poisoned_cache_files:
    audio_warnings.append(
        f"invalidated {len(poisoned_cache_files)} poisoned cache file(s) "
        f"on schema-validate fail (route-up → refetched)")
```
(Or fold the count into the summary print at line 818-820.)

### WR-02: `s["id"]` unguarded — malformed shots.json entry crashes pipeline

**File:** `analysis/call_audio_analysis.py:632`
**Issue:** Main per-shot loop does `sid = s["id"]` then `cache_file = os.path.join(cache_dir, f"shot_{sid:03d}.json")`. No `isinstance(sid, int)` guard. If a shots.json entry is `{"id": "1"}` or `{"id": 1.5}` or `{}` or a non-dict element, the result is:
- missing `id` → `KeyError` (uncaught, pipeline aborts)
- non-int `id` → `:03d` format raises `TypeError`/`ValueError` (uncaught, pipeline aborts)
- non-dict `s` → `TypeError` on `s["id"]` (uncaught, pipeline aborts)

The `--force` branch at line 569-570 DOES guard with `isinstance(sid, int)`,
creating an inconsistency within the same file. The docstring claims
"CR-02 broaden except" defense-in-depth pattern; it is not applied here.
`call_shot_analysis.py:307` has the same pattern (mirror), but that is an
established defect, not a justification.

**Fix:**
```python
for s in shots_meta:
    if not isinstance(s, dict) or not isinstance(s.get("id"), int):
        audio_warnings.append(
            f"skip malformed shots.json entry (not dict or id not int): "
            f"{type(s).__name__ if not isinstance(s, dict) else s.get('id')!r}")
        continue
    sid = s["id"]
    ...
```

### WR-03: `normalize_audio_semantic` trusts `shot_meta` keys — missing timing fields crash

**File:** `analysis/call_audio_analysis.py:192-197, 652, 717`
**Issue:** Skeleton construction does `shot_meta["start_sec"]`, `shot_meta["end_sec"]`, `shot_meta["duration"]` without `.get()` fallback. A shots.json entry like `{"id": 1}` (id only, no timing — e.g., hand-edited or partial) raises `KeyError` inside `normalize_audio_semantic`, which is called inside the per-shot loop with no enclosing try/except → pipeline aborts.

`shots_meta` is only validated to be a `list` at line 528-529; entry shape is never checked. The docstring at line 184 explicitly claims "timing 永远来自 shot_meta (producer-owns-timing invariant)" — but does not defend that invariant.

**Fix:** Either (a) pre-validate `shots_meta` against `shots.schema.json` after load (preferred — single schema gate), or (b) use `.get()` with sentinel defaults in skeleton and skip shots missing required timing.

### WR-04: Cache write catches `OSError` only — `TypeError`/`ValueError` from `json.dump` propagates

**File:** `analysis/call_audio_analysis.py:693-697`
**Issue:**
```python
try:
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, ensure_ascii=False, indent=2)
except OSError as e:
    audio_warnings.append(f"shot {sid}: cache write failed: {e}")
```
If `cache_payload` (built from `{**route_shot, "_cache_key": ...}`) ever contains
a non-JSON-serializable value (e.g., a route bug returns a body with
`NaN`/`Infinity` floats — `json.dump` default `allow_nan=True` accepts these
but they violate strict JSON; or a custom object), `TypeError` or
`ValueError` propagates → uncaught → pipeline aborts.

In practice `resp.json()` only yields JSON-native types, so risk is low.
`call_reid.py:392-393` has the same narrow except — established pattern.
Flagging for defense-in-depth consistency with CR-02 elsewhere in this file.

**Fix:**
```python
except (OSError, TypeError, ValueError) as e:
    audio_warnings.append(f"shot {sid}: cache write failed: {e}")
```

## Info

### IN-01: Smoke harness is single-shot only — Pitfall 6 (per-shot isolation) untested

**File:** `tests/run_audio_analysis_smoke.sh:117-119`
**Issue:** `shots.json` fixture has 1 entry. The docstring at `call_audio_analysis.py:16, 338` and 10-02-SUMMARY emphasize per-shot isolation (`shot_id_range=[N,N]`) as a key correctness property (Pitfall 6). Cross-shot cache contamination (e.g., wrong cache_key, normalize leaking state) would not be detected by this smoke. Also untested: multi-shot has_any_data aggregation, word_level_experimental OR-semantics across shots.

**Fix:** Add a 2-3 shot fixture (e.g., one with dialogue+words, one with sfx only, one skeleton) and assert word_level_experimental=true + per-shot cache files exist with distinct names.

### IN-02: `sys.path.insert` in SCHEMA_VERSION lazy-import is dead code with misleading comment

**File:** `analysis/call_audio_analysis.py:539-541`
**Issue:**
```python
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
# sys.path 补 repo root 让 `from scripts.export_asset import SCHEMA_VERSION` 可达
import importlib.util
spec = importlib.util.spec_from_file_location(
    "_export_asset_for_version", repo_root / "scripts" / "export_asset.py")
```
The `sys.path.insert` and its comment reference a `from scripts.export_asset import ...` style that the actual code below does NOT use — `importlib.util.spec_from_file_location` takes an absolute path and does not consult `sys.path`. The mutation persists (subprocess-scoped) but is pure noise. Comment actively misleads future readers.

**Fix:** Delete lines 539-541 (keep only the `repo_root` Path computation, which is reused at line 545).

### IN-03: `cache write failed: {e}` bypasses `_safe_error` — minor T-12-04 inconsistency

**File:** `analysis/call_audio_analysis.py:697`
**Issue:** `audio_warnings.append(f"shot {sid}: cache write failed: {e}")` interpolates a raw `OSError` str. The T-12-04 mitigation claim ("所有错误串均过 _safe_error") literally covers this path but the implementation skips it. Practical risk is low: `OSError` str from `open()` typically contains the file path (which may include `--work-dir`), rarely a URL with basic-auth. But the mitigation claim and code disagree.

**Fix:** Wrap with `_safe_error(f"shot {sid}: cache write failed: {e}")` for consistency, or narrow the T-12-04 claim to "URL-bearing error paths".

---

_Reviewed: 2026-07-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
