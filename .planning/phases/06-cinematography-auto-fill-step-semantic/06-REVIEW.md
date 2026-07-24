---
phase: 06-cinematography-auto-fill-step-semantic
reviewed: 2026-07-24T00:00:00Z
depth: deep
files_reviewed: 5
files_reviewed_list:
  - analysis/call_shot_analysis.py
  - run_pipeline.py
  - scripts/export_asset.py
  - scripts/verify_phase6_smoke.py
  - spec/schemas/asset.schema.json
findings:
  blocker: 2
  warning: 6
  info: 4
  total: 12
status: findings
---

# Phase 6: Code Review Report

**Reviewed:** 2026-07-24
**Depth:** deep (cross-file: call_shot_analysis.py + run_pipeline.py + export_asset.py + schema + harness; bug repros executed)
**Files Reviewed:** 5
**Status:** findings

## Summary

Phase 6 introduces shot-timeline's first network dependency (`analysis/call_shot_analysis.py`,
httpx sync client → kais-aigc-platform shot-analysis route) and threads its output
through `run_pipeline.py` (step 5/7), `scripts/export_asset.py` (warnings sidecar),
and a new regression harness. The schema deltas (`asset.schema.json`) are confirmed
additive-only — no required/const drift.

The mapping layer (`compose_facets`) is correct for all 7 captured fixtures
including the null/empty edge cases the brief called out (`shot_002` `shot_scale=null`,
`shot_005/007` empty/null `subject_motion`); the join produces no literal `"None"`
and no leading/trailing `", "`.

However, the **graceful-degrade surface has two real holes** that the harness does
not cover and that will cause the pipeline to abort or silently corrupt data in
plausible real-world conditions. Both reproduced during this review. The cache-
invalidation logic also has a documented-contract gap (`route_name` checked in
docstring but not in code; stale-cache + offline silently degrades). The mtime
cache in `step_semantic` repeats the WR-07 video-identity gap that `step_export`
already fixed.

**Empirically confirmed GREEN by the brief** (compose_facets on shot_003; 7 fixtures
0 errors; route-down degrade; --offline cache-hit; verify_phase6_smoke 3/3) — those
all still pass. The defects below are in surfaces the harness does not exercise.

---

## Critical Issues

### CR-01: Stale-cache + offline silently degrades prompts to empty facets (violates Pitfall 4)

**File:** `analysis/call_shot_analysis.py:280`
**Issue:**

The comment cites "Pitfall 4：不静默，显式记 warning" but the implementation only
emits a warning when the cache file is **absent**. There is a second route-to-None
path the guard misses: **cache file exists but `_cache_key` mismatches** (video
file swapped, or `ROUTE_VERSION` bumped in source). In that case `route_shot`
stays `None`, `route_down` is `True`, but `os.path.exists(cache_file)` is `True`,
so the entire `if` short-circuits — no warning is appended. The operator gets an
empty-facets `prompts.json` (schema-valid, looks fine) with **zero indication**
that anything was lost.

I reproduced this end-to-end:

```text
STDOUT: [semantic] wrote /tmp/stale-test-XXX/prompts.json (1 shots, 0 warnings)
WARNINGS: {'warnings': []}
PROMPTS camera: ''
```

(pre-filled cache with `_cache_key.video_content_hash = "WRONG_HASH_VALUE"`,
ran `--offline` against unreachable URL; got empty camera, empty warnings.)

This is exactly the silent-degrade Pitfall 4 was written to prevent, and it
matters most exactly here: ROUTE_VERSION bumps are how the operator is meant to
invalidate caches after route logic changes — the miss signal is the only
feedback that the cache refresh actually happened.

**Fix:**

```python
# (c) cache miss + route_down —— Pitfall 4：不静默，显式记 warning
# 注意：cache_file 存在但 _cache_key 不匹配（video 变 / ROUTE_VERSION bump）
# 也是 miss —— 旧实现用 `not os.path.exists(cache_file)` 把这种情况漏了。
if route_shot is None and route_down:
    if os.path.exists(cache_file):
        warnings.append(
            f"shot {sid}: offline/stale-cache (_cache_key mismatch) "
            f"→ empty facets")
    else:
        warnings.append(
            f"shot {sid}: offline/cache-miss → empty facets")
```

