---
phase: 08-prompt-reference-system-shot-timeline-html-gallery
fixed_at: 2026-07-25T00:00:00Z
review_path: .planning/phases/08-prompt-reference-system-shot-timeline-html-gallery/08-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 8: Code Review Fix Report

**Fixed at:** 2026-07-25
**Source review:** `.planning/phases/08-prompt-reference-system-shot-timeline-html-gallery/08-REVIEW.md`
**Iteration:** 1
**Scope:** critical + warning (1 BLOCKER + 5 WARNING; 5 INFO explicitly out of scope)

**Summary:**
- Findings in scope: 6
- Fixed: 6
- Skipped: 0
- Status: all_fixed

Each fix was empirically reproduced (the original failure was triggered on the
pre-fix code), the fix was applied, and the same reproduction script was re-run
to confirm the failure no longer occurs. Per-finding commits are atomic with
conventional `fix(08): <ID> <one-line>` format.

## Fixed Issues

### CR-01: XSS via unescaped `title` interpolation in `<title>` and `<h1>`

**Files modified:** `html/gen_timeline_html.py`
**Commit:** `e5e0299`
**Root cause:** Phase 7 CR-04 `_esc()` carry-over was selective — applied to
gallery card `name`/`id`/`representative_image` and ref-chip badges, but the
page `<title>` (line 211) and `<h1>` (line 312) still interpolated `title`
raw. `title` defaults to `f"音轨时间轴 - {os.path.basename(args.video)}"`
or the `--title` CLI flag; Linux filenames allow `< > " '` (everything but
`/` and NUL), so an attacker-controlled filename or `--title` payload becomes
executable HTML in the victim's browser.

**Reproduction (pre-fix, run during this fix):**
```bash
$ python3 html/gen_timeline_html.py --shots shots.json \
    --title 'x</title><script>alert(1)</script>' --output t.html
# HTML contained:  <title>x</title><script>alert(1)</script></title>
# Browser parses a NEW <script> element in <head> and executes alert(1).

$ python3 html/gen_timeline_html.py --shots shots.json \
    --title 'ep</h1><script>alert(document.cookie)</script><h1>' --output t2.html
# HTML contained:  <h1>🎵 ep</h1><script>alert(document.cookie)</script><h1> ...
```
Both confirmed: raw `<script>` element present in `<head>` / `<body>`.

**Applied fix:**
```python
# html/gen_timeline_html.py, in build_html after n_shots_val assignment:
safe_title = _esc(title)
# Then:
#   <title>{safe_title}</title>          (was: <title>{title}</title>)
#   <h1>🎵 {safe_title} ({n_shots_val} shots)</h1>   (was: ... {title} ...)
```
`_esc()` is the existing Phase 7 CR-04 helper at `html/gen_timeline_html.py:24`
(5-char HTML escape: `& < > " '`). Reused, not reinvented.

**Closed (post-fix):**
- `<script>alert(1)</script>` no longer present in `<head>` (now `&lt;script&gt;...`).
- `<script>alert(document.cookie)</script>` no longer present in body.
- Escaped forms `&lt;/title&gt;&lt;script&gt;` confirmed present.

---

### WR-01: `step_timeline` cache uses raw `os.path.getmtime` (TOCTOU inconsistent with `step_export`)

**Files modified:** `run_pipeline.py`
**Commit:** `ffa84e1`
**Root cause:** `step_timeline`'s cache check used `os.path.exists(p)` +
`os.path.getmtime(p)` — a two-step TOCTOU pattern. A concurrent `--force`
rerun, external cleanup, or NFS hiccup deleting an input between the two
calls would surface as an uncaught `FileNotFoundError` traceback. The
project already has `_safe_mtime` (`run_pipeline.py:387`) used by
`step_export` / `step_semantic` / `step_reid`; `step_timeline` was missed.
The new `prompts_json` mtime check (Pitfall 9 cache inclusion) inherited
the same unsafe pattern.

**Reproduction (pre-fix, simulated):**
```
OLD pattern raises: FileNotFoundError  (os.path.getmtime on missing file)
```

