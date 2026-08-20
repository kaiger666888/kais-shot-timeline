# Phase 22: Dataset Export + Integration - Pattern Map

**Mapped:** 2026-08-20
**Files analyzed:** 13 (10 new, 3 modified)
**Analogs found:** 13 / 13 (11 with in-repo analog; 2 partial — XSS test cases and dataset-dir export have no direct same-form precedent, closest structural analogs identified)

> Corrections to RESEARCH.md found during mapping (both verified by live grep this session):
> 1. Banner renumber surface is **27** `[N/9]` literal occurrences (not 29): `[1..5/9]`×3 each, `[6/9]`×4, `[7/9]`×3, `[8/9]`×2, `[9/9]`×3 — plus **2 prose `[N/9]` mentions** in comments at run_pipeline.py:35 and :921 that should also be updated for doc hygiene.
> 2. Everything else in RESEARCH (line numbers, semantics, CLI shapes) verified accurate against source.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `html/gen_roundtrip_review.py` (NEW) | HTML generator (component) | file-I/O + transform | `html/gen_registry_review.py` (728L) | exact |
| `analysis/roundtrip/export_dataset.py` (NEW, name discretionary) | export utility (CLI) | batch file-I/O | `analysis/roundtrip/judge.py` importlib shared-load + `scripts/export_asset.py` structural | role-match |
| `registry/apply_roundtrip_edits.py` or `analysis/roundtrip/apply_edits.py` (NEW, name discretionary) | standalone HITL CLI (service) | CRUD (sidecar READ-merge) | `registry/apply_edits.py` (547L) | exact |
| `spec/schemas/roundtrip-edits.schema.json` (NEW) | config (schema) | validation | `spec/schemas/registry-edits.schema.json` | exact variant |
| `tests/test_phase22_e2e.sh` (NEW) | test (bash e2e harness) | e2e / batch | `tests/run_audio_analysis_smoke.sh` (227L) | exact |
| `tests/test_pipeline_roundtrip_wiring.py` (NEW) | test (static wiring) | static source assert | `tests/test_pipeline_vision_seq_wiring.py` | exact |
| `tests/test_roundtrip_review.py` (NEW) | test (unit) | transform (gen→assert) | `tests/test_judge.py` (importlib direct-call); XSS cases themselves novel | partial |
| `tests/test_export_dataset.py` (NEW) | test (unit) | file-I/O | `tests/test_judge.py` (tmp sidecar fixture style) | role-match |
| `tests/test_roundtrip_apply_edits.py` (NEW) | test (unit) | CRUD | `tests/test_judge.py` (apply_verdict/frozen tests, L15-18 docstring) | role-match |
| `tests/fixtures/roundtrip_sample.json` (NEW) | test fixture | — | `tests/fixtures/speaker_edits_phase13_smoke.json` (fixtures-dir precedent) | exact-form |
| `run_pipeline.py` (MODIFY) | orchestrator | batch (subprocess chain) | itself: `step_reid` + `step_export` + canvas post-step | exact (in-file) |
| `tests/test_pipeline_vision_wiring.py` (MODIFY) | test (static wiring) | static | itself (regex/substring locks) | exact |
| `tests/test_pipeline_vision_seq_wiring.py` (MODIFY) | test (static wiring) | static | itself (regex/substring locks) | exact |

## Pattern Assignments

### `html/gen_roundtrip_review.py` (HTML generator, file-I/O + transform)

**Analog:** `html/gen_registry_review.py` — UI-SPEC designates it the唯一模板. Read in full this session; excerpts below.

**XSS layer 1 — inline `_esc()`** (gen_registry_review.py:79-91; must be inlined, html/ is a namespace package with no cross-file imports — docstring at :83-84 states this explicitly):
```python
def _esc(s):
    """HTML-escape 字符串以安全插值进 HTML text/attribute context (CR-04 XSS defense)。
    转义 5 个字符: & < > " '。顺序固定 (& 先，防双重转义)。"""
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;")
                  .replace("'", "&#x27;"))
```

