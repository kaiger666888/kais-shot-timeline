#!/usr/bin/env python3
"""从 prompts.json + frames.json 生成分镜 prompt 审阅 HTML。

卡片式布局:每镜一张卡 —— 首尾帧缩略图 + 结构化字段(主体/动作/镜头/场景/光影/风格)
+ 完整 prompt_text(一键复制)。深色主题,与 gen_shots_preview.py 一致。

用法:
  python html/gen_prompts_html.py \
      --prompts output/<stem>/prompts.json \
      --frames output/<stem>/frames.json \
      [--transcript output/<stem>/transcript.json] \
      [--output output/<stem>/prompts.html] [--ep-name ep01]
"""
import argparse
import html as html_mod
import json
import os
from pathlib import Path

CSS = """<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; }

.header { position: sticky; top: 0; z-index: 200; background: #161b22; border-bottom: 1px solid #30363d;
          display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 10px 20px; }
.header h1 { font-size: 18px; color: #58a6ff; }
.stats { color: #8b949e; font-size: 13px; }
.badge { background: #1f6feb; color: white; font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.search-box { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; padding: 5px 10px;
              border-radius: 6px; font-size: 13px; width: 220px; outline: none; }
.search-box:focus { border-color: #58a6ff; }
.tool-btn { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 5px 12px;
            border-radius: 6px; cursor: pointer; font-size: 12px; }
.tool-btn:hover { border-color: #58a6ff; }

.prompts-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; padding: 16px;
                max-width: 1800px; margin: 0 auto; }
@media (max-width: 900px) { .prompts-grid { grid-template-columns: 1fr; } }

.shot-card { background: #161b22; border: 2px solid #30363d; border-radius: 10px; overflow: hidden; transition: border-color 0.2s; }
.shot-card:hover { border-color: #58a6ff; }

.shot-header { display: flex; justify-content: space-between; align-items: center;
               padding: 6px 12px; background: rgba(0,0,0,0.3); }
.shot-num { color: #58a6ff; font-size: 14px; font-weight: 700; }
.shot-dur { color: #8b949e; font-size: 11px; }

.frames { display: flex; gap: 3px; padding: 6px 8px 0; }
.frame { flex: 1; position: relative; }
.frame img { width: 100%; display: block; aspect-ratio: 16/9; object-fit: cover; border-radius: 4px; }
.frame-label { position: absolute; bottom: 4px; left: 4px; background: rgba(0,0,0,0.75);
               color: #aaa; font-size: 10px; padding: 1px 6px; border-radius: 3px; }

.dialogue { margin: 8px 12px 0; padding: 6px 10px; background: rgba(210,153,34,0.08);
            border-left: 3px solid #d29922; border-radius: 4px; font-size: 12.5px;
            line-height: 1.6; color: #e3b341; }
.dialogue::before { content: '💬 '; }

.fields { padding: 8px 12px 0; }
.field { display: flex; gap: 8px; margin-bottom: 5px; font-size: 12px; line-height: 1.55; }
.field .k { flex: 0 0 34px; color: #8b949e; font-weight: 600; }
.field .v { color: #c9d1d9; }

.prompt-box { margin: 8px 12px 12px; background: #0d1117; border: 1px solid #30363d;
              border-left: 3px solid #1f6feb; border-radius: 6px; padding: 8px 10px;
              display: flex; gap: 10px; align-items: flex-start; }
.prompt-text { flex: 1; font-size: 13px; line-height: 1.65; color: #7ee787; user-select: all; }
.copy-btn { flex: 0 0 auto; background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
            padding: 4px 10px; border-radius: 5px; cursor: pointer; font-size: 12px; white-space: nowrap; }
.copy-btn:hover { border-color: #58a6ff; color: #58a6ff; }
.copy-btn.copied { border-color: #3fb950; color: #3fb950; }

.hidden { display: none !important; }
</style>"""

JS = """<script>
const PROMPTS = __PROMPTS_JSON__;

function copyText(text, btn) {
    const done = () => {
        const old = btn.textContent;
        btn.textContent = '✅ 已复制';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = old; btn.classList.remove('copied'); }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
        fallbackCopy(text, done);
    }
}

function fallbackCopy(text, done) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); done(); } catch (e) {}
    document.body.removeChild(ta);
}

function copyPrompt(shotId, btn) {
    const p = PROMPTS.find(p => p.shot_id === shotId);
    if (p) copyText(p.prompt_text, btn);
}

function copyAll(btn) {
    const text = PROMPTS.map(p =>
        `#${p.shot_id} (${p.start_sec.toFixed(1)}s→${p.end_sec.toFixed(1)}s)\\n${p.prompt_text}`
    ).join('\\n\\n');
    copyText(text, btn);
}

function filterCards(q) {
    q = q.trim().toLowerCase();
    document.querySelectorAll('.shot-card').forEach(card => {
        card.classList.toggle('hidden', q !== '' && !card.textContent.toLowerCase().includes(q));
    });
}
</script>"""

