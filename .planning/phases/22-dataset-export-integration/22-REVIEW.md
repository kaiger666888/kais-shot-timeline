---
phase: 22-dataset-export-integration
reviewed: 2026-08-20T08:59:50Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - html/gen_roundtrip_review.py
  - analysis/roundtrip/apply_edits.py
  - analysis/roundtrip/export_dataset.py
  - spec/schemas/roundtrip-edits.schema.json
  - run_pipeline.py
  - tests/test_roundtrip_review.py
  - tests/test_roundtrip_apply_edits.py
  - tests/test_export_dataset.py
  - tests/test_pipeline_roundtrip_wiring.py
findings:
  critical: 1
  warning: 4
  info: 8
  total: 13
status: issues_found
---

# Phase 22: Code Review Report

**Reviewed:** 2026-08-20T08:59:50Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the Phase 22 round-trip integration layer: review-panel generator, confirmed-only apply CLI, dataset exporter, edits schema, pipeline wiring, and the four test modules. Cross-referenced `h3_regen.py` shared helpers (`_iter_sidecar_errors` / `_atomic_write_json` / `append_roundtrip_warnings` / `extract_endpoint_frames`), `judge.py` frozen-skip semantics, `roundtrip.schema.json`, and 22-UI-SPEC (data-mapping + XSS hardening checklists).

Verified sound (adversarial trace, no defect found):

- **apply_edits frozen-replacement edges** — human→human change of mind replaces the verdict with a fresh `decided_at` (correct); reject→accept round trip works (same mechanism); auto same-direction explicit confirm upgrades `source` to human (locked design, "防未来重打分翻案"); same-decision replay skips write so `decided_at` never drifts (byte-idempotent). Intersection/unknown-id/schema failures all exit before any sidecar write. One audit-accuracy and one swallowed-warning edge remain (IN-01/IN-02).
- **XSS `_esc` completeness** — every dynamic string that reaches an HTML text or attribute context was checked field-by-field against the UI-SPEC mapping table: `reason`, `attribution`, `decision/source/decided_at`, `status.error`, `midframe_sim.model`, `prompt_version`, `prompt_text`, six facets, `character_refs/prop_refs`, `asset_name`, `video_src_base`, `regen.path` — all escaped. Numbers are `:.Nf`-formatted floats or `int()` shot ids only; `data-verdict` is a closed whitelist; onclick interpolates ints only. The one deviation is that `engine_name`/`engine_version` never render at all (WR-04).
- **Schema completeness** — `roundtrip-edits.schema.json` is consistent with the sidecar (`integer minimum 1` matches `shot_id` constraints; `additionalProperties:false`; empty `{}` valid). Duplicates are schema-tolerated but the consumer dedupes via set — acceptable.
- **Wiring flags** — `--tau-sim` always explicitly forwarded to judge and panel; scorer `--device` non-passthrough held; conditional `roundtrip.json` mount into step_export inputs correctly guarded by `os.path.exists`.

Key concerns: one blocker in the review panel's queue sidebar (destroyed on page load by a `textContent` assignment on the wrong element — source-level tests cannot catch DOM behavior), accepted-list/manifest inconsistency in dataset export under partial failure, prior-good dataset directories deleted on degraded reruns, misleading τ display after a `--tau-sim` change on a cache-hit rerun, and a UI-SPEC field-mapping omission.

## Critical Issues

### CR-01: Queue sidebar wiped on page load — `textContent` set on the `<a>` instead of the `.queue-check` placeholder span

**File:** `html/gen_roundtrip_review.py:659-660` (render site `:316`, initial call `:746`)
**Issue:** `applyVisualState()` contains:

```js
const q = document.getElementById('q-' + shotRef(sid));
if (q) q.textContent = state.reviewed.has(sid) ? '✓ ' : '';
```