### CR-02: `call_route` / `compose_facets` raise uncaught tracebacks on malformed route responses

**File:** `analysis/call_shot_analysis.py:152-163, 119-120`

**Issue:**

The brief asks: "does it catch the FULL httpx degrade surface?" — yes, it catches
`httpx.HTTPError` (the root for `ConnectError`/`TimeoutException`/`NetworkError`/
`HTTPStatusError`). **But it does not catch the non-httpx exceptions that a misbehaving
route or reverse proxy will produce in production:**

1. **Non-JSON 200 body** (e.g., nginx 502 HTML error page with `Content-Type: text/html`
   but status 200, or a misconfigured proxy returning HTML). `resp.json()` raises
   `json.JSONDecodeError` (a `ValueError`, NOT subclass of `httpx.HTTPError`).
   Reproduced:

   ```text
   File ".../call_shot_analysis.py", line 154, in call_route
       payload = resp.json()
   ValueError: Expecting value: line 1 column 1 (char 0)
   ```

2. **Non-dict route payload** (route returns a bare list, string, or number).
   `payload.get("code")` raises `AttributeError`. Reproduced for all of
   `semantic=["a","b"]`, `semantic="string"`, `semantic=42`, `geometry="string"`.

3. **`compose_facets` crashes on non-dict truthy `semantic`/`geometry`**: the `or {}`
   coercion only handles `None`/falsy. A route bug returning `semantic: [...]` makes
   `route_shot.get("semantic") or {}` return the list, and the next line's
   `sem.get("shot_scale")` raises `AttributeError`. Reproduced.

All three escape the `except httpx.HTTPError` clause → uncaught traceback →
`step_semantic` subprocess exits non-zero → `run_pipeline` aborts via
`subprocess.run(check=True)`. This is precisely the "traceback instead of graceful-
degrade" failure mode the brief flagged as a review focus, and the harness does
not cover it (it only exercises `ConnectError` via an unreachable port).

**Fix:** broaden the catch + defend the parsing.

```python
def call_route(client, body: dict) -> tuple[dict | None, str | None]:
    import httpx
    try:
        resp = client.post("/api/v1/production/shot-analysis", json=body)
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as e:                          # non-JSON 200 (HTML proxy page)
            return None, f"route returned non-JSON body: {type(e).__name__}: {e}"
        if not isinstance(payload, dict):
            return None, f"route envelope not a dict: {type(payload).__name__}"
        if payload.get("code") != 200:
            return None, f"route code={payload.get('code')}: {payload.get('message')}"
        shots = (payload.get("data") or {}).get("shots") or []
        if not shots:
            return None, (f"route returned 0 shots for "
                          f"shot_id_range={body.get('shot_id_range')}")
        return shots[0], None
    except httpx.HTTPError as e:
        return None, f"{type(e).__name__}: {e}"
```

And in `compose_facets`, replace `route_shot.get("semantic") or {}` with a typed guard:

```python
sem = route_shot.get("semantic") if isinstance(route_shot.get("semantic"), dict) else {}
geo = route_shot.get("geometry") if isinstance(route_shot.get("geometry"), dict) else {}
```

---

## Warnings

### WR-01: `step_semantic` mtime cache ignores video identity and `ROUTE_VERSION` (re-introduces 02-REVIEW WR-07)

**File:** `run_pipeline.py:186-189`

**Issue:**

```python
if (os.path.exists(prompts_json)
        and _safe_mtime(prompts_json) > _safe_mtime(shots_json)):
    print(f"[5/7] cached prompts: {prompts_json}")
    return prompts_json
```

This cache check only compares `prompts.json` mtime to `shots.json` mtime. But
`prompts.json` content depends on three more things this check ignores:

1. **Video file content** — `video_content_hash` is the per-shot cache key. If the
   operator swaps `--video` for a different file with same/older mtime (backup
   restore, version control checkout, file copied with `cp --preserve=timestamps`),
   the per-shot cache invalidates inside `call_shot_analysis.py`, but the outer
   mtime cache short-circuits before that runs → stale `prompts.json` ships.
