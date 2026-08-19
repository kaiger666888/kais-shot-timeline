#!/usr/bin/env python3
"""驱动 vision_seq spike 四步 GPU 双跑 + 离线产物导出（THROWAWAY —— 见 README）

步骤（每步独立 CLI 调用 analysis/vision_seq_facets.py，均幂等 —— cache
断点续跑：中断后重跑同命令即续，已答帧绝不重烧）：
  a. sandbox/ --no-ear —— 6 镜 × ~15 calls RAW 烧（ear_off 信封）
  b. sandbox_ear/ --audio-semantic —— 3 镜 ear=true 信封烧（demo audio）
  c. build_sandbox.py --reset --target sandbox 后 sandbox/ --merge-strategy
     llm —— B 合并 2 ask_text/镜，merged_B 落 cache（重置保证三策略从同一
     RAW 证据出发产出可对比文本）
  d. 产物导出（零 GPU）：从 cache RAW answers + merged_B 生成三策略
     （temporal/llm/longest）同镜文本对比 + 客观辅助指标 + ear diff +
     甲/乙/丙盲评表 → results/

设计为 tmux 后台可跑：无交互输入；日志双写 stdout 与 results/run.log
（子进程输出逐行 relay，实时可见）。

盲评防泄漏（T-19-07 mitigate）：甲/乙/丙 ↔ 策略的随机映射（固定 seed）
只落 results/strategy_mapping.txt；blind_review.md 内不出现任何策略
标识词（导出后 grep 自检）。

CLI 用法：
  python3 spike/vision_seq/run_spike.py                 # a,b,c,d 全跑
  python3 spike/vision_seq/run_spike.py --steps d       # 只重导出产物（零 GPU）
  python3 spike/vision_seq/run_spike.py --steps a,b     # 部分步（断点续跑）
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPIKE_ROOT = Path(__file__).resolve().parent
MODULE = REPO_ROOT / "analysis" / "vision_seq_facets.py"
BUILD = SPIKE_ROOT / "build_sandbox.py"
RESULTS = SPIKE_ROOT / "results"
LOG_PREFIX = "[vision-seq]"

# 与 build_sandbox.py 同源（不 import —— spike 脚本不依赖彼此，重复常量即可）。
SPIKE_SHOTS = [1, 46, 66, 70, 88, 91]
EAR_SHOTS = [1, 88, 91]
LIVE_WORK_DIR = REPO_ROOT / "output" / (
    "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。")

STRATEGIES = ["temporal", "llm", "longest"]
BLIND_LABELS = ["甲", "乙", "丙"]
MAPPING_SEED = 20260819

# 客观辅助指标（Claude's discretion 区，按 plan 实现说明落档）：时序连接词
# 密度 = 下列连接词计数 / 百字；实体/动作动词覆盖率 = v1 现行值的字符
# bigram 在产物中出现的比例（简单字符匹配，零分词依赖）。
CONNECTORS = ["然后", "接着", "随后", "此时", "最终", "随即", "紧接着"]

# 盲评表禁词（出现即映射泄漏 —— 导出后自检 fail-loud）。
BLIND_FORBIDDEN = ["temporal", "llm", "longest", "时序拼接", "二次合并", "最长",
                   "策略A", "策略B", "策略 A", "策略 B"]


class _Tee:
    """stdout + run.log 双写（append；flush 保证 tmux 实时可见）。"""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "a", encoding="utf-8")

    def __call__(self, msg: str):
        print(msg, flush=True)
        self.f.write(msg + "\n")
        self.f.flush()


def _relay(cmd: list, log) -> None:
    """subprocess 逐行 relay（live 进度进 run.log）；非零退出 fail-loud。"""
    log(f"{LOG_PREFIX} $ {' '.join(str(c) for c in cmd)}")
    proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        log("  " + line.rstrip())
    rc = proc.wait()
    if rc != 0:
        sys.exit(f"{LOG_PREFIX} 子进程退出码 {rc}: {cmd[1]}")


def _run_module(sandbox: Path, log, extra: list) -> None:
    """按路径调用 analysis/vision_seq_facets.py（subprocess，check 语义）。"""
    cmd = [sys.executable, MODULE,
           "--shots", sandbox / "shots.json",
           "--frames-dir", sandbox / "frames_5fps",
           "--work-dir", sandbox,
           "--output", sandbox / "prompts.json",
           "--video", sandbox / "video.mp4"] + extra
    _relay(cmd, log)


def _cache_files(sandbox: Path) -> list:
    d = sandbox / "route_cache" / "vision_seq"
    return sorted(d.glob("shot_*.json")) if d.is_dir() else []


# ─── 步骤 a/b/c ─────────────────────────────────────────────────────────────

def step_a(log):
    log(f"{LOG_PREFIX} === step a: sandbox no-ear RAW 烧（6 镜 × ~15 calls）===")
    sb = SPIKE_ROOT / "sandbox"
    if not (sb / "prompts.json").exists():
        _relay([sys.executable, BUILD], log)
    _run_module(sb, log, ["--no-ear"])
    n = len(_cache_files(sb))
    if n < len(SPIKE_SHOTS):
        sys.exit(f"{LOG_PREFIX} step a 后 cache 仅 {n}/{len(SPIKE_SHOTS)} 镜 —— "
                 f"查 {sb}/route_cache/warnings.json（引擎 degrade？）后重跑续烧")


def step_b(log):
    log(f"{LOG_PREFIX} === step b: sandbox_ear ear=true 烧（3 镜 × ~15 calls）===")
    sb = SPIKE_ROOT / "sandbox_ear"
    if not (sb / "prompts.json").exists():
        _relay([sys.executable, BUILD], log)
    _run_module(sb, log, ["--audio-semantic", sb / "audio_semantic.json"])
    want = {f"shot_{s:03d}.json" for s in EAR_SHOTS}
    got = {p.name for p in _cache_files(sb)}
    missing = want - got
    if missing:
        sys.exit(f"{LOG_PREFIX} step b 后 ear cache 缺 {sorted(missing)} —— "
                 f"查 warnings.json 后重跑续烧")


def step_c(log):
    log(f"{LOG_PREFIX} === step c: 重置 sandbox → llm 合并（2 ask_text/镜）===")
    _relay([sys.executable, BUILD, "--reset", "--target", "sandbox"], log)
    sb = SPIKE_ROOT / "sandbox"
    _run_module(sb, log, ["--no-ear", "--merge-strategy", "llm"])
    for p in _cache_files(sb):
        with open(p, encoding="utf-8") as f:
            env = (json.load(f).get("ear_off") or {})
        mb = env.get("merged_B") or {}
        sid = int(p.stem.split("_")[1])
        if sid in SPIKE_SHOTS and not (mb.get("action") and mb.get("camera")):
            sys.exit(f"{LOG_PREFIX} step c 后 shot {sid} merged_B 不全 —— 重跑 step c 续烧")


# ─── 步骤 d：产物导出（零 GPU） ──────────────────────────────────────────────

def _load_env(sandbox: Path, sid: int, envelope: str) -> dict:
    p = sandbox / "route_cache" / "vision_seq" / f"shot_{sid:03d}.json"
    if not p.exists():
        sys.exit(f"{LOG_PREFIX} cache 缺失: {p}（先跑烧 GPU 的步骤）")
    with open(p, encoding="utf-8") as f:
        return json.load(f).get(envelope) or {}


def _facet_values(env: dict, facet: str) -> list:
    """信封 answers → 该 facet 非空 RAW 答案按帧序/对序排序（mirror 模块逻辑）。"""
    prefix = "action_frame_" if facet == "action" else "camera_pair_"
    answers = env.get("answers") or {}
    items = []
    for k, v in answers.items():
        if isinstance(k, str) and k.startswith(prefix) and isinstance(v, str) and v:
            try:
                items.append((int(k[len(prefix):]), v))
            except ValueError:
                continue
    items.sort()
    return [v for _, v in items]


def _product(env: dict, facet: str, strategy: str) -> str:
    """三策略产物：temporal/longest 纯归约；llm 读 cache merged_B。"""
    values = _facet_values(env, facet)
    if strategy == "llm":
        mb = env.get("merged_B") or {}
        return mb.get(facet) or ""
    if not values:
        return ""
    if strategy == "longest":
        return max(values, key=len)
    return "→".join(values)


def _strip_punct(text: str) -> str:
    """只留 CJK 与字母数字（标点/空白不参与 bigram）。"""
    return "".join(c for c in text
                   if "\u4e00" <= c <= "\u9fff" or c.isalnum())


def _bigrams(text: str) -> set:
    s = _strip_punct(text)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()


def _metrics(product: str, v1: str) -> dict:
    """客观辅助指标：长度 / 时序连接词密度（每百字）/ v1 bigram 覆盖率。"""
    if not product:
        return {"length": 0, "connector_density": None, "v1_bigram_coverage": None}
    conn = sum(product.count(c) for c in CONNECTORS)
    b1, bp = _bigrams(v1), _bigrams(product)
    cov = round(len(b1 & bp) / len(b1) * 100, 1) if b1 else None
    return {"length": len(product),
            "connector_density": round(conn / len(product) * 100, 2),
            "v1_bigram_coverage": cov}


def _v1_refs() -> dict:
    with open(LIVE_WORK_DIR / "prompts.json", encoding="utf-8") as f:
        prompts = json.load(f)
    return {p["shot_id"]: p for p in prompts}


def _md_escape_cell(text: str) -> str:
    """markdown 表格单元：换行→<br>，竖线转义。"""
    return (text or "(空)").replace("|", "\\|").replace("\n", "<br>")


def step_d(log):
    log(f"{LOG_PREFIX} === step d: 产物导出（零 GPU，纯 cache 归约）===")
    RESULTS.mkdir(parents=True, exist_ok=True)
    v1_by_id = _v1_refs()
    envs = {sid: _load_env(SPIKE_ROOT / "sandbox", sid, "ear_off")
            for sid in SPIKE_SHOTS}
    ear_envs = {sid: _load_env(SPIKE_ROOT / "sandbox_ear", sid, "ear_on")
                for sid in EAR_SHOTS}

    # 甲/乙/丙随机映射（固定 seed 可复现）—— 只落 strategy_mapping.txt。
    order = list(STRATEGIES)
    random.Random(MAPPING_SEED).shuffle(order)
    mapping = dict(zip(BLIND_LABELS, order))
    with open(RESULTS / "strategy_mapping.txt", "w", encoding="utf-8") as f:
        f.write(f"# 甲/乙/丙 ↔ 策略映射（seed={MAPPING_SEED}，盲评裁决前勿看）\n")
        for label in BLIND_LABELS:
            f.write(f"{label} = {mapping[label]}\n")
        f.write(f"v1 = live ep01 prompts.json 现行值（route 产物，参照列）\n")

    # metrics.json（机器可读全量）。
    metrics = {"shots": {}, "ear_diff": {}}
    shot_fragments = []
    for sid in SPIKE_SHOTS:
        v1p = v1_by_id[sid]
        frag = [f"# shot #{sid} 三策略产物对比（ear_off 证据）\n"]
        for facet in ("action", "camera"):
            v1_text = v1p.get(facet) or ""
            frag.append(f"## {facet}\n")
            frag.append(f"- **v1 现行值**: {v1_text}\n")
            mrow = {}
            for st in STRATEGIES:
                prod = _product(envs[sid], facet, st)
                m = _metrics(prod, v1_text)
                mrow[st] = {"product": prod, **m}
                frag.append(f"- **{st}** (len={m['length']}, "
                            f"连接词/百字={m['connector_density']}, "
                            f"v1覆盖={m['v1_bigram_coverage']}%): {prod or '(缺失)'}\n")
            raw = _facet_values(envs[sid], facet)
            frag.append(f"- RAW 答案（{len(raw)} 条）: " +
                        " | ".join(raw) + "\n")
            metrics["shots"].setdefault(str(sid), {})[facet] = mrow
        (RESULTS / f"shot_{sid:03d}.md").write_text("".join(frag),
                                                    encoding="utf-8")
        shot_fragments.append(f"shot_{sid:03d}.md")

    # ear diff（#1/#88/#91，action 提问产物并排，同用 temporal 归约保可比）。
    ear_lines = ["# ear on/off 同镜 diff（action；temporal 归约，同一 RAW 证据语义）\n"]
    for sid in EAR_SHOTS:
        off = _product(envs[sid], "action", "temporal")
        on = _product(ear_envs[sid], "action", "temporal")
        metrics["ear_diff"][str(sid)] = {"ear_off": off, "ear_on": on}
        ear_lines.append(f"## shot #{sid}\n")
        ear_lines.append(f"- **ear_off**: {off or '(缺失)'}\n")
        ear_lines.append(f"- **ear_on** : {on or '(缺失)'}\n")
        ear_lines.append(f"- RAW ear_off: {' | '.join(_facet_values(envs[sid], 'action'))}\n")
        ear_lines.append(f"- RAW ear_on : {' | '.join(_facet_values(ear_envs[sid], 'action'))}\n")
    (RESULTS / "ear_diff.md").write_text("".join(ear_lines), encoding="utf-8")

    # 盲评表（甲/乙/丙 + v1 参照；禁词自检 fail-loud）。
    blind = ["# 三策略盲评表（甲/乙/丙匿名 + v1 现行值参照）\n",
             "逐镜逐 facet 并排对比：动作链完整性、运镜描述准确性、有无幻觉/啰嗦。\n",
             "裁决话术：「锁定 <甲/乙/丙>」或描述问题（映射见 strategy_mapping.txt，裁决后再看）。\n"]
    for sid in SPIKE_SHOTS:
        v1p = v1_by_id[sid]
        blind.append(f"\n## shot #{sid}\n")
        for facet in ("action", "camera"):
            blind.append(f"\n### {facet}\n\n")
            blind.append("| 产物 | 文本 |\n|------|------|\n")
            blind.append(f"| v1 现行值 | {_md_escape_cell(v1p.get(facet))} |\n")
            for label in BLIND_LABELS:
                prod = _product(envs[sid], facet, mapping[label])
                blind.append(f"| {label} | {_md_escape_cell(prod)} |\n")
    blind_text = "".join(blind)
    for w in BLIND_FORBIDDEN:
        if w in blind_text:
            sys.exit(f"{LOG_PREFIX} 盲评表泄漏策略标识词「{w}」")
    (RESULTS / "blind_review.md").write_text(blind_text, encoding="utf-8")

    with open(RESULTS / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({"mapping_seed": MAPPING_SEED,
                   "connectors": CONNECTORS,
                   "metric_definition": {
                       "connector_density": "连接词计数/百字（连接词表见 connectors）",
                       "v1_bigram_coverage": "v1 现行值去标点字符 bigram 在产物中出现的比例（%）"},
                   **metrics}, f, ensure_ascii=False, indent=2)
    log(f"{LOG_PREFIX} step d 导出: {shot_fragments} + ear_diff.md + "
        f"blind_review.md + strategy_mapping.txt + metrics.json")


def main():
    ap = argparse.ArgumentParser(
        description="vision_seq spike 四步双跑驱动（THROWAWAY；cache 断点续跑）")
    ap.add_argument("--steps", default="a,b,c,d",
                    help="要跑的步骤子集（逗号分隔，默认 a,b,c,d；d 零 GPU）")
    args = ap.parse_args()

    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    valid = {"a": step_a, "b": step_b, "c": step_c, "d": step_d}
    unknown = [s for s in steps if s not in valid]
    if unknown:
        sys.exit(f"{LOG_PREFIX} 未知步骤: {unknown}")
    log = _Tee(RESULTS / "run.log")
    log(f"{LOG_PREFIX} run_spike 启动 steps={steps} "
        f"({time.strftime('%Y-%m-%dT%H:%M:%S%z')})")
    for s in steps:
        valid[s](log)
    log(f"{LOG_PREFIX} 全部完成 steps={steps}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
