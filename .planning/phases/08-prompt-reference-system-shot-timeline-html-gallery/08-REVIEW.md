---
phase: 08-prompt-reference-system-shot-timeline-html-gallery
reviewed: 2026-07-25T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - prompts/attach_refs.py
  - scripts/export_asset.py
  - scripts/verify_contract.py
  - html/gen_timeline_html.py
  - run_pipeline.py
  - scripts/verify_phase8_smoke.py
findings:
  critical: 1
  warning: 5
  info: 5
  total: 11
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-07-25
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 8 ships the prompt-reference system (attach_refs.py), registry snapshot
freezing in export_asset.py, prompts→registry integrity (Pitfall 17), the
HTML gallery with `_esc()` XSS defense, and the step_timeline mtime cache
extension. The idempotency, snapshot-freeze, and confirmed-only properties
were verified empirically by re-running `verify_phase8_smoke.py`
(6/6 green) plus targeted reproductions.

However, the Phase 7 CR-04 XSS-defense carry-over is **incomplete**. The
review focus explicitly asks "is `_esc()` applied to EVERY operator-influenced
name/ID interpolation?" — and the answer is no. The page `<title>` and the
`<h1>` heading are still interpolated raw from the operator-supplied video
filename / `--title` flag, and the resulting HTML executes attacker-controlled
`<script>` in the browser. This is a BLOCKER that the smoke harness's
scenario 6 cannot catch (it only tests ONE specific payload against ONE
specific sink).

A handful of robustness/consistency warnings round out the report:
TOCTOU inconsistency in step_timeline, TypeError on null registry names,
attribute-context breakout via `--video-src`, narrow XSS smoke coverage,
and silent corruption in `_build_registry_snapshot`.

## Critical Issues

### CR-01: XSS via unescaped `title` interpolation in `<title>` and `<h1>`

**File:** `html/gen_timeline_html.py:211` (head `<title>`) and `:312` (body `<h1>`)
**Issue:**

Phase 7 CR-04 introduced `_esc()` and Phase 8 carried it over to gallery cards
(`build_html:178,179,188,189`) and ref-chip badges (JS-side `_esc` at `:371-375`).
But `title` — which is operator-influenced via `--title` flag or, by default,
`os.path.basename(args.video)` — is still interpolated **raw** into two HTML
contexts:

```python
# build_html:211 (head)
<title>{title}</title>

# build_html:312 (body)
<h1>🎵 {title} ({n_shots_val} shots)</h1>
```

`title` defaults to `f"音轨时间轴 - {os.path.basename(args.video) if args.video else 'video'}"`
(gen_timeline_html.py:1258). Linux filenames permit `<`, `>`, `"`, `'`
(everything except `/` and NUL), so an attacker-controlled video filename
becomes executable HTML in the victim's browser when the operator runs
`python3 run_pipeline.py --video '<malicious>.mp4'`.

**Empirical reproduction (run during this review):**

```bash
$ python3 html/gen_timeline_html.py --shots shots.json \
    --title 'x</title><script>alert(1)</script>' --output timeline.html
# HTML now contains:  <title>x</title><script>alert(1)</script></title>
# Browser parses a NEW <script> element in <head> and executes alert(1).

$ python3 html/gen_timeline_html.py --shots shots.json \
    --title 'ep</h1><script>alert(document.cookie)</script><h1>' --output t.html
# HTML now contains:  <h1>🎵 ep</h1><script>alert(document.cookie)</script><h1> ...
# Browser closes the real <h1> at the payload's </h1>, then executes the script.

# Also reproducible via filesystem: create file `<img src=x onerror=alert(1)>.mp4`
# (legal Linux filename) → run_pipeline → timeline.html executes onerror handler.
```

This is precisely the class of bug Phase 7 CR-04 was supposed to eliminate,
and Phase 8's stated XSS focus ("is `_esc()` applied to EVERY operator-influenced
interpolation?") should have caught it. The carry-over is selective, not
complete.

`verify_phase8_smoke.py` scenario 6 (`html_xss_inert`) does NOT catch this
because it tests only one sink (gallery card `name`) with only one payload
(literal `</script><script>`). See WR-04.

**Fix:**