2. **`ROUTE_VERSION` constant** — bumped in source as the documented cache-
   invalidation knob. Source code edits don't change `prompts.json` mtime either.
3. **`call_shot_analysis.py` source itself** — bug fixes to mapping logic don't
   bust the mtime cache.

`step_export` already solved this with a `asset.json.video-stamp` sidecar that
encodes `path|size|mtime_ns` (`run_pipeline.py:291-305`, `_video_identity`).
`step_semantic` has no equivalent. The Phase 6 SUMMARY explicitly invokes
"mirror step_export 02-REVIEW WR-07" for the TOCTOU part but skips the identity
part.

**Fix:** mirror the video-stamp pattern. After a successful `call_shot_analysis.py`
run, write `prompts.json.video-stamp` with `_video_identity(video)`; include it
in the cache-hit check:

```python
video_stamp = prompts_json + ".video-stamp"
cached_video_id = None
if os.path.exists(video_stamp):
    try:
        with open(video_stamp, encoding="utf-8") as f:
            cached_video_id = f.read().strip()
    except OSError:
        cached_video_id = None
current_video_id = _video_identity(video)
if (not force
        and os.path.exists(prompts_json)
        and _safe_mtime(prompts_json) > _safe_mtime(shots_json)
        and cached_video_id is not None
        and cached_video_id == current_video_id):
    ...
```

(Also add `prompts.json.video-stamp` to the `--force` cleanup list at line 400-407.)

### WR-02: `import httpx` is unconditional even in `--offline` mode

**File:** `analysis/call_shot_analysis.py:230`

**Issue:**

The CLI advertises `--offline` as "仅读 route_cache 不联网". In a fully cached +
offline run, **no network call is ever made** — yet `import httpx` at line 230
runs unconditionally before the per-shot loop, so httpx must be importable. The
project convention (per `CLAUDE.md` and `audio/transcribe.py`) is lazy-import
optional dependencies exactly so the non-using code path doesn't require them.

If an operator wants to run `--offline` on a box where httpx isn't installed
(minimal CI, container without the network-step deps), the step crashes with
`ImportError: No module named 'httpx'` instead of doing the cache-only work it
was designed for.

**Fix:** move the `import httpx` inside the `if not args.offline:` branch (or
make the long-lived client construction conditional on `not args.offline`):

```python
client = None
if not args.offline:
    import httpx
    client = httpx.Client(base_url=args.analysis_url,
                          timeout=httpx.Timeout(connect=5.0, read=args.analysis_timeout,
                                                write=5.0, pool=5.0))
try:
    for s in shots_meta:
        ...
finally:
    if client is not None:
        client.close()
```

(Or use `contextlib.nullcontext()` to keep the `with` shape.)

### WR-03: `--analysis-url` path component beyond `/api/v1` is silently dropped

**File:** `analysis/call_shot_analysis.py:152, 177, 231`

**Issue:**

Both the long-lived client and `preflight` strip the URL at `/api/v1` and then
rebuild a hardcoded `/api/v1/production/shot-analysis` path. Because `client.post()`
is called with an **absolute** path, RFC 3986 resolution replaces any path in
`base_url` entirely. Empirically:

```text
httpx.URL("http://host:8000/some/other/path").join("/api/v1/production/shot-analysis")
  -> http://host:8000/api/v1/production/shot-analysis
```

So `--analysis-url http://host:8000/foo/bar/api/v1/...` silently requests
`/api/v1/production/shot-analysis` regardless. The `--help` text says "含
/api/v1/production/shot-analysis path" but doesn't warn the path is also hardcoded
and the suffix is ignored. An operator that sets a custom path (e.g., a reverse
proxy that mounts the route under `/prod/api/v1/...`) will get the default path
with no error.

**Fix:** either (a) drop the path-stripping in `preflight` and let `--analysis-url`
be the full URL (use `""` as the post path), or (b) factor the path into a module
constant and document it as non-customizable:

```python
ROUTE_PATH = "/api/v1/production/shot-analysis"   # hardcoded route path (CONTEXT lock)

# long-lived client uses the host-only base; post uses ROUTE_PATH
base = args.analysis_url.rsplit("/api/v1", 1)[0]
with httpx.Client(base_url=base, timeout=...) as client:
    ...
    resp = client.post(ROUTE_PATH, json=body)
```