`q` is the queue item anchor `<a class="queue-item">`, whose children are `<span class="queue-check">`, `<span class="queue-topline">` (shot id + sim number) and the micro sim bar. Setting `.textContent` on the anchor **replaces all children with a single text node**. The intended target — the empty `<span class="queue-check"></span>` server-rendered precisely to receive the ✓ (per `_queue_item_html` docstring "✓ 前缀占位 span 由 JS textContent 填充") — is never selected. Because `applyVisualState()` is invoked once at script load ("Initial state application"), every queue item is blanked to `''` **on page load, before any interaction**: the 240px τ-sorted review queue — the panel's primary navigation and the "最难决定先审" ordering surface — loses all shot ids, sim numbers, and bars on every generated panel. The anchors remain as invisible empty rows. The test suite (`test_roundtrip_review.py`) is source-level only (string assertions on generated HTML, no DOM execution), so this is structurally undetectable by the current tests.
**Fix:**

```js
// queue 侧同步：已复核卡对应 queue 项的占位 span 填 ✓（不动 anchor 其余子节点）
const q = document.getElementById('q-' + shotRef(sid));
const check = q ? q.querySelector('.queue-check') : null;
if (check) check.textContent = state.reviewed.has(sid) ? '✓' : '';
```

**Outcome:** fixed (6cc0cde) — applyVisualState 改经 `.queue-check` 占位 span 更新 ✓（anchor 其余子节点不动）；新增回归锚 `test_queue_checkmark_targets_dedicated_span`（源码断言不写 `q.textContent` + check span 选择器/填充形态/server 渲染 span 计数锁）；ep01 正本 roundtrip_review.html 已重生成复验 19/19 queue 项 topline/sim bar 完好，roundtrip.json sha 不变。

## Warnings

### WR-01: `accepted.txt` and `manifest["shots"]` list accepted shots whose directories were never created (or were removed) — count and index contradict each other

**File:** `analysis/roundtrip/export_dataset.py:318, 363-369`
**Issue:** `current_dirs` is computed from **all** accepted shots before the export loop. Shots later skipped (prompts.json entry missing, or `_ensure_endpoint_frames` returned None) get no directory (or have it removed), yet `accepted.txt` is written from `sorted(current_dirs)` and `manifest["shots"]` maps every accepted id → `shot_NNN`. Result under partial failure: `accepted.txt` references non-existent directories, and `manifest["accepted_count"]` (= `exported`) disagrees with `len(manifest["shots"])`. A consumer iterating `accepted.txt` or the manifest index hits missing dirs; the hard-negative/audit surface silently lies.
**Fix:** Track actually-exported dirs in the loop and derive both artifacts from them:

```python
exported_dirs: set[str] = set()
# in the loop after prompt.json write:
exported_dirs.add(f"shot_{sid:03d}")
...
manifest = {..., "accepted_count": len(exported_dirs),
            "shots": {str(...): name for name in sorted(exported_dirs)}}  # or keep id→name map built in-loop
with open(..., "accepted.txt", ...) as f:
    for name in sorted(exported_dirs):
        f.write(name + "\n")
```

**Outcome:** fixed (d4d8b11) — 导出循环内建 `exported_names`（本轮成功集）+ `skipped_ids`；accepted.txt / manifest["shots"] 均从实际导出集派生（accepted_count == len(shots) == accepted.txt 行数），skipped 镜单列 manifest["exported_skipped"]；新增两回归锚（prompts 缺条目路径 + 帧降级路径的索引三一致断言）。

### WR-02: Degraded rerun deletes previously-good dataset shot directories

