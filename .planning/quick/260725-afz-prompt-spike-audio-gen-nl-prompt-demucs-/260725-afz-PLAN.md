---
phase: quick
plan: 260725-afz
type: execute
wave: 1
depends_on: []
files_modified:
  - audio/gen_audio_prompts.py
autonomous: false
requirements:
  - SPIKE-AUDIO-PROMPT-01  # local-heuristic NL audio-gen prompt per shot
user_setup: []

must_haves:
  truths:
    - "脚本可对 output/ 下任一 episode 执行，且在 episode 目录写出 audio_prompts.json sidecar"
    - "audio_prompts.json 覆盖 shots.json 的每一个 shot（连续无缺）"
    - "每条 prompt 读起来像 generative-audio 风格的自然语言（质感 [+tempo] [+对白/人声] [+亮度/能量] bed）"
    - "ep03 缺 transcript.json 时仍产出 prompt（仅省略 dialogue_excerpt，不崩溃）"
    - "tempo_bpm 仅在 drum onset 数量充分时出现，否则为 null 并从 prompt 中省略"
    - "脚本不修改 audio_analysis.json / SPEC.md / schemas / asset.json / export_asset.py / run_pipeline.py（合约零改动）"
  artifacts:
    - path: "audio/gen_audio_prompts.py"
      provides: "独立 CLI：从已算好的 Demucs 能量/频谱 + Whisper 对白 + drum/bass onset 推导 NL audio-gen prompt，写 audio_prompts.json sidecar"
      min_lines: 150
  key_links:
    - from: "audio/gen_audio_prompts.py"
      to: "output/<ep>/audio_analysis.json"
      via: "json.load 读取 shots[].energies/ratios/spectral_centroid/dominant_type"
      pattern: "audio_analysis\\.json"
    - from: "audio/gen_audio_prompts.py"
      to: "output/<ep>/transcript.json"
      via: "可选 json.load（缺失则降级）"
      pattern: "transcript\\.json"
    - from: "audio/gen_audio_prompts.py"
      to: "output/<ep>/stems/htdemucs/<ep>/drums.wav"
      via: "stdlib wave + numpy 读取，peak-pick onset 估 tempo"
      pattern: "wave\\.open"
    - from: "audio/gen_audio_prompts.py"
      to: "output/<ep>/audio_prompts.json"
      via: "json.dump(ensure_ascii=False, indent=2) 写 sidecar"
      pattern: "audio_prompts\\.json"
---

<objective>
为每镜生成 audio-gen 风格的自然语言 prompt（spike）。

Purpose: 经验性验证"从已有 Demucs 能量/频谱 + Whisper 对白 + drum/bass onset 推导出的本地启发式 NL prompt"是否具备晋升为 v1.2 milestone 的质量。这是 **producer-only spike** —— 合约零改动、零网络、不进 pipeline。

Output: 一个自包含脚本 `audio/gen_audio_prompts.py`，对 `output/` 下的真实样本数据执行后产出 sidecar `audio_prompts.json`，供肉眼 spot-check。
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@audio/separate_stems.py
@audio/transcribe.py

<interfaces>
<!-- 关键既有契约 —— 执行器直接用，无需再次探索代码 -->

From audio/separate_stems.py (load_audio_stem —— spike 读取 stem WAV 的范式):
```python
def load_audio_stem(path: str):
    """读取 wav 文件，返回 (mono float32 numpy, sample_rate)。"""
    import wave
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
    return audio, sr
```