**Applied fix:** Mirrored `step_export:442-444` pattern.
```python
inputs = [shots_json]
if audio_json: inputs.append(audio_json)
if transcript: inputs.append(transcript)
if prompts_json and os.path.exists(prompts_json): inputs.append(prompts_json)
input_mtimes = [_safe_mtime(p) for p in inputs]
max_input_mtime = max(input_mtimes) if input_mtimes else 0
if os.path.exists(out_html) and _safe_mtime(out_html) > max_input_mtime:
    print(f"[7/8] cached timeline: {out_html}")
    return out_html
```

**Closed (post-fix):** `_safe_mtime(missing)` returns `+inf` → forces cache
miss (regeneration) instead of crashing. Behavior is consistent with
`step_export` / `step_semantic` / `step_reid`. The Pitfall 9 cache inclusion
of `prompts_json` is preserved (still in `inputs[]`).

---

### WR-02: `attach_refs._recompose` crashes `TypeError` on registry entry with `name: null`

**Files modified:** `prompts/attach_refs.py`
**Commit:** `bb7c1bc`
**Root cause:** `_load_registry` filtered loaded JSON to `confirmed` entries
but did **not** schema-validate the input (only the output `prompts.json`
is validated at line 168-178). A malformed registry entry with `"name": null`
passed the filter, then `name_by_char[cid] = c.get("name", cid)` stored
`None` (because `.get` default only fires when key is absent, not when value
is null). At line 134, `', '.join([None, ...])` raised
`TypeError: sequence item 0: expected str instance, NoneType found`,
propagating as an uncaught traceback.

**Reproduction (pre-fix):**
```
$ cat characters.json
[{"id":"char_001","name":null,"appearance_shots":[1],"review_state":"confirmed"}]
$ python3 prompts/attach_refs.py --prompts p.json --work-dir .
# TypeError: sequence item 0: expected str instance, NoneType found
#   File ".../attach_refs.py", line 135, in _recompose
#     parts.append(f"角色:[{', '.join(names)}]")
```

**Applied fix:** Chose option (a) from REVIEW.md — schema-validate loaded
canonical registry BEFORE filter/consume (preferred; consistent with Phase 7
WR-05 apply_edits.py `_validate` pattern).
```python
# prompts/attach_refs.py — new helper (mirror apply_edits._validate):
def _validate_registry(schema_path, instance, label):
    from jsonschema import Draft202012Validator
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    errors = list(Draft202012Validator(schema).iter_errors(instance))
    if errors:
        msgs = [...]
        sys.exit(f"[attach-refs] FAIL: {label} registry ({schema_path.name}) "
                 f"validation failed ({len(errors)} errors):\n" + "\n".join(msgs))

# In _load_registry, after json.load(f):
_validate_registry(CHARACTERS_SCHEMA, loaded, "characters")
chars = [c for c in loaded if ...]   # filter runs AFTER schema gate
```
The schema (`characters.schema.json:19-22`) already requires `name` to be
a non-empty string — defense-in-depth now enforces it at attach_refs load
time instead of relying on upstream apply_edits correctness.

**Closed (post-fix):**
```
$ python3 prompts/attach_refs.py --prompts p.json --work-dir .
# [attach-refs] FAIL: characters registry (characters.schema.json) validation
#   failed (1 errors):
#   - [0/name] None is not of type 'string'
# (exit 1, labeled [attach-refs] FAIL — not a bare TypeError traceback)
```
Valid registry case unchanged (regression-checked): `小明` still flows to
`prompt_text: "s · sc · 角色:[小明] · x · a · c · l"`.

---

### WR-03: `video_src` interpolated raw into `<source src="{video_src}">` attribute

**Files modified:** `html/gen_timeline_html.py`
**Commit:** `02d59c0`
**Root cause:** Same class as CR-01 — `video_src` (defaults to
`os.path.basename(args.video)` or `--video-src` flag) interpolated raw into
`<source src="{video_src}">`. Payload containing `"` breaks out of the
double-quoted attribute, injecting a new attribute.