**XSS layer 2 — JSON-in-`<script>` bootstrap** (gen_registry_review.py:318):
```python
draft_json = json.dumps(draft, ensure_ascii=False).replace("</", "<\\/")
```

**XSS layer 3 — JS state updates via classList/textContent only** (gen_registry_review.py:509-526 `applyVisualState()`; exportEdits 642-673 builds payload from Sets, never innerHTML). Card state classes precedent (:393-394): `.state-confirmed { border-color:#3fb950; box-shadow:0 0 0 1px #3fb950 }` / `.state-rejected { opacity:0.45; border-color:#f85149 }` — mirror as `state-accept`/`state-reject` per UI-SPEC.

**Export edits JS** (gen_registry_review.py:642-673 — Blob download, copy verbatim):
```javascript
const blob = new Blob([JSON.stringify(edits, null, 2)], {{ type: 'application/json' }});
const url = URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url; a.download = 'registry.edits.json';
document.body.appendChild(a); a.click(); document.body.removeChild(a);
URL.revokeObjectURL(url);
```
New payload per UI-SPEC §5: `{accept_overrides:[int], reject_overrides:[int], review_notes:str}` — `Array.from(set).sort((a,b)=>a-b)` for int ascending (registry uses `.sort()` lexicographic at :659-660 because its IDs are strings; **shot_ids are ints — must use numeric comparator**).

**Queue sort key** (gen_registry_review.py:170-181 `_tier_sort_key` — "hardest first" tuple pattern; roundtrip version: `(missing_signal ? 0 : 1, abs(sim − τ) asc, shot_id asc)` per UI-SPEC §4).

**CSS/palette/layout** (gen_registry_review.py:331-453): GitHub-dark tokens `#0d1117/#161b22/#21262d/#30363d/#58a6ff/#3fb950/#d29922/#f85149/#8b949e` (CLAUDE.md Conventions lock). Sticky header `top:0` + queue sidebar `sticky top:80px` + `scroll-padding-top:80px` + sticky export bar — all mirror. **Single diff per UI-SPEC:** cards-container `grid-template-columns: 1fr; max-width: 1200px` (registry uses `repeat(auto-fill, minmax(440px,1fr))` at :382) because dual 16:9 videos need full row width.

**Empty state** (gen_registry_review.py:311-312): `"<p>(空 draft —— 无 cluster 可审阅)</p>"` / queue `"<p>(无)</p>"` — panel still generates. Speaker precedent confirms empty export stays schema-valid (`html/gen_speaker_review.py:32` "空 {} schema-valid"; speaker-edits.schema.json has `additionalProperties:false` + all-optional fields).

**f-string `{{ }}` discipline** (gen_registry_review.py:225-227, :323-324 comments): every literal `{`/`}` in the CSS/JS blocks must be doubled — RESEARCH Pitfall 8 (ValueError: unexpected '{').

**CLI + atomic write** (gen_registry_review.py:688-724):
```python
ap.add_argument("--draft", required=True, ...)   # roundtrip version: --roundtrip/--video/--shots/
                                                # --prompts/--tau-sim (default 0.9670)/--output
...
tmp = args.output + ".tmp"
os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
with open(tmp, "w", encoding="utf-8") as f:
    f.write(html)
os.replace(tmp, args.output)
print(f"[registry-review] wrote {args.output} ({n_clusters} clusters)")
# roundtrip 版收尾打印（UI-SPEC 生成器形态契约）: print(f"[roundtrip-review] wrote {args.output} ({n} shots)")
```

---

### `analysis/roundtrip/export_dataset.py` (export utility, batch file-I/O)