audio_analysis.json schema (per-shot 已算好的特征 —— spike 直接消费):
```jsonc
{
  "episode": "<video stem>",
  "duration": 308.33,
  "stems": ["vocals","drums","bass","other"],
  "shots": [
    {
      "shot_id": 1,
      "start_sec": 0.0, "end_sec": 6.73, "duration": 6.73,
      "energies":  {"vocals": 0.0644, "drums": 0.0004, "bass": 0.0003, "other": 0.0017},
      "ratios":    {"vocals": 0.9655, "drums": 0.0054, "bass": 0.0041, "other": 0.0250},
      "spectral_centroid": {"vocals": 2439.0, "drums": 4332.6, "bass": 8538.7, "other": 5825.9},
      "dominant_type": "dialogue"  // dialogue | bgm | sfx | mixed
    }
  ],
  "type_distribution": {"dialogue": 44, "mixed": 14, "bgm": 20, "sfx": 15}
}
```

transcript.json schema (OPTIONAL 输入 —— 缺失时降级):
```jsonc
{
  "backend": "faster-whisper",
  "model": "large-v3",
  "language": "zh",
  "duration": 308.33,
  "segments": [{"start": 0.0, "end": 2.5, "text": "..."}],
  "text": "（全文拼接）",
  "source": "<video filename>"
}
```

shots.json schema (覆盖性合同 —— spike 必须对每个 shot 产 prompt):
```jsonc
[{"id": 1, "start_sec": 0.0, "end_sec": 6.73, "duration": 6.73}]
```

样本数据布局 (output/ 实测，3 个 episode):
```
output/<ep-name>/
├── shots.json                              # 全 3 ep 都有
├── audio_analysis.json                     # 全 3 ep 都有
├── transcript.json                         # 仅 ep01 / ep02；ep03 缺失 → 降级测试用例
└── stems/htdemucs/<ep-name>/
    ├── vocals.wav  drums.wav  bass.wav  other.wav
```
ep-name 示例（带中文与括号，pathlib Path 处理稳妥即可）:
- `虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。`
- `虫虫武侠小故事《小江湖》第02话：刀和小番茄（ 有苦有甜，才是人生`
- `《小江湖》第03话：白头发的少女（画面只是工具，情绪只是目的`

