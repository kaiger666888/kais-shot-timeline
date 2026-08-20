#!/usr/bin/env python3
"""html/gen_roundtrip_review.py — round-trip HITL 审阅 HTML 生成器（PRESENT-01）。

把 analysis/roundtrip 三件套（h3_regen / scorer / judge）产出的 roundtrip.json
渲染成 self-contained monolithic HTML：per-shot 双 <video> 并排（左 = 原片 Media
Fragments 时窗裁切 / 右 = regen mp4 相对路径）+ sim bar（τ 1px 虚线 tick）+
归因色块 badge + judge reason + prompt 快照折叠 + 三态覆盖按钮
（✓ Accept / ✗ Reject / ⟲ 维持 auto）+ τ 边界排序审阅队列 + Export edits 下载
（roundtrip-edits.json，confirmed-only apply CLI 在 22-02 落地）。

mirror html/gen_registry_review.py 全套先例：sticky header / 240px sticky queue /
sticky export bar 四件套 + GitHub-dark palette + 原子写 + 收尾打印。与 registry
review 的唯一形态差异：卡片区单列（max-width 1200px——双 16:9 视频需要整行宽度）
且外部资源是 2 个 <video> src 相对路径（经 scripts/serve.py Range 服务）而非
base64 缩略图 inline。

XSS 三层 hardening（SC3 / 22-UI-SPEC §XSS Hardening 强制清单）：
  1. 内联 _esc() 5 字符转义（& 先）覆盖每一个进入 HTML 的动态字符串：
     judge.reason / attribution（enum 也转，defense-in-depth）/
     verdict.decision+source+decided_at / status.error / midframe_sim.model /
     regen.prompt_version+engine_version（prompt 折叠 summary 尾注；engine_name
     不渲染——UI-SPEC 映射表未含该行，引擎名进 dataset prompt.json 而非本
     面板）/ prompt_text + 全部六 facet /
     character_refs+prop_refs / asset_name / regen.path；数字经 _esc 内 str() 兜底。
  2. JSON-in-<script> bootstrap：json.dumps(...).replace("</", "<\\/") 防
     </script> 序列从 script 岛破出（registry/speaker 双先例原样）。
  3. JS 动态更新（按钮态/计数/queue ✓ 前缀/video 失败占位）一律
     classList / textContent，零 innerHTML。

⚠ _esc 必须内联在本文件——html/ 是 namespace package（无 __init__.py），
  禁跨文件 import（gen_registry_review.py docstring 明文惯例）。

操作流程（HITL 硬门语义 mirror registry/speaker）：
  1. step_roundtrip 产出 roundtrip.json（缺席/空 → 本脚本仍产空态面板）
  2. 操作员浏览器审阅（scripts/serve.py Range 服务双 video src）
  3. 三态覆盖 → 📥 Export edits → 下载 roundtrip-edits.json
     （维持 auto 不进 edits；与 auto 同向的显式覆盖照导——apply 后 source 变
      human，防未来重打分翻案）
  4. 操作员手动跑 apply CLI（confirmed-only）写回 sidecar——面板永不写 sidecar

用法：
    python3 html/gen_roundtrip_review.py \\
        --roundtrip <roundtrip.json>  (必填 — sidecar；缺席 swallow-to-empty 空态) \\
        --video     <原视频>          (必填 — 左 video src 基准，relpath 到输出目录) \\
        --shots     <shots.json>      (必填 — id → start/end_sec 时窗解析) \\
        --prompts   <prompts.json>    (必填 — prompt 快照源，按 shot_id 对齐) \\
        --tau-sim   <τ>               (可选 — 默认 0.9670，Phase 21 Kai 裁决值) \\
        --output    <HTML 输出路径>   (必填)
"""
import argparse
import json
import os
import sys
from pathlib import Path

# ============================================================================
# Module-level constants
# ============================================================================

# 归因三色（22-UI-SPEC Color 节语义色映射 —— 复用 registry review TIER_COLORS
# 原班 green/yellow/grey hex，操作员跨面板零重学）
ATTR_COLORS = {
    "prompt_faithful":       "#3fb950",  # green
    "model_diverged":        "#d29922",  # yellow
    "prompt_underspecified": "#8b949e",  # grey
}

COLOR_GREY = "#8b949e"   # pending / muted / 缺席归因兜底
COLOR_GREEN = "#3fb950"  # verdict accepted
COLOR_RED = "#f85149"    # verdict rejected / 降级卡红边

# τ_sim 默认值（Phase 21 Kai 裁决锁定值，PROJECT.md Key Decisions v1.3 Phase 21 行）
TAU_SIM_DEFAULT = 0.9670

# prompt 快照六 facet（prompts.json 平铺键——非嵌套 facets 对象）
FACET_KEYS = ["subject", "action", "camera", "scene", "lighting", "style"]

# video 加载失败占位文案（22-UI-SPEC Copywriting 表 Error state 行，逐字）
VIDEO_ERROR_TEXT = (
    "⚠ 视频加载失败 — 确认 scripts/serve.py 正在服务本目录（默认 :8765）"
    "且 regen mp4 未被移动。"
)