**Analog A — shared-piece reuse via importlib** (judge.py:100-103, also scorer.py:109-112 — copy this exact block):
```python
import importlib.util
_h3_spec = importlib.util.spec_from_file_location(
    "h3_regen_shared", Path(__file__).resolve().parent / "h3_regen.py")
h3s = importlib.util.module_from_spec(_h3_spec)
_h3_spec.loader.exec_module(h3s)
# 可复用: h3s.extract_endpoint_frames / resolve_source_video / video_content_hash /
#         load_shot_prompts / _atomic_write_json / _iter_sidecar_errors
```
Comment convention (judge.py:96-99) lists exactly which h3s symbols are used — keep that audit comment.

**Analog B — endpoint frame extraction, DO NOT hand-roll** (h3_regen.py:387-417 `extract_endpoint_frames`): full-resolution ffmpeg (no `-vf scale`), `lf_ts = max(start_sec, end_sec - LAST_FRAME_GUARD_SEC)` (guard const at :172), delete-old-dest-before-extract, fail-loud `RuntimeError` with `_stderr_snip`. Frame cache files land at `route_cache/h3_regen/frames/kst_{vch}_shot{NNN:03d}_{ff,lf}.jpg` (path built at :404, frames_dir defined at h3_regen.py:1314) — **direct-copy these two per accepted shot; only fall back to `h3s.extract_endpoint_frames` when absent**. Note: extracted names are fixed `kst_..._ff.jpg` — the dataset copy must rename to `first_frame.jpg`/`last_frame.jpg` inside `dataset/<video-stem>/shot_NNN/`.

**Analog C — shots/prompts join** (h3_regen.py:297-325 `load_shot_prompts`): prompts.json top level is a **flat list**, facets are flat keys (`subject/action/camera/scene/lighting/style` + `character_refs/prop_refs`), no `prompt_version` key — version comes from sidecar `regen.prompt_version`. Source video resolution order `h264.mp4 → video.mp4` (h3_regen.py:328-335 `resolve_source_video`).

**Analog D — rejected bucketing** (judge.py:604-620 `summarize_scores` tau_preview): `rejected_by_bucket = {prompt_faithful: (s < tau count), model_diverged: N, prompt_underspecified: N}` — but at export time count directly from frozen verdicts, no recompute.

**Analog E — atomic JSON write** (h3_regen.py:654-663, PID-suffixed tmp):
```python
def _atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```

**Analog F — defensive sidecar read** (h3_regen.py:770-776 `_iter_sidecar_errors` via h3s; scorer.py:458-464 `_read_sidecar_shots` swallow-to-empty read pattern). Do NOT create a schema for dataset outputs (RESEARCH Pattern 6 — dataset is not a contract surface).

**Structural analog:** `scripts/export_asset.py` — reads work_dir JSONs, computes derived counts, writes manifest + copies media; its conditional roundtrip mount at :375-404 is the shape of "read sidecar → count → emit" (with malformed→OMIT warning at :403-404).

---

### `registry/apply_roundtrip_edits.py` (or `analysis/roundtrip/apply_edits.py`) — apply CLI (CRUD)

**Analog:** `registry/apply_edits.py` — "直接模板" per CONTEXT. Structural skeleton to mirror:

**Standalone-CLI docstring/hard-gate semantics** (apply_edits.py:1-35): "独立 standalone CLI（run_pipeline.py 永远不调用它；操作员在审阅完 HTML 后手动运行）" + fixed apply order + exit-code contract in docstring.

**Schema pre-validation, fails loud** (apply_edits.py:239-259 `_validate` — lazy-import jsonschema, iter_errors, sys.exit with first-10 messages):
```python
from jsonschema import Draft202012Validator
errors = list(Draft202012Validator(schema).iter_errors(instance))
if errors: sys.exit(f"[apply-edits] FAIL: ...")
```
Apply to: roundtrip-edits schema **before** touching sidecar (T-07-02), and optionally the sidecar itself before write.

**Core apply flow** (apply_edits.py:275-509): read inputs → `_validate(EDITS_SCHEMA, edits)` → transform entries in fixed order → hard gate at build time → `_validate(OUTPUT_SCHEMA, result)` pre-write → `_atomic_write` (:262-268).