FIELD_LABELS = (
    ("subject", "主体"),
    ("action", "动作"),
    ("camera", "镜头"),
    ("scene", "场景"),
    ("lighting", "光影"),
    ("style", "风格"),
)


def esc(s) -> str:
    return html_mod.escape(str(s or ""), quote=True)


def main():
    ap = argparse.ArgumentParser(description="分镜 prompt 审阅 HTML 生成器")
    ap.add_argument("--prompts", required=True, help="prompts.json(merge_prompts.py 产物)")
    ap.add_argument("--frames", required=True, help="frames.json(首尾帧 base64)")
    ap.add_argument("--transcript", default=None,
                    help="transcript.json(Whisper 转录),按时间对齐到镜头显示台词")
    ap.add_argument("--output", default=None,
                    help="输出 HTML 路径(默认与 prompts.json 同目录 prompts.html)")
    ap.add_argument("--ep-name", default=None, help="标题名(默认 prompts.json 所在目录名)")
    args = ap.parse_args()

    with open(args.prompts, encoding="utf-8") as f:
        prompts = json.load(f)
    with open(args.frames, encoding="utf-8") as f:
        frames = {e["id"]: e for e in json.load(f)}

    # 台词:transcript segment 按起点落入镜头区间对齐(与 gen_timeline_html.py 同规则)
    dialogue_by_id = {}
    if args.transcript and os.path.exists(args.transcript):
        with open(args.transcript, encoding="utf-8") as f:
            segments = json.load(f).get("segments", [])
        for p in prompts:
            texts = [seg.get("text", "").strip() for seg in segments
                     if p["start_sec"] <= seg.get("start", 0) < p["end_sec"]]
            dialogue_by_id[p["shot_id"]] = " ".join(t for t in texts if t)

    out_html = args.output or os.path.join(
        os.path.dirname(os.path.abspath(args.prompts)), "prompts.html")
    ep_name = args.ep_name or Path(os.path.dirname(os.path.abspath(args.prompts))).name

    total_duration = prompts[-1]["end_sec"] if prompts else 0

    cards = ""
    for p in prompts:
        sid = p["shot_id"]
        fr = frames.get(sid, {})
        fields_html = "".join(
            f'      <div class="field"><span class="k">{label}</span>'
            f'<span class="v">{esc(p.get(key))}</span></div>\n'
            for key, label in FIELD_LABELS)
        dialogue = dialogue_by_id.get(sid, "")
        dialogue_html = (f'    <div class="dialogue">{esc(dialogue)}</div>\n'
                         if dialogue else "")
        cards += f"""  <div class="shot-card" id="shot-{sid}">
    <div class="shot-header"><span class="shot-num">#{sid}</span><span class="shot-dur">{p['start_sec']:.1f}s → {p['end_sec']:.1f}s · {p['duration']:.1f}s</span></div>
    <div class="frames"><div class="frame"><img src="{fr.get('first_frame', '')}" loading="lazy"><span class="frame-label">首帧</span></div><div class="frame"><img src="{fr.get('last_frame', '')}" loading="lazy"><span class="frame-label">尾帧</span></div></div>
{dialogue_html}    <div class="fields">
{fields_html}    </div>
    <div class="prompt-box"><div class="prompt-text">{esc(p.get('prompt_text'))}</div><button class="copy-btn" onclick="copyPrompt({sid}, this)">📋 复制</button></div>
  </div>
"""

    # 嵌入 JS 用的精简数据(不含图片)
    prompts_js = json.dumps(
        [{k: p[k] for k in ("shot_id", "start_sec", "end_sec", "prompt_text")}
         for p in prompts],
        ensure_ascii=False).replace("</", "<\\/")
    js_block = JS.replace("__PROMPTS_JSON__", prompts_js)

    n_dialogue = sum(1 for v in dialogue_by_id.values() if v)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分镜 Prompt - {esc(ep_name)}</title>
{CSS}
</head>
<body>

<div class="header">
    <h1>🎬 {esc(ep_name)}</h1>
    <span class="badge">prompt 反推</span>
    <div class="stats">{len(prompts)} 镜 · 总时长 {total_duration:.1f}s · 台词 {n_dialogue} 镜</div>
    <div class="toolbar">
        <input class="search-box" type="text" placeholder="🔍 搜索镜头 / 角色 / 关键词…" oninput="filterCards(this.value)">
        <button class="tool-btn" onclick="copyAll(this)">📋 复制全部 prompt</button>
    </div>
</div>

<div class="prompts-grid">
{cards}</div>

{js_block}
</body>
</html>"""

    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    size_mb = os.path.getsize(out_html) / 1024 / 1024
    print(f"HTML: {out_html} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
