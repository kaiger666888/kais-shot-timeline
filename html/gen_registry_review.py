#!/usr/bin/env python3
"""html/gen_registry_review.py — HITL 审阅 HTML 生成器（FIRST-CLASS 交付物，CAST-06）。

把 step_reid 产出的 registry.draft.json 渲染成 self-contained monolithic HTML：
cluster cards + cosine-sorted review queue + three-tier viz + Export edits button
→ 客户端序列化 registry.edits.json 下载（no server；offline review；mirror
html/gen_timeline_html.py + html/gen_shots_preview.py 的 monolithic 模式 + GitHub-dark palette）。

操作流程（CONTEXT Q1 + Q2 lock）：
  1. step_reid 产出 registry.draft.json（route 不可达则文件缺席；本脚本仍可跑空态）
  2. 本脚本 ffmpeg 抽每个 cluster 代表帧 → base64 inline 进 HTML
     （Pitfall 2 prevention：canonical PNGs 在 apply_edits 之前尚不存在，
      必须在 HTML gen 时 inline —— HTML 完全自包含，offline 可审阅）
  3. 操作员在浏览器中（scripts/serve.py 提供）审阅：合并/拆分/重命名/确认/拒绝
  4. 点击 "Export edits" → 浏览器 Blob + URL.createObjectURL → 下载 registry.edits.json
  5. 操作员手动跑 registry/apply_edits.py 应用 edits → canonical characters.json/props.json

设计优先级（CONTEXT Q1 lock —— HITL HTML 是一等交付物，非附属脚本）：
  - 视觉 cluster cards + 可读缩略图（base64 inline → offline 可用）
  - 清晰的 merge/split/rename/confirm/reject 操作 affordance（图标 + 标签）
  - cosine-sorted queue：mid-band (0.6-0.85 review tier) 优先 surface（最难决定先审）
  - 三档色彩 viz（green/yellow/grey badges + 顶部 summary）
  - Export 产 schema-valid registry.edits.json（可校验：导出后 validate.py green）

用法：
    python html/gen_registry_review.py \\
        --draft  <abs path>   (必填 — registry.draft.json) \\
        --video  <abs path>   (必填 — 原视频，ffmpeg 抽代表帧用) \\
        --shots  <abs path>   (必填 — shots.json，frame_pos → 时间戳解析) \\
        --output <abs path>   (必填 — HTML 输出路径)
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# ============================================================================
# Module-level constants
# ============================================================================

# Three-tier colors (reuse gen_timeline_html.py GitHub-dark palette — CONTEXT D lock)
TIER_COLORS = {
    "auto_merge":   "#3fb950",  # green (>= 0.85)
    "review":       "#d29922",  # yellow (0.6 .. 0.85)
    "auto_distinct":"#8b949e",  # grey (< 0.6)
}

# Deterministic 152x85 grey-box placeholder SVG ("无缩略图").
# Used when ffmpeg thumbnail extraction fails (e.g. corrupt frame / non-video input).
# Encoded as data:image/svg+xml;base64,... so HTML stays self-contained.
# WARNING-1 fix: the verify block asserts on <img + cluster-thumb class (NOT 'data:image'),
# so this placeholder is robust to base64 wiring — both real png and svg placeholders pass.
_PLACEHOLDER_SVG = (
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmci"
    "IHdpZHRoPSIxNTIiIGhlaWdodD0iODUiPjxyZWN0IHdpZHRoPSIxNTIiIGhlaWdodD0iODUiIGZp"
    "bGw9IiMzMDM2M2QiLz48dGV4dCB4PSI3NiIgeT0iNDMiIGZvbnQtZmFtaWx5PSJzYW5zLXNlcmlm"
    "IiBmb250LXNpemU9IjEyIiBmaWxsPSIjOGI5NDllIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7pooTo"
    "p4jgppw8L3RleHQ+PC9zdmc+"
)

# Best-member quality ranking (mirror apply_edits.py QUALITY_RANK; high > medium > low > unusable).
_QUALITY_RANK = {"high": 0, "medium": 1, "low": 2, "unusable": 3}

# frame_pos keyword → shot-relative fraction
_FRAME_POS_FRACTIONS = {
    "first": 0.0, "25%": 0.25, "50%": 0.5, "75%": 0.75, "last": 1.0,
}


# ============================================================================
# Helpers (mirror apply_edits.py — small enough to inline; no cross-module dep)
# ============================================================================

def _resolve_frame_ts(shot_id, frame_pos, shots_meta):
    """frame_pos ('first'/'last'/'25%'/'50%'/'75%' 或 number) → 绝对秒数。

    与 registry/apply_edits.py:_resolve_frame_ts 同款逻辑。
    未知 shot_id → 0.0 (advisory；不阻塞抽帧)。
    """
    shot = next((s for s in shots_meta if s.get("id") == shot_id), None)
    if not shot:
        return 0.0
    start = shot.get("start_sec", 0.0)
    end = shot.get("end_sec", start)
    if isinstance(frame_pos, (int, float)):
        return float(frame_pos)
    fraction = _FRAME_POS_FRACTIONS.get(str(frame_pos), 0.5)
    return float(start) + float(end - start) * fraction


def _extract_frame_b64(video, ts):
    """ffmpeg 抽单帧 → base64 data URI。

    DIRECT copy of html/gen_shots_preview.py:24-39 pattern (arg-list subprocess, no shell mode).
    Returns "data:image/png;base64,..." on success; "" on failure (caller falls back
    to _PLACEHOLDER_SVG — Pitfall 2 prevention: HTML still rendered, no broken-img icon).
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", str(ts), "-i", video,
                        "-frames:v", "1", "-q:v", "2", "-vf", "scale=480:-1",
                        tmp, "-loglevel", "error"],
                       capture_output=True, timeout=10)
        if os.path.exists(tmp) and os.path.getsize(tmp) > 100:
            with open(tmp, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return "data:image/png;base64," + b64
        return ""
    except (subprocess.TimeoutExpired, OSError):
        return ""
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _best_member_ts(cluster, shots_meta):
    """挑 cluster 中 best member (最高 mask_quality) → 解析时间戳。

    无 quality 信号时取首 member。Returns float seconds.
    """
    members = cluster.get("members", []) or []
    if not members:
        return 0.0
    best = min(members,
               key=lambda m: _QUALITY_RANK.get(m.get("mask_quality", ""), 3))
    shot_id = best.get("shot_id")
    frame_pos = best.get("frame_pos", "first")
    return _resolve_frame_ts(shot_id, frame_pos, shots_meta)


def _default_name(cluster):
    """derive 默认展示名 from cluster_id prefix (char_ → 角色 NNN；prop_ → 道具 NNN)。"""
    cid = cluster["cluster_id"]
    if cid.startswith("char_"):
        return f"角色 {cid[-3:]}"
    if cid.startswith("prop_"):
        return f"道具 {cid[-3:]}"
    return cid


def _tier_sort_key(cluster):
    """Cosine-sorted review queue key: review tier first (mid-band hardest),
    then auto_merge, then auto_distinct. Within tier, lower mean_cosine first
    (closer to boundary = harder decision).

    Returns (priority, mean_cosine) tuple for sorted().
    """
    tier = cluster.get("tier", "review")
    mc = cluster.get("mean_cosine", 0.0)
    # priority 0 = review (surface first); 1 = auto_merge; 2 = auto_distinct
    priority = {"review": 0, "auto_merge": 1, "auto_distinct": 2}.get(tier, 0)
    return (priority, float(mc))


# ============================================================================
# HTML rendering
# ============================================================================

def _cluster_card_html(cluster, thumbnail_b64, index):
    """渲染单个 cluster card HTML。

    Args:
        cluster:        dict —— draft cluster。
        thumbnail_b64:  str —— base64 data URI；空串时 fallback 到 _PLACEHOLDER_SVG。
        index:          int —— card 序号（用于 tabindex 等）。
    """
    cid = cluster["cluster_id"]
    tier = cluster.get("tier", "review")
    mean_cosine = float(cluster.get("mean_cosine", 0.0))
    tier_color = TIER_COLORS.get(tier, TIER_COLORS["review"])
    default_name = _default_name(cluster)
    members = cluster.get("members", []) or []

    thumb_src = thumbnail_b64 if thumbnail_b64 else _PLACEHOLDER_SVG
    cosine_pct = max(0.0, min(1.0, mean_cosine)) * 100.0

    # members list items
    member_lis = []
    for m in members:
        mq = m.get("mask_quality", "unknown")
        member_lis.append(
            f'<li>shot {m.get("shot_id", "?")} · {m.get("frame_pos", "?")} '
            f'· <span class="quality-chip">{mq}</span></li>'
        )
    members_html = "\n".join(member_lis) if member_lis else "<li>(无 members)</li>"

    # IMPORTANT: this f-string is a Python f-string; literal { } in the inline JS
    # onclick handlers MUST be doubled ({{ }}) per gen_timeline_html.py convention.
    # We keep the onclick handlers minimal — JS logic is centralized in the <script> block.
    return f"""    <div class="cluster-card" id="card-{cid}" data-cluster-id="{cid}"
         data-tier="{tier}" data-mean-cosine="{mean_cosine:.4f}"
         data-default-name="{default_name}">
      <div class="card-thumb-wrap">
        <img src="{thumb_src}" class="cluster-thumb" alt="{cid} representative frame" loading="lazy">
      </div>
      <div class="card-body">
        <div class="card-header">
          <span class="cluster-id">{cid}</span>
          <span class="tier-badge" style="background:{tier_color}">{tier}</span>
          <span class="cosine-label">cos={mean_cosine:.3f}</span>
        </div>
        <div class="cosine-bar-container">
          <div class="cosine-bar" style="width:{cosine_pct:.1f}%; background:{tier_color}"></div>
        </div>
        <input type="text" class="cluster-name" value="{default_name}"
               placeholder="展示名" data-cluster-id="{cid}">
        <ul class="members-list">
{members_html}
        </ul>
        <div class="card-actions">
          <button class="action-button action-confirm" data-cluster-id="{cid}"
                  onclick="toggleConfirm('{cid}')">✓ Confirm</button>
          <button class="action-button action-reject" data-cluster-id="{cid}"
                  onclick="toggleReject('{cid}')">✗ Reject</button>
          <button class="action-button action-merge" data-cluster-id="{cid}"
                  onclick="mergeWith('{cid}')">↔ Merge</button>
          <button class="action-button action-split" data-cluster-id="{cid}"
                  onclick="splitCluster('{cid}')">✂ Split</button>
          <button class="action-button action-type" data-cluster-id="{cid}"
                  onclick="toggleType('{cid}')">🔄 Type</button>
        </div>
      </div>
    </div>
"""


def build_html(draft, video, shots_meta, asset_name):
    """生成完整 self-contained HTML string。

    Args:
        draft:      dict —— registry.draft.json 内容。
        video:      str —— 原视频路径（ffmpeg 抽帧用）。
        shots_meta: list[dict] —— shots.json。
        asset_name: str —— header 显示用 asset 名。

    Returns:
        str —— 完整 HTML（单文件；所有 CSS/JS/data inline）。
    """
    clusters = draft.get("clusters", []) or []

    # Three-tier summary counts
    n_merge = sum(1 for c in clusters if c.get("tier") == "auto_merge")
    n_review = sum(1 for c in clusters if c.get("tier") == "review")
    n_distinct = sum(1 for c in clusters if c.get("tier") == "auto_distinct")

    # Cosine-sorted: review tier first (mid-band hardest decisions surface first)
    sorted_clusters = sorted(clusters, key=_tier_sort_key)

    # Build cluster cards + review queue sidebar
    cards_html_parts = []
    queue_html_parts = []
    for i, cluster in enumerate(sorted_clusters):
        ts = _best_member_ts(cluster, shots_meta)
        thumb_b64 = _extract_frame_b64(video, ts)
        cards_html_parts.append(_cluster_card_html(cluster, thumb_b64, i))
        cid = cluster["cluster_id"]
        tier = cluster.get("tier", "review")
        mc = float(cluster.get("mean_cosine", 0.0))
        tier_color = TIER_COLORS.get(tier, TIER_COLORS["review"])
        cosine_pct = max(0.0, min(1.0, mc)) * 100.0
        queue_html_parts.append(
            f'    <a href="#card-{cid}" class="queue-item" data-tier="{tier}">'
            f'<span class="queue-id">{cid}</span>'
            f'<span class="queue-cos-bar" style="width:{cosine_pct:.1f}%; background:{tier_color}"></span>'
            f'<span class="queue-cos-num">{mc:.3f}</span></a>'
        )

    cards_html = "\n".join(cards_html_parts) if cards_html_parts else "<p>(空 draft —— 无 cluster 可审阅)</p>"
    queue_html = "\n".join(queue_html_parts) if queue_html_parts else "<p>(无)</p>"

    # Inline the draft JSON for client-side state bootstrap (no external fetch)
    draft_json = json.dumps(draft, ensure_ascii=False)

    # IMPORTANT: the entire HTML body below is an f-string. Literal { } in CSS / JS
    # blocks MUST be doubled to {{ }} to escape them (gen_timeline_html.py:131-941 convention).
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HITL 审阅 — {asset_name}</title>
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
.summary .pill.merge {{ color: #3fb950; border-color: #2ea043; }}
.summary .pill.review {{ color: #d29922; border-color: #9e6a03; }}
.summary .pill.distinct {{ color: #8b949e; }}

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
    border-left: 3px solid transparent;
    transition: background 0.15s;
}}
.queue-item:hover {{ background: #21262d; }}
.queue-item[data-tier="review"] {{ border-left-color: #d29922; }}
.queue-item[data-tier="auto_merge"] {{ border-left-color: #3fb950; }}
.queue-item[data-tier="auto_distinct"] {{ border-left-color: #8b949e; }}
.queue-id {{ font-family: monospace; color: #58a6ff; margin-right: 8px; }}
.queue-cos-num {{ float: right; color: #8b949e; font-family: monospace; }}

.cards-container {{
    flex: 1; padding: 16px;
    display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr));
    gap: 16px; align-content: start;
}}

/* ===== Cluster card ===== */
.cluster-card {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    overflow: hidden; display: flex;
    transition: border-color 0.15s, box-shadow 0.15s;
}}
.cluster-card:hover {{ border-color: #58a6ff; }}
.cluster-card.state-confirmed {{ border-color: #3fb950; box-shadow: 0 0 0 1px #3fb950; }}
.cluster-card.state-rejected {{ opacity: 0.45; border-color: #f85149; }}
.card-thumb-wrap {{ width: 152px; flex-shrink: 0; background: #0d1117; }}
.cluster-thumb {{ width: 100%; display: block; aspect-ratio: 16/9; object-fit: cover; }}
.card-body {{ flex: 1; padding: 10px 12px; min-width: 0; }}
.card-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.cluster-id {{ font-family: monospace; color: #58a6ff; font-size: 13px; font-weight: 700; }}
.tier-badge {{
    color: #0d1117; font-size: 10px; font-weight: 700;
    padding: 1px 6px; border-radius: 8px;
}}
.cosine-label {{ margin-left: auto; font-family: monospace; font-size: 11px; color: #8b949e; }}
.cosine-bar-container {{
    height: 4px; background: #21262d; border-radius: 2px;
    margin-bottom: 8px; overflow: hidden;
}}
.cosine-bar {{ height: 100%; transition: width 0.2s; }}
.cluster-name {{
    width: 100%; padding: 4px 8px; margin-bottom: 8px;
    background: #0d1117; color: #c9d1d9;
    border: 1px solid #30363d; border-radius: 4px;
    font-size: 13px;
}}
.cluster-name:focus {{ outline: none; border-color: #58a6ff; }}
.members-list {{
    list-style: none; margin-bottom: 8px;
    font-size: 11px; color: #8b949e;
    max-height: 80px; overflow-y: auto;
}}
.members-list li {{ padding: 1px 0; font-family: monospace; }}
.quality-chip {{
    display: inline-block; padding: 0 4px; border-radius: 3px;
    background: #21262d; font-size: 10px; color: #c9d1d9;
}}
.card-actions {{ display: flex; flex-wrap: wrap; gap: 4px; }}
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
  <h1>HITL 审阅 — {asset_name}</h1>
  <div class="summary">
    <span>📊 {len(clusters)} 簇</span>
    <span class="pill merge">🟢 {n_merge} auto-merge</span>
    <span class="pill review">🟡 {n_review} review</span>
    <span class="pill distinct">⚪ {n_distinct} auto-distinct</span>
    <span class="pill">cosine-sorted queue — 最难决定先审</span>
  </div>
</div>

<div class="app">
  <div class="review-queue">
    <h2>📋 审阅队列 (cosine-sorted)</h2>
{queue_html}
  </div>
  <div class="cards-container">
{cards_html}
  </div>
</div>

<div class="export-section">
  <div class="export-info">
    操作员：审阅上方 cluster，编辑名称，确认/拒绝，再点右侧导出 →
    得到 registry.edits.json，运行 registry/apply_edits.py 产 canonical 文件。
  </div>
  <button class="export-button" onclick="exportEdits()">📥 Export edits (registry.edits.json)</button>
</div>

<script>
// Bootstrap server-side data: original draft (for member lookup etc.)
const DRAFT = {draft_json};

// Operator-edits state (mutable; updated by toggle handlers)
const state = {{
    confirmIds: new Set(),       // cluster_id → confirmed
    rejectIds: new Set(),        // cluster_id → rejected
    renames: {{}},                // cluster_id → new name
    typeOverrides: {{}},          // cluster_id → "char" | "prop"
    mergeGroups: [],             // [[cid, cid, ...], ...]
    splits: {{}},                 // cid → [new_label, ...]
}};

// Pre-select auto_merge + auto_distinct as confirmed (Claude's Discretion lock per RESEARCH Q2):
// these tiers are high-confidence (>=0.85 or <0.6); reviewer can override.
// review tier (0.6-0.85) is left UNSELECTED — must be human-decided.
DRAFT.clusters.forEach(c => {{
    if (c.tier === 'auto_merge' || c.tier === 'auto_distinct') {{
        state.confirmIds.add(c.cluster_id);
    }}
}});

function applyVisualState() {{
    document.querySelectorAll('.cluster-card').forEach(card => {{
        const cid = card.dataset.clusterId;
        card.classList.remove('state-confirmed', 'state-rejected');
        const confirmBtn = card.querySelector('.action-confirm');
        const rejectBtn = card.querySelector('.action-reject');
        if (confirmBtn) confirmBtn.classList.remove('active');
        if (rejectBtn) rejectBtn.classList.remove('active');
        if (state.confirmIds.has(cid)) {{
            card.classList.add('state-confirmed');
            if (confirmBtn) confirmBtn.classList.add('active');
        }}
        if (state.rejectIds.has(cid)) {{
            card.classList.add('state-rejected');
            if (rejectBtn) rejectBtn.classList.add('active');
        }}
    }});
}}

function toggleConfirm(cid) {{
    if (state.confirmIds.has(cid)) {{
        state.confirmIds.delete(cid);
    }} else {{
        state.confirmIds.add(cid);
        state.rejectIds.delete(cid);  // mutually exclusive
    }}
    applyVisualState();
}}

function toggleReject(cid) {{
    if (state.rejectIds.has(cid)) {{
        state.rejectIds.delete(cid);
    }} else {{
        state.rejectIds.add(cid);
        state.confirmIds.delete(cid);
    }}
    applyVisualState();
}}

function toggleType(cid) {{
    // Flip char_ ↔ prop_ in typeOverrides
    const current = state.typeOverrides[cid];
    if (current === 'char') {{
        state.typeOverrides[cid] = 'prop';
    }} else if (current === 'prop') {{
        state.typeOverrides[cid] = 'char';
    }} else {{
        // Infer from cid prefix
        const prefix = cid.startsWith('char_') ? 'prop' : 'char';
        state.typeOverrides[cid] = prefix;
    }}
    const newType = state.typeOverrides[cid];
    alert(`Type override: ${{cid}} → ${{newType}}_ prefix (applied on export)`);
}}

function mergeWith(cid) {{
    const target = prompt(`合并 ${{cid}} 到哪个 cluster_id？(输入 canonical cluster_id，如 char_001)`);
    if (!target || target === cid) return;
    // Find or create a merge group containing both
    let group = state.mergeGroups.find(g => g.includes(cid) || g.includes(target));
    if (group) {{
        if (!group.includes(cid)) group.push(cid);
        if (!group.includes(target)) group.push(target);
    }} else {{
        // canonical = target (first); members appended
        state.mergeGroups.push([target, cid]);
    }}
    alert(`已记录合并：${{cid}} → ${{target}} (导出时生效)`);
}}

function splitCluster(cid) {{
    const labelsStr = prompt(`拆分 ${{cid}} 为 N 个新簇。输入新 label 列表，逗号分隔（≥2 个）：\n例如：少年, 老年`);
    if (!labelsStr) return;
    const labels = labelsStr.split(',').map(s => s.trim()).filter(Boolean);
    if (labels.length < 2) {{
        alert('需要至少 2 个 label 才能拆分');
        return;
    }}
    state.splits[cid] = labels;
    alert(`已记录拆分：${{cid}} → [${{labels.join(', ')}}] (apply_edits 分配新 ID：max+1)`);
}}

// Capture rename edits on input blur
document.addEventListener('blur', (e) => {{
    if (e.target && e.target.classList && e.target.classList.contains('cluster-name')) {{
        const cid = e.target.dataset.clusterId;
        const newVal = e.target.value.trim();
        const defaultName = e.target.placeholder !== '展示名' ? e.target.placeholder : null;
        // Only record if differs from the input's original default
        // (we set value=default_name on render; placeholder is just hint)
        // Always record current value — apply_edits treats renames as overrides.
        if (newVal) state.renames[cid] = newVal;
    }}
}}, true);

function exportEdits() {{
    // Capture current names from all cluster-name inputs (final state)
    document.querySelectorAll('.cluster-name').forEach(inp => {{
        const cid = inp.dataset.clusterId;
        const v = inp.value.trim();
        if (v) state.renames[cid] = v;
    }});

    // Build registry.edits.json per spec/schemas/registry-edits.schema.json
    const edits = {{
        merge_groups: state.mergeGroups.filter(g => g && g.length >= 2),
        splits: Object.keys(state.splits).reduce((acc, k) => {{
            acc[k] = state.splits[k];
            return acc;
        }}, {{}}),
        renames: {{ ...state.renames }},
        type_overrides: {{ ...state.typeOverrides }},
        confirm_ids: Array.from(state.confirmIds).sort(),
        reject_ids: Array.from(state.rejectIds).sort(),
        review_notes: `Exported from HITL review HTML on ${{new Date().toISOString()}}`,
    }};

    const blob = new Blob([JSON.stringify(edits, null, 2)], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'registry.edits.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}}

// Initial state application (pre-selections etc.)
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
            "HITL 审阅 HTML 生成器（CAST-06 first-class deliverable）。"
            "读取 registry.draft.json，ffmpeg 抽代表帧 inline base64，"
            "渲染 cluster cards + cosine-sorted queue + 三档 viz + Export edits 按钮。"
        ))
    ap.add_argument("--draft", required=True,
                    help="registry.draft.json 路径 (step_reid 产物)")
    ap.add_argument("--video", required=True,
                    help="原视频路径 (ffmpeg 抽代表帧用)")
    ap.add_argument("--shots", required=True,
                    help="shots.json 路径 (frame_pos → 时间戳解析)")
    ap.add_argument("--output", required=True,
                    help="输出 HTML 路径 (建议 <work-dir>/registry_review.html)")
    args = ap.parse_args()

    with open(args.draft, encoding="utf-8") as f:
        draft = json.load(f)
    with open(args.shots, encoding="utf-8") as f:
        shots_meta = json.load(f)

    # asset name: derive from --draft parent dir name (or basename) — advisory
    draft_path = Path(args.draft).resolve()
    asset_name = draft_path.parent.name or draft_path.stem

    html = build_html(draft, args.video, shots_meta, asset_name)

    # Atomic write (temp + os.replace; mirror apply_edits.py + export_asset.py pattern)
    tmp = args.output + ".tmp"
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, args.output)

    n_clusters = len(draft.get("clusters", []))
    print(f"[registry-review] wrote {args.output} ({n_clusters} clusters)")


if __name__ == "__main__":
    sys.exit(main())