**Roundtrip-specific write-back — the critical difference from registry:** do NOT write a new file; **READ-merge into existing roundtrip.json preserving every other half**, reusing `judge._merge_write_sidecar` semantics (judge.py:326-429). Key excerpt — verdict freeze check (:371-372):
```python
if isinstance(prev.get("verdict"), dict):
    e.pop("verdict", None)                # 冻结：已有 verdict 永不覆盖
```
**This is exactly what the roundtrip apply CLI must NOT do** — human override is the one path allowed to replace a frozen verdict (CONTEXT lock; judge.apply_verdict :530-532 auto-skips frozen). Load judge via importlib (same block as judge.py:100-103 but targeting `judge.py`; note judge itself loads h3s at module level — loading judge transitively loads h3_regen, both are side-effect-safe per their comments) or reimplement merge against h3s helpers using scorer.py:347-453 (`write_scores_sidecar`) as the canonical merge-loop template (kept-keys except merged half, shallow-merge sub-object, two-layer validation, `.bak-<ts>` backup of pre-existing bad entries at :404-407/:432-435).

**Verdict entry shape to write** (judge.py:547-551 — same fields, `source:"human"`):
```python
{"shot_id": sid, "verdict": {
    "decision": decision,        # "accepted" | "rejected" from edits
    "source": "human",
    "decided_at": _utc_now_iso(),   # judge.py:321-323: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
}}
```
**Idempotency guard (A3, recommended):** skip write when `prev.verdict.source == "human" and prev.verdict.decision == new_decision` — makes replay a true no-op and aligns with judge frozen-skip semantics.

**Audit-line + summary print** (mirror judge.py:718-721 format):
```python
print(f"[roundtrip-apply] shot_{sid:03d} {prev_source}→human/{decision}")
# 收尾: print(f"[roundtrip-apply] 完成：applied=N skipped_frozen=M same_decision_replay=K（τ 无关——edits 显式）")
```

---

### `spec/schemas/roundtrip-edits.schema.json` (config/schema)

**Analog:** `spec/schemas/registry-edits.schema.json` (read in full). Mirror skeleton: `$schema` Draft 2020-12, `$id` `https://kais.shot-timeline/spec/schemas/roundtrip-edits.schema.json`, `title` naming producer (gen_roundtrip_review.py) and consumer (apply CLI), `description` + `$comment` carrying the HITL/idempotency rationale, `"type":"object"`, `"additionalProperties": false`, **all properties optional (empty `{}` valid — operator reviewed with no changes)**, trailing `review_notes: {"type":"string"}` free-text audit field.

**The one structural difference** (RESEARCH Pattern 5): overrides are **integer shot_ids**, not pattern-locked strings:
```json
"accept_overrides": {
  "type": "array",
  "items": {"type": "integer", "minimum": 1}
},
"reject_overrides": {
  "type": "array",
  "items": {"type": "integer", "minimum": 1}
},
"review_notes": {"type": "string"}
```
(integer minimum 1 matches roundtrip.schema.json:26-28 shot_id — also天然拒 path traversal, V5 control.)

---

### `tests/test_phase22_e2e.sh` (bash e2e harness)

**Analog:** `tests/run_audio_analysis_smoke.sh` (read in full, 227 lines). Copy this contract:

**Header/scenario contract** (:1-37): scenario list in header comment, `set -euo pipefail`, `WORK="/tmp/p22-smoke-$$"`, `cleanup()` + `trap cleanup EXIT` (kill background PIDs + `rm -rf WORK`).

**Assertion helpers** (:59-99): `assert_file_exists` / `assert_file_absent` / `assert_grep` / `assert_not_grep` — all `[PASS]/[FAIL]` + `exit 1` with evidence (`cat` the file on grep failure). Plus `wait_stub_ready` polling pattern (:101-113) if any background service is needed.