# ============================================================================
# Helpers（_esc 必须内联——html/ 是 namespace package，禁跨文件 import）
# ============================================================================

def _esc(s):
    """HTML-escape 字符串以安全插值进 HTML text/attribute context（SC3 第 1 层）。

    转义 5 个字符: & < > " '。顺序固定 (& 先，防双重转义)。
    Self-contained inline impl（不走 stdlib html.escape）—— 本仓库 html/ 目录
    是 namespace package，避免任何 import-resolution 歧义；符合 standalone-script
    约定（mirror gen_registry_review.py:79-91 逐字）。
    输入先 str() 兜底（非 string 字段如 int shot_id / float score 也安全）。
    """
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;")
                  .replace("'", "&#x27;"))


def _load_json(path, default):
    """读 JSON 文件；缺席/坏文件 → default（swallow-to-empty——空态面板仍可生成）。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _shot_id(shot):
    """sidecar 条目 shot_id → int（schema 锁 integer；defensive 兜底 0）。"""
    try:
        return int(shot.get("shot_id", 0))
    except (TypeError, ValueError):
        return 0


def _queue_sort_key(shot, tau):
    """审阅队列排序 key（UI-SPEC §Interaction 4「最难决定先审」）。

    sort key = (verdict/scores 缺失 ? 0 : 1, |midframe_sim − τ| 升序, shot_id 升序)
    —— 信息不全（未打分/未裁决）的最先；其余按 τ 边界距离升序（边界镜最需要
    人眼）；同距按 id。缺 sim 的条目距离记 1.0（组内沉底，确定性）。
    """
    scores = shot.get("scores") or {}
    sim = (scores.get("midframe_sim") or {}).get("score")
    missing = (not scores) or (shot.get("verdict") is None)
    try:
        dist = abs(float(sim) - tau) if sim is not None else 1.0
    except (TypeError, ValueError):
        dist = 1.0
    return (0 if missing else 1, dist, _shot_id(shot))


def _index_by(entries, key):
    """list[dict] → {key值: dict} 索引（shots.json 按 id / prompts.json 按 shot_id）。"""
    idx = {}
    if isinstance(entries, list):
        for e in entries:
            if isinstance(e, dict) and key in e:
                idx[e.get(key)] = e
    return idx


def _refs_text(prompt, key):
    """character_refs / prop_refs → mono 逗号列表；缺席/空 → (无)（UI-SPEC §6）。"""
    refs = (prompt or {}).get(key)
    if isinstance(refs, list) and refs:
        return ", ".join(str(r) for r in refs)
    return "(无)"


# ============================================================================
# Per-shot card + queue item rendering
# ============================================================================

def _shot_card_html(shot, prompt, meta, video_src_base, tau):
    """渲染单张 per-shot 审阅卡。

    Args:
        shot:          dict —— roundtrip.json shots[] 条目。
        prompt:        dict|None —— prompts.json 对齐条目（缺席 → 快照区 (无)）。
        meta:          dict|None —— shots.json 对齐条目（id → start/end_sec）。
        video_src_base: str —— 原视频相对输出目录的路径（左 video src 基准）。
        tau:           float —— τ_sim（sim bar 虚线 tick 位置）。

    降级卡（status{state:"failed"}）：红边 + ⚠ regen 失败 — {error}，无
    video/分数/verdict 行；三态按钮保留（human 覆盖是这类卡拿到 verdict 的
    唯一路径——UI-SPEC §Interaction 2 明文）。
    """
    sid = _shot_id(shot)
    label = f"shot_{sid:03d}"
    esc_label = _esc(label)
    regen = shot.get("regen") or {}
    status = shot.get("status") or {}
    scores = shot.get("scores") or {}
    sim_obj = scores.get("midframe_sim") or {}
    judge = scores.get("judge") or {}
    verdict = shot.get("verdict") or {}
    failed = bool(status)

    start = float((meta or {}).get("start_sec", 0.0) or 0.0)
    end = float((meta or {}).get("end_sec", start) or start)
    orig_dur = max(0.0, end - start)

    # ---- card header：shot_NNN（accent）+ verdict badge + 归因色块 ----
    header_bits = [f'<span class="shot-id">{esc_label}</span>']
    if verdict:
        dec = verdict.get("decision", "")
        src = verdict.get("source", "")
        vcls = "verdict-badge accepted" if dec == "accepted" else "verdict-badge rejected"
        # human 时 title 提示 decided_at（UI-SPEC 数据→UI 映射表）；decided_at 也过 _esc
        title_attr = (f' title="{_esc(verdict.get("decided_at", ""))}"'
                      if src == "human" else "")
        header_bits.append(
            f'<span class="{vcls}"{title_attr}>{_esc(dec)}·{_esc(src)}</span>')
    elif not failed:
        header_bits.append('<span class="pending-badge">未裁决</span>')
    if judge and not failed:
        attr = judge.get("attribution", "")
        header_bits.append(
            f'<span class="attr-badge" style="background:{ATTR_COLORS.get(attr, COLOR_GREY)}">'
            f'{_esc(attr)}</span>')

    parts = []

    # ---- 降级卡：⚠ regen 失败 — {error}（红边由 card-failed 类承担）----
    if failed:
        parts.append(f'      <div class="failed-line">⚠ regen 失败 — '
                     f'{_esc(status.get("error", ""))}</div>')

    # ---- 双 video 行 + 同步控件（regen 在场才有对比面）----
    if regen and not failed:
        regen_dur = regen.get("duration_sec")
        regen_chip = (f"⏱ {float(regen_dur):.1f}s"
                      if isinstance(regen_dur, (int, float)) else "⏱ —")
        left_src = f"{_esc(video_src_base)}#t={start:.3f},{end:.3f}"
        parts.append(f"""      <div class="video-row">
        <div class="video-col">
          <div class="video-topline"><span class="video-label">原始片段 (t={start:.1f}-{end:.1f}s)</span><span class="dur-chip">⏱ {orig_dur:.1f}s</span></div>
          <div class="video-well"><video class="sync-left" src="{left_src}" controls preload="metadata"></video></div>
        </div>
        <div class="video-col">
          <div class="video-topline"><span class="video-label">重生成 (regen)</span><span class="dur-chip">{_esc(regen_chip)}</span></div>
          <div class="video-well"><video class="sync-right" src="{_esc(regen.get("path", ""))}" controls preload="metadata"></video></div>
        </div>
      </div>
      <div class="sync-controls">
        <button class="sync-button sync-toggle" onclick="toggleSync({sid})">▶ 同步播放</button>
        <button class="sync-button" onclick="resetSync({sid})">⏮ 重置</button>
      </div>""")

        # ---- sim bar（τ tick）+ score 行；未打分 → 灰 badge ----
        if sim_obj:
            try:
                score = float(sim_obj.get("score", 0.0) or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            attr = judge.get("attribution", "")
            color = ATTR_COLORS.get(attr, COLOR_GREY)
            parts.append(f"""      <div class="sim-row">
        <div class="sim-bar-container"><div class="sim-bar" style="width:{max(0.0, min(1.0, score)) * 100.0:.2f}%; background:{color}"></div><div class="sim-tick" style="left:{tau * 100.0:.2f}%"></div></div>
        <span class="score-line">sim={score:.4f} · {_esc(sim_obj.get("model", ""))}</span>
      </div>""")
        else:
            parts.append('      <div class="sim-row"><span class="pending-badge">未打分</span></div>')

        # ---- judge 行：归因 · conf + reason（11px，长文 word-break）----
        if judge:
            conf = judge.get("confidence")
            conf_txt = (f"conf={float(conf):.2f}"
                        if isinstance(conf, (int, float)) and not isinstance(conf, bool)
                        else "conf=—")
            parts.append(f"""      <div class="judge-row">
        <span class="judge-meta">{_esc(judge.get("attribution", ""))} · <span class="mono">{conf_txt}</span></span>
        <p class="reason">{_esc(judge.get("reason", ""))}</p>
      </div>""")

    # ---- prompt 快照折叠（默认折叠；全部字符串过 _esc——route/模型产出文本）----
    # WR-04（22-REVIEW）：summary 尾注补 engine_version——22-UI-SPEC 数据→UI
    # 映射表行「regen.engine_version / prompt_version | prompt 快照 <summary>
    # 尾注」此前只实现了 prompt_version 半边；补齐后操作员不开 sidecar JSON
    # 即可审计各 regen 的引擎版本（regen 4-tuple 契约的审计目的）。
    prompt_ver = regen.get("prompt_version") if regen else None
    eng_ver = regen.get("engine_version") if regen else None
    tail_bits = []
    if prompt_ver:
        tail_bits.append(f"prompt v{_esc(prompt_ver)}")
    if eng_ver:
        tail_bits.append(_esc(eng_ver))
    summary_txt = (f"▸ Prompt 快照 ({' · '.join(tail_bits)})"
                   if tail_bits else "▸ Prompt 快照")
    facet_rows = "".join(
        f'<tr><td class="facet-key">{_esc(k)}</td>'
        f'<td class="facet-val">{_esc((prompt or {}).get(k) or "(无)")}</td></tr>'
        for k in FACET_KEYS)
    parts.append(f"""      <details class="prompt-fold">
        <summary>{summary_txt}</summary>
        <div class="prompt-body">
          <p class="prompt-text">{_esc((prompt or {}).get("prompt_text") or "(无)")}</p>
          <table class="facet-table">
{facet_rows}
          </table>
          <p class="refs-line mono">character_refs: {_esc(_refs_text(prompt, "character_refs"))} · prop_refs: {_esc(_refs_text(prompt, "prop_refs"))}</p>
        </div>
      </details>""")

    # ---- 三态覆盖按钮（14/600 档——产生 edit 动作的按钮；onclick 插值仅 int shot_id）----
    parts.append(f"""      <div class="card-actions">
        <button class="action-button action-accept" onclick="setState({sid}, 'accept')">✓ Accept</button>
        <button class="action-button action-reject" onclick="setState({sid}, 'reject')">✗ Reject</button>
        <button class="action-button action-auto" onclick="setState({sid}, 'auto')">⟲ 维持 auto</button>
      </div>""")

    card_cls = "shot-card card-failed" if failed else "shot-card"
    return (f'    <div class="{card_cls}" id="card-{esc_label}" data-shot-id="{sid}"\n'
            f'         data-start="{start:.3f}" data-end="{end:.3f}">\n'
            f'      <div class="card-header">{"".join(header_bits)}</div>\n'
            + "\n".join(parts) + "\n    </div>")


def _queue_item_html(shot):
    """渲染单个 queue 项：verdict 色条 + shot_NNN + 微型 sim bar + {sim:.3f}。

    ✓ 前缀占位 span（.queue-check —— anchor #q-shot_NNN 的首子节点）由 JS
    textContent 填充（零 innerHTML）。CR-01（22-REVIEW）：JS 只写这个专用
    span，绝不碰 anchor 其余子节点（topline / 微 sim bar）。
    """
    sid = _shot_id(shot)
    label = f"shot_{sid:03d}"
    esc_label = _esc(label)
    verdict = shot.get("verdict") or {}
    dec = verdict.get("decision")
    data_v = dec if dec in ("accepted", "rejected") else "none"
    sim = ((shot.get("scores") or {}).get("midframe_sim") or {}).get("score")
    if isinstance(sim, (int, float)) and not isinstance(sim, bool):
        attr = ((shot.get("scores") or {}).get("judge") or {}).get("attribution", "")
        color = ATTR_COLORS.get(attr, COLOR_GREY)
        bar = (f'<span class="queue-sim-bar" style="width:{max(0.0, min(1.0, float(sim))) * 100.0:.1f}%; '
               f'background:{color}"></span>')
        num = f"{float(sim):.3f}"
    else:
        bar = ""
        num = "—"
    return (f'    <a href="#card-{esc_label}" class="queue-item" data-verdict="{data_v}" id="q-{esc_label}">'
            f'<span class="queue-check"></span>'
            f'<span class="queue-topline"><span class="queue-id">{esc_label}</span>'
            f'<span class="queue-sim-num">{num}</span></span>{bar}</a>')


# ============================================================================
# HTML assembly
# ============================================================================

def build_html(shots, video_src_base, meta_idx, prompt_idx, asset_name, tau):
    """生成完整 self-contained HTML string（CSS/JS/data 全 inline）。

    Args:
        shots:          list[dict] —— roundtrip.json shots[]（原始序）。
        video_src_base: str —— 原视频相对输出目录路径。
        meta_idx:       dict —— shots.json 按 id 索引。
        prompt_idx:     dict —— prompts.json 按 shot_id 索引。
        asset_name:     str —— header 显示用 asset 名（work_dir 目录名）。
        tau:            float —— τ_sim。

    Returns:
        str —— 完整 HTML（外部资源仅 2 个 <video> src 相对路径）。
    """
    n = len(shots)
    n_accepted = sum(1 for s in shots
                     if (s.get("verdict") or {}).get("decision") == "accepted")
    n_rejected = sum(1 for s in shots
                     if (s.get("verdict") or {}).get("decision") == "rejected")
    n_human = sum(1 for s in shots
                  if (s.get("verdict") or {}).get("source") == "human")
    n_failed = sum(1 for s in shots if s.get("status"))

    # τ 边界排序（最难决定先审）—— 卡区与 queue 同序
    sorted_shots = sorted(shots, key=lambda s: _queue_sort_key(s, tau))

    cards_html = "\n".join(
        _shot_card_html(s, prompt_idx.get(_shot_id(s)),
                        meta_idx.get(_shot_id(s)), video_src_base, tau)
        for s in sorted_shots) if shots else (
        '    <div class="empty-state">\n'
        '      <p>(空 roundtrip —— 无 shot 可审阅)</p>\n'
        '      <p>先运行 step_roundtrip 产出 roundtrip.json，再运行 '
        'html/gen_roundtrip_review.py 生成审阅面板。空态下面板仍可生成'
        '（mirror 先例空态可跑）。</p>\n'
        '    </div>')
    queue_html = ("\n".join(_queue_item_html(s) for s in sorted_shots)
                  if shots else "    <p>(无)</p>")

    # SC3 第 2 层：JSON-in-<script> bootstrap 防 </script> 破出
    # （HTML 解析器见 </script> 即终止 script block，无视 JS string context）
    rt_json = json.dumps(shots, ensure_ascii=False).replace("</", "<\\/")
    # video 失败占位文案进 JS 常量（textContent 用；无 </ 序列，仍走同款 dumps）
    video_err_json = json.dumps(VIDEO_ERROR_TEXT, ensure_ascii=False)

    # SC3 第 1 层：asset_name 来自路径派生（可含特殊字符）—— 过 _esc
    esc_asset_name = _esc(asset_name)

    # ⚠ F regen 失败 pill 仅 F>0 时显示（UI-SPEC Copywriting 表）
    failed_pill = (f'\n    <span class="pill pill-failed">⚠ {n_failed} regen 失败</span>'
                   if n_failed > 0 else "")
    # ⏳ 已复核 pill 初始 0/N：N>0 黄（R<N），N=0 视作已达（绿）
    reviewed_cls = "pill-warn" if n > 0 else "pill-ok"

    # IMPORTANT: 整个 HTML 是 Python f-string —— CSS/JS 块内字面 { } 一律 {{ }}
    # （gen_timeline_html.py / gen_registry_review.py 惯例，Pitfall 8）
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Round-trip 审阅 — {esc_asset_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; scroll-padding-top: 80px; }}
body {{
    background: #0d1117;
    color: #c9d1d9;
    font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    min-height: 100vh;
}}
.mono {{ font-family: monospace; }}

/* ===== Header (sticky) ===== */
.header {{
    position: sticky; top: 0; z-index: 200;
    background: #161b22; border-bottom: 1px solid #30363d;
    padding: 12px 20px;
}}
.header h1 {{ color: #58a6ff; font-size: 18px; font-weight: 600; margin-bottom: 6px; }}
.summary {{ display: flex; gap: 16px; font-size: 13px; color: #8b949e; flex-wrap: wrap; }}
.summary .pill {{
    padding: 2px 10px; border-radius: 12px;
    background: #21262d; border: 1px solid #30363d;
}}
.summary .pill.pill-warn {{ color: #d29922; border-color: #9e6a03; }}
.summary .pill.pill-ok {{ color: #3fb950; border-color: #2ea043; }}
.summary .pill.pill-failed {{ color: #f85149; border-color: #f85149; }}

/* ===== Two-column layout: 240px queue sidebar + single-column cards ===== */
.app {{ display: flex; gap: 0; min-height: calc(100vh - 80px); }}
.review-queue {{
    width: 240px; flex-shrink: 0;
    background: #161b22; border-right: 1px solid #30363d;
    padding: 12px; overflow-y: auto;
    position: sticky; top: 80px; max-height: calc(100vh - 80px);
}}
.review-queue h2 {{ font-size: 13px; color: #8b949e; margin-bottom: 8px; font-weight: 600; }}
.queue-item {{
    display: block; padding: 6px 8px; margin-bottom: 4px;
    color: #c9d1d9; text-decoration: none;
    border-radius: 4px; font-size: 11px;
    border-left: 3px solid transparent;
    transition: background 0.15s;
}}
.queue-item:hover {{ background: #21262d; }}
.queue-item[data-verdict="accepted"] {{ border-left-color: #3fb950; }}
.queue-item[data-verdict="rejected"] {{ border-left-color: #f85149; }}
.queue-item[data-verdict="none"] {{ border-left-color: #8b949e; }}
.queue-check {{ color: #3fb950; font-weight: 600; }}
.queue-topline {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px; }}
.queue-id {{ font-family: monospace; color: #58a6ff; }}
.queue-sim-num {{ color: #8b949e; font-family: monospace; }}
.queue-sim-bar {{ display: block; height: 4px; border-radius: 2px; background: #21262d; }}

/* 与 registry review 的唯一布局差异：单列 max-width 1200px（双 16:9 视频要整行） */
.cards-container {{
    flex: 1; padding: 16px;
    display: grid; grid-template-columns: 1fr; max-width: 1200px;
    gap: 16px; align-content: start;
}}

/* ===== Per-shot card ===== */
.shot-card {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 12px;
    transition: border-color 0.15s, box-shadow 0.15s, opacity 0.15s;
}}
.shot-card:hover {{ border-color: #58a6ff; }}
.shot-card.state-accept {{ border-color: #3fb950; box-shadow: 0 0 0 1px #3fb950; }}
.shot-card.state-reject {{ opacity: 0.45; border-color: #f85149; }}
.shot-card.card-failed {{ border-color: #f85149; }}
.card-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
.shot-id {{ font-family: monospace; color: #58a6ff; font-size: 13px; font-weight: 600; }}
.verdict-badge {{ font-size: 11px; padding: 1px 6px; border-radius: 8px; border: 1px solid #30363d; background: #21262d; }}
.verdict-badge.accepted {{ color: #3fb950; border-color: #2ea043; }}
.verdict-badge.rejected {{ color: #f85149; border-color: #f85149; }}
.pending-badge {{
    font-size: 11px; padding: 1px 6px; border-radius: 8px;
    color: #8b949e; border: 1px solid #30363d; background: #21262d;
}}
.attr-badge {{
    color: #0d1117; font-size: 11px; font-weight: 600;
    padding: 1px 6px; border-radius: 8px;
}}
.failed-line {{
    color: #f85149; font-size: 13px; padding: 8px;
    border: 1px dashed #f85149; border-radius: 4px;
    margin-bottom: 8px; word-break: break-word;
}}

/* ===== Dual video row (16:9 / object-fit contain / well bg #0d1117) ===== */
.video-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; }}
.video-topline {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; gap: 4px; }}
.video-label {{ font-size: 11px; color: #8b949e; }}
.dur-chip {{
    font-size: 11px; color: #8b949e; font-family: monospace;
    background: #21262d; padding: 0 4px; border-radius: 3px; white-space: nowrap;
}}
.video-well {{ background: #0d1117; border-radius: 4px; padding: 4px; }}
.video-well video {{ width: 100%; aspect-ratio: 16/9; object-fit: contain; display: block; }}
.video-well.video-error {{
    background: #30363d; color: #8b949e; font-size: 11px;
    padding: 16px 8px; word-break: break-word; aspect-ratio: 16/9;
    display: flex; align-items: center; justify-content: center; text-align: center;
}}

/* ===== Sync controls（accent 保留清单第 5 处）===== */
.sync-controls {{ display: flex; gap: 8px; margin-bottom: 8px; }}
.sync-button {{
    background: #21262d; color: #58a6ff;
    border: 1px solid #30363d; border-radius: 4px;
    padding: 3px 8px; font-size: 13px;
    cursor: pointer; transition: all 0.15s;
}}
.sync-button:hover {{ border-color: #58a6ff; }}

/* ===== sim bar（4px 高 / τ 1px 虚线 tick）===== */
.sim-row {{ margin-bottom: 8px; }}
.sim-bar-container {{
    position: relative; height: 4px; background: #21262d;
    border-radius: 2px; margin-bottom: 4px;
}}
.sim-bar {{ height: 100%; border-radius: 2px; transition: width 0.2s; }}
.sim-tick {{
    position: absolute; top: -2px; bottom: -2px; width: 0;
    border-left: 1px dashed #8b949e;
}}
.score-line {{ font-family: monospace; font-size: 11px; color: #8b949e; }}
.judge-row {{ margin-bottom: 8px; }}
.judge-meta {{ font-size: 11px; color: #c9d1d9; }}
.reason {{ font-size: 11px; color: #8b949e; margin-top: 2px; word-break: break-word; }}

/* ===== Prompt 快照折叠（默认折叠；长文 word-break）===== */
.prompt-fold {{ margin-bottom: 8px; }}
.prompt-fold summary {{ font-size: 13px; color: #c9d1d9; cursor: pointer; }}
.prompt-body {{ padding: 8px 0 0 0; }}
.prompt-text {{ font-size: 11px; color: #c9d1d9; margin-bottom: 8px; word-break: break-word; }}
.facet-table {{ border-collapse: collapse; margin-bottom: 8px; }}
.facet-table td {{ font-size: 11px; padding: 1px 8px 1px 0; vertical-align: top; }}
.facet-key {{ color: #8b949e; font-family: monospace; }}
.facet-val {{ color: #c9d1d9; word-break: break-word; }}
.refs-line {{ font-size: 11px; color: #8b949e; word-break: break-word; }}

/* ===== 三态覆盖按钮（14/600 档）===== */
.card-actions {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.action-button {{
    background: #21262d; color: #c9d1d9;
    border: 1px solid #30363d; border-radius: 4px;
    padding: 4px 12px; font-size: 14px; font-weight: 600;
    cursor: pointer; transition: all 0.15s;
}}
.action-button:hover {{ border-color: #58a6ff; color: #58a6ff; }}
.action-button.active {{ background: #1f6feb; border-color: #1f6feb; color: white; }}
.action-accept.active {{ background: #238636; border-color: #2ea043; color: white; }}
.action-reject.active {{ background: #da3633; border-color: #f85149; color: white; }}

/* ===== Empty state ===== */
.empty-state {{ color: #8b949e; font-size: 13px; }}
.empty-state p {{ margin-bottom: 8px; }}

/* ===== Export bar (sticky bottom) ===== */
.export-section {{
    position: sticky; bottom: 0; z-index: 100;
    background: #161b22; border-top: 1px solid #30363d;
    padding: 10px 20px; display: flex; justify-content: space-between;
    align-items: center; gap: 16px;
}}
.export-info {{ color: #8b949e; font-size: 13px; }}
.export-counter {{ font-family: monospace; }}
.export-button {{
    background: #238636; color: white;
    border: 1px solid #2ea043; border-radius: 6px;
    padding: 8px 16px; font-size: 14px; font-weight: 600;
    cursor: pointer; transition: background 0.15s; white-space: nowrap;
}}
.export-button:hover {{ background: #2ea043; }}
</style>
</head>
<body>

<div class="header">
  <h1>Round-trip 审阅 — {esc_asset_name}</h1>
  <div class="summary">
    <span class="pill">📊 {n} shots</span>
    <span class="pill">🟢 {n_accepted} accepted</span>
    <span class="pill">🔴 {n_rejected} rejected</span>
    <span class="pill">🧑 {n_human} human 覆盖</span>
    <span class="pill {reviewed_cls}" id="reviewed-pill">⏳ 已复核 0/{n}</span>
    <span class="pill">τ_sim={tau:.4f}</span>{failed_pill}
  </div>
</div>

<div class="app">
  <div class="review-queue">
    <h2>📋 审阅队列 (τ 边界排序 — 最难决定先审)</h2>
{queue_html}
  </div>
  <div class="cards-container">
{cards_html}
  </div>
</div>

<div class="export-section">
  <div class="export-info">
    <span class="export-counter" id="export-counter">已复核 0/{n} · 覆盖 0/0</span><br>
    操作员：逐镜比对原始 vs 重生成，必要时三态覆盖 verdict，再点右侧导出 →
    得到 roundtrip-edits.json，运行 apply CLI（confirmed-only）写回
    sidecar（source:"human"）。
  </div>
  <button class="export-button" onclick="exportEdits()">📥 Export edits (roundtrip-edits.json)</button>
</div>

<script>
// Bootstrap server-side data（原始序 shots；member/时窗查找用）。
// SC3 第 2 层：Python 侧已对整段 JSON 做 "</" → "<\\/" 转义（见 build_html）。
const RT_SHOTS = {rt_json};
const TAU = {tau:.4f};
const N_TOTAL = RT_SHOTS.length;
const VIDEO_ERROR_TEXT = {video_err_json};

// 三态覆盖状态（SC3 第 3 层：动态更新一律 classList/textContent，禁 inner-HTML 拼接）
// —— reviewed = 点过任一三态按钮（含显式「维持 auto」）；accept/reject 进 edits；
//    keepAuto 显式标记已复核但不产 edit 记录（维持 auto 不进 edits）。
const state = {{
    reviewed: new Set(),
    accept: new Set(),
    reject: new Set(),
    keepAuto: new Set(),
}};

function shotRef(sid) {{ return 'shot_' + String(sid).padStart(3, '0'); }}
function cardEl(sid) {{ return document.getElementById('card-' + shotRef(sid)); }}

function setState(sid, choice) {{
    // 互斥：任一时刻至多一个 active；点当前 active 项 = 撤销回未复核默认态
    const set = choice === 'accept' ? state.accept
              : choice === 'reject' ? state.reject
              : state.keepAuto;
    if (set.has(sid)) {{
        set.delete(sid);
        state.reviewed.delete(sid);
    }} else {{
        state.accept.delete(sid);
        state.reject.delete(sid);
        state.keepAuto.delete(sid);
        set.add(sid);
        state.reviewed.add(sid);
    }}
    applyVisualState();
}}

function applyVisualState() {{
    document.querySelectorAll('.shot-card').forEach(card => {{
        const sid = Number(card.dataset.shotId);
        card.classList.remove('state-accept', 'state-reject');
        const bA = card.querySelector('.action-accept');
        const bR = card.querySelector('.action-reject');
        const bK = card.querySelector('.action-auto');
        if (bA) bA.classList.remove('active');
        if (bR) bR.classList.remove('active');
        if (bK) bK.classList.remove('active');
        if (state.accept.has(sid)) {{
            card.classList.add('state-accept');
            if (bA) bA.classList.add('active');
        }}
        if (state.reject.has(sid)) {{
            card.classList.add('state-reject');
            if (bR) bR.classList.add('active');
        }}
        if (state.keepAuto.has(sid)) {{
            if (bK) bK.classList.add('active');
        }}
        // queue 侧同步：已复核卡对应 queue 项的 .queue-check 占位 span 填 ✓
        // （CR-01 22-REVIEW：绝不对 queue anchor <a> 整体赋 textContent——那会
        // 把 topline（shot id + sim 数）与微型 sim bar 子节点全部替换成单一
        // 文本节点，页面一加载 applyVisualState() 即把整个队列抹成空行；
        // ✓ 只进 server 渲染的专用占位 span，anchor 其余子节点不动）
        const q = document.getElementById('q-' + shotRef(sid));
        const check = q ? q.querySelector('.queue-check') : null;
        if (check) check.textContent = state.reviewed.has(sid) ? '✓ ' : '';
    }});
    // ⏳ 已复核 R/N pill：R<N 黄 / R=N 绿；export bar 左侧实时计数
    const r = state.reviewed.size;
    const pill = document.getElementById('reviewed-pill');
    if (pill) {{
        pill.textContent = '⏳ 已复核 ' + r + '/' + N_TOTAL;
        pill.classList.toggle('pill-warn', r < N_TOTAL);
        pill.classList.toggle('pill-ok', r >= N_TOTAL);
    }}
    const counter = document.getElementById('export-counter');
    if (counter) {{
        counter.textContent = '已复核 ' + r + '/' + N_TOTAL +
            ' · 覆盖 ' + state.accept.size + '/' + state.reject.size;
    }}
}}

// ===== 双 video 同步（事件级——play/pause 同驱两侧；不做 timeupdate 从属锁）=====
function toggleSync(sid) {{
    const card = cardEl(sid);
    if (!card) return;
    const left = card.querySelector('video.sync-left');
    const right = card.querySelector('video.sync-right');
    const btn = card.querySelector('.sync-toggle');
    const playing = left && !left.paused;
    if (playing) {{
        if (left) left.pause();
        if (right) right.pause();
        if (btn) btn.textContent = '▶ 同步播放';
    }} else {{
        if (left) left.play().catch(() => {{}});
        if (right) right.play().catch(() => {{}});
        if (btn) btn.textContent = '⏸ 同步暂停';
    }}
}}

function resetSync(sid) {{
    const card = cardEl(sid);
    if (!card) return;
    const left = card.querySelector('video.sync-left');
    const right = card.querySelector('video.sync-right');
    const btn = card.querySelector('.sync-toggle');
    const start = Number(card.dataset.start) || 0;
    if (left) {{
        try {{ left.currentTime = start; }} catch (e) {{}}
        left.pause();
    }}
    if (right) {{
        try {{ right.currentTime = 0; }} catch (e) {{}}
        right.pause();
    }}
    if (btn) btn.textContent = '▶ 同步播放';
}}

// ===== video 加载失败占位（不出 broken 图标、不阻塞另一侧与全卡操作）=====
document.querySelectorAll('video').forEach(v => {{
    v.addEventListener('error', () => {{
        const well = v.parentElement;
        if (!well) return;
        well.classList.add('video-error');
        well.textContent = VIDEO_ERROR_TEXT;  // textContent 赋值即移除失败 video
    }});
}});

// ===== Export edits（confirmed-only apply 闭环的导出半边）=====
// 只收显式 Accept/Reject（维持 auto 不进 edits）；与 auto 判定同向的显式覆盖
// 照导（apply 后 source 变 human，防未来重打分翻案——schema source 字段设计用途）。
// shot_id 是 int —— 升序必须 numeric comparator（registry 用字典序因其 ID 是字符串）。
function exportEdits() {{
    const edits = {{
        accept_overrides: Array.from(state.accept).sort((a, b) => a - b),
        reject_overrides: Array.from(state.reject).sort((a, b) => a - b),
        review_notes: `Exported from roundtrip review HTML on ${{new Date().toISOString()}}`,
    }};
    const blob = new Blob([JSON.stringify(edits, null, 2)], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'roundtrip-edits.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}}

// Initial state application（默认态：三按钮全不 active——维持 auto 是隐式默认）
applyVisualState();
</script>

</body>
</html>"""
    return html


