---
phase: quick
plan: 260725-afz
subsystem: audio
tags: [audio, prompt, spike, nl, demucs, whisper]
requires:
  - output/<ep>/shots.json
  - output/<ep>/audio_analysis.json
provides:
  - audio/gen_audio_prompts.py (独立 CLI, sidecar producer)
  - output/<ep>/audio_prompts.json (gitignored sidecar, not in spec)
affects: []
tech_stack:
  added: []
  patterns:
    - 本地启发式 NL prompt 拼接（无 ML 推理、无网络）
    - stdlib wave + numpy envelope peak-pick tempo 估计
    - 确定性输出（无时间戳/绝对路径；ensure_ascii=False；字典 key 固定序）
key_files:
  created:
    - audio/gen_audio_prompts.py
  modified: []
decisions:
  - brightness 3 档（< 400 Hz deep low rumble / < 1500 warm mid-range / 否则 bright airy）
  - loudness 3 档（overall RMS < 0.02 quiet / < 0.08 moderate / 否则 loud）
  - tempo 置信门槛：drums ratio ≥ 0.10 AND onset_count ≥ 3（不达标 bpm=null）
  - dialogue 降级（无 transcript）：按 vocals SC 高低降级为 non-vocal melodic vocalise / vocal texture
  - prompt 拼接顺序：{leading}[ ~Xbpm][, "excerpt"], {loudness} {brightness} bed
  - 合约零改动：sidecar 不含 schema_version；未触及 SPEC/schemas/asset.json/export_asset.py/run_pipeline.py
metrics:
  duration: ~12min
  completed: 2026-07-25
  tasks: 2/2
  verdict: approved → promote v1.2 milestone (concept validated; 3 tuning issues carried as v1.2 input)
---

# Quick Plan 260725-afz: Audio-gen NL Prompt Spike — Task 1 Summary

**One-liner:** 独立 CLI 脚本 `audio/gen_audio_prompts.py`，从 Demucs 能量/频谱 + Whisper 对白 + drum envelope onset 推导每镜 audio-gen 风格 NL prompt，写 gitignored sidecar `audio_prompts.json`；合约零改动、未进 pipeline、未引入新依赖。

## Task 1: 实现 `audio/gen_audio_prompts.py`（独立 CLI）

### 建了什么

`audio/gen_audio_prompts.py`（398 行，单文件，stdlib + numpy）。模块结构严格按 PLAN.md 13-step spec：
1. 中文 module docstring（用途 / 算法 / 降级路径 / 输出 schema / CLI 用法）
2. imports：`argparse, json, os, sys, wave` + `from pathlib import Path` + `import numpy as np`（**零新依赖**）
3. `load_audio_stem(path)` —— 逐字镜像 `audio/separate_stems.py:77-88`
4. `estimate_tempo_from_envelope(audio, sr, start_sec, end_sec) → (bpm|None, onset_count)` —— 短窗 RMS envelope (hop=512/win=1024) + 自适应阈值 + peak-pick（局部极大 + 0.20s 防抖）+ 相邻间隔中位数 → 60/median，clamp [40, 200]
5. `brightness_word(hz)` —— 3 档 SC 词
6. `loudness_word(rms_energy)` —— 3 档 RMS 词
7. `leading_phrase(dominant_type, brightness, vocal_presence)` —— 4 类 dominant_type 分支；dialogue 高 vocal_presence 带 "clear lead vocal"
8. `find_dialogue_excerpt(transcript_segments, start_sec, end_sec, max_chars=20)` —— 首个时间重叠 segment 前 20 字符，引号转义（T-afz-02 mitigate）
9. `compose_prompt(leading, tempo_bpm, dialogue_excerpt, loudness, brightness)` —— `{leading}[ ~Xbpm][, "excerpt"], {loudness} {brightness} bed`
10. `derive_facets_and_prompt(shot, drum_audio, drum_sr, transcript_segments)` —— 单 shot 派生 entry
11. `gen_prompts(episode_dir, output_path)` —— 读 3 个 JSON + drum stem、循环、进度打印、统计
12. `main()` —— argparse `--episode-dir` (required) + `--output` (default `<ep>/audio_prompts.json`)
13. `if __name__ == "__main__": main()`

### 启发式关键决策（可调阈值常量集中在模块顶部 UPPER_CASE）

