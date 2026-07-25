# Phase 10 Audio Spike — THROWAWAY 脚本

> ⚠️ **THROWAWAY Phase 10 spike 脚本 —— 不是 pipeline 代码。**
>
> 不要在 `run_pipeline.py` 任何 `step_*` 函数里 `import` 本目录任何模块。
> 不要把它们接到 `analysis/*` 任何客户端。这些脚本**只**服务 Phase 10 的
> 4 个一次性 spike 任务，其最终交付物是
> `.planning/research/audio-spike-report.md`。脚本本身仅为可复现而提交。

## 用途

按 Plan 10-03 / 10-04 / 10-05 的顺序产出 per-model 结果 JSON，落到
`results/`，最终由 `aggregate_report.py` 汇总到 spike 报告。

| 脚本 | 计划 | 输出文件 | 解 req |
|------|------|----------|--------|
| `run_ser_sensevoice.py` | Plan 10-03 | `results/ser_sensevoice_ep01.json` | DIA-04 (中文 SER 跨域) |
| `run_mir_head_to_head.py` | Plan 10-04 | `results/mir_mert_ep01.json` + `results/mir_panns_ep01.json` | MUS-04 (乐器识别 + MERT-vs-PANNs 头对头) |
| `run_whisperx_align.py` | Plan 10-05 | `results/whisperx_align_ep01.json` | DIA-05 (WhisperX 词级 drift) |
| `run_diarize_pyannote.py` | （可选 5th） | `results/diarize_ep01.json` | 信息性，不卡 req |

Wave 0（Plan 10-01）已交付：`common.py` / `aggregate_report.py` 骨架 / 4 个
`tests/` smoke 检查（`smoke_all.sh` / `route_stub_smoke.sh` /
`results_schema_check.py` / `staleness_check.sh`）。

## 关键不变量（VALIDATION.md "Spike Reproducibility Invariants"）

- **stratified_sample n=30, seed=10** —— 4 个 spike **必须**用
  `common.stratified_sample(segments, n=30, seed=10)` 抽出的同一段样本，
  否则 MERT-vs-PANNs、SenseVoice-vs-... 头对头可比性失效（Pitfall 9
  head-to-head integrity）。
- **device='cpu'** —— CONTEXT.md user decision（GPU 当前 DOWN：driver
  mismatch），spike 全部 CPU 跑。accuracy 指标与设备无关；latency/VRAM
  留给 route host 阶段。
- **fixture = ep01** —— `output/虫虫武侠小故事《小江湖》第01话：…/` 的
  v1.1 缓存 intermediates（shots.json 93 镜、transcript.json 155 段、
  4 stems、frames.json、audio_analysis.json）。零 re-extraction。

## WhisperX 隔离 venv（Pitfall 1 强制要求）

WhisperX 的 PyPI 依赖会拽 `torch>=2.6` 的 **CUDA 12.8** wheel，与项目
runtime `torch 2.6.0+cu124` 冲突。**绝对禁止**在项目环境里
`pip install whisperx` —— 必须：

```bash
python3 -m venv /tmp/whisperx-spike-venv
/tmp/whisperx-spike-venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
/tmp/whisperx-spike-venv/bin/pip install whisperx==3.8.6
```

之后所有 WhisperX 相关 spike 脚本用
`/tmp/whisperx-spike-venv/bin/python` 执行。Plan 10-05 会单独验证
venv 隔离（`python3 -c "import torch; assert '+cu124' in torch.__version__"`
保证项目环境未受污染）。

## Quickstart

```bash
# Wave 0 baseline smoke（results/ 空 + 路由 host 未启动）
bash spike/audio/tests/smoke_all.sh

# 强制跳过 ROUTE-01（Plan 02 才建路由 host）
SKIP_ROUTE_STUB=1 bash spike/audio/tests/smoke_all.sh

# 单独 staleness 检查（Pitfall 10 staleness gate）
python3 spike/audio/aggregate_report.py --check-staleness
```

## 注意事项

- 目录名含全角括号与中文冒号（`虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（…）`）
  —— 用 `pathlib.Path`，**不要** `subprocess.run(["ls", path])` 走 shell
  （Pitfall 8 encoding edge cases）。
- HF_TOKEN（pyannote 3.1 / WhisperX diarize）从环境变量读，**绝不**硬编码；
  错误信息一律过 `common._safe_error` regex 兜底（Pitfall 6 / T-10-01 mitigation）。
- 不在本目录里跑模型训练 / 微调；只做一次性 inference 取数。
