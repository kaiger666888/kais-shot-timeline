#!/usr/bin/env python3
"""html/gen_speaker_review.py — HITL 说话人审阅 HTML 生成器（SPEAKER-01 first-class 交付物，DIA-03）。

把 step_audio_semantic 产出的 audio_semantic.json（含 dialogue.spk_id）渲染成
self-contained monolithic HTML：说话人 cards（按 shot_count desc 排序）+ 角色下拉
（FILTERED 到 characters.json#review_state=='confirmed'，Pitfall 7 upstream gate）
+ Confirm/Reject 按钮 + Export edits 按钮 → 客户端序列化 speaker-edits.json 下载
（no server；offline review；mirror html/gen_registry_review.py 的 monolithic 模式 +
GitHub-dark palette）。

操作流程（CONTEXT decisions lock）：
  1. step_audio_semantic 产出 audio_semantic.json（dialogue.spk_id 来自 Phase 12 diarize）
  2. 本脚本聚合 spk_NNN → 每个 speaker 的 turns / total_speech_sec / shot_count
  3. 操作员在浏览器中（scripts/serve.py 提供）审阅：
     - 按 shot_count desc 浏览说话人队列（最活跃的先审）
     - 在角色下拉中选择 confirmed character（旁白/群杂留空 = 无映射）
     - Confirm（流向 canonical speakers.json）或 Reject（软删除，ID 保留）
     - 可选：合并相似 speaker（merge_groups）或拆分一个 speaker（splits PARTITION）
  4. 点击 "Export edits" → 浏览器 Blob + URL.createObjectURL → 下载 speaker-edits.json
  5. 操作员手动跑 registry/link_speakers.py 应用 edits → canonical speakers.json

设计优先级（CONTEXT decisions lock —— HITL HTML 是一等交付物）：
  - 中文 UI（CLAUDE.md lock）
  - GitHub-dark palette 复用（#0d1117 bg, #161b22 panel, #58a6ff accent 等）
  - XSS 加固（mirror v1.1 Phase 8 PRESENT）：_esc 5-char HTML escape 应用于每个动态字符串
    + JSON-in-<script> bootstrap .replace("</", "<\\/") 防 </script> payload 破出
  - shot_count desc 排序（最活跃说话人先审 —— 与 gen_registry_review.py 的 cosine-sorted
    queue 同等优先级理念：信息密度最高的 card 先 surface）
  - 角色下拉 FILTERED 到 confirmed only（Pitfall 7 upstream gate —— 操作员无法在 UI 层
    选择 non-confirmed character 作为 link_mapping 目标）
  - Export 产 schema-valid speaker-edits.json（validates against
    spec/schemas/speaker-edits.schema.json，Draft202012Validator；空 {} schema-valid）

threat_model（PLAN.md T-13-01/09/10/11/12/SC）：
  - T-13-01 XSS：_esc 应用于 spk_id / char_name / dialogue excerpts / asset_name
  - T-13-09 JSON-in-script bootstrap：.replace("</", "<\\/")
  - T-13-10 unconfirmed character 下拉过滤（_load_confirmed_chars hard filter）
  - T-13-11/12 SC：accept；零新依赖（stdlib-only）

用法：
    python html/gen_speaker_review.py \\
        --audio-semantic <abs path>   (必填 — audio_semantic.json，含 dialogue.spk_id) \\
        --characters     <abs path>   (必填 — characters.json，confirmed 过滤源) \\
        --shots          <abs path>   (必填 — shots.json，asset 上下文) \\
        --output         <abs path>   (必填 — HTML 输出路径，建议 <work-dir>/speaker_review.html)
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


# ============================================================================
# Module-level constants
# ============================================================================

HERE = Path(__file__).resolve().parent

# Speaker review-state colors (mirror TIER_COLORS reuse of GitHub-dark palette)
SPEAKER_STATE_COLORS = {
    "confirmed": "#3fb950",  # green (flows to canonical speakers.json)
    "rejected":  "#f85149",  # red (soft-delete; spk_id reserved for referential integrity)
    "pending":   "#8b949e",  # grey (operator has not yet toggled)
}

# Contract that the export-edits button output targets. The HTML does NOT validate at
# runtime, but the path is documented for the operator + downstream link_speakers.py
# Draft202012Validator pre-apply gate (T-07-02 Phase 11 schema lock).
SPEAKER_EDITS_SCHEMA = HERE.parent / "spec" / "schemas" / "speaker-edits.schema.json"

# Dropdown sentinel for 旁白/群杂 — exports as omitted key in link_mappings → null char_id
# downstream in speakers.json (speakers.schema.json#char_id is nullable for this path).
NO_CHAR_LINK_VALUE = ""

# Defensive re-validation on read; route output is untrusted (T-13-01 defense-in-depth).
# Pattern-locked at the schema layer (speaker-edits.schema.json patternProperties) AND
# re-validated here so a malformed route payload never reaches the HTML body.
SPK_PATTERN = re.compile(r"^spk_[0-9]{3}$")
CHAR_PATTERN = re.compile(r"^char_[0-9]{3}$")


# ============================================================================
# Helpers
# ============================================================================

def _esc(s):
    """HTML-escape 字符串以安全插值进 HTML text/attribute context (CR-04 XSS defense,
    mirror gen_registry_review.py:79-91)。

    转义 5 个字符: & < > " '。顺序固定 (& 先，防双重转义)。
    Self-contained inline impl (不走 stdlib html.escape) —— 本仓库 html/ 目录是
    namespace package，避免任何 import-resolution 歧义；符合 standalone-script 约定。
    输入先 str() 兜底 (非 string 字段如 int shot_id 也安全)。
    """
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;")
                  .replace("'", "&#x27;"))


def _aggregate_speakers(audio_semantic):
    """聚合 audio_semantic.json 的 dialogue.spk_id → 说话人列表。

    Args:
        audio_semantic: dict | list —— audio_semantic.json 解析结果。
            预期 dict 含 "shots" 列表；defensive 也接受裸 list。

    Returns:
        list[dict] —— 按 (-shot_count, spk_id) 排序的说话人 dict 列表。每个 dict:
            {spk_id, turns: [{shot_id, start_sec, end_sec}], total_speech_sec, shot_count}
        turns 按 (shot_id, start_sec) 排序（idempotency-friendly 下游消费）。
        shot_count 用 set 去重 unique shot_id。

    Defensive guards (CR-02 mirror)：malformed shot (非 dict / 缺 dialogue / spk_id null /
    spk_id pattern mismatch / 非数值 timing) → 跳过 silently；不阻塞 HTML gen。
    """
    # Defensive: accept dict-with-shots OR bare list
    if isinstance(audio_semantic, dict):
        shots = audio_semantic.get("shots", []) or []
    elif isinstance(audio_semantic, list):
        shots = audio_semantic
    else:
        return []

    speakers = {}  # spk_id -> {turns: [], shot_ids: set(), total_speech_sec: float}
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        dlg = shot.get("dialogue")
        if not isinstance(dlg, dict):
            continue
        spk = dlg.get("spk_id")
        # T-13-01: pattern mismatch → skip silently (route-controlled field, untrusted).
        if not isinstance(spk, str) or not SPK_PATTERN.match(spk):
            continue

        # Timing: prefer shot-level start/end_sec; defensive on non-numeric.
        try:
            start_sec = float(shot.get("start_sec", 0.0))
            end_sec = float(shot.get("end_sec", start_sec))
        except (TypeError, ValueError):
            start_sec = 0.0
            end_sec = 0.0
        if end_sec < start_sec:
            end_sec = start_sec  # defensive: enforce non-negative duration

        shot_id_raw = shot.get("shot_id")
        try:
            shot_id_key = int(shot_id_raw) if shot_id_raw is not None else None
        except (TypeError, ValueError):
            shot_id_key = None

        entry = speakers.setdefault(
            spk,
            {"turns": [], "shot_ids": set(), "total_speech_sec": 0.0},
        )
        entry["turns"].append({
            "shot_id": shot_id_key if shot_id_key is not None else shot_id_raw,
            "start_sec": start_sec,
            "end_sec": end_sec,
        })
        if shot_id_key is not None:
            entry["shot_ids"].add(shot_id_key)
        entry["total_speech_sec"] += max(0.0, end_sec - start_sec)

    # Materialize + sort: (-shot_count, spk_id) → shot_count desc, spk_id asc tiebreak
    # (deterministic ordering is idempotency-friendly for downstream consumers).
    result = []
    for spk, entry in speakers.items():
        turns_sorted = sorted(
            entry["turns"],
            key=lambda t: (
                t["shot_id"] if isinstance(t["shot_id"], int) else (1 << 30),
                t["start_sec"],
            ),
        )
        # shot_count = unique shot_ids if any; else fall back to turn count.
        shot_count = len(entry["shot_ids"]) if entry["shot_ids"] else len(entry["turns"])
        result.append({
            "spk_id": spk,
            "turns": turns_sorted,
            "total_speech_sec": entry["total_speech_sec"],
            "shot_count": shot_count,
        })
    result.sort(key=lambda s: (-s["shot_count"], s["spk_id"]))
    return result


def _load_confirmed_chars(characters):
    """过滤 characters.json → 仅 confirmed characters 用于下拉。

    Pitfall 7 upstream gate: non-confirmed entries 永不进入下拉选项 —— 操作员无法在
    UI 层选择一个 unconfirmed character 作为 link_mapping 目标。Mirror apply_edits.py:476
    hard gate at the UI layer（confirmed-only flows downstream）。

    Args:
        characters: list[dict] —— characters.json 解析结果。

    Returns:
        list[tuple[char_id, name]] —— 按 char_id asc 排序（deterministic 下拉顺序）。
    """
    if not isinstance(characters, list):
        return []
    out = []
    for entry in characters:
        if not isinstance(entry, dict):
            continue
        if entry.get("review_state") != "confirmed":
            continue  # Pitfall 7 gate — confirmed only reaches the dropdown
        cid = entry.get("id")
        if not isinstance(cid, str) or not CHAR_PATTERN.match(cid):
            continue  # T-13-01 defense-in-depth
        name = entry.get("name") or cid
        out.append((cid, str(name)))
    out.sort(key=lambda t: t[0])
    return out


# ============================================================================
# HTML rendering
# ============================================================================

def _speaker_card_html(speaker, confirmed_chars, index):
    """渲染单个说话人 card HTML（mirror gen_registry_review.py:_cluster_card_html）。

    Args:
        speaker:         dict —— _aggregate_speakers 返回项。
        confirmed_chars: list[tuple[char_id, name]] —— confirmed-only 下拉选项源。
        index:           int —— card 序号（保留以兼容签名；当前未用）。
    """
    spk = speaker["spk_id"]
    turns = speaker.get("turns", []) or []
    total = float(speaker.get("total_speech_sec", 0.0))
    shot_count = int(speaker.get("shot_count", 0))

    # CR-04 XSS defense: _esc applied to every dynamic string; spk_id/char_id are
    # schema-pattern-locked but route-controlled fields (dialogue text excerpts,
    # character names) need the escape.
    esc_spk = _esc(spk)

    # Turns list items: "shot {shot_id} · {start:.1f}-{end:.1f}s · {duration:.1f}s"
    turn_lis = []
    for t in turns:
        try:
            t_start = float(t.get("start_sec", 0.0))
            t_end = float(t.get("end_sec", t_start))
        except (TypeError, ValueError):
            t_start = 0.0
            t_end = 0.0
        dur = max(0.0, t_end - t_start)
        turn_lis.append(
            f'<li>shot {_esc(t.get("shot_id", "?"))} · '
            f'{t_start:.1f}-{t_end:.1f}s · {dur:.1f}s</li>'
        )
    turns_html = "\n".join(turn_lis) if turn_lis else "<li>(无 turns)</li>"

    # Character dropdown — FILTERED to confirmed only (_load_confirmed_chars upstream gate).
    # Leading "(无角色映射)" option is the 旁白/群杂 path → omitted key in link_mappings.
    options = [f'<option value="{NO_CHAR_LINK_VALUE}">(无角色映射) — 旁白/群杂</option>']
    for cid, cname in confirmed_chars:
        options.append(f'<option value="{_esc(cid)}">{_esc(cname)}</option>')
    options_html = "\n".join(options)

    # IMPORTANT: this f-string is a Python f-string; literal { } in the inline JS
    # onclick handlers MUST be doubled ({{ }}) per gen_timeline_html.py convention.
    # CR-04: spk 经 _esc 后插值进 onclick JS string context —— spk 虽 schema-pattern-locked
    # (^spk_[0-9]{3}$，无引号/尖括号可达)，_esc 在此是无害 no-op + defense-in-depth。
    return f"""    <div class="cluster-card" id="card-{esc_spk}"
         data-speaker-id="{esc_spk}" data-shot-count="{shot_count}"
         data-total-speech-sec="{total:.2f}">
      <div class="card-body">
        <div class="card-header">
          <span class="cluster-id">{esc_spk}</span>
          <span class="state-badge pending">待审</span>
          <span class="chip chip-shots">🎬 {shot_count} shots</span>
          <span class="chip chip-duration">⏱ {total:.1f}s</span>
        </div>
        <ul class="members-list">
{turns_html}
        </ul>
        <div class="card-actions">
          <button class="action-button action-confirm" data-speaker-id="{esc_spk}"
                  onclick="toggleConfirm('{esc_spk}')">✓ Confirm</button>
          <button class="action-button action-reject" data-speaker-id="{esc_spk}"
                  onclick="toggleReject('{esc_spk}')">✗ Reject</button>
          <button class="action-button action-merge" data-speaker-id="{esc_spk}"
                  onclick="mergeWith('{esc_spk}')">↔ Merge</button>
          <button class="action-button action-split" data-speaker-id="{esc_spk}"
                  onclick="splitSpeaker('{esc_spk}')">✂ Split</button>
          <select name="char-link-{esc_spk}" data-speaker-id="{esc_spk}"
                  class="char-dropdown" onchange="setCharacterLink('{esc_spk}', this.value)">
{options_html}
          </select>
        </div>
      </div>
    </div>
