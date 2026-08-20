---
phase: 21-scorer-threshold-calibration
fixed_at: 2026-08-20T03:01:42Z
review_path: .planning/phases/21-scorer-threshold-calibration/21-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 21: Code Review Fix Report

**Fixed at:** 2026-08-20T03:01:42Z
**Source review:** .planning/phases/21-scorer-threshold-calibration/21-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 6
- Fixed: 6
- Skipped: 0
- Info findings (IN-01..IN-06): out of scope per fix_scope (`critical_warning`), not attempted

**Verification:**
- `python3 -m pytest tests/ -q` → **170 passed** (160 baseline zero-regression + 10 new regression anchors)
- `python3 spec/validate.py` → exit 0 (`[validate] OK`, failures=0 across minimal/v1.1/v1.2/v1.3 fixtures)
- Diff scope: only `analysis/roundtrip/scorer.py`, `analysis/roundtrip/judge.py`, `tests/test_scorer.py`, `tests/test_judge.py`, `21-REVIEW.md` — runtime `roundtrip.json` data / ROADMAP / STATE untouched; the 19 frozen verdicts (τ=0.9670) are semantically untouched (merge-writers' verdict-freeze paths unchanged; cache-key changes only cause cache misses → rescoring may refresh **scores**, verdicts stay frozen by design).

## Fixed Issues

### CR-01: cache 全命中路径永不回填 sidecar + cache 写先于 sidecar 写 —— 中断后重跑「静默成功」且分数永不落盘

**Files modified:** `analysis/roundtrip/scorer.py`, `analysis/roundtrip/judge.py`, `tests/test_scorer.py`, `tests/test_judge.py`, `.planning/phases/21-scorer-threshold-calibration/21-REVIEW.md`
**Commit:** 4fdc75e
**Applied fix:** Both modules gained `_replay_hit_entries(work_dir, hit_shots, keys)`: cache-hit shots are rebuilt into half-entries from cache meta (scorer: `score`+`model`; judge: `parsed` 三件套 passed through as-is so the write-side schema gate stays the single fail-loud authority), diffed against the current sidecar half — only absent/changed halves are replayed, so pure no-op reruns do not rewrite roundtrip.json. Wired into both paths: ① the all-hit early-exit branch backfills (and flushes warnings) before `return 0`; ② the mixed path extends the batch-tail `new_entries` with replayed hits — the "per-shot cache_write persisted but batch-tail sidecar write never happened" interruption window is now self-healing on rerun (mirror of h3_regen L742-745 cache-hit rebuild). Chose the reviewer's primary fix (replay) over per-shot writes to keep the single batch-tail atomic write. Regression anchors: `test_cache_hit_backfills_missing_sidecar_half`, `test_partial_hit_backfills_interrupted_half` (scorer), `test_judge_cache_hit_backfills_missing_sidecar_half` (judge).

### WR-01: judge cache key 缺 prompt 身份维 —— prompts.json 修订后 stale attribution 命中

**Files modified:** `analysis/roundtrip/judge.py`, `tests/test_judge.py`, `.planning/phases/21-scorer-threshold-calibration/21-REVIEW.md`
**Commit:** e8da8ce
**Applied fix:** `_JUDGE_KEY_FIELDS` 4 → 5 fields (+`prompt_version`, mirroring h3_regen `_CACHE_KEY_FIELDS`); key assembly adds `str(regen.get("prompt_version") or "")` from the sidecar regen half; `payload = dict(key)` carries the dimension into cache for audit. Docstrings updated (步骤 2 / cache 惯例). Existing judge caches miss once and re-judge (expected: attribution is a direct function of prompt_text). Regression anchors: `test_judge_cache_key_prompt_revision_rejudges` (pv1→pv2 with unchanged mp4 bytes → re-judged + payload records pv2); `test_judge_all_cache_hit_zero_instantiation` preset payload updated with `prompt_version`.

### WR-02: scorer cache key 缺 orig 侧镜几何维 —— 重分割后 stale 分数命中

**Files modified:** `analysis/roundtrip/scorer.py`, `tests/test_scorer.py`, `.planning/phases/21-scorer-threshold-calibration/21-REVIEW.md`
**Commit:** 9974fc0
**Applied fix:** `_SCORER_KEY_FIELDS` 5 → 6 fields (+`orig_window: [round(start_sec,3), round(duration,3)]`); key assembly looks up shot geometry from shots_index (dur derivation identical to `score_shot`). Docstrings updated (步骤 2 / cache 惯例 / `cache_read`). Existing scorer caches miss once and re-score (expected; scores refresh, verdicts frozen). Regression anchor: `test_cache_key_miss_on_geometry_change` (start 0→1.5, mp4 bytes unchanged → rescored + `orig_window == [1.5, 6.73]` recorded).

### WR-03: scorer 的 `float(regen.get("duration_sec"))` 在 per-shot try 守卫之外 —— 单条坏值炸整批

**Files modified:** `analysis/roundtrip/scorer.py`, `tests/test_scorer.py`, `.planning/phases/21-scorer-threshold-calibration/21-REVIEW.md`
**Commit:** a115b8a
**Applied fix:** coercion + probe moved inside the per-shot `try:` (now line-for-line aligned with judge.py — the drift evidence cited in the review is gone). A bad `duration_sec` (e.g. `"6,73"`) raises ValueError inside the per-shot handler → printed failure + `failed` list + batch continues. Regression anchor: `test_bad_duration_sec_single_shot_fail_not_batch` (2 shots, shot 1 corrupt → rc=0, shot 2 scored, shot 1 in failed list and evicted by the pre-existing schema-invalid layer).

### WR-04: 预存条目「形状不对」（非 dict / shot_id 非 int）在 merge 中被静默丢弃 —— 无 warning 无备份

**Files modified:** `analysis/roundtrip/scorer.py`, `analysis/roundtrip/judge.py`, `tests/test_scorer.py`, `tests/test_judge.py`, `.planning/phases/21-scorer-threshold-calibration/21-REVIEW.md`
**Commit:** 3fb6906
**Applied fix:** Both merge-writers (`write_scores_sidecar` / `_merge_write_sidecar`) collect malformed entries in an else branch, and before dropping them: `shutil.copy2` the original file to `roundtrip.json.bak-<ts>` + per-shot str warning (entry snippet 120 chars + backup filename) — same two-layer semantics as the existing schema-invalid eviction, going one step beyond the Fix sketch per the fix contract (mirror h3_regen WR-04). Writer docstrings updated. Top-level unknown-key dropping deliberately left un-warned (would fire on every write; out of the Fix guidance). Regression anchors: `test_preexisting_malformed_entry_warned_with_backup` in both test files (shot_id string `"5"` carrying a human verdict → dropped + warning + exactly one .bak + this batch still lands).

### WR-05: `regen_dur <= 0`（probe 失败返 0.0）无守卫 —— 退化为全 t=0 帧的静默垃圾打分/判定

**Files modified:** `analysis/roundtrip/scorer.py`, `analysis/roundtrip/judge.py`, `tests/test_scorer.py`, `tests/test_judge.py`, `.planning/phases/21-scorer-threshold-calibration/21-REVIEW.md`
**Commit:** c4fc324
**Applied fix:** Both per-shot loops add `if regen_dur <= ENDPOINT_GUARD_SEC:` after the probe → str warning (with the measured value) + `failed.append(sid)` + `continue` — no frame extraction, no score/attribution produced. Threshold = ENDPOINT_GUARD_SEC (0.2s), below which every window position in `plan_frames`/`grid_ts` collapses to t≈0 (matches the issue's "dur < guard 的极短流同样全坍缩"). Regression anchors: `test_regen_duration_unmeasurable_or_short_skips` (scorer: probe→0.0 and 0.15s forms → zero extraction/cache/scores + warnings), `test_judge_regen_duration_unmeasurable_skips` (judge: zero observe_single calls, engine orchestration still runs, warning flushed).

## Skipped Issues

None — all 6 in-scope findings fixed.

## Notes

- **Verdict freeze:** no changes touch verdict semantics. `apply_verdict` untouched; merge-writers' verdict pop/kept-keys logic unchanged; the cache-key changes (WR-01/WR-02) only invalidate caches → rescore/rejudge refresh **scores** halves, while verdicts remain frozen per the Pattern 4 merge skeleton. The real 19-verdict sidecar (τ=0.9670) was never read or written by this fix pass.
- **Cache invalidation side effect (intended):** WR-01/WR-02 key changes cause a one-time full cache miss on the real machine's `route_cache/judge` + `route_cache/scorer` — reruns re-judge/re-score and, thanks to CR-01, now also self-heal any missing sidecar halves.
- Per the fix contract, each finding's outcome is also annotated inline in `21-REVIEW.md` ("**Outcome (fix):** …" lines), committed together with that finding's atomic commit.
- Info findings IN-01..IN-06 were not in fix_scope and were not attempted.

---

_Fixed: 2026-08-20T03:01:42Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