**File:** `analysis/roundtrip/export_dataset.py:338-346`
**Issue:** For each accepted shot the code does `os.makedirs(shot_dir, exist_ok=True)` **on the pre-existing directory from a prior successful export**, then calls `_ensure_endpoint_frames`; on failure (transient ffmpeg error, or source video absent → "无源视频，跳过该镜") it runs `shutil.rmtree(shot_dir, ignore_errors=True)` — destroying last run's valid `first_frame.jpg`/`last_frame.jpg`/`prompt.json`. The module's own idempotent-rebuild contract ("重跑整目录自重建") assumes re-derivation succeeds; when it degrades, prior good derived data is destroyed rather than preserved-with-warning. Combined with WR-01, the shot also remains listed in `accepted.txt` while its data is gone. Dataset is derived data (re-runnable), but silent destruction on a degraded pass is a data-loss edge in the output tree.
**Fix:** Only remove the directory if this run created it, or keep the prior contents on degradation:

```python
created = not os.path.isdir(shot_dir)
os.makedirs(shot_dir, exist_ok=True)
frames = _ensure_endpoint_frames(...)
if frames is None:
    if created:
        shutil.rmtree(shot_dir, ignore_errors=True)  # 仅清本轮半成品
    # else: 保留上轮完好导出，仅记 warning
    skipped_shots += 1
    continue
```

**Outcome:** fixed (c7bcd6c) — `created = not isdir(shot_dir)` 区分本轮自建/上轮遗存：降级只 rmtree 本轮半成品，上轮完好目录保留 + warning（不进本轮索引，WR-01 口径）；新增两回归锚（降级重跑上轮帧/prompt.json 字节不变 + 对照面：本轮自建半成品仍清）。

### WR-03: τ change on a cache-hit rerun displays a non-governing τ as governing (panel pill/tick/queue-sort + dataset manifest)