"""


def build_html(speakers, confirmed_chars, asset_name):
    """生成完整 self-contained HTML string。

    Args:
        speakers:        list[dict] —— _aggregate_speakers 输出（已按 shot_count desc 排序）。
        confirmed_chars: list[tuple[char_id, name]] —— confirmed-only 下拉源。
        asset_name:      str —— header 显示用 asset 名。

    Returns:
        str —— 完整 HTML（单文件；所有 CSS/JS/data inline）。
    """
    n_speakers = len(speakers)
    # No pre-selection — operator must toggle each card explicitly (cleaner UX for
    # speaker review where every acoustic ID is by default "unknown identity").
    n_confirmed = 0
    n_rejected = 0
    n_pending = n_speakers

    # Build speaker cards + queue sidebar (queue mirrors gen_registry_review.py sidebar
    # but sorts by shot_count desc — the input `speakers` list is already sorted).
    cards_html_parts = []
    queue_html_parts = []
    for i, speaker in enumerate(speakers):
        cards_html_parts.append(_speaker_card_html(speaker, confirmed_chars, i))
        esc_spk = _esc(speaker["spk_id"])
        shot_count = int(speaker.get("shot_count", 0))
        queue_html_parts.append(
            f'    <a href="#card-{esc_spk}" class="queue-item">'
            f'<span class="queue-id">{esc_spk}</span>'
            f'<span class="queue-meta">{shot_count} shots</span></a>'
        )

    cards_html = "\n".join(cards_html_parts) if cards_html_parts \
        else "<p>(空 audio_semantic —— 无 speaker 可审阅)</p>"
    queue_html = "\n".join(queue_html_parts) if queue_html_parts else "<p>(无)</p>"

    # Inline the speakers + confirmed_chars as const bootstrap JSON.
    # CR-04 JSON-in-<script> defense: .replace("</", "<\\/") prevents </script> payload
    # from breaking out of the script block (HTML parser sees </script> as terminator
    # regardless of JS string context). Mirror gen_registry_review.py:316-318 CR-04.
    speakers_json = json.dumps(speakers, ensure_ascii=False).replace("</", "<\\/")
    confirmed_chars_json = json.dumps(
        [{"id": cid, "name": name} for cid, name in confirmed_chars],
        ensure_ascii=False,
    ).replace("</", "<\\/")

    esc_asset_name = _esc(asset_name)

    # IMPORTANT: the entire HTML body below is an f-string. Literal { } in CSS / JS
    # blocks MUST be doubled to {{ }} (gen_timeline_html.py:131-941 convention).
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HITL 说话人审阅 — {esc_asset_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; scroll-padding-top: 80px; }}
body {{
    background: #0d1117;
    color: #c9d1d9;
    font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    min-height: 100vh;
}}

/* ===== Header (sticky) ===== */
.header {{
    position: sticky; top: 0; z-index: 200;
    background: #161b22; border-bottom: 1px solid #30363d;
    padding: 12px 20px;
}}
.header h1 {{ color: #58a6ff; font-size: 18px; margin-bottom: 6px; }}
.summary {{ display: flex; gap: 16px; font-size: 13px; color: #8b949e; flex-wrap: wrap; }}
.summary .pill {{
    padding: 2px 10px; border-radius: 12px;
    background: #21262d; border: 1px solid #30363d;
}}
.summary .pill.confirmed {{ color: #3fb950; border-color: #2ea043; }}
.summary .pill.rejected  {{ color: #f85149; border-color: #da3633; }}
.summary .pill.pending   {{ color: #8b949e; }}

/* ===== Two-column layout: queue sidebar + cards ===== */
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
    border-radius: 4px; font-size: 12px;
    border-left: 3px solid #58a6ff;
    transition: background 0.15s;
}}
.queue-item:hover {{ background: #21262d; }}
.queue-id {{ font-family: monospace; color: #58a6ff; margin-right: 8px; }}
.queue-meta {{ float: right; color: #8b949e; font-family: monospace; }}

.cards-container {{
    flex: 1; padding: 16px;
    display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr));
    gap: 16px; align-content: start;
}}

/* ===== Speaker card (reuse .cluster-card class name — mirror gen_registry_review.py) ===== */
.cluster-card {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    overflow: hidden;
    transition: border-color 0.15s, box-shadow 0.15s;
}}
.cluster-card:hover {{ border-color: #58a6ff; }}
.cluster-card.state-confirmed {{ border-color: #3fb950; box-shadow: 0 0 0 1px #3fb950; }}
.cluster-card.state-rejected {{ opacity: 0.45; border-color: #f85149; }}
.card-body {{ padding: 10px 12px; min-width: 0; }}
.card-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }}
.cluster-id {{ font-family: monospace; color: #58a6ff; font-size: 13px; font-weight: 700; }}
.state-badge {{
    color: #0d1117; font-size: 10px; font-weight: 700;
    padding: 1px 6px; border-radius: 8px;
}}
.state-badge.pending   {{ background: #8b949e; }}
.state-badge.confirmed {{ background: #3fb950; }}
.state-badge.rejected  {{ background: #f85149; }}
.chip {{
    font-size: 11px; color: #c9d1d9;
    padding: 1px 8px; border-radius: 10px;
    background: #21262d; border: 1px solid #30363d;
}}
.chip-duration {{ color: #d29922; }}
.members-list {{
    list-style: none; margin-bottom: 8px;
    font-size: 11px; color: #8b949e;
    max-height: 100px; overflow-y: auto;
}}
.members-list li {{ padding: 1px 0; font-family: monospace; }}
.card-actions {{ display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }}
.action-button {{
    background: #21262d; color: #c9d1d9;
    border: 1px solid #30363d; border-radius: 4px;
    padding: 3px 8px; font-size: 11px;
    cursor: pointer; transition: all 0.15s;
}}
.action-button:hover {{ border-color: #58a6ff; color: #58a6ff; }}
.action-button.active {{ background: #1f6feb; border-color: #1f6feb; color: white; }}
.action-confirm.active {{ background: #238636; border-color: #2ea043; }}
.action-reject.active {{ background: #da3633; border-color: #f85149; }}
/* Character dropdown (NEW — replaces cluster-name input from gen_registry_review.py) */
.char-dropdown {{
    margin-left: auto;
    background: #0d1117; color: #c9d1d9;
    border: 1px solid #30363d; border-radius: 4px;
    padding: 4px 8px; font-size: 12px;
    min-width: 160px;
}}
.char-dropdown:focus {{ outline: none; border-color: #58a6ff; }}

/* ===== Export footer (sticky bottom) ===== */
.export-section {{
    position: sticky; bottom: 0; z-index: 100;
    background: #161b22; border-top: 1px solid #30363d;
    padding: 10px 20px; display: flex; justify-content: space-between; align-items: center;
}}
.export-info {{ color: #8b949e; font-size: 12px; }}
.export-button {{
    background: #238636; color: white;
    border: 1px solid #2ea043; border-radius: 6px;
    padding: 8px 16px; font-size: 14px; font-weight: 600;
    cursor: pointer; transition: background 0.15s;
}}
.export-button:hover {{ background: #2ea043; }}
</style>
</head>
<body>

<div class="header">
  <h1>HITL 说话人审阅 — {esc_asset_name}</h1>
  <div class="summary">
    <span>📊 {n_speakers} 说话人</span>
    <span class="pill confirmed">🟢 {n_confirmed} 已确认</span>
    <span class="pill rejected">🔴 {n_rejected} 已拒绝</span>
    <span class="pill pending">⚪ {n_pending} 待审</span>
    <span class="pill">shot_count desc 队列 — 最活跃先审</span>
  </div>
</div>

<div class="app">
  <div class="review-queue">
    <h2>📋 审阅队列 (按 shot_count desc)</h2>
{queue_html}
  </div>
  <div class="cards-container">
{cards_html}
  </div>
</div>

<div class="export-section">
  <div class="export-info">
    操作员：审阅上方 speaker，选择角色（confirmed only），确认/拒绝，再点右侧导出 →
    得到 speaker-edits.json，运行 registry/link_speakers.py 产 canonical speakers.json。
  </div>
  <button class="export-button" onclick="exportEdits()">📥 Export edits (speaker-edits.json)</button>
</div>

<script>
// Bootstrap server-side data (CR-04 JSON-in-script defense applied at producer side).
// The producer runs json.dumps(...).replace("</", "<\\/") which deflects any
// closing-script-tag sequence inside JSON string values. (The literal closing-tag
// token is intentionally NOT spelled out in this JS comment, so the HTML parser
// cannot mistake this comment for the real block terminator.)
const SPEAKERS = {speakers_json};
const CONFIRMED_CHARS = {confirmed_chars_json};
const NO_CHAR_LINK_VALUE = "{NO_CHAR_LINK_VALUE}";

// Operator-edits state (mutable; updated by toggle handlers).
// link_mappings is the SPEAKER-01 NEW field (orthogonal to confirm_ids — a speaker
// may be confirmed AND linked to a character; multiple speakers may link to the same
// character, e.g. 多声优饰同一角色).
const state = {{
    confirmIds: new Set(),       // spk_id → confirmed
    rejectIds: new Set(),        // spk_id → rejected
    mergeGroups: [],             // [[spk_id, spk_id, ...], ...] (≥2 items each)
    splits: {{}},                 // spk_id → [{{label, member_indexes}}, ...] (PARTITION of turns)
    linkMappings: {{}},           // spk_id → char_id (omits 旁白/群杂 null links)
}};

function applyVisualState() {{
    document.querySelectorAll('.cluster-card').forEach(card => {{
        const sid = card.dataset.speakerId;
        card.classList.remove('state-confirmed', 'state-rejected');
        const confirmBtn = card.querySelector('.action-confirm');
        const rejectBtn = card.querySelector('.action-reject');
        const badge = card.querySelector('.state-badge');
        if (confirmBtn) confirmBtn.classList.remove('active');
        if (rejectBtn) rejectBtn.classList.remove('active');
        if (state.confirmIds.has(sid)) {{
            card.classList.add('state-confirmed');
            if (confirmBtn) confirmBtn.classList.add('active');
            if (badge) {{ badge.classList.remove('pending','rejected'); badge.classList.add('confirmed'); badge.textContent = '已确认'; }}
        }} else if (state.rejectIds.has(sid)) {{
            card.classList.add('state-rejected');
            if (rejectBtn) rejectBtn.classList.add('active');
            if (badge) {{ badge.classList.remove('pending','confirmed'); badge.classList.add('rejected'); badge.textContent = '已拒绝'; }}
        }} else {{
            if (badge) {{ badge.classList.remove('confirmed','rejected'); badge.classList.add('pending'); badge.textContent = '待审'; }}
        }}
    }});
    // Update summary pill counts
    const confirmed = state.confirmIds.size;
    const rejected = state.rejectIds.size;
    const pending = SPEAKERS.length - confirmed - rejected;
    document.querySelectorAll('.summary .pill.confirmed').forEach(el => el.textContent = `🟢 ${{confirmed}} 已确认`);
    document.querySelectorAll('.summary .pill.rejected').forEach(el => el.textContent = `🔴 ${{rejected}} 已拒绝`);
    document.querySelectorAll('.summary .pill.pending').forEach(el => el.textContent = `⚪ ${{pending}} 待审`);
}}

function toggleConfirm(sid) {{
    if (state.confirmIds.has(sid)) {{
        state.confirmIds.delete(sid);
    }} else {{
        state.confirmIds.add(sid);
        state.rejectIds.delete(sid);  // mutually exclusive
    }}
    applyVisualState();
}}

function toggleReject(sid) {{
    if (state.rejectIds.has(sid)) {{
        state.rejectIds.delete(sid);
    }} else {{
        state.rejectIds.add(sid);
        state.confirmIds.delete(sid);
    }}
    applyVisualState();
}}

function setCharacterLink(sid, charId) {{
    // Dropdown onchange handler. NO_CHAR_LINK_VALUE → 旁白/群杂 → omit key (null char_id downstream).
    if (!charId || charId === NO_CHAR_LINK_VALUE) {{
        delete state.linkMappings[sid];
    }} else {{
        state.linkMappings[sid] = charId;
    }}
}}

function mergeWith(sid) {{
    const target = prompt(`合并 ${{sid}} 到哪个 spk_id？(输入 canonical spk_id，如 spk_001)`);
    if (!target || target === sid) return;
    // Find or create a merge group containing both
    let group = state.mergeGroups.find(g => g.includes(sid) || g.includes(target));
    if (group) {{
        if (!group.includes(sid)) group.push(sid);
        if (!group.includes(target)) group.push(target);
    }} else {{
        // canonical = target (first); members appended
        state.mergeGroups.push([target, sid]);
    }}
    alert(`已记录合并：${{sid}} → ${{target}} (导出时生效)`);
}}

function splitSpeaker(sid) {{
    // CR-01 mirror: split 是 turns 的 PARTITION（非克隆）。
    const speaker = SPEAKERS.find(s => s.spk_id === sid);
    if (!speaker || !speaker.turns || speaker.turns.length < 2) {{
        alert(`无法拆分 ${{sid}}：少于 2 个 turn（分区需要 ≥2 turn）`);
        return;
    }}
    const nTurns = speaker.turns.length;
    const turnList = speaker.turns.map((t, i) =>
        `[${{i}}] shot ${{t.shot_id}}·${{t.start_sec.toFixed(1)}}-${{t.end_sec.toFixed(1)}}s`).join('\\n');
    const labelsStr = prompt(`拆分 ${{sid}} 为 N 个子说话人（PARTITION，非克隆）。\n`
        + `Turn 列表（0-based 索引）：\n${{turnList}}\n\n`
        + `输入新 label 列表，逗号分隔（≥2 个）：\n例如：说话人A-男, 说话人A-女`);
    if (!labelsStr) return;
    const labels = labelsStr.split(',').map(s => s.trim()).filter(Boolean);
    if (labels.length < 2) {{
        alert('需要至少 2 个 label 才能拆分');
        return;
    }}
    if (labels.length > nTurns) {{
        alert(`label 数 (${{labels.length}}) 超过 turn 数 (${{nTurns}})——每个 child 至少 1 turn`);
        return;
    }}
    // 逐 label（除最后一个）收 member_indexes；最后一个自动收剩余（保证完整分区）
    const children = [];
    const usedIdx = new Set();
    for (let li = 0; li < labels.length - 1; li++) {{
        const idxStr = prompt(`label "${{labels[li]}}" 的 turn 索引（逗号分隔，0-based，至少 1 个）：\n`
            + `剩余可选：[${{[...Array(nTurns).keys()].filter(i => !usedIdx.has(i)).join(', ')}}]`);
        if (!idxStr) return;  // cancel
        const idxs = idxStr.split(',').map(s => s.trim()).filter(Boolean).map(Number);
        if (idxs.length < 1 || idxs.some(i => isNaN(i) || i < 0 || i >= nTurns || usedIdx.has(i))) {{
            alert(`无效或重复的索引：${{idxStr}}（取消拆分）`);
            return;
        }}
        idxs.forEach(i => usedIdx.add(i));
        children.push({{label: labels[li], member_indexes: idxs}});
    }}
    // 最后一个 label 收剩余未分配的（保证完整分区 —— link_speakers 拒绝不完整分区）
    const remainder = [...Array(nTurns).keys()].filter(i => !usedIdx.has(i));
    if (remainder.length < 1) {{
        alert(`label "${{labels[labels.length - 1]}}" 无剩余 turn——已全分配给前面的 label（取消拆分）`);
        return;
    }}
    children.push({{label: labels[labels.length - 1], member_indexes: remainder}});
    state.splits[sid] = children;
    alert(`已记录拆分（PARTITION）：${{sid}} → ${{children.map(c => c.label + '[' + c.member_indexes.length + ']').join(', ')}}`);
}}

function exportEdits() {{
    // Build speaker-edits.json per spec/schemas/speaker-edits.schema.json
    // (drop renames + type_overrides vs registry-edits; add link_mappings — Phase 11 SUMMARY:115).
    // confirm_ids + reject_ids sorted (idempotency-friendly downstream).
    // link_mappings spread from state (旁白/群杂 already excluded by setCharacterLink).
    const edits = {{
        merge_groups: state.mergeGroups.filter(g => g && g.length >= 2),
        splits: Object.keys(state.splits).reduce((acc, k) => {{
            acc[k] = state.splits[k];
            return acc;
        }}, {{}}),
        confirm_ids: Array.from(state.confirmIds).sort(),
        reject_ids: Array.from(state.rejectIds).sort(),
        link_mappings: {{ ...state.linkMappings }},
        review_notes: `Exported from HITL speaker review HTML on ${{new Date().toISOString()}}`,
    }};

    const blob = new Blob([JSON.stringify(edits, null, 2)], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'speaker-edits.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}}

// Initial state application (no pre-selection — operator must toggle each card).
applyVisualState();
</script>

</body>
</html>"""
    return html