**Scenario shape** (:130-155): echo scenario header → run command redirecting to `${WORK}/scenN.log` → asserts on files + grep on log → `echo "[smoke] SCENARIO N: PASS"`.

**byte-identical precedent** (:153-167): snapshot `cp` after run 1, then `diff -q` after run 2 — use for RT-01 md5-equality of the 5 data JSONs + asset.json in the ComfyUI-down scenario, and sha256 of roundtrip.json in the cache-hit scenario.

**Exit contract** (:224-226): `echo "ALL_SCENARIOS_PASS"; exit 0`.

**Phase-22 specifics to layer on:** mkdtemp fixture work_dir for down-degrade (ep01 has roundtrip.json already — Pitfall 6); GPU1 free-VRAM probe ≥22528MiB before live scenarios (Pitfall 3); TTS port 5110/5111 not listening check (Pitfall 4); full-width-CJK work_dir path via `ls -d output/*/ | head -1` or python glob, never hardcoded (Pitfall 5). Grep anchors table is in RESEARCH §Code Examples — all verified present in source.

---

### `tests/test_pipeline_roundtrip_wiring.py` (static wiring test)

**Analog:** `tests/test_pipeline_vision_seq_wiring.py` (read in full, 108 lines). Copy the four-test structure:

1. `test_flags_exist_in_help` (:49-56) — subprocess `--help`, assert new flags in stdout.
2. `test_flags_parse_defaults_and_off` (:59-69) — `_capture_namespace` spy (argparse `parse_args` monkeypatch + `_StopMain` exception short-circuit, :20-46); assert `skip_roundtrip is False`, `tau_sim == 0.9670`, etc.
3. `test_pre_step_wiring_static` (:72-95) — `src.index()` ordering asserts. Roundtrip version: `src.index("step_roundtrip") < src.index("step_export(work_dir")`; flags-in-argv asserts (`'"--tau-sim", str(args.tau_sim)'` between roundtrip and export indexes — mirror the `--audio-semantic`/`--frame-fps` index-window asserts at :85-93); banner label asserts `'"[9/10] roundtrip'`-ish strings in src; Pattern-4 conditional input assert: `"roundtrip.json" in src` within step_export's inputs region and `os.path.exists` guard present.
4. `test_step_banner_count_unchanged` (:98-107) — **use `\d+` form**: `re.findall(r"\[\d+/10\]", src)`; assert `"[6/10" in src`, `"[5.5/10]" not in src`, `"[5.6/10]" not in src`, and `grep -c "/9\]" == 0` equivalent: `assert not re.findall(r"/9\]", src)`.

---

### `tests/test_roundtrip_review.py` + `tests/test_export_dataset.py` + `tests/test_roundtrip_apply_edits.py` (unit tests)

**Analog:** `tests/test_judge.py` (read :1-70). Style to copy:

**Module load via importlib direct-call** (:37-40):
```python
_spec = importlib.util.spec_from_file_location(
    "judge", REPO_ROOT / "analysis" / "roundtrip" / "judge.py")
jm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jm)
```
Use `"gen_roundtrip_review"` / `"export_dataset"` / `"apply_roundtrip_edits"` aliases; call `main([...])` or the core function on tmp_path fixtures. Docstring = behavior checklist (numbered coverage list, :4-24). Fake/stub classes module-level (:45-70 `FakeHTTP` recording stub precedent).

**No existing XSS test in repo** (verified: tests/ has zero XSS tests) — SC3 payload set and assertions are new; skeleton in RESEARCH §Code Examples (three payloads, assert escaped-form present / raw form absent). Fixture: `tests/fixtures/roundtrip_sample.json` schema-valid sidecar with payload variants + four UI-SPEC States variants (empty / regen-failed / unscored / no-verdict).

---

### `run_pipeline.py` (MODIFY — orchestrator, batch subprocess chain)