**Reproduction (pre-fix):**
```bash
$ python3 html/gen_timeline_html.py --shots shots.json \
    --video-src 'x" onerror="alert(1)' --output t.html
# HTML: <source src="x" onerror="alert(1)" type="video/mp4">
```
Modern browsers don't fire `onerror` on `<source>` directly (low impact),
but the principle — operator-controlled string in HTML attribute without
escaping — is defense-in-depth failure.

**Applied fix:**
```python
safe_video_src = _esc(video_src)
# Then: <source src="{safe_video_src}" type="video/mp4">
```
`_esc` converts `"` → `&quot;` (HTML5 parser restores `"` inside the
attribute, but it's no longer a delimiter).

**Closed (post-fix):**
```
SOURCE LINE: <source src="x&quot; onerror=&quot;alert(1)" type="video/mp4">
raw onerror attribute survived: False
```

---

### WR-04: Smoke scenario 6 (`html_xss_inert`) tests only ONE XSS payload against ONE sink

**Files modified:** `scripts/verify_phase8_smoke.py`
**Commit:** `a73a897`
**Root cause:** Original scenario 6 seeded one registry entry with
`name="</script><script>alert(1)</script>"` and asserted the literal
substring `"</script><script>"` was not in the HTML. That proved the
JSON-in-script `</`→`<\/` defense worked for THAT payload in THAT sink
(the inline JSON literal). It did not cover:
- Other sinks: page `<title>`, `<h1>`, `<source src>` — all of which
  interpolated operator-influenced values raw (CR-01, WR-03).
- Other payloads: `<img onerror=...>`, attribute breakout via `"`, etc.
- Defense-in-depth: future regressions where someone adds a new
  interpolation point and forgets `_esc`.

The narrow scope is precisely why CR-01 and WR-03 survived Phase 8 review.

**Reproduction (pre-fix, simulated regression):** When CR-01 was reverted
(title sink raw interpolation restored), the original scenario 6 still
PASSED (it didn't test the title sink).

**Applied fix:** Broadened `scenario_html_xss_inert` to a 5-sink ×
multi-payload XSS matrix:

| # | Sink | Payload | Defense |
|---|------|---------|---------|
| a | gallery name (body)         | `</script><script>alert(1)</script>` | CR-04 carry (`_esc`) |
| b | gallery name (body)         | `<img src=x onerror=alert(1)>`       | CR-04 carry (`_esc`) |
| c | page `<title>` (head)       | `</title><script>alert('title')...</script><h1>` | CR-01 fix (`_esc(title)`) |
| d | page `<h1>` (body)          | (same title payload, also hits h1 sink) | CR-01 fix |
| e | `<source src>` (attribute)  | `x" onerror="alert(1)`               | WR-03 fix (`_esc(video_src)`) |

**Forbidden raw patterns (must NOT appear in HTML):**
- `</script><script>` (JSON-in-script defense failure)
- `</title><script>` (title head breakout)
- `</h1><script>` (h1 body breakout)
- `src="x" onerror` (source attribute breakout)
- `onerror="alert(1)` (raw attribute injection)

**Positive assertions (escaped forms MUST appear):**
- `&lt;script&gt;` (gallery name via `_esc`)
- `&lt;img src=x onerror=alert(1)&gt;` (char_002 gallery name via `_esc`)
- `&lt;/title&gt;&lt;script&gt;` (title via `_esc`)
- `x&quot; onerror=&quot;alert(1)` (video_src via `_esc`)

**Closed (post-fix):** Scenario 6 now catches simulated regressions of both
CR-01 (title sink) and WR-03 (video_src sink) — verified by temporarily
reverting each fix and confirming the scenario FAILs with a labeled reason.
Full smoke returns to 6/6 green when fixes are in place.

---

### WR-05: `_build_registry_snapshot` silently emits empty snapshot on malformed registry JSON

**Files modified:** `scripts/export_asset.py`
**Commit:** `b8f4db7`
**Root cause:** When `characters.json` / `props.json` existed but contained
malformed JSON (truncated write, mid-edit crash) or schema-invalid content
(e.g. `name: null`), `_build_registry_snapshot` set `snapshot["characters"]
= []` (or props) silently — no `[warn]` print. The non-None return value
then caused `**({"registry_snapshot": snapshot} if snapshot is not None
else {})` at line 323 to emit the empty snapshot into `asset.json`. The
operator sees "this video has zero characters/zero props" rather than
"registry unreadable, investigate." Corruption persists into the asset
and is invisible until a downstream consumer (canvas) notices missing
cards. Inconsistent with line 437 sidecar pattern which DOES print
`[warn] route_cache/warnings.json malformed → ignoring: {e}`.

**Reproduction (pre-fix):** With a truncated `characters.json`, the
function returned `{'characters': [], 'props': []}` (or just
`{'characters': []}`) — non-None, so the empty snapshot was emitted.

**Applied fix:** Per task spec: on malformed JSON (`JSONDecodeError`/
`OSError`) OR schema-invalid content, **print `[warn]` + return `None`**
(snapshot field OMITTED from asset.json). Mirrors line 437 sidecar
philosophy; consistent with attach_refs WR-02 schema-gate.

```python
class _SchemaInvalid(Exception):
    """signal exception for schema-invalid registry (not sys.exit)."""
    ...

def _validate_registry_for_snapshot(schema_path, instance, label):
    """fail-soft schema check (raise vs sys.exit) — lets caller decide."""
    from jsonschema import Draft202012Validator
    ...
    if errors: raise _SchemaInvalid(msgs)

def _build_registry_snapshot(work_dir):
    ...
    for path, schema_path, key, label in (
            (chars_path, CHARACTERS_SCHEMA, "characters", "characters.json"),
            (props_path, PROPS_SCHEMA, "props", "props.json")):
        if not os.path.isfile(path): continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            _validate_registry_for_snapshot(schema_path, data, label)
            loaded[key] = _project(data)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[warn] {label} malformed → registry_snapshot will be OMITTED: {e}")
            return None
        except _SchemaInvalid as e:
            print(f"[warn] {label} schema-invalid → registry_snapshot will be OMITTED: "
                  f"{e.errors[0] if e.errors else e}")
            return None
    return loaded
```

**Closed (post-fix):** 4-case verification matrix pass:
- (A) Malformed JSON → `[warn]` printed + returns `None` (snapshot OMITTED)
- (B) Schema-invalid (`name: null`) → `[warn]` printed + returns `None`
- (C) Valid registry → returns projected dict (no regression)
- (D) No files → returns `None` (graceful-degrade byte-identical to v1.0)

---

## Skipped Issues

None. All 6 in-scope findings were fixed.

## Final Gate Results

All six final-gate commands pass after the fixes:

| Gate | Command | Result |
|------|---------|--------|
| 1 | `python3 spec/validate.py` | OK (minimal failures=0, v1.1 failures=0, smoke failures=0) |
| 2 | `python3 scripts/verify_phase8_smoke.py` | OK: 6/6 scenarios green (scenario 6 broadened) |
| 3 | `python3 scripts/verify_phase7_smoke.py` | OK: 5/5 scenarios green (no regression) |
| 4 | `python3 scripts/verify_phase6_smoke.py` | OK: 4/4 scenarios green (no regression) |
| 5 | `PHASE4_ASSET_DIR=... python3 scripts/verify_contract.py --mode=producer` | OK (asset.json + data shapes schema-valid; v1↔v1.1 cross-version compat) |
| 6 | `PHASE4_ASSET_DIR=... PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer` | OK (self-test corrupt-asset rejection + producer pass) |

Note: `output/` is gitignored; the producer contract gate was run against the
main checkout's existing `output/<asset>/` directory (read-only — the gate
validates existing `asset.json` against the schema; my changes do not affect
this consumer-side check).

## Out-of-Scope (5 INFO findings)

Not addressed (default scope = critical + warning). Listed for completeness:

- IN-01: `console.log` debug statements in embedded production HTML (gen_timeline_html.py:679,738,740)
- IN-02: `attach_refs._load_registry` swallows `JSONDecodeError` without `[warn]` print
- IN-03: `attach_refs.py` lazy-imports `jsonschema` with no fallback / no friendly error
- IN-04: `_atomic_write` uses fixed `.tmp` suffix — concurrent-invocation race
- IN-05: `attach_refs._recompose` destructively overwrites upstream `prompt_text`

---

_Fixed: 2026-07-25_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