Stem 目录解析兜底（镜像 separate_stems.py:67-73 兜底逻辑）:
首选 `<episode_dir>/stems/htdemucs/<ep_name>/`；不存在则尝试 `<episode_dir>/stems/`；再不存在 → 跳过 tempo，prompt 仍产出。
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: 实现 audio/gen_audio_prompts.py 独立 CLI</name>
  <files>audio/gen_audio_prompts.py</files>
  <behavior>
    - 输入: --episode-dir <path> 指向 output/<ep-name>/（含 shots.json + audio_analysis.json，可选 transcript.json + stems/）
    - 输出: 在 episode-dir 下写 audio_prompts.json（覆盖式写）
    - 覆盖性: audio_prompts.json 数组长度 == shots.json 数组长度，shot_id 一一对应
    - 降级路径 A (无 transcript.json): prompt 仍产出，facets.dialogue_excerpt 为空串、facets.vocal_presence 由能量比推导
    - 降级路径 B (无 stems 目录): prompt 仍产出，facets.tempo_bpm 为 null、prompt 中不出现 "Xxbpm"
    - 确定性: 相同输入两次运行产出 byte-identical 的 audio_prompts.json（不写时间戳、不写绝对路径、字典遍历按固定 key 序）
    - 合约零改动: 不创建/修改 audio_analysis.json、SPEC.md、spec/schemas/*、asset.json、export_asset.py、run_pipeline.py
  </behavior>
  <action>
按 D6 创建单一自包含脚本 `audio/gen_audio_prompts.py`，严格镜像 `audio/separate_stems.py` 的风格（4 空格缩进、中文 docstring/comment、snake_case、stdlib `wave` 读 stem、numpy 做数学、`json.dump(..., ensure_ascii=False, indent=2)`、模块级 docstring 说明用途/算法/输出 JSON schema/CLI 用法）。

模块结构（按从上到下顺序）：
1. **Module docstring**（中文，说明：用途=为每镜生成 audio-gen 风格 NL prompt 的 spike；算法=本地启发式融合 Demucs 能量/频谱 + Whisper 对白 + drum/bass onset tempo；输出=sidecar audio_prompts.json，不进 spec/asset；CLI 用法）。
2. **imports**: `argparse, json, os, sys, wave` from stdlib；`from pathlib import Path`；`import numpy as np`。**禁止新增任何第三方依赖**（D3）。
3. **load_audio_stem(path)** —— 复制 `audio/separate_stems.py:77-88` 同一实现（stdlib `wave` + numpy int16→float32 + 双声道均值）。这是项目既有范式，必须保持一致。
4. **estimate_tempo_from_envelope(audio, sr, start_sec, end_sec)** → `tuple[int | None, int]` 返回 `(bpm_or_None, onset_count)`:
   - 取该 shot 时段的 drum stem mono 数组（按 separate_stems.py:93-98 的方式切片、夹边界）
   - 短窗 (hop=512, win=1024) 计算 RMS envelope → `np.sqrt(np.mean(seg**2)+1e-10)` per hop
   - 自适应阈值 = `envelope.mean() + 0.5 * envelope.std()`；peak-pick：envelope[i] > 阈值 AND 局部极大（高于左右各 1 邻居）AND 与上一个 onset 距离 ≥ 0.20s（防抖）
   - 若 onset_count < 3 → 返回 `(None, onset_count)`（不够置信）
   - 否则取相邻 onset 间隔的中位数 → `60.0 / median_interval_sec`；clamp 到 [40, 200]；round 到整数
5. **brightness_word(hz)** → str: `<400` → `"deep low rumble"`；`400..1500` → `"warm mid-range"`；`>1500` → `"bright airy"`。（D3 频谱重心→亮度词指导）
6. **loudness_word(rms_energy)** → str: 按整体 RMS（shot 内四 stem 能量和）相对阈值：`<0.02` → `"quiet"`；`<0.08` → `"moderate"`；否则 → `"loud"`。阈值作为模块常量（`LOUDNESS_QUIET_THRESHOLD = 0.02` 等），便于 spot-check 后调参。
7. **leading_phrase(dominant_type, brightness, vocal_presence)** → str（D3 指导）:
   - `"dialogue"` → `"calm male vocal narration"` / `"spoken vocal"`（vocal_presence 高时带 "clear lead vocal"，仅 transcript 缺失时降级为 `"non-vocal melodic vocalise"` 当 spectral centroid 高 / `"vocal texture"` 当低 —— 仅在 dominant_type 含 vocals 倾向且无 transcript 时触发这条分支）
   - `"bgm"` → `"{brightness} instrumental bed"`
   - `"sfx"` → `"textural {brightness} effect"`
   - `"mixed"` → `"blended {brightness} bed with vocals"`
   顺序可微调，关键是确定性（同一输入→同一短语）。
8. **find_dialogue_excerpt(transcript_segments, start_sec, end_sec, max_chars=20)** → str: 找首个 `seg.start < end_sec AND seg.end > start_sec` 的 segment；取 `seg.text` 前 `max_chars` 字符；用 `text.replace('"', '\\"')` 转义引号；无匹配返回 `""`。
9. **compose_prompt(leading, tempo_bpm, dialogue_excerpt, loudness, brightness)** → str: 按序拼接：`"{leading}"` + (`tempo_bpm` 非空时 `f" ~{tempo_bpm}bpm"`) + (`dialogue_excerpt` 非空时 `f", \"{excerpt}\""`) + `f", {loudness} {brightness} bed"`。无 tempo 不出现 bpm；无对白不出现引号。
10. **derive_facets_and_prompt(shot, drum_audio, drum_sr, transcript_segments)** → dict:
   - `dominant_type` ← `shot["dominant_type"]`
   - 计算 `overall_rms = sum(shot["energies"].values())`；`loudness = loudness_word(overall_rms)`
   - `dominant_stem` = `shot["dominant_type"]` 对应的主 stem 名（dialogue→vocals, bgm→取 drums/bass 中 energy 大者, sfx→other, mixed→vocals 但 brightness 取四 stem 频谱按能量加权平均）
   - `brightness = brightness_word(shot["spectral_centroid"][dominant_stem])`
   - `vocal_presence` ← `shot["ratios"]["vocals"]`（0.0-1.0 浮点，不转字符串）
   - `tempo_bpm, onset_count = estimate_tempo_from_envelope(...)` 仅当 `shot["ratios"]["drums"] >= 0.10` 时调用，否则 `(None, 0)`（drums 占比过低则不估 tempo）
   - `dialogue_excerpt` ← `find_dialogue_excerpt(...)`（transcript_segments 为 `None` 时直接 `""`）
   - `leading = leading_phrase(...)`；`prompt = compose_prompt(...)`
   - 返回 `{shot_id, start_sec, end_sec, duration, prompt, facets:{dominant_type, tempo_bpm, brightness, loudness, vocal_presence, dialogue_excerpt}}`
11. **gen_prompts(episode_dir, output_path)** → list[dict]:
   - `[stage]` print 开始；读 shots.json、audio_analysis.json（按 shot_id 建索引字典，不假设数组顺序但实测是顺序的）
   - transcript.json 缺失 → `print("[stage] no transcript.json — degrading (dialogue_excerpt will be empty)")`，segments 设 None；存在则 `json.load`
   - 解析 stem 目录（见 context `<interfaces>` 中 Stem 目录解析兜底），优先 `episode_dir/stems/htdemucs/<episode_dir.name>/drums.wav`；尝试失败时 `print("[stage] stems not found — degrading (tempo will be null)")`，drum_audio 设 None
   - 仅当 drum_audio 可用且 audio_analysis 里 `shots[*].ratios.drums >= DRUM_RATIO_TEMPO_THRESHOLD (默认 0.10)` 时估 tempo
   - 每 10 个 shot 打印进度（`if (i+1) % 10 == 0: print(f"  {i+1}/{len(shots)}")` —— 镜像 separate_stems.py:171 的范式）
   - 循环结束打印简短统计：有 bpm 的 shot 数 / 总数，有对白摘录的 shot 数 / 总数
   - `json.dump(out, f, indent=2, ensure_ascii=False)`（D4 输出格式）
12. **main()**:
    - `ap = argparse.ArgumentParser(description="为每镜生成 audio-gen 风格 NL prompt（spike，sidecar 输出，不进 spec/pipeline）")`
    - `--episode-dir` required，中文 help `"episode 输出目录（包含 shots.json + audio_analysis.json）"`
    - `--output` default=None，中文 help `"输出 JSON 路径（默认 <episode-dir>/audio_prompts.json）"`
    - `args.output or args.episode_dir + "/audio_prompts.json"`
    - 调 `gen_prompts`，`print(f"[stage] wrote {len(out)} shot prompts → {output}")`
    - 结尾 print 一行提醒 `"sidecar spike — NOT referenced by spec/asset.json (per D4)"`（防止后续 agent 误以为这是正式合约）
13. `if __name__ == "__main__": main()`

**禁止清单（合约零改动 —— D1/D4）**：
- 不得 import 或修改 `export_asset.py` / `run_pipeline.py`
- 不得修改 `spec/SPEC.md` / `spec/schemas/*.schema.json`
- 不得修改 `audio_analysis.json`（只读）
- 不得写任何 `schema_version` 字段进 audio_prompts.json（D1：sidecar 不是合约产物）
- 不得引入新 pip 包（D3：numpy + wave 已够）

**输出 JSON schema（D4 + 输出约束）**：
```
[
  {
    "shot_id": 1,
    "start_sec": 0.0,
    "end_sec": 6.73,
    "duration": 6.73,
    "prompt": "calm male vocal narration, \"爸爸去哪儿？\", moderate warm mid-range bed",
    "facets": {
      "dominant_type": "dialogue",
      "tempo_bpm": null,
      "brightness": "warm mid-range",
      "loudness": "moderate",
      "vocal_presence": 0.9655,
      "dialogue_excerpt": "爸爸去哪儿？"
    }
  }
]
```

注意：`facets.loudness` 和 `facets.vocal_presence` 字段名出现在 schema 中（vocal_presence 是 float、loudness 是 str）；约束文档原列的字段集可扩展（loudness/vocal_presence 都属于"已经从既有特征算出来"的派生 facet，与 D3 一致 —— 不引入新输入源，只是把既有能量比/总和呈现出来便于 spot-check）。

**确定性微细节**：
- 遍历 shots 用 `for shot in shots:`（数组原序），不要按 dict 遍历
- 浮点 round 到 4 位（与 audio_analysis 一致）
- brightness/loudness 阈值常量提到模块顶部 `UPPER_CASE`
  </action>
  <verify>
    <automated>python3 -c "import ast, sys; ast.parse(open('audio/gen_audio_prompts.py').read()); print('syntax ok')" && python3 -c "import importlib.util, sys; spec=importlib.util.spec_from_file_location('m','audio/gen_audio_prompts.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); assert hasattr(m,'main') and hasattr(m,'gen_prompts') and hasattr(m,'load_audio_stem') and hasattr(m,'estimate_tempo_from_envelope') and hasattr(m,'compose_prompt'); print('exports ok')" && grep -v '^#' audio/gen_audio_prompts.py | grep -c 'ensure_ascii=False' | grep -qE '^[1-9]' && echo 'ensure_ascii ok' && grep -vE '^#|^\s*#' audio/gen_audio_prompts.py | grep -qE 'schema_version' && echo 'FAIL: schema_version leaked' && exit 1 || echo 'no schema_version ok'</automated>
  </verify>
  <done>
脚本存在、语法合法、导出 5 个必要函数、写 JSON 用 ensure_ascii=False、未包含任何 schema_version 字段。脚本未被 run_pipeline.py 调用（grep 验证 run_pipeline.py 不引用 gen_audio_prompts）。spec/SPEC.md、spec/schemas/*.schema.json、export_asset.py、asset.json 与 git HEAD 字节一致（无改动）。
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: 在 3 个真实 episode 上 spot-check prompt 质量</name>
  <action>人工执行 Step 1-3 的验证流程（详见 <how-to-verify>）， eyeball 3 个 episode 的 prompt 质量、覆盖性、降级路径，按 <resume-signal> 反馈。</action>
  <what-built>
Task 1 落地的 `audio/gen_audio_prompts.py` —— 一个 producer-only spike 脚本，读 audio_analysis.json + 可选 transcript.json + 可选 stems，按本地启发式为每个分镜产出 audio-gen 风格 NL prompt，写 sidecar `audio_prompts.json`。**合约零改动、未进 pipeline、未引入新依赖**。
  </what-built>
  <how-to-verify>
**Step 1 — 在 3 个真实 episode 上跑脚本**（D5：必须对 output/ 真实数据可运行）：
```bash
cd /data/workspace/kais-shot-timeline

# ep01 —— 有 transcript + stems（happy path）
python3 audio/gen_audio_prompts.py \
  --episode-dir "output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"

# ep02 —— 有 transcript + stems（happy path, 第二样本）
python3 audio/gen_audio_prompts.py \
  --episode-dir "output/虫虫武侠小故事《小江湖》第02话：刀和小番茄（ 有苦有甜，才是人生"

# ep03 —— 无 transcript（降级路径 A 必须 graceful）
python3 audio/gen_audio_prompts.py \
  --episode-dir "output/《小江湖》第03话：白头发的少女（画面只是工具，情绪只是目的"
```

期望：3 次执行都 exit 0；每个 episode 目录下新生成 `audio_prompts.json`；ep03 stderr/stdout 应出现 `[stage] no transcript.json — degrading ...` 行。

**Step 2 — 覆盖性与 schema 检查**：
```bash
python3 - <<'PY'
import json, os
eps = [
  "output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。",
  "output/虫虫武侠小故事《小江湖》第02话：刀和小番茄（ 有苦有甜，才是人生",
  "output/《小江湖》第03话：白头发的少女（画面只是工具，情绪只是目的",
]
for ep in eps:
    shots = json.load(open(f"{ep}/shots.json"))
    prompts = json.load(open(f"{ep}/audio_prompts.json"))
    assert len(shots) == len(prompts), f"{ep}: {len(shots)} shots vs {len(prompts)} prompts"
    assert [s["id"] for s in shots] == [p["shot_id"] for p in prompts], f"{ep}: shot_id mismatch"
    for p in prompts:
        assert set(p.keys()) >= {"shot_id","start_sec","end_sec","duration","prompt","facets"}
        assert set(p["facets"].keys()) == {"dominant_type","tempo_bpm","brightness","loudness","vocal_presence","dialogue_excerpt"}
        assert isinstance(p["facets"]["tempo_bpm"], (int, type(None)))
        assert isinstance(p["facets"]["vocal_presence"], float)
        assert p["prompt"]  # non-empty
    # ep03 must have empty dialogue_excerpt everywhere
    if "03" in ep:
        assert all(p["facets"]["dialogue_excerpt"] == "" for p in prompts), "ep03 should have empty excerpts"
    print(f"OK {ep}: {len(prompts)} prompts, "
          f"bpm-coverage={sum(1 for p in prompts if p['facets']['tempo_bpm'])}/{len(prompts)}, "
          f"with-dialogue={sum(1 for p in prompts if p['facets']['dialogue_excerpt'])}/{len(prompts)}")
PY
```

期望：3 个 episode 全部 OK；ep03 bpm-coverage 可能 >0（drum stem 仍存在）、with-dialogue 必须 =0。

**Step 3 — Spot-check prompt 质量**（核心验收）：
```bash
python3 - <<'PY'
import json
eps = [
  ("ep01", "output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"),
  ("ep02", "output/虫虫武侠小故事《小江湖》第02话：刀和小番茄（ 有苦有甜，才是人生"),
  ("ep03", "output/《小江湖》第03话：白头发的少女（画面只是工具，情绪只是目的"),
]
# 每个 episode 各 type 选 1 条（dialogue/bgm/sfx/mixed 各一，缺则跳过），打印 shot_id / dominant_type / prompt / facets
for tag, ep in eps:
    prompts = json.load(open(f"{ep}/audio_prompts.json"))
    print(f"\n=== {tag} ({ep.split('/')[-1]}) ===")
    seen = set()
    for p in prompts:
        dt = p["facets"]["dominant_type"]
        if dt in seen: continue
        seen.add(dt)
        print(f"  shot {p['shot_id']:>3} [{dt:>8}] bpm={p['facets']['tempo_bpm']}")
        print(f"    prompt: {p['prompt']}")
        if p['facets']['dialogue_excerpt']:
            print(f"    excerpt: \"{p['facets']['dialogue_excerpt']}\"")
PY
```

期望（人工 eyeball）：
- prompt 读起来像 audio-gen 提示词（不是标签堆栈、不是 JSON 片段）
- dialogue 型 shot 含中文对白摘录（ep01/02）；ep03 dialogue 型 shot prompt 仍成形（无对白但有 "vocal" 类前缀或降级为 "vocal texture"）
- bgm/sfx 型 shot 不含对白引号；tempo 仅在 drums 占比高且 onset 充分的 shot 出现
- 不同 dominant_type 的 prompt 在 texture 词上明显区分
  </how-to-verify>
  <resume-signal>
若 prompt 质量可接受，回复 "approved" 并简要指出 1-2 条可改进项（用于 v1.2 milestone 的 input，无需在本 spike 内改）。
若质量不达标，回复具体问题（如：brightness 词分布太集中 / tempo 误检 / dialogue 型漏掉人声前缀），Task 1 将据此调阈值常量后重跑 Step 1-3。
  </resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| filesystem → script | 脚本读取 `output/<ep>/` 下既有 JSON + WAV（gitignored 本地样本数据，用户自产） |
| script → filesystem | 脚本写单一 sidecar `audio_prompts.json` 到 episode 目录（与输入同目录，无特权路径） |

无网络、无 subprocess、无 untrusted 输入、无认证边界。

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-afz-01 | Information Disclosure | audio_prompts.json 内容 | accept | 仅含从既有 Demucs/Whisper 输出派生的描述 + 已转录对白（transcript.json 已是明文）；sidecar 与 audio_analysis.json 同目录同敏感级 |
| T-afz-02 | Tampering | dialogue_excerpt 引号转义 | mitigate | find_dialogue_excerpt 内 `text.replace('"','\\"')` 防止破坏 JSON / 注入未预期字符到 prompt 字符串内 |
| T-afz-03 | Denial of Service | 大型 stem WAV 读入内存 | mitigate | estimate_tempo_from_envelope 只切该 shot 时段切片（镜像 separate_stems.py:93-98 的切片范式），不全量保留；gen_prompts 中 drum_audio 在循环外读一次（不到 100MB，48000Hz * ~5min ≈ 30MB float32） |
| T-afz-04 | Repudiation | 输出处可追溯性 | accept | 脚本不写时间戳 / 绝对路径（确定性输出）；sidecar 不进 git，无需审计链 |

注：本 spike 不安装任何 pip 包（D3），故 Package Legitimacy Gate 不适用、无 T-afz-SC 行。
</threat_model>

<verification>
- `audio/gen_audio_prompts.py` 存在且语法合法（ast.parse）
- 脚本导出 `main / gen_prompts / load_audio_stem / estimate_tempo_from_envelope / compose_prompt`
- 不引入新 pip 依赖（import 行仅 stdlib + numpy）
- 不修改 `audio_analysis.json` / `SPEC.md` / `spec/schemas/*` / `asset.json` / `export_asset.py` / `run_pipeline.py`（`git status` 仅 `audio/gen_audio_prompts.py` 一行变化，外加 output/ 下未跟踪的 sidecar）
- `run_pipeline.py` grep 不到 `gen_audio_prompts`（确认未误接入 pipeline，D1）
- 对 3 个真实 episode 执行 exit 0
- 覆盖性：audio_prompts.json 长度 == shots.json 长度，shot_id 一一对应
- 降级：ep03（无 transcript）仍产出 prompt；dialogue_excerpt 全为空串；脚本不崩溃
- Spot-check：prompt 读起来像 audio-gen 提示词，不同 dominant_type 在 texture 词上区分明显
</verification>

<success_criteria>
- 单一脚本 `audio/gen_audio_prompts.py` 实现完成、风格匹配既有 audio/ 模块
- 3 个真实 episode 全部跑通、产出 audio_prompts.json（gitignored）
- 覆盖性合同满足（每 shot 一 prompt）
- 降级路径 A/B 验证通过
- 用户 spot-check 通过（Task 2 resume-signal = "approved"）
- 合约零改动（D1/D4 的核心保证）
</success_criteria>

<output>
完成后创建 `.planning/quick/260725-afz-prompt-spike-audio-gen-nl-prompt-demucs-/260725-afz-SUMMARY.md`，记录：
- 实现的关键决策（亮度/响度阈值、tempo 置信门槛、prompt 拼接顺序）
- 3 个 episode 的 spot-check 结果（每 type 1 条样例 prompt）
- 用户 spot-check 结论（approved / 改进项清单）
- 是否建议晋升为 v1.2 milestone 的输入信号（合约如何吸收 sidecar：audio_analysis.json 加 prompts 字段 vs 独立 asset 字段 vs spec 新 section）
</output>