**Analog for step_roundtrip body — `step_reid`** (run_pipeline.py:256-334, the only existing dual-subprocess numbered step):

**Outer mtime cache + video-stamp** (:290-307 — the exact block to mirror for roundtrip.json vs prompts.json+shots.json):
```python
video_stamp = registry_draft + ".video-stamp"
cached_video_id = None
if os.path.exists(video_stamp):
    try:
        with open(video_stamp, encoding="utf-8") as f:
            cached_video_id = f.read().strip()
    except OSError:
        cached_video_id = None
current_video_id = _video_identity(video)
if (os.path.exists(registry_draft)
        and _safe_mtime(registry_draft) > _safe_mtime(shots_json)
        and cached_video_id is not None
        and cached_video_id == current_video_id):
    print(f"[6/9] cached registry draft: {registry_draft}")
    return registry_draft
```
(`_safe_mtime` at :527-537 returns +inf on missing → forced miss; `_video_identity` at :540-552 = `path|size|mtime_ns`.) **Cache-hit path must still generate review HTML** when roundtrip.json exists (research Pattern 1 / A2) — keep the gen_roundtrip_review subprocess outside the cache short-circuit or re-invoke before returning.

**Second-subprocess-in-step precedent** (:327-333 — gen HTML after draft exists):
```python
if os.path.exists(registry_draft):
    cmd2 = [sys.executable, str(HERE / "html" / "gen_registry_review.py"),
            "--draft", registry_draft, "--video", video,
            "--shots", shots_json, "--output", review_html]
    run_step(cmd2, "[6/9] HITL review HTML generation")
```

**`run_step` helper** (:122-126): banner `print(f"\n{'='*60}\n{label}\n{'='*60}")` + `$ cmd` echo + `subprocess.run(cmd, check=True)`. step_roundtrip chains 4 such subprocesses (h3_regen → scorer → judge `--apply-verdict --tau-sim <always passed explicitly>` → gen_roundtrip_review).

**skip short-circuit** (:212-214 / :287-289): `if skip: print("[9/10] --skip-roundtrip: skipping ..."); return rt if os.path.exists(rt) else None`.

**Flags wiring precedent** (:696-705 vision-seq dest/store_false pair; numeric flags :706 `--sample-fps` type=float). Flag→argv passthrough style: conditional `cmd += ["--flag", val]` blocks (:242-243, :414-415, :481-522). Defaults per RESEARCH Pattern 3 table (`--tau-sim` default 0.9670, always passed explicitly to judge; do NOT pass `--device` to scorer).

**Pattern 4 — conditional mtime input in step_export** (:572-580 inputs list; insert after, before :582):
```python
# Phase 22：roundtrip.json 条件性入 cache inputs（mirror step_timeline :471-474）。
# 存在且比 asset.json 新 → miss → 重导出挂载 data.roundtrip；缺席 → 不入 inputs
# → cache 命中保持 → byte-identical-absent。绝不无条件 append（_safe_mtime
# 缺席=+inf 会永久 miss）。
roundtrip_json_path = os.path.join(work_dir, "roundtrip.json")
if os.path.exists(roundtrip_json_path):
    inputs.append(roundtrip_json_path)
```
Conditional-append precedent: step_timeline :460-474 (audio_json/transcript/prompts/audio_semantic/speakers all `if ... and os.path.exists(...): inputs.append(...)`). The consumer of this mtime is already built: export_asset.py:375-404 reads roundtrip.json and emits `data.roundtrip {path, accepted_count, rejected_count}` (SCHEMA_VERSION "1.3" single-source at export_asset.py:59 — importlib it, never copy the literal; loader precedent h3_regen.py:704-721).

