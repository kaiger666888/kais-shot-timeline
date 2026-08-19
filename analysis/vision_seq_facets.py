#!/usr/bin/env python3
"""qwen-eye v2 帧序列逐帧问答填充 prompts.json 的 action/camera facets（vision_seq）

背景：v1 路径（scene/subject 走 3 静帧取最长回答）把 action/camera 留在
「单帧脑补」水平。v2 用 ≤8 帧序列逐帧实证升级：action 逐帧独立问答、
camera 相邻帧对问（运镜本质是帧间差异，单帧答不出）。llama.cpp 单图
bug 硬约束下（单条 user 带 N 图只算 ceil(N/2) 张），对问走引擎客户端的
observe_pair（恰两条 user 各一图）。ear（v1.2 audio_semantic 摘要）在
生成时注入提问上下文 —— 模型自己权衡视听证据，非后处理改写。

facet 边界（不越权）：只填 action/camera 两个 facet；已有值永不覆盖
（route/人工产物无法从文本长度区分优劣，不做「更短就替换」）；subject
身份归 re-id，本步骤永不写 char_XXX。

算法步骤：
  1. 采样：每镜时窗内均匀 ≤8 帧（f%06d.jpg 等间隔序列，忽略 *_ds1280
     变体帧）。
  2. 逐帧/对问：action = 每采样帧一次 observe_single；camera = 每相邻
     帧对一次 observe_pair(f_i, f_{i+1})。ear 开且该镜有音频上下文时
     提问前拼「该镜音频：…。」。
  3. RAW cache：route_cache/vision_seq/shot_XXX.json 双信封（ear_on /
     ear_off）存逐帧/逐对原始答案（action_frame_N / camera_pair_M，
     键缺席 = 从未问过）+ merged_B（策略 B 合并产物）；合并是纯归约，
     策略切换零 GPU 重烧。
  4. 合并（写出时执行，读 cache RAW answers）：--merge-strategy
     temporal（默认，「→」时序拼接，零 GPU 安全默认）/ longest（最长
     单条，baseline 参照）/ llm（ask_text 纯文本二次合并，结果写回
     cache merged_B 键，下次零 GPU）。
  5. 写保护：只填空缺 → 写前 Draft202012Validator(prompts.schema.json)
     自校验 → tmp + os.replace 原子写；本次运行零 facet 改动 → 完全
     不重写输出文件（保 byte-identical），warnings 为空且 sidecar 不
     存在 → 不创建 sidecar 文件。

ear 时序后果（pipeline 挂载位 5.6 在 step 7 audio_semantic 产出之前）：
ear 激活发生在 audio_semantic.json 就位后的第二次管线跑（5.6 在 step 7
之前）；ear 进 cache key，切换 ear 会重烧一次；想跳过重烧保持 --no-ear。

graceful-degrade：引擎不可用（ensure_ready 失败：VRAM 不足 / 启动超时 /
server.log 记录 load 失败）→ pending 镜 facet 保持 "" + [vision-seq]
warning + exit 0；--audio-semantic 文件缺席 → 自动无 ear 且零 warning
（v1.2 集没跑 audio 步是常态，静默 degrade）；per-shot 引擎异常 → 该镜
该 facet warning + continue，不阻塞其余镜。

引擎生命周期（防 13.4GB 泄漏 + cache 覆盖预判）：main() 先做 per-shot
预判 —— pending（空缺 facet 且本 ear 信封有缺失 RAW 键）非空才实例化
QwenEye 并 try/finally 包 ensure_ready…stop_if_owned；全 cache 命中时
完全不进入引擎生命周期（QwenEye 零实例化，重跑秒级）。

cache（mirror WR-04 4-tuple 惯例 + ear 第 5 维）：_cache_key =
{video_content_hash, engine_name, engine_version, prompt_version, ear}
—— 任一不匹配即 miss 重拉；查找只读本 ear 信封，写入 read-merge-write
只更新本 ear 信封（ear on/off 双跑证据共存，切换不丢数据）。

输出：
  1. prompts.json —— 读入现有文件（step 5 产物），只改 action/camera
     两键，其余 facets + character_refs/prop_refs/prompt_text 原样保留
     （additive），写前 schema 自校验 + 原子写。
  2. route_cache/vision_seq/shot_XXX.json —— 双信封 RAW 答案缓存。
  3. route_cache/warnings.json —— READ-merge-write sidecar（strip 本
     step 上一轮的 [vision-seq] 条目防 self-accumulate，他 step 条目保留）。

用法（被 run_pipeline.py 以 subprocess 调用）：
  python3 analysis/vision_seq_facets.py \
      --shots /abs/path/to/shots.json \
      --frames-dir /abs/path/to/frames_5fps \
      --work-dir output/<video-stem>/ \
      --output output/<video-stem>/prompts.json \
      --video /abs/path/to/video.mp4 \
      [--audio-semantic /abs/path/to/audio_semantic.json] [--no-ear] \
      [--merge-strategy {temporal,llm,longest}]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

# 引擎客户端是同仓 sibling 包模块（engine_clients/ 无 __init__.py —— 直接
# sys.path 注入其目录 import，mirror 上游「stage 脚本互相不 import，例外：
# 本文件独占拥有这个复制来的客户端」约定）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_clients.qwen_eye_client import (  # noqa: E402
    ENGINE_NAME,
    ENGINE_VERSION,
    QwenEye,
)

# ─── 模块级常量 ─────────────────────────────────────────────────────────────
# cache key 组成部分。PROMPT_VERSION 是 cache-invalidation 旋钮 —— ACTION_PROMPT/
# CAMERA_PAIR_PROMPT 文案变了就 bump 此串 → 全部 cache miss（mirror ROUTE_VERSION 惯例）。
CACHE_NAME = "vision_seq"
# v1 → v2（19-REVIEW CR-01）：时窗下界 floor→ceil 修正改变了帧号→图像的映射
# （RAW cache 键 action_frame_N 按帧号索引），旧 cache 的答案是按偏移窗口烧的
# —— bump 使全部 cache miss 重烧（设计行为；spike 实录约 15min/集）。
PROMPT_VERSION = "vision-seq-v2"

# frames_5fps 抽帧频率（run_pipeline --sample-fps 默认 5.0；detect_v3b 同值）。
# 帧文件名 f%06d.jpg 从 1 起编号：f000001.jpg ≈ t=0s，f000N.jpg ≈ (N-1)/fps。
FRAME_SAMPLING_FPS = 5.0

# 每镜最多均匀采样的帧数（v2 序列问答；q3 ctx=16K 单 slot —— 控制单镜调用量：
# action ≤8 次逐帧问 + camera ≤7 次相邻对问）。v1 scene/subject 路径的
# 3 帧上限常量属另一模块，与本常量互不影响。
MAX_SEQ_FRAMES_PER_SHOT = 8

# 引擎身份写进 warnings —— 便于追溯哪个引擎/版本产的 facet（与 v1 的
# [vision] 前缀区分开）。
STEP_TAG = "[vision-seq]"

# 合并策略默认值 —— temporal 是零 GPU 安全默认（纯归约，不依赖引擎存活）。
MERGE_STRATEGY_DEFAULT = "temporal"

ACTION_PROMPT = (
    "请用一句简洁中文描述这一帧画面中正在发生的动作：人物在做什么、肢体动作与交互、"
    "动作进行到哪一步。只输出动作描述本身，不要描述场景环境，不要描述镜头运动，"
    "不要编号或前缀。"
)

CAMERA_PAIR_PROMPT = (
    "这两帧是同一镜头中相邻的两帧（第1帧在前、第2帧在后）。请用一句简洁中文描述："
    "相对第1帧，第2帧的镜头怎么运动了（推、拉、摇、移、升降、跟随）或画面主体怎么位移、"
    "景别怎么变化。只输出运镜与相对变化描述本身，不要编号或前缀。"
)

# 策略 B（--merge-strategy llm）二次合并的提问模板：输入 = 编号的逐帧/逐对
# 答案清单，输出 = 一条连贯中文描述。纯文本调用无图 = 豁免多图丢弃 bug。
MERGE_B_PROMPT = (
    "以下是同一镜头中按时间顺序逐条采集的视觉观察答案（编号顺序即时间顺序）：\n{items}\n"
    "请把它们合并成一条连贯的中文描述，保留时序与因果结构，合并重复信息。"
    "只输出合并后的描述本身，不要编号或前缀。"
)

# prompts.schema.json 绝对路径（写前 Draft202012Validator 自校验用）。
# analysis/vision_seq_facets.py → repo root/spec/schemas/prompts.schema.json
PROMPTS_SCHEMA = Path(__file__).resolve().parent.parent / "spec" / "schemas" / "prompts.schema.json"


def video_content_hash(video_path: str) -> str:
    """sha256(first_1MB + last_1MB + str(filesize))[:16] —— mirror
    call_shot_analysis.py:91-108（multi-GB 视频毫秒级、确定性 cache key）。"""
    size = os.path.getsize(video_path)
    h = hashlib.sha256()
    with open(video_path, "rb") as f:
        h.update(f.read(1024 * 1024))                    # head 1MB
        if size > 2 * 1024 * 1024:
            f.seek(-1024 * 1024, os.SEEK_END)            # 跳到尾部前 1MB
            h.update(f.read(1024 * 1024))                # tail 1MB
    h.update(str(size).encode())                         # 文件大小参与 hash
    return h.hexdigest()[:16]


def _frame_number(path: Path) -> int:
    """f000123.jpg → 123。文件名不合式（防御）→ -1（永不落进任何时窗）。"""
    digits = path.stem.lstrip("f")
    try:
        return int(digits)
    except ValueError:
        return -1


def select_uniform_frames(frames_dir: str, start_sec: float, end_sec: float,
                          max_frames: int = MAX_SEQ_FRAMES_PER_SHOT) -> list[Path]:
    """取该镜时窗 [start_sec, end_sec] 内均匀间隔的 ≤max_frames 帧。

    frames_5fps 的命名是 f%06d.jpg、编号从 1 起（detect_v3b.sample_frames），
    第 N 帧的时间戳 ≈ (N-1)/FRAME_SAMPLING_FPS。窗口内帧数 ≤ max_frames
    全取；否则均匀索引 round(i*(len-1)/(max_frames-1)) —— 首尾帧恒在列
    （时序覆盖完整）。0 帧 → 空列表（调用方 degrade）。忽略 `*_ds1280.jpg`
    变体帧（dissolve 扫描的旁路产物，非等间隔采样序列）。
    """
    all_frames = sorted(
        p for p in Path(frames_dir).glob("f[0-9]*.jpg")
        if "_ds" not in p.stem
    )
    # CR-01（19-REVIEW）：帧 N 时间戳 = (N-1)/fps，首个 t ≥ start 的帧号是
    # ceil(start*fps)+1 —— int() floor 会把 start*fps 非整数时窗前的最后一帧
    # （通常是上一镜的硬切尾帧）拉进证据链。ceil 对网格对齐边界（整数
    # start*fps）与旧行为完全一致。hi 用 floor 不变（inclusive-safe 侧）。
    lo = math.ceil(start_sec * FRAME_SAMPLING_FPS) + 1   # 首个 t≥start 的帧号
    hi = int(end_sec * FRAME_SAMPLING_FPS) + 1       # 最后一个 ≤ end 的帧号上界
    window = [p for p in all_frames
              if lo <= _frame_number(p) <= hi]
    if not window:
        return []
    if len(window) <= max_frames:
        return window
    # 均匀索引（去重集合防 round 碰撞；排序保时序；首尾索引 0/len-1 恒在）。
    idx = {round(i * (len(window) - 1) / (max_frames - 1))
           for i in range(max_frames)}
    return [window[i] for i in sorted(idx)]


def _clean_answer(text: str) -> str:
    """引擎回答 → facet 文本：去首尾空白 + 去包裹引号；空/纯标点 → ""。"""
    t = (text or "").strip().strip('"').strip("'").strip()
    return t.strip("。；;.,、").strip() if t.strip("。；;.,、") else ""


def _read_existing_warnings(sidecar: str) -> list[str]:
    """读现有 warnings sidecar（他 step 可能已写入）。
    损坏/缺席 → []（不阻塞本步骤）。"""
    if not os.path.exists(sidecar):
        return []
    try:
        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict) and isinstance(data.get("warnings"), list):
        return [w for w in data["warnings"] if isinstance(w, str)]
    return []


def _cache_key(vch: str, ear: bool) -> dict:
    """5 字段 cache key（4-tuple 惯例 + ear 第 5 维，CONTEXT 锁定：
    ear on/off 进 cache key —— 切换 ear 即整体 miss 重拉）。"""
    return {
        "video_content_hash": vch,
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "ear": ear,
    }


def _envelope_name(ear: bool) -> str:
    """cache 文件内的信封键名 —— ear on/off 双信封共存于同一 shot_XXX.json。"""
    return "ear_on" if ear else "ear_off"


def _fresh_envelope(key: dict) -> dict:
    return {"_cache_key": key, "answers": {}}


def _load_cache_envelope(cache_file: str, ear: bool, key: dict) -> dict:
    """读本 ear 信封。文件缺失 / 损坏 / 文件非 dict / 信封缺席 /
    _cache_key 任一字段不匹配 → 全新空信封（miss 重拉）。
    他 ear 信封绝不被本函数触碰。"""
    miss = _fresh_envelope(key)
    if not os.path.exists(cache_file):
        return miss
    try:
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return miss
    if not isinstance(data, dict):
        return miss
    env = data.get(_envelope_name(ear))
    if not isinstance(env, dict) or env.get("_cache_key") != key:
        return miss
    if not isinstance(env.get("answers"), dict):
        env["answers"] = {}
    return env


def _save_cache_envelope(cache_file: str, ear: bool, key: dict,
                         new_answers: dict | None = None,
                         merged_b: dict | None = None) -> None:
    """read-merge-write 只更新本 ear 信封（他 ear 信封原样保留 —— ear on/off
    双跑证据共存，切换不丢数据）。cache 目录懒创建（零写入时连目录都不留）。
    best-effort：写失败不阻塞，下次重拉即可。"""
    data: dict = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}
    name = _envelope_name(ear)
    env = data.get(name)
    if not isinstance(env, dict) or env.get("_cache_key") != key:
        env = _fresh_envelope(key)
    answers = env.get("answers") if isinstance(env.get("answers"), dict) else {}
    if new_answers:
        answers.update(new_answers)
    env["answers"] = answers
    if merged_b:
        mb = env.get("merged_B") if isinstance(env.get("merged_B"), dict) else {}
        mb.update(merged_b)
        env["merged_B"] = mb
    data[name] = env
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        tmp = cache_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, cache_file)
    except OSError:
        pass   # cache 写失败不阻塞 —— 下次重拉即可


def build_audio_context(shot_audio: dict, max_text: int = 200) -> str:
    """ear 白名单提取：dialogue.text（截断 max_text 字）+ dialogue.emotion +
    sfx.events + sfx.description。缺字段/类型错一律跳过该字段（V5 语义：
    不信任模型输出 shape）；word-level timestamps / reproduction 层 /
    spk_id / speakers 永不进（实验性/复现 prompt 非感知证据/身份归 re-id）。"""
    if not isinstance(shot_audio, dict):
        return ""
    parts: list[str] = []
    d = shot_audio.get("dialogue")
    d = d if isinstance(d, dict) else {}
    text = d.get("text")
    if isinstance(text, str) and text:
        emo = d.get("emotion")
        emo = emo if isinstance(emo, str) and emo else None
        parts.append(f"对白「{text[:max_text]}」"
                     + (f"（情绪:{emo}）" if emo else ""))
    sfx = shot_audio.get("sfx")
    sfx = sfx if isinstance(sfx, dict) else {}
    events = sfx.get("events")
    if isinstance(events, list) and events:
        ev = [e for e in events if isinstance(e, str) and e]
        desc = sfx.get("description")
        desc = desc if isinstance(desc, str) else ""
        if ev:
            parts.append(f"音效:{'/'.join(ev)} {desc}".strip())
    return "；".join(parts)


def _ear_question(base_prompt: str, audio_ctx: str) -> str:
    """ear 开且该镜有音频上下文 → 「该镜音频：…。{基础提问}」（生成时注入）；
    无上下文 → 原提问原样。"""
    if audio_ctx:
        return f"该镜音频：{audio_ctx}。{base_prompt}"
    return base_prompt


def _facet_key(facet: str, i: int) -> str:
    """RAW 答案键名：action_frame_N（逐帧）/ camera_pair_M（相邻对）。"""
    return f"action_frame_{i}" if facet == "action" else f"camera_pair_{i}"


def _needed_count(facet: str, n_frames: int) -> int:
    """该 facet 需要的 RAW 答案键数：action = 帧数；camera = 帧数 - 1（对数）。"""
    return n_frames if facet == "action" else n_frames - 1


def _facet_answer_values(env: dict, facet: str) -> list[str]:
    """从信封 answers 提取该 facet 的非空 RAW 答案，按帧序/对序排序。"""
    prefix = "action_frame_" if facet == "action" else "camera_pair_"
    answers = env.get("answers") if isinstance(env.get("answers"), dict) else {}
    items: list[tuple[int, str]] = []
    for k, v in answers.items():
        if not (isinstance(k, str) and k.startswith(prefix)):
            continue
        if not (isinstance(v, str) and v):
            continue
        try:
            idx = int(k[len(prefix):])
        except ValueError:
            continue
        items.append((idx, v))
    items.sort()
    return [v for _, v in items]


def merge_answers(values: list[str], strategy: str) -> str:
    """确定性纯归约（零引擎调用）：temporal = 按帧序/对序以「→」join 非空
    答案；longest = 取最长单条（baseline 参照）。llm 策略不在此层 ——
    需引擎 ask_text 二次合并（见 _merge_llm_pass）。"""
    if not values:
        return ""
    if strategy == "longest":
        return max(values, key=len)
    return "→".join(values)


def _ask_raw_answers(engine, item: dict, audio_ctx: str) -> tuple[dict, str | None]:
    """补齐 item 缺失的 RAW 答案键。action 逐帧 observe_single；camera 相邻
    对 observe_pair。每个成功答案增量落盘（断点续跑：spike/全量可能被中断，
    已答帧绝不重烧）。返回 (fresh_answers, None) 或 (partial, err_msg) ——
    引擎异常即中断该 facet（mirror v1 per-shot degrade 语义）。"""
    facet = item["facet"]
    base = ACTION_PROMPT if facet == "action" else CAMERA_PAIR_PROMPT
    question = _ear_question(base, audio_ctx)
    frames = item["frames"]
    fresh: dict = {}
    for i in item["missing"]:
        try:
            if facet == "action":
                raw = engine.observe_single(frames[i - 1], question)
            else:
                raw = engine.observe_pair(frames[i - 1], frames[i], question)
        except (RuntimeError, OSError) as e:
            return fresh, f"engine call failed: {e}"
        ans = _clean_answer(raw)
        k = _facet_key(facet, i)
        fresh[k] = ans
        _save_cache_envelope(item["cache_file"], item["ear"], item["key"],
                             new_answers={k: ans})
    return fresh, None


def _ask_merge_b(engine, values: list[str]) -> tuple[str, str | None]:
    """策略 B：纯文本 ask_text 二次合并（无图 = 豁免多图丢弃 bug）。"""
    lines = "\n".join(f"{i}. {v}" for i, v in enumerate(values, 1))
    try:
        raw = engine.ask_text(MERGE_B_PROMPT.format(items=lines))
    except (RuntimeError, OSError) as e:
        return "", f"merge call failed: {e}"
    ans = _clean_answer(raw)
    if not ans:
        return "", "merge returned empty answer"
    return ans, None


def _merge_llm_pass(engine, work: list[dict], warnings: list[str]) -> None:
    """策略 B 合并轮：对 RAW 证据完整且 merged_B 未缓存的 facet 做 ask_text
    二次合并，结果写回 cache（下次零 GPU）。失败的 facet degrade（warning
    + 本轮不产出），不影响其余。"""
    for item in work:
        if item["error"] or item["missing"]:
            continue
        mb = item["env"].get("merged_B")
        if isinstance(mb, dict) and mb.get(item["facet"]):
            continue   # 已缓存 —— 零 GPU
        values = _facet_answer_values(item["env"], item["facet"])
        if not values:
            continue
        merged, err = _ask_merge_b(engine, values)
        if err:
            warnings.append(f"{STEP_TAG} shot {item['sid']}: "
                            f"{item['facet']}: {err}")
            continue
        _save_cache_envelope(item["cache_file"], item["ear"], item["key"],
                             merged_b={item["facet"]: merged})
        item["env"].setdefault("merged_B", {})[item["facet"]] = merged


def main():
    ap = argparse.ArgumentParser(
        description="qwen-eye v2 帧序列逐帧问答填充 prompts.json 的 action/camera facets")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径（含 id/start_sec/end_sec —— 时窗选帧用）")
    ap.add_argument("--frames-dir", required=True,
                    help="frames_5fps/ 目录（step 2 产物，f%%06d.jpg 等间隔采样帧）"
                    )   # %% 转义：argparse help 走 % 格式化，裸 % 会崩 --help
    ap.add_argument("--work-dir", required=True,
                    help="资产根目录（output/<video-stem>/）—— route_cache 写在其下")
    ap.add_argument("--output", required=True,
                    help="prompts.json 路径（读入现有 → 只改 action/camera → 原子写回）")
    ap.add_argument("--video", default=None,
                    help="原始视频路径（cache key 的 video_content_hash 用；"
                         "缺席 → 'unknown'（cache 仍可用，仅跨视频不失效））")
    ap.add_argument("--audio-semantic", default=None,
                    help="audio_semantic.json 路径（v1.2 step 7 产物）；在位且"
                         "未 --no-ear 时 ear 默认开；文件缺席自动无 ear（零 warning）")
    ap.add_argument("--no-ear", action="store_true",
                    help="显式关闭 ear 音频上下文注入（cache 随之切到 ear_off 信封）")
    ap.add_argument("--merge-strategy",
                    choices=["temporal", "llm", "longest"],
                    default=MERGE_STRATEGY_DEFAULT,
                    help="RAW 答案合并策略（默认 temporal —— 零 GPU 安全默认；"
                         "llm 需引擎纯文本二次合并；longest 为 baseline 参照）")
    args = ap.parse_args()

    warnings: list[str] = []

    # 1. ear 输入解析：--no-ear 显式关；--audio-semantic 文件缺席 = 自动无
    #    ear 且零 warning（CONTEXT 锁定，静默 degrade）；文件损坏 = warning + 无 ear。
    ear = False
    audio_by_shot: dict = {}
    if not args.no_ear and args.audio_semantic:
        if os.path.exists(args.audio_semantic):
            try:
                with open(args.audio_semantic, encoding="utf-8") as f:
                    adata = json.load(f)
                shots_audio = adata.get("shots") if isinstance(adata, dict) else None
                if isinstance(shots_audio, list):
                    audio_by_shot = {s.get("shot_id"): s for s in shots_audio
                                     if isinstance(s, dict)}
                    ear = True
                else:
                    warnings.append(f"{STEP_TAG} audio_semantic.json has no "
                                    f"shots[] — ear disabled")
            except (OSError, json.JSONDecodeError) as e:
                warnings.append(f"{STEP_TAG} audio_semantic.json unreadable "
                                f"({e}) — ear disabled")
        # 文件缺席：ear 保持 False，零 warning —— v1.2 集没跑 audio 步是常态。

    # 2. 载入现有 prompts.json（step 5 产物）+ shots 元数据 + cache key
    if not os.path.exists(args.output):
        sys.exit(f"{STEP_TAG} input prompts.json not found: {args.output} "
                 f"(step 5 must run first — 本步骤是 additive 填充，不从零生成)")
    with open(args.output, encoding="utf-8") as f:
        prompts = json.load(f)
    with open(args.shots, encoding="utf-8") as f:
        shots_meta = json.load(f)
    vch = (video_content_hash(args.video)
           if args.video and os.path.exists(args.video) else "unknown")

    # 3. cache 目录（懒创建）+ warnings sidecar READ + 本 ear 的 cache key
    cache_dir = os.path.join(args.work_dir, "route_cache", CACHE_NAME)
    warnings_sidecar = os.path.join(args.work_dir, "route_cache", "warnings.json")
    existing_warnings = _read_existing_warnings(warnings_sidecar)
    key = _cache_key(vch, ear)

    # 4. per-shot 预判（cache 覆盖预判，SC4）：对每个空缺 facet 算出本 ear
    #    信封中已有/缺失的 RAW 答案键。pending（缺失键）非空才进入引擎生命
    #    周期 —— 全 cache 命中时 QwenEye 从未被实例化。
    by_id = {s["id"]: s for s in shots_meta}
    work: list[dict] = []
    needs_engine = False
    done = 0
    for p in prompts:
        sid = p.get("shot_id")
        meta = by_id.get(sid)
        if meta is None:
            continue
        frames = select_uniform_frames(args.frames_dir,
                                       meta["start_sec"], meta["end_sec"])
        if not frames:
            warnings.append(
                f"{STEP_TAG} shot {sid}: no frames in window "
                f"[{meta['start_sec']:.2f}, {meta['end_sec']:.2f}] — "
                f"facets left as-is")
            continue
        cache_file = os.path.join(cache_dir, f"shot_{sid:03d}.json")
        env = _load_cache_envelope(cache_file, ear, key)
        for facet in ("action", "camera"):
            if p.get(facet):
                continue   # 已有值（route/人工产物）—— 不覆盖，永不替换
            if facet == "camera" and len(frames) < 2:
                warnings.append(
                    f"{STEP_TAG} shot {sid}: only 1 frame in window — "
                    f"camera pair question impossible, left as-is")
                continue
            needed = _needed_count(facet, len(frames))
            missing = [i for i in range(1, needed + 1)
                       if _facet_key(facet, i) not in env["answers"]]
            work.append({"p": p, "sid": sid, "facet": facet, "frames": frames,
                         "cache_file": cache_file, "env": env, "ear": ear,
                         "key": key, "missing": missing, "error": False})
            if missing:
                needs_engine = True
        done += 1
        if (done % 10) == 0:
            print(f"[vision-seq] {done}/{len(prompts)} shots processed")

    # llm 合并需求并入预判：merged_B 未缓存 → 需要引擎（ask_text）。
    if args.merge_strategy == "llm":
        for item in work:
            mb = item["env"].get("merged_B")
            if not (isinstance(mb, dict) and mb.get(item["facet"])):
                needs_engine = True

    filled = {"action": 0, "camera": 0}

    # 5. 引擎生命周期：仅 needs_engine 时实例化；try/finally 包
    #    ensure_ready…stop_if_owned —— 崩溃也不泄漏 13.4GB。
    if needs_engine:
        engine = QwenEye()
        try:
            healthy, _owned = engine.ensure_ready()
            if not healthy:
                # graceful-degrade：pending facet 保持原值（通常 ""），
                # 显式 warning，exit 0。
                warnings.append(
                    f"{STEP_TAG} engine unavailable "
                    f"(ensure_ready failed: VRAM/startup) — "
                    f"pending action/camera facets left as-is")
                print(f"[vision-seq] engine unavailable — degrading")
            else:
                for item in work:
                    if not item["missing"]:
                        continue
                    audio_ctx = (build_audio_context(audio_by_shot.get(item["sid"]) or {})
                                 if ear else "")
                    fresh, err = _ask_raw_answers(engine, item, audio_ctx)
                    if fresh:
                        item["env"].setdefault("answers", {}).update(fresh)
                        item["missing"] = [i for i in item["missing"]
                                           if _facet_key(item["facet"], i) not in fresh]
                    if err:
                        item["error"] = True
                        warnings.append(f"{STEP_TAG} shot {item['sid']}: "
                                        f"{item['facet']}: {err}")
                        continue   # 该镜该 facet degrade，不阻塞其余
                if args.merge_strategy == "llm":
                    _merge_llm_pass(engine, work, warnings)
        finally:
            engine.stop_if_owned()

    # 6. 合并 + 应用（写出时执行）：RAW 证据完整的 facet 才产出；只填空缺
    #    （已有值在预判阶段已 continue）。temporal/longest 纯归约；llm 用
    #    merged_B（缓存或本轮引擎合并）。
    changed = False
    for item in work:
        if item["error"] or item["missing"]:
            continue   # RAW 证据不完整（degrade / 中断）—— 本轮不产出
        values = _facet_answer_values(item["env"], item["facet"])
        if not values:
            warnings.append(f"{STEP_TAG} shot {item['sid']}: {item['facet']}: "
                            f"engine returned empty answers for all frames/pairs")
            continue
        if args.merge_strategy == "llm":
            mb = item["env"].get("merged_B")
            value = mb.get(item["facet"]) if isinstance(mb, dict) else ""
            value = value or ""
        else:
            value = merge_answers(values, args.merge_strategy)
        if value:
            item["p"][item["facet"]] = value
            changed = True
            filled[item["facet"]] += 1

    # 7. 写出保护：零 facet 改动 → 完全不重写输出文件（保 byte-identical）。
    if changed:
        from jsonschema import Draft202012Validator
        with open(PROMPTS_SCHEMA, encoding="utf-8") as f:
            prompts_schema = json.load(f)
        errors = list(Draft202012Validator(prompts_schema).iter_errors(prompts))
        if errors:
            sys.exit(
                f"prompts.json schema validation failed ({len(errors)} errors): "
                + "; ".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
                            for e in errors[:3]))
        tmp = args.output + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
        os.replace(tmp, args.output)

    # 8. warnings sidecar —— READ-merge-write：strip 本 step 上一轮的
    #    [vision-seq] 条目再 append fresh（防 self-accumulate）；他 step 的
    #    warnings 保留（cross-step 非破坏性合并）。warnings 为空且 sidecar
    #    不存在 → 不创建 sidecar 文件。
    if warnings or os.path.exists(warnings_sidecar):
        prior = [w for w in existing_warnings if not w.startswith(STEP_TAG)]
        os.makedirs(os.path.dirname(warnings_sidecar), exist_ok=True)
        with open(warnings_sidecar, "w", encoding="utf-8") as f:
            json.dump({"warnings": prior + warnings}, f, ensure_ascii=False, indent=2)

    if changed:
        print(f"[vision-seq] wrote {args.output} "
              f"(action filled: {filled['action']}, "
              f"camera filled: {filled['camera']}, "
              f"strategy: {args.merge_strategy}, ear: {'on' if ear else 'off'}, "
              f"{len(warnings)} new warnings)")
    else:
        print(f"[vision-seq] {args.output} unchanged "
              f"(zero facets modified — output not rewritten; "
              f"ear: {'on' if ear else 'off'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