```python
# html/gen_timeline_html.py:206 (in build_html), after computing title:
safe_title = _esc(title)
# Then replace both raw interpolations:
#   <title>{title}</title>          →  <title>{safe_title}</title>
#   <h1>🎵 {title} (...)</h1>        →  <h1>🎵 {safe_title} (...)</h1>
```

While at it, also `_esc(video_src)` in `<source src="{video_src}">` (line 324)
and any other operator-influenced value interpolated into HTML — see WR-03.

## Warnings

### WR-01: `step_timeline` cache uses raw `os.path.getmtime` (TOCTOU inconsistent with `step_export`)

**File:** `run_pipeline.py:343-347`
**Issue:**

`step_timeline`'s mtime cache reads mtimes directly:

```python
if os.path.exists(out_html) and os.path.getmtime(out_html) > max(
        os.path.getmtime(shots_json),
        os.path.getmtime(audio_json) if audio_json else 0,
        os.path.getmtime(transcript) if transcript else 0,
        os.path.getmtime(prompts_json) if prompts_json and os.path.exists(prompts_json) else 0):
```

The project already has a `_safe_mtime` helper (`run_pipeline.py:387-398`)
specifically built to fix this TOCTOU in `step_export` (docstring: *"两步
之间存在 TOCTOU 窗口：另一进程删文件会让 getmtime raise FileNotFoundError
变 uncaught traceback"*) and `step_semantic`/`step_reid` (which use `_safe_mtime`).
`step_timeline` was missed when this defense was added — it still has the
exists-then-getmtime two-step pattern on `out_html`, `shots_json`, plus
direct `getmtime` on inputs.

If any input file is removed between the check and the `getmtime` call (e.g.
concurrent `--force` rerun, external cleanup script, NFS hiccup), the user
sees a raw FileNotFoundError traceback instead of a cache miss.

This is also a Phase 8 regression surface: the new `prompts_json` mtime
check uses the same unsafe pattern, so the very fix Pitfall 9 was guarding
(attach_refs rewrite → cache miss) can itself be bypassed by a TOCTOU race.

**Fix:**

```python
# Mirror step_export's pattern (run_pipeline.py:442-444)
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

### WR-02: `attach_refs._recompose` crashes TypeError on registry entry with `name: null`

**File:** `prompts/attach_refs.py:87-88, 134-135`
**Issue:**

`_load_registry` filters `characters.json`/`props.json` to `review_state ==
"confirmed"` but **does not schema-validate** the input (only the output
`prompts.json` is validated at lines 168-178). So a malformed registry entry
with `"name": null` flows through:

```python
# attach_refs.py:87
cid = c.get("id")
name_by_char[cid] = c.get("name", cid)   # if "name": null → stores None
                                         # (.get default only fires when key absent)

# attach_refs.py:134
names = [name_by_char.get(cid, cid) for cid in crefs]   # [None, ...]
parts.append(f"角色:[{', '.join(names)}]")               # TypeError: can't join None
```

`', '.join([None])` raises `TypeError: sequence item 0: expected str
instance, NoneType found`. The traceback propagates uncaught from main()
(the `try/except (OSError, json.JSONDecodeError)` in `_load_registry` only
covers load-time errors, not the in-memory None that survives the load).

The schema (characters.schema.json:21) does reject null names, but defense-
in-depth says: don't trust upstream input. apply_edits.py bugs, hand-edits,
or future schema changes can all surface a None here.

Realistic trigger: an operator edits characters.json during HITL review,
sets a character's name to JSON `null` accidentally (intended to flag for
deletion), confirms it, runs the pipeline → `attach_refs.py` crashes with
a TypeError traceback instead of a labeled `[attach-refs]` error.

**Fix:**

```python
# attach_refs.py:87 — coerce name to str, fall back to cid
raw_name = c.get("name")
name_by_char[cid] = str(raw_name) if raw_name else cid

# Same pattern for props at line 95
raw_name = p.get("name")
name_by_prop[pid] = str(raw_name) if raw_name else pid
```

### WR-03: `video_src` interpolated raw into `<source src="{video_src}">` attribute

**File:** `html/gen_timeline_html.py:324`
**Issue:**

```python
<source src="{video_src}" type="video/mp4">
```

`video_src` defaults to `os.path.basename(args.video)` (line 1257) or can be
set explicitly via `--video-src`. Either way it's operator-influenced and
unescaped. While the HTML parser treats attribute values as raw text
(until the closing `"`), a payload containing `"` breaks out of the
attribute quoting:

```
$ python3 html/gen_timeline_html.py --shots shots.json \
    --video-src 'x" onerror="alert(1)' --output t.html
# HTML: <source src="x" onerror="alert(1)" type="video/mp4">
```

Modern browsers do not fire `onerror` on `<source>` elements directly, so
this specific payload is low-impact. But the principle — operator-controlled
string interpolated into an HTML attribute without escaping — is a defense-
in-depth failure, and the same `video_src` is reused in the JS template
literal `${STEM_BASENAME}` (line 659) where the impact differs.

This is the same class of bug as CR-01; the fix (`_esc`) is one line.

**Fix:**

```python
# html/gen_timeline_html.py, in build_html where video_src is consumed:
safe_video_src = _esc(video_src)
# Then: <source src="{safe_video_src}" type="video/mp4">
```

### WR-04: Smoke scenario 6 (`html_xss_inert`) tests only ONE XSS payload against ONE sink

**File:** `scripts/verify_phase8_smoke.py:481-545`
**Issue:**

Scenario 6 seeds one registry entry with `name="</script><script>alert(1)</script>"`
and asserts the literal substring `"</script><script>"` does not appear in
the generated HTML. That proves the JSON-in-script `</`→`<\/` defense works
for THAT specific payload in THAT specific sink (the inline JSON literal).

It does NOT cover:
- Other sinks: page `<title>`, `<h1>`, `<source src>`, `--stem-basename`
  audio references — all of which interpolate operator-influenced values raw
  (see CR-01, WR-03).
- Other payloads: `<img onerror=...>` (escaped by `_esc` for gallery cards
  but untested), attribute breakout via `"`, `'`-quoted attributes, etc.
- Defense-in-depth: the smoke cannot detect a future regression where
  someone adds a new interpolation point and forgets `_esc`.

The smoke's narrow scope is precisely why CR-01 survived: the smoke proves
"the gallery-card name path is inert" but not "the HTML is XSS-inert."
Given the Phase 8 review's explicit XSS focus, this is a significant
false-negative risk.

**Fix:**

```python
# Add at least these assertions to scenario_html_xss_inert (or a new
# scenario_html_xss_inert_full):
# (1) title in <h1> context — drive via --title flag
# (2) title breakout from <title> element — drive via --title with </title>
# (3) video_src attribute breakout — drive via --video-src
# (4) Gallery name with <img onerror> payload (not just </script><script>)
# (5) ID with attribute-breakout chars (if hand-edit path is in scope)
#
# Concretely:
r = subprocess.run([gen_timeline_html, '--shots', shots,
                    '--title', 'x</title><script>alert(1)</script>',
                    '--output', html])
html = open(html).read()
assert '<script>alert(1)</script>' not in html.split('</head>')[0], \
    "head script injection via title"
```

Without broader coverage, "smoke green" gives false confidence about XSS
posture.

### WR-05: `_build_registry_snapshot` silently emits empty snapshot on malformed registry JSON

**File:** `scripts/export_asset.py:179-191`
**Issue:**

When `characters.json` / `props.json` exist but are malformed (truncated
write, mid-edit crash), the function sets `snapshot["characters"] = []`
(or props) and returns the dict — which then becomes
`generator.registry_snapshot = {characters: [], props: []}` in the emitted
asset.json:

```python
if os.path.isfile(chars_path):
    try:
        with open(chars_path, encoding="utf-8") as f:
            snapshot["characters"] = _project(json.load(f))
    except (OSError, json.JSONDecodeError):
        snapshot["characters"] = []     # silent — no [warn] print
```

The operator sees an asset that claims "this video has zero characters and
zero props" rather than "registry unreadable, please investigate." A
downstream consumer (canvas) renders an empty gallery and the corruption is
invisible until someone notices the missing cards. Compare export_asset.py:437
which DOES print `[warn] route_cache/warnings.json malformed → ignoring: {e}`
on the sidecar — inconsistent treatment of two malformed-JSON inputs in the
same file.

Worse: because the function returned a non-None value, the conditional emit
(`**({"registry_snapshot": snapshot} if snapshot is not None else {})` at
line 323) DOES emit the empty snapshot — so the corruption is persisted
into asset.json, not just left out.

**Fix:**

Either print a warning (consistent with sidecar pattern), or skip the
malformed side entirely (return None for that side so it's omitted from
the snapshot dict), or fail loud (sys.exit) since a corrupt canonical
registry is a real producer-side problem.

```python
# Minimal fix: print warning (mirror line 437 sidecar pattern)
except (OSError, json.JSONDecodeError) as e:
    print(f"[warn] characters.json malformed → snapshot will be empty: {e}")
    snapshot["characters"] = []
```

## Info

### IN-01: `console.log` debug statements in embedded production HTML

**File:** `html/gen_timeline_html.py:679, 738, 740`
**Issue:** Three `console.log(...)` / `console.error(...)` calls ship in
the embedded `<script>` block of every generated timeline.html. CLAUDE.md
notes `print(...)` is the Python-side convention; the browser equivalent
should be removed (or wrapped in a `DEBUG` flag) for shipped artifacts.

**Fix:** Delete the three statements, or gate behind `if (window.DEBUG)`.

### IN-02: `attach_refs._load_registry` swallows `JSONDecodeError` without `[warn]` print

**File:** `prompts/attach_refs.py:62-63, 72-73`
**Issue:**

```python
except (OSError, json.JSONDecodeError):
    pass   # 静默降级 —— 不阻断 timeline 生成
```

The "silent degrade" is the documented behavior, but the project convention
(bracketed `[stage]` prefixes; see export_asset.py:437, separate_stems.py)
is to emit a `[warn]` line on degraded paths so operators can diagnose.
A malformed registry currently produces zero console output — the timeline
silently renders without refs and the operator has no signal.

**Fix:** `print(f"[warn] characters.json malformed → refs will be empty: {e}")`
before the `pass`.

### IN-03: `attach_refs.py` lazy-imports `jsonschema` with no fallback / no friendly error

**File:** `prompts/attach_refs.py:169`
**Issue:** `from jsonschema import Draft202012Validator` inside `main()`
raises an uncaught `ModuleNotFoundError` traceback if the dependency is
absent. This is consistent with `export_asset.py:120` (same pattern) so
not a regression — but if the project ever cares about friendly errors
for missing optional deps (cf. `audio/transcribe.py` which catches
`ImportError` and falls back), both files should be updated together.

**Fix:** Optional — wrap in try/except and emit `[attach-refs] jsonschema
required for pre-write validation: pip install jsonschema`.

### IN-04: `_atomic_write` uses fixed `.tmp` suffix — concurrent-invocation race

**File:** `prompts/attach_refs.py:32-37`
**Issue:** `tmp = path + ".tmp"` — if two `attach_refs` processes ever run
concurrently against the same `--prompts` path (e.g. an orchestration
mistake, or `--force` racing a scheduled rerun), they would clobber each
other's `.tmp` file before `os.replace`. The pipeline is single-threaded
so this is theoretical, but `tempfile.mkstemp(dir=..., prefix=".tmp-")`
would eliminate the window structurally.

**Fix:** Optional — use `tempfile.NamedTemporaryFile(dir=os.path.dirname(path),
delete=False)` and `os.replace(tmp.name, path)`.

### IN-05: `attach_refs._recompose` destructively overwrites upstream `prompt_text`

**File:** `prompts/attach_refs.py:108, 146`
**Issue:** `_recompose` always rebuilds `prompt_text` from facets + identity
clauses via the Pattern 2 locked template, discarding whatever `prompt_text`
was present in the input. This is intentional per the docstring ("PROMPT-02
deterministic identity-injecting recomposition (Pattern 2 锁定)") and per the
ROADMAP/CONTEXT design — but it does mean an operator who hand-tunes
`prompt_text` in `prompts.json` (e.g. to add a custom suffix for a specific
shot) will have their edit silently replaced on the next pipeline run.

**Fix:** No code change required if Pattern 2 is the locked contract. Worth
a one-line doc note in the operator-facing README that `prompt_text` is
derived, not authoritative. (If preservation is ever desired: add a
`--preserve-prompt-text` flag that only attaches refs without recomposing.)

---

_Reviewed: 2026-07-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
