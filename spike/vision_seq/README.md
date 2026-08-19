# Phase 19 Vision-Seq Spike — THROWAWAY 脚本

> ⚠️ **THROWAWAY Phase 19 spike 脚本 —— 不是 pipeline 代码。**
>
> 不要在 `run_pipeline.py` 任何 `step_*` 函数里 `import` 本目录任何模块。
> 不要把它们接到 `analysis/*` 任何客户端。这些脚本**只**服务 Phase 19
> Plan 19-02 的一次性 spike 任务，其最终交付物是
> `.planning/research/vision-seq-spike-report.md`。脚本本身仅为可复现而提交。

## 用途

ep01 live 集 action/camera 空缺率 0/93 ——「只填空缺、永不覆盖」语义在
live 上是 no-op（RESEARCH Pitfall 1）。spike 在 **sandbox 副本目录**（facet
置空）真实烧 GPU 逐帧/逐对问答，产出 A/B/baseline 三策略同镜产物 + ear
on/off 双跑 diff，供 Kai 盲评锁定合并策略（SC2）。

| 脚本 | 作用 | 输出 |
|------|------|------|
| `build_sandbox.py` | 离线构建 sandbox 副本（幂等；只读 live 只写本目录） | `sandbox/` + `sandbox_ear/` |
| `run_spike.py` | 四步双跑驱动（tmux 后台可跑；cache 断点续跑） | `results/` + sandbox cache |

## sandbox 布局

```text
spike/vision_seq/
├── sandbox/                  # 6 镜（#1/#46/#66/#70/#88/#91）action+camera 置 ""
│   ├── shots.json            # live 副本（93 镜，与 live 逐值同）
│   ├── prompts.json          # live 副本 + 6 镜两 facet 置空（v2 填充对象）
│   ├── audio_semantic.json   # demo 级 ear 输入（真 dialogue + 手工 sfx，过 schema 校验）
│   ├── frames_5fps -> ../../../output/<ep01>/frames_5fps   # symlink，不复制大文件
│   ├── video.mp4   -> ../../../output/<ep01>/h264.mp4      # symlink（video_content_hash 用）
│   └── route_cache/vision_seq/shot_XXX.json                # RAW 证据 cache（断点续跑）
├── sandbox_ear/              # 同构但只置空 3 镜（#1/#88/#91 —— ear 双跑子集）
└── results/                  # run.log + 三策略产物 + 指标 + 盲评表
```

## 四步序列（run_spike.py）

- **a** `sandbox/ --no-ear`——6 镜 × ~15 calls RAW 烧（ear_off 信封）
- **b** `sandbox_ear/ --audio-semantic`——3 镜 ear=true 信封烧
- **c** `--reset` 重置 sandbox facets 后 `--merge-strategy llm`——B 合并
  （2 ask_text/镜，merged_B 落 cache；三策略从同一 RAW 证据出发）
- **d** 产物导出（零 GPU）：三策略文本对比 / 客观指标 / ear diff /
  甲/乙/丙盲评表（随机映射记录在 `results/strategy_mapping.txt`）

```bash
# tmux 后台跑（脚本自带 run.log 双写，无需 shell tee）
tmux new-session -d -s vision_seq_spike 'python3 spike/vision_seq/run_spike.py'

# 监控进度（cache 文件增量 = 已烧镜数）
ls spike/vision_seq/sandbox/route_cache/vision_seq/shot_*.json | wc -l
tail -f spike/vision_seq/results/run.log
```

中断/超时重跑同命令即续（cache 幂等，已答帧绝不重烧）。

## 注意事项

- 目录名含全角括号与中文冒号（`output/虫虫武侠小故事《小江湖》第01话：…`）
  —— 脚本内一律 `pathlib.Path`，禁 shell 字符串拼接（mirror spike/audio
  同款警告）。
- `build_sandbox.py` 全量重建会把 sandbox prompts.json 的 facets 重新置空
  （**不动 route_cache** —— 重跑 run_spike 可从 cache 零 GPU 重填）。
  `--reset [--target sandbox|sandbox_ear|both]` 只重置 prompts facets，
  供 19-03 复用。
- `sandbox/video.mp4` symlink 命中 gitignore `*.mp4`（有意——大文件不进
  git；`build_sandbox.py` 幂等重建）。
- live ep01 work_dir 全程零写入：跑前跑后 `sha256sum` live prompts.json
  必相等（SC1 负测试，记录进 spike report）。
- 盲评前不要看 `results/strategy_mapping.txt`（甲/乙/丙 ↔ 策略映射，
  裁决后才回写报告）。