(Consistent base for both `preflight` and `call_route`, removes the surprising
absolute-path-replace behavior, and DRYs the hardcoded string — see IN-01.)

### WR-04: `_cache_key` comparison omits `route_name` despite documented key

**File:** `analysis/call_shot_analysis.py:248-249`

**Issue:**

The module docstring (line 45) and the per-shot cache-write (lines 271-277) both
treat the cache key as the **4-tuple** `(video_content_hash, route_name,
route_version)`. But the cache-lookup check only compares two of the four:

```python
ck = cached.get("_cache_key", {})
if (ck.get("video_content_hash") == vch
        and ck.get("route_version") == ROUTE_VERSION):
```

`route_name` is written into `_cache_key` but never read back. The fourth element
(`shot_id`) is encoded in the filename (`shot_{sid:03d}.json`), which is fine.

This is practically benign today — `ROUTE_NAME` is a module constant that never
changes at runtime — but it's a latent bug if a second route is ever cached under
the same `route_cache/` tree (e.g., a future Phase 7 re-id route), and it
contradicts the documented key shape (which makes the next reviewer assume the
check is complete).

**Fix:**

```python
if (ck.get("video_content_hash") == vch
        and ck.get("route_name") == ROUTE_NAME
        and ck.get("route_version") == ROUTE_VERSION):
```

### WR-05: `--analysis-url` embedded credentials may leak into `asset.json.warnings`

**File:** `analysis/call_shot_analysis.py:163, 319-320`

**Issue:**

`f"{type(e).__name__}: {e}"` interpolates `str(e)`. For `httpx.HTTPError`
subclasses, `str(e)` typically includes the request URL. If the operator passes
`--analysis-url http://user:pass@host:8000/...` (basic auth in URL), the warning
string can contain the credentials, which then flow into
`route_cache/warnings.json` → `export_asset.py:307-318` → `asset.json#generator.warnings`
→ shipped with the asset. The schema explicitly forbids "auth tokens/body
payloads" in `warnings` (`asset.schema.json:59`).

Modern httpx versions mask auth in `URL.__str__` (shows `user:***@`), so this is
defense-in-depth rather than an active leak today — but the exporter accepts any
`list[str]` without redaction, so a future httpx regression or a different
exception path (e.g., a custom transport that surfaces the raw URL) would expose
it.

**Fix:** redact in the warning-builder, or assert the URL has no embedded auth
at startup:

```python
def _safe_error(e: Exception) -> str:
    msg = str(e)
    # Defense-in-depth against credential leak if URL has user:pass@host
    import re
    return re.sub(r"(https?://)([^@/]+@)", r"\1***@", msg)
```

### WR-06: `verify_phase6_smoke.py` does not cover the stale-cache + offline scenario (CR-01 reproduces silently)

**File:** `scripts/verify_phase6_smoke.py:250-348`

**Issue:**

The harness has three scenarios:
- `route_down` (no pre-existing cache)
- `skip_semantic`
- `cache_hit_offline` (pre-fills cache with **correct** `_cache_key`)

None of them pre-fill the cache with a **mismatched** `_cache_key` while `route_down`
is true. That is exactly the CR-01 surface, and it's the most plausible real-world
trigger (operator swaps video file, runs `--offline`, gets empty prompts without
warning). The harness as written cannot detect CR-01 — it false-passes.

This is also the reason CR-01 was not caught during the brief's "3/3 green"
verification.

**Fix:** add a fourth scenario alongside `cache_hit_offline`:

```python
def scenario_stale_cache_offline(verbose: bool = False) -> tuple:
    """Pre-fill cache with WRONG _cache_key, run --offline, assert warning emitted."""
    work_dir = _tmp_work_dir()
    try:
        # ... write shots.json with 1 shot ...
        # ... pre-fill shot_001.json with mismatched video_content_hash ...
        # ... run --offline against UNREACHABLE_URL ...
        # Assert: exit 0 AND len(warnings) >= 1 AND
        #         any("stale-cache" in w or "cache-miss" in w for w in warnings)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
```