**Dataset post-step — canvas-import analog** (run_pipeline.py:926-953, keyed-on-file + graceful check=False):
```python
if args.canvas_auto_import:
    if not os.path.exists(asset_json):
        print(f"[canvas-import] warning: asset.json 不存在（...），跳过画布导入")
    else:
        ...
        # NOT run_step —— 那是 check=True helper；本 post-step 要求 graceful-degrade，
        # 自写 check=False + returncode 判断（T-AW2-03）。
        try:
            r = subprocess.run(cmd_canvas, check=False)
        except OSError as e:
            print(f"[canvas-import] warning: ...（graceful-degrade，管线继续）")
        else:
            if r.returncode != 0:
                print(f"[canvas-import] warning: ...")
```
Roundtrip dataset post-step mirrors this keyed on `roundtrip.json` instead of `--canvas-auto-import`+asset.json, plain label `"roundtrip dataset export (post-step)"` (no `[N/M]` prefix).

**`--force` list (:753-793): DO NOT add roundtrip artifacts.** Keep the Phase 20 comment (:768-773) intact and re-word its rationale per RESEARCH SOTA table ("verdict/scores 是冻结人工数据"). route_cache rmtree already covers the three module caches. T-14-01: explicit list, never glob/rmtree parent.

**HITL hint print precedent** (:893-904 speaker-link hint) — optional post-step hint showing the operator the exact apply CLI command.