| 维度 | 阈值 | 输出 |
|------|------|------|
| **brightness** (spectral_centroid hz) | `<400` / `<1500` / 否则 | `deep low rumble` / `warm mid-range` / `bright airy` |
| **loudness** (overall RMS = Σ stem energies) | `<0.02` / `<0.08` / 否则 | `quiet` / `moderate` / `loud` |
| **tempo 置信门** | drums ratio ≥ 0.10 AND onset_count ≥ 3 | 否则 `tempo_bpm = null`（不出现 Xbpm 片段） |
| **vocal_presence** | ratios.vocals ≥ 0.70 触发 leading 加 "clear lead vocal" | 0.0–1.0 浮点保留 4 位 |
| **dialogue 降级** (无 transcript) | dialogue 型 + 无 transcript | vocals SC ≥ 2500 → `non-vocal melodic vocalise`；否则 → `vocal texture` |
| **prompt 拼接顺序** | — | `{leading}[ ~Xbpm][, "excerpt"], {loudness} {brightness} bed` |

### 降级路径

- **Path A (无 transcript.json)：** `dialogue_excerpt=""`、dialogue 型 shot 按频谱重心降级为 `non-vocal melodic vocalise` 或 `vocal texture`；其它 type 不受影响。ep03 即此用例。
- **Path B (无 stems 目录)：** `tempo_bpm=null`、prompt 不出现 `~Xbpm` 片段；prompt 仍成形。
- **Stem 目录解析兜底**（镜像 `separate_stems.py:67-73`）：首选 `<ep>/stems/htdemucs/<ep_name>/drums.wav`；失败尝试 `<ep>/stems/drums.wav`；都失败 → degrade。

### 确定性保证

相同输入两次运行产出 byte-identical 的 `audio_prompts.json`：
- 不写时间戳、不写绝对路径
- `json.dump(out, f, indent=2, ensure_ascii=False)`（D4 输出格式）
- shots 按数组原序遍历（不按 dict）
- 浮点 round 到 4 位（与 audio_analysis.json 一致）
- 字典 key 序在源码里固定（Python 3.7+ 保序）

### 合约零改动（D1/D4 核心保证）

- 未修改：`spec/SPEC.md` / `spec/schemas/*.schema.json` / `audio_analysis.json` / `scripts/export_asset.py` / `run_pipeline.py` / `asset.json`
- 未新增任何 `schema_version` 字段进 `audio_prompts.json`
- `run_pipeline.py` grep 不到 `gen_audio_prompts`（未误接入 pipeline）
- 未引入新 pip 包（imports 仅 stdlib + numpy）

PLAN.md `<verify><automated>` 块全绿：
```
syntax ok
exports ok
ensure_ascii ok
no schema_version ok
```

`git diff --stat HEAD -- spec/SPEC.md spec/schemas/ scripts/export_asset.py audio_analysis.json` 为空。

## Smoke run（ep01 happy path）

```bash
python3 audio/gen_audio_prompts.py \
  --episode-dir "output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
```

**结果：** exit 0；93/93 prompts（覆盖 1:1）；43/93 with bpm；93/93 with dialogue excerpt。

样本 prompts：
```
shot 1 [dialogue] bpm=None
  prompt: clear lead vocal, calm male vocal narration, "八 七 六", moderate bright airy bed
  facets: dominant_type=dialogue, brightness=bright airy, loudness=moderate,
          vocal_presence=0.9655, dialogue_excerpt="八 七 六"

shot 9 [mixed] bpm=None
  prompt: blended bright airy bed with vocals, "爸爸还要陪你玩呢", loud bright airy bed
  facets: dominant_type=mixed, brightness=bright airy, loudness=loud,
          vocal_presence=0.3832, dialogue_excerpt="爸爸还要陪你玩呢"

shot 12 [bgm] bpm=200
  prompt: bright airy instrumental bed ~200bpm, "正是", loud bright airy bed
  facets: dominant_type=bgm, brightness=bright airy, loudness=loud,
          vocal_presence=0.3642, dialogue_excerpt="正是", tempo_bpm=200
```

**覆盖性 sanity check：** `len(shots) == len(prompts)` ✓、`shot_id` 一一对应 ✓。

## Spot-check (Task 2): DONE — orchestrator 跑 3-episode spot-check + 收集 user verdict

Task 2 是 `checkpoint:human-verify` blocking gate。orchestrator（非 worktree，可读 gitignored `output/`）跑完 PLAN.md `<how-to-verify>` Step 1-3。

### Step 1 — 3 episode 全部 exit 0

| episode | shots | prompts | bpm 覆盖 | with-dialogue | transcript |
|---------|-------|---------|----------|---------------|------------|
| ep01 爸爸去哪儿 | 93 | 93 | 43/93 | 93/93 | ✓ |
| ep02 刀和小番茄 | 100 | 100 | 36/100 | 97/100 | ✓ |
| ep03 白头发的少女 | 76 | 76 | 28/76 | 0/76 | ✗ (degraded) |

ep03 降级路径 A 实测生效：`with-dialogue=0/76`、脚本不崩溃。