**File:** `run_pipeline.py:630-651` (τ forwarded to `_gen_review_html` on both hit and miss paths), `analysis/roundtrip/export_dataset.py:355-357` (manifest `tau_sim`)
**Issue:** `--tau-sim` is not part of the step_roundtrip cache key and verdicts are frozen by design (judge skips any shot with an existing verdict). Scenario: first full run at τ=0.9670 freezes verdicts; operator re-runs with `--tau-sim 0.93` — shots/prompts mtimes and video-stamp unchanged → outer cache hits → judge never re-runs (and would skip frozen verdicts anyway) → the review HTML is regenerated with the **new** τ: header pill `τ_sim=0.9300`, tick at 93%, and `_queue_sort_key` "τ 边界排序" computed under the new τ — all describing verdicts actually decided under 0.9670. The dataset post-step then records `tau_sim: 0.93` in `manifest.json` for the same frozen verdicts. The panel and manifest actively misrepresent the threshold that produced the data (provenance/audit defect; judge's frozen semantics are locked, so the fix belongs on the display/provenance side).
**Fix:** Record the effective τ with the verdict at freeze time (e.g. judge writes `decided_at` alongside a `tau_sim` field, or sidecar top-level `verdict_tau`), and have the panel/manifest read the frozen value when present; at minimum, when the passed τ differs from the τ under which frozen verdicts were decided, print a prominent warning and/or stamp the manifest with the sidecar's τ rather than the CLI flag.

**Outcome:** fixed (daf8365) — 三处最小正确解：(1) judge.apply_verdict 首次实际 apply 把决策 τ 写 `roundtrip.json.verdict-tau` stamp（mirror .video-stamp 纯文本先例；阈值不进 roundtrip.schema.json——two-tier authority lock 不动；写后不覆盖 + 换 τ 重跑不一致 warning）；(2) step_roundtrip 外层 cache stamp 身份追加 `|tau=<τ>` 后缀——换 τ 强制 miss 重生成 HTML/manifest；(3) export_dataset manifest 的 `tau_sim` 拆成 `verdict_tau`（从 stamp 读，缺席/坏值 → null + warning）与 `export_tau`（本轮 CLI τ）双记。新增六回归锚（judge 两 + export 三 + wiring 一）。schema 未动（spec/validate.py 0 failures 保持）。

### WR-04: UI-SPEC data-mapping deviation — `regen.engine_version` / `engine_name` never rendered; `_esc` docstring overclaims coverage

**File:** `html/gen_roundtrip_review.py:262-264` (prompt fold summary), docstring `:20-22`
**Issue:** 22-UI-SPEC data→UI mapping table row "`shots[].regen.engine_version` / `prompt_version` | prompt 快照 `<summary>` 尾注`" is only half-implemented: only `prompt_version` appears in the `<summary>`; `engine_version` (and `engine_name`) are not rendered anywhere in the panel. The module docstring's XSS checklist claims `engine_name+engine_version+prompt_version` are escaped — vacuously true for two of the three since they never reach the HTML. Operator-facing consequence: the panel provides no way to audit which engine version produced a regen (a stated purpose of the regen 4-tuple contract); the operator must open the sidecar JSON.
**Fix:** Add engine version to the fold header, e.g. `▸ Prompt 快照 (prompt v{prompt_version} · {engine_version})` (through `_esc`), or a mono line inside the fold body; alternatively amend the UI-SPEC if the omission was a deliberate cut — but then also fix the docstring claim.

**Outcome:** fixed (bc51e50) — fold summary 尾注改「prompt v{pv} · {engine_version}」（均经 _esc，半边缺席退化）；docstring 第 1 层清单改为实际到达 HTML 的字段（engine_name 不渲染——映射表未含，进 dataset prompt.json）；新增回归锚 `test_prompt_fold_summary_includes_engine_version`；ep01 正本重生成复验 19/19 尾注含引擎版本、roundtrip.json sha 不变。

## Info

### IN-01: apply_edits no-op early-return swallows malformed-entry warnings; `skipped` counter is dead

**File:** `analysis/roundtrip/apply_edits.py:185-191` (vs flush block `:204-213`)
**Issue:** When edits are empty or all-replay (`if not entries: return 0`), the `malformed` list collected at step 4 is never reported — the `.bak`/warning flush lives after the early return. Nothing is written so no data is lost, but the operator gets no signal that the sidecar contains shape-invalid entries. Also `skipped = len(targets) - applied - same_replay` is structurally always 0 (every target either appends or replays) — defensive bookkeeping that can never fire.
**Fix:** Print malformed-entry warnings before the early return (no backup needed since nothing is written); either drop the `skipped` counter or assert it stays 0.

### IN-02: apply_edits `applied` count can overstate actual writes when a target shot is quarantined by merge validation

**File:** `analysis/roundtrip/apply_edits.py:183, 217-250`
**Issue:** `applied` is incremented when the entry is built; if the merge-validation step later attributes schema errors to that same pre-existing shot (bad regen half), the shot is popped from `merged` (with `.bak` backup + warning) and the just-confirmed human verdict is not persisted — yet the closing summary still prints `applied=N`. Audit line vs disk state diverge on this edge.
**Fix:** After the quarantine pass, recompute the report (e.g. subtract quarantined target ids from `applied`) or print an explicit "quarantined after apply: [...]" line in the summary.

### IN-03: Bootstrap `</`-only escape leaves a parser-state DoS vector (`<!--` + `<script>` without `-->`)

**File:** `html/gen_roundtrip_review.py:366`
**Issue:** `json.dumps(...).replace("</", "<\\/")` blocks `</script>` breakout (and `json.dumps` quote-escaping blocks JS-string breakout — verified), but an injected `<!--` followed by `<script>` with no `-->` puts the HTML parser into script-data-double-escaped state where the block's real `</script>` no longer closes it; the script element then swallows the rest of the document and the whole panel's JS dies (DoS, not execution — I found no execution path since the payload stays inside a JS string literal). `reason`/`error`/`model` are local LLM/ffmpeg outputs, so risk is low; mirrors the registry/speaker precedent and is locked by `test_bootstrap_script_breakout`.
**Fix:** Harden the bootstrap to `json.dumps(...).replace("<", "\\u003c")` (or additionally neutralize `<!--`) in this generator and note the divergence from precedent; adjust the bootstrap test accordingly.

### IN-04: `RT_SHOTS` bootstrap JSON is dead weight — only `.length` consumed

**File:** `html/gen_roundtrip_review.py:599-604`
**Issue:** The full sidecar `shots` array is embedded as `const RT_SHOTS = {...}` but the JS only reads `RT_SHOTS.length` (as `N_TOTAL`); the comment claims "member/时窗查找用" yet no member lookup exists (all card content is server-rendered). It is also the largest attack surface for IN-03 for no functional benefit.
**Fix:** Either embed only `const N_TOTAL = {n};` or keep the payload and add the member lookup it was sized for.

### IN-05: Dataset frame-fallback timing sourced from prompts.json while cache frames are keyed/extracted from shots.json timing

**File:** `analysis/roundtrip/export_dataset.py:174-176` (vs `h3_regen.py:297-325, 399-401`)
**Issue:** Direct-copy frames come from the h3 cache (extracted from `shots.json` `start/end_sec`); the fallback path re-extracts using `prompts.json` `start_sec/end_sec`. Both producers derive from shots.json today (`call_shot_analysis.py:390`), so normally identical — but if prompts.json is hand-edited, stale relative to a re-detection, or has explicit `null` timing (`float(None)` → TypeError → traceback rather than graceful skip), cache-miss shots get frames from a different time window than h3 actually consumed, silently.
**Fix:** Read timing from `shots.json` (single source of truth, same as h3_regen) in `_ensure_endpoint_frames`, and guard `float(x) if isinstance(x, (int, float)) else 0.0`.

### IN-06: `accepted.txt` / `rejected.txt` written non-atomically while JSONs use `_atomic_write_json`

**File:** `analysis/roundtrip/export_dataset.py:367-372`
**Issue:** The two plain-text manifests are written with bare `open(..., "w")` while `manifest.json`/`prompt.json` go through tmp+`os.replace`. An interrupted run can leave truncated txt files next to intact JSONs.
**Fix:** Mirror the tmp+`os.replace` pattern for the txt files.

### IN-07: No revert-to-auto path once a human verdict is applied — "⟲ 维持 auto" is misleading on human-verdict cards

**File:** `html/gen_roundtrip_review.py:280-285` + `spec/schemas/roundtrip-edits.schema.json` (payload), `analysis/roundtrip/apply_edits.py:161-184`
**Issue:** The three-state UI offers "维持 auto", but for a card whose verdict is already `source:"human"` that button produces no edit and no operation exists to restore an auto verdict (schema has only accept/reject overrides; apply only replaces human-with-human). Frozen-forever-after-human is consistent with the "human 覆盖唯一冻结替换路径" lock, but the button label implies reversibility that does not exist.
**Fix:** Document the irreversibility in the UI-SPEC/export-bar copy (e.g. dim or relabel the auto button on human-verdict cards), or add an explicit revert operation if that capability is ever required.

### IN-08: `--force` consistency gap — step_roundtrip takes no `force` parameter and `roundtrip.json.video-stamp` is missing from the force-clear list (currently masked)

**File:** `run_pipeline.py:570-574, 642-651, 948-959`
**Issue:** Unlike step_export (whose cache condition includes `not force`), step_roundtrip's cache condition has no force bypass and `main()` never passes `args.force` to it; the `roundtrip.json.video-stamp` sidecar is also absent from the `--force` clear list (asset/prompts/registry/audio_semantic stamps are all cleared). Today this is unreachable as a bug: `--force` always deletes `prompts.json`, and `_safe_mtime` on the missing file returns `+inf`, forcing a cache miss on every force run. It is a latent consistency defect — any future change that stops force from deleting prompts.json (or a `--force --skip-semantic` fast path that preserves it) would let `--force` silently short-circuit the roundtrip chain.
**Fix:** Add `force: bool` to `step_roundtrip` and include `not force` in the cache condition (mirror step_export), and add `rt_json + ".video-stamp"` to the force-clear list.

---

_Reviewed: 2026-08-20T08:59:50Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