**Banner renumber surface (verified this session):** 27 literals — `[1/9]`×3, `[2/9]`×3, `[3/9]`×3, `[4/9]`×3, `[5/9]`×3, `[6/9]`×4, `[7/9]`×3, `[8/9]`×2, `[9/9]`×3 (export's 3 become `[10/10]`); plus prose `[N/9]` at :35 and :921; plus module docstring step list (:4-35) needs a `9.5→relabel` roundtrip entry inserted and canvas renumbered. New step adds ~4 `[9/10]` banners (skip/cached/subprocess-chain/HTML).

---

### `tests/test_pipeline_vision_wiring.py` + `tests/test_pipeline_vision_seq_wiring.py` (MODIFY)

Both files, same two touch points (read in full this session):

**Regex at vision_wiring.py:102 and seq_wiring.py:103:**
```python
numbered = re.findall(r"\[\d/9\]", src)   # 改为 r"\[\d+/10\]" —— [10/10] 是双位数
```
**Substring locks — vision_wiring.py:104:**
```python
assert "[5.5/9]" not in src and "[6/9" in src
# → assert "[5.5/10]" not in src and "[6/10" in src
```
**seq_wiring.py:105-106 (keeps plain-label locks):**
```python
assert "[5.5/9]" not in src and "[6/9" in src      # → "[5.5/10]" / "[6/10"
assert "[5.6/9]" not in src                        # → "[5.6/10]"
```
Also relax `len(numbered) >= 9` if desired (stays true: 27→~31 occurrences). These two files MUST land in the same task as the run_pipeline renumber or pytest goes red (RESEARCH Pitfall 1).

---

## Shared Patterns

### XSS three-layer hardening (applies to: gen_roundtrip_review.py + its tests)
1. Inline `_esc()` — gen_registry_review.py:79-91 (html/ namespace package forbids cross-file import).
2. JSON bootstrap `</`→`<\/` — gen_registry_review.py:318.
3. JS textContent/classList only — gen_registry_review.py:509-526.
SC3 mandatory field list (UI-SPEC XSS section): judge.reason, attribution (enum too), verdict.decision/source, status.error, midframe_sim.model, engine_name/engine_version/prompt_version, prompt_text + all 6 facets, character_refs/prop_refs, asset_name; numbers via `str()` first. Schema maxLength 2000 pre-bounds reason/error (roundtrip.schema.json:61,87).

### importlib shared-module loading (applies to: export_dataset.py, apply CLI, tests)
judge.py:100-103 / scorer.py:109-112 (h3_regen as `h3_regen_shared`), h3_regen.py:704-721 (export_asset for SCHEMA_VERSION — never copy the "1.3" literal). test_judge.py:37-40 (module-under-test load). Note the three-parent repo-root off-by-one trap for files in `analysis/roundtrip/` (h3_regen.py:190-194 comment).

### READ-merge sidecar write + two-layer validation (applies to: apply CLI; read-side of export_dataset)
Canonical loop: scorer.py:347-453 / judge.py:326-429. Elements: swallow-read-to-empty (:362-369); own-batch validate fail-loud sys.exit (:371-378); kept-keys merge with shallow-merged sub-object (:389-400); malformed pre-existing entries → `.bak-<ts>` backup + per-shot str warning (:401-412); merged-payload validate → attribute errors to shot_id → evict + backup + re-validate (:416-449); PID-tmp atomic write (h3_regen.py:654-663). Roundtrip apply CLI's sole semantic inversion: verdict half is replaceable (human override) instead of frozen.

### Sibling subprocess orchestration (applies to: run_pipeline.py step_roundtrip + dataset post-step)
`run_step(cmd, label)` check=True for numbered-step modules (each module owns its degrade/exit-0); plain-label post-step uses hand-rolled `check=False` + warning (canvas precedent :926-953). List-form argv always (T-14-02). Outer mtime+video-stamp cache to skip the whole chain incl. h3_regen's unconditional batch guard (step_reid :290-307 form).

### Warnings sidecar protocol (applies to: anything writing route_cache/warnings.json)
STEP_TAG `[roundtrip]` shared by all three modules (h3_regen.py:153, scorer.py:79, judge.py:107); read-strip-append via `h3s.append_roundtrip_warnings` (h3_regen.py:685-699) strips prior `[roundtrip]` str entries + closed-enum dict codes (`comfyui_unreachable`/`vram_insufficient`/`scorer_model_missing`, h3_regen.py:157-161).

### Schema-validation gate (applies to: apply CLI, edits schema)
`Draft202012Validator(...).iter_errors()` + sys.exit with capped message list — apply_edits.py:239-259. All edits schemas: `additionalProperties:false`, all fields optional, empty-object valid.

### HTML visual conventions (applies to: gen_roundtrip_review.py)
GitHub-dark palette + sticky header/queue/export-bar + `{{ }}` f-string escaping + monospace for ids/scores + Chinese UI text + Unicode glyph icons (no icon lib) — CLAUDE.md Conventions lock + gen_registry_review.py:325-453. UI-SPEC is the authoritative contract (typography 3-tier, accent reserved list, attribution 3-color mapping, states table).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_roundtrip_review.py` (SC3 XSS cases only) | test | transform | No XSS test exists anywhere in tests/ (grep-verified). Structure analog = test_judge.py; payload/assertion set is novel — follow RESEARCH §Code Examples skeleton + UI-SPEC XSS rule 5. |
| `dataset/<video-stem>/` output layout | export artifact | file-I/O | No existing per-shot self-contained dataset export (export_asset.py is the closest — manifest+media from work_dir, but single-file asset not per-shot dirs). Layout is fully specified by CONTEXT/RT-05 + UI-SPEC; no code to copy beyond the Analog E atomic-write. |

Everything else has a direct in-repo analog listed above.

## Metadata

**Analog search scope:** repo root (html/, registry/, analysis/roundtrip/, scripts/, spec/schemas/, tests/, tests/fixtures/, run_pipeline.py, CLAUDE.md)
**Files fully read:** gen_registry_review.py, apply_edits.py, run_pipeline.py, test_pipeline_vision_wiring.py, test_pipeline_vision_seq_wiring.py, registry-edits.schema.json, roundtrip.schema.json, run_audio_analysis_smoke.sh, CLAUDE.md
**Files targeted-read (non-overlapping ranges):** h3_regen.py (126-235, 297-419, 642-801, 1180-1444), judge.py (95-149, 321-435, 503-627, 688-747), scorer.py (60-124, 347-461), export_asset.py (50-67, 370-409), test_judge.py (1-70)
**Pattern extraction date:** 2026-08-20