---

## Info

### IN-01: Hardcoded route path duplicated in 3 places

**File:** `analysis/call_shot_analysis.py:152, 177, 182`

The string `"/api/v1/production/shot-analysis"` appears in `call_route.post()`,
`preflight`'s `rsplit` arg, and `preflight`'s `probe.get()`. Any change to the
route path requires editing three lines with no compile-time guard that they
stay in sync. Factor into `ROUTE_PATH = "/api/v1/production/shot-analysis"` at
module scope alongside `ROUTE_NAME` / `ROUTE_VERSION`.

### IN-02: `s["id"]` assumed present without `KeyError` guard

**File:** `analysis/call_shot_analysis.py:236`

`shots.json` schema requires `id`, but a malformed shots file (e.g., exported
from a different tool, or truncated) would `KeyError` here and abort the step
with a bare traceback instead of an actionable error. Defensive:

```python
try:
    sid = s["id"]
except KeyError:
    sys.exit(f"shots.json entry missing 'id' field: {s!r}")
```

### IN-03: `scenario_cache_hit_offline` docstring overstates "0 网络调用（offline + cache hit 双保险）"

**File:** `scripts/verify_phase6_smoke.py:30, 293`

The "双保险" framing implies both conditions are needed to prevent network
calls. In the implementation, `route_down = args.offline` short-circuits the
network-call block unconditionally before the cache check matters. Cache hit is
needed only to populate the camera value, not to suppress network. The harness
works correctly, but the comment misrepresents the defense-in-depth structure
and could mislead a future maintainer into thinking cache-hit alone is
sufficient to suppress network calls.

### IN-04: `_safe_mtime(prompts_json) > _safe_mtime(shots_json)` is `>` not `>=`

**File:** `run_pipeline.py:187`

If `prompts.json` and `shots.json` have identical mtime (possible on fast
filesystems with coarse mtime resolution, or when both are written by the same
`os.replace` second), the cache miss fires and `call_shot_analysis.py` re-runs
unnecessarily. Not incorrect, just a minor extra invalidation. Consistent with
`step_export`'s pattern, so changing it would diverge from the established
convention — leave as-is, but worth knowing.

---

## Schema Additivity Verification (asset.schema.json)

Diffed the v1.0 schema (git tag) against the Phase 6 changes — **additive only**,
no required/const drift:

| Path | v1.0 | Phase 6 | Verdict |
|---|---|---|---|
| `additionalProperties: false` at root | yes | yes | unchanged |
| `required` at root | 6 keys | 6 keys (no `warnings`) | additive only |
| `generator.required` | `tool, version, generated_at` | same (no `warnings`) | additive only |
| `generator.warnings` | absent | optional `array<string>` | additive ✓ |
| `data.required` | 5 keys | 5 keys (no `characters`/`props`) | additive only |
| `data.characters`, `data.props` | absent | optional `string` (anti-traversal pattern) | additive ✓ |
| `media.required` | `video, stems` | same | additive only |
| `media.characters`, `media.props` | absent | optional `array<string>` (anti-traversal pattern) | additive ✓ |
| `schema_version` pattern | semver-lite | unchanged | ✓ |
| `asset_type` const | `"shottimeline"` | unchanged | ✓ |

All four additive keys are guarded by anti-traversal patterns
(`^(?!.*\\.\\.)([^/]+/)*...`) consistent with the existing `stems/*.wav` patterns.
v1.0 assets without these keys still validate. Producer emits `generator.warnings`
only when the list is non-empty (`export_asset.py:191`), so clean runs produce
v1-shaped output — graceful-degrade default preserved.

---

## REVIEW COMPLETE

**Status:** `findings` — 2 BLOCKER, 6 WARNING, 4 INFO.

The two blockers (CR-01 stale-cache silent degrade, CR-02 uncaught non-httpx
exceptions) both reproduce against the current code and are outside the harness's
coverage envelope — they should be fixed before this code is asked to handle a
real route round-trip in production. The warnings are correctness/robustness
gaps (cache invalidation, httpx-required offline, contract inconsistencies) that
won't block the green path but will bite during route instability or operator
workflow changes. Schema changes are clean additive-only.