# ============================================================================
# CLI entry point
# ============================================================================

def main():
    ap = argparse.ArgumentParser(
        description=(
            "HITL 说话人审阅 HTML 生成器（SPEAKER-01 first-class deliverable）。"
            "读取 audio_semantic.json（dialogue.spk_id）+ characters.json（confirmed 过滤）+ "
            "shots.json（asset 上下文），渲染 speaker cards（shot_count desc 排序）+ 角色下拉"
            "（confirmed only）+ Confirm/Reject + Export edits 按钮。"
        )
    )
    ap.add_argument("--audio-semantic", required=True,
                    help="audio_semantic.json 路径 (Phase 12 producer 产物，提供 dialogue.spk_id 来源)")
    ap.add_argument("--characters", required=True,
                    help="characters.json 路径 (确认状态的角色用于下拉过滤)")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径 (asset 上下文)")
    ap.add_argument("--output", required=True,
                    help="输出 HTML 路径 (建议 <work-dir>/speaker_review.html)")
    args = ap.parse_args()

    # Defensive JSON load with clear error messages (mirror gen_registry_review.py:705-712).
    # T-13-12 (Info Disclosure): file paths in error messages are operator-audit-only;
    # no PII / secrets in inputs (asset_name = parent dir basename).
    try:
        with open(args.audio_semantic, encoding="utf-8") as f:
            audio_semantic = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"[speaker-review] 无法读取 --audio-semantic ({args.audio_semantic}): {e}")
    try:
        with open(args.characters, encoding="utf-8") as f:
            characters = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"[speaker-review] 无法读取 --characters ({args.characters}): {e}")
    try:
        with open(args.shots, encoding="utf-8") as f:
            _shots_meta = json.load(f)  # advisory; not currently wired into build_html
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"[speaker-review] 无法读取 --shots ({args.shots}): {e}")

    speakers = _aggregate_speakers(audio_semantic)
    confirmed_chars = _load_confirmed_chars(characters)

    # asset name: derive from --audio-semantic parent dir name (advisory; mirror
    # gen_registry_review.py asset-name derivation from --draft parent dir).
    as_path = Path(args.audio_semantic).resolve()
    asset_name = as_path.parent.name or as_path.stem

    html = build_html(speakers, confirmed_chars, asset_name)

    # Atomic write (temp + os.replace — mirror gen_registry_review.py:716-721 +
    # apply_edits.py + export_asset.py pattern; guards against partial writes on crash).
    tmp = args.output + ".tmp"
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, args.output)

    print(f"[speaker-review] wrote {args.output} "
          f"({len(speakers)} speakers, {len(confirmed_chars)} confirmed characters for dropdown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