> **过程注记：** PLAN.md `<interfaces>` 与 executor prompt 里 ep03 目录名误抄为 `...情绪只是目的`（实际为 `...情绪才是目的`）。脚本对错误路径行为正确（打印 `shots.json not found` 后 exit，不静默）；用正确目录名重跑即通过。仅文档拼写问题，非脚本缺陷。

### Step 2 — 覆盖性 + schema 断言 3/3 OK

- `len(shots) == len(prompts)` ✓（93/93、100/100、76/76）
- `[s["id"]] == [p["shot_id"]]` ✓
- `facets` key 集精确等于 `{dominant_type, tempo_bpm, brightness, loudness, vocal_presence, dialogue_excerpt}` ✓
- ep03 `dialogue_excerpt` 全为空串 ✓

### Step 3 — 每 type 1 条样本 prompt（核心人工 eyeball）

```
ep01 shot  1 [dialogue] → clear lead vocal, calm male vocal narration, "八 七 六", moderate bright airy bed
ep01 shot 12 [bgm]      → bright airy instrumental bed ~200bpm, "正是", loud bright airy bed
ep02 shot  1 [mixed]    → blended bright airy bed with vocals ~92bpm, "人家都打完收工了", loud bright airy bed
ep03 shot  1 [dialogue] → vocal texture ~200bpm, moderate warm mid-range bed   (无 transcript 降级)
ep03 shot 23 [sfx]      → textural bright airy effect ~200bpm, moderate bright airy bed
```

**亮点：** 4 类 dominant_type 的 leading phrase 区分明显（narration / instrumental bed / textural effect / blended bed）；中文对白摘录嵌入清晰；ep03 降级为 `vocal texture` 仍成形。

### User resume-signal: **APPROVED → 晋升 v1.2 milestone**

Concept validated：本地启发式 per-shot audio-gen NL prompt 可用、降级优雅、合约零改动。3 个质量问题作为 v1.2 milestone 的明确 input（见下 §"v1.2 milestone input"），不在本 spike 内调。

## v1.2 milestone input（user-approved carry-forward）

**整体：prompts 可读、覆盖性合同满足、降级路径优雅、合约零改动。** Concept 达 milestone-ready 最低门槛，user 已 approve 晋升。

3 个需在 v1.2 解决的质量问题（spot-check 实测确认，非初判）：
- **brightness 词偏 `bright airy`**：ep01 大量 shot vocals SC > 1500 Hz → 全 "bright airy"。这可能掩盖了 brightness 的区分度。如 user 反馈"词太集中"，可加中间档（如 1500–3500 → "open mid-range"、≥3500 → "bright airy"）。
- **tempo bpm=200 是 clamp 上界**：说明 ep01 shot 12 的 onset 间隔中位数 < 0.30s（即 onset 检得偏密）。可能 peak-pick 阈值 `mean + 0.5*std` 偏低，导致过检。如 user 反馈"tempo 误检"，可调到 `mean + 1.0*std` 或提高 `TEMPO_DEBOUNCE_SEC`。
- **dialogue 高 vocal_presence 双短语堆叠**（"clear lead vocal, calm male vocal narration"）有点冗长；如 user 反馈"冗余"，可改为二选一而非拼接。

**晋升 v1.2 milestone 路径建议（待 user 决策）：**
1. **独立 asset 字段**：asset.json 新增顶层 `audio_prompts` 数组（与 `shots`/`cinematography` 平级）—— 最干净、改动局部、producer 自包含
2. **audio_analysis.json 加 prompts 字段**：复用既有 sidecar —— 但破坏"audio_analysis.json 只描述客观特征"的语义
3. **spec 新 section**：把 audio-gen prompt 提升为合约一等公民 —— 最重，需 schema bump（v1.2 or v2）

推荐 (1)：与 v1.0/v1.1 一贯的 "additive optional field" 模式一致（参考 `cinematography`、`registry_snapshot`）。

## Self-Check

- [x] `audio/gen_audio_prompts.py` 存在（398 行）
- [x] 语法合法（`ast.parse` ok）
- [x] 5 个必要函数导出（main / gen_prompts / load_audio_stem / estimate_tempo_from_envelope / compose_prompt）
- [x] `ensure_ascii=False` 出现 1 次（输出 JSON 写入处）
- [x] 无 `schema_version` 字段泄漏
- [x] `run_pipeline.py` 不引用 `gen_audio_prompts`
- [x] spec/SPEC.md / spec/schemas/* / scripts/export_asset.py / audio_analysis.json 与 HEAD 字节一致
- [x] ep01 smoke run exit 0，93/93 prompts，覆盖性合同满足

**Self-Check: PASSED**