# ============================================================================
# CLI entry point
# ============================================================================

def main(argv=None):
    ap = argparse.ArgumentParser(
        description=(
            "round-trip HITL 审阅 HTML 生成器（PRESENT-01）。读取 roundtrip.json，"
            "渲染双 video 并排 + sim bar(τ tick) + 归因色块 + judge reason + "
            "prompt 快照折叠 + 三态覆盖按钮 + τ 边界排序队列 + Export edits 下载。"
        ))
    ap.add_argument("--roundtrip", required=True,
                    help="roundtrip.json 路径 (step_roundtrip sidecar；缺席 → 空态面板)")
    ap.add_argument("--video", required=True,
                    help="原视频路径 (左 video src 基准，relpath 到输出目录)")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径 (id → start/end_sec 时窗解析)")
    ap.add_argument("--prompts", required=True,
                    help="prompts.json 路径 (prompt 快照源，按 shot_id 对齐)")
    ap.add_argument("--tau-sim", type=float, default=TAU_SIM_DEFAULT,
                    help=f"τ_sim 阈值 (默认 {TAU_SIM_DEFAULT} — Phase 21 Kai 裁决值)")
    ap.add_argument("--output", required=True,
                    help="输出 HTML 路径 (建议 <work-dir>/roundtrip_review.html)")
    args = ap.parse_args(argv)

    # 数据装载（全部 swallow-to-empty——缺席/坏文件不 raise，空态面板仍可生成）
    sidecar = _load_json(args.roundtrip, {})
    shots = sidecar.get("shots") if isinstance(sidecar, dict) else None
    if not isinstance(shots, list):
        shots = []
    meta_idx = _index_by(_load_json(args.shots, []), "id")
    prompt_idx = _index_by(_load_json(args.prompts, []), "shot_id")

    # 左 video src 基准：原视频相对输出目录（Media Fragments 时窗在卡片侧拼）
    out_dir = os.path.dirname(os.path.abspath(args.output)) or "."
    video_src_base = os.path.relpath(args.video, out_dir)

    # asset name：roundtrip.json 父目录名（mirror gen_registry_review.py 惯例）
    rt_path = Path(args.roundtrip).resolve()
    asset_name = rt_path.parent.name or rt_path.stem

    html = build_html(shots, video_src_base, meta_idx, prompt_idx,
                      asset_name, args.tau_sim)

    # Atomic write（tmp + os.replace；mirror gen_registry_review.py 先例）
    tmp = args.output + ".tmp"
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, args.output)

    print(f"[roundtrip-review] wrote {args.output} ({len(shots)} shots)")


if __name__ == "__main__":
    sys.exit(main())
