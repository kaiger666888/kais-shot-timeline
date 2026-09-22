#!/usr/bin/env python3
# P2 拆件重标注 (0922): G2_R_039(39a)/G2_R_040(39b) 新窗语义, 走 GLM 视觉链(p2_annotate_runner_v2 同款 prompt/解析)
#   帧已抽: frames_p2_97/G2_R_039_{1,2,3}.jpg / G2_R_040_{1,2,3}.jpg (新窗 前/中/后)
#   产物: p2_reannotation.jsonl 追加 → 复用 p2_backfill 逻辑回填 evidence_packs_v2_98phys
import json, subprocess, os, re, sys, time

GSRT = "/data/workspace/kais-shot-timeline/gsrt"
FR = f"{GSRT}/frames_p2_97"
OUTJ = f"{GSRT}/p2_reannotation_rev5.jsonl"
ITEMS = [
    ("G2_R_039", [f"{FR}/G2_R_039_1.jpg", f"{FR}/G2_R_039_2.jpg", f"{FR}/G2_R_039_3.jpg"], [112.1, 112.4333], "split_from_kst_39"),
    ("G2_R_040", [f"{FR}/G2_R_040_1.jpg", f"{FR}/G2_R_040_2.jpg", f"{FR}/G2_R_040_3.jpg"], [112.4333, 112.9333], "merged_kst_39_40"),
]
BY = {s: (f, w, lin) for s, f, w, lin in ITEMS}

def clean_json_text(txt):
    t = txt.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    s = t.find("["); e = t.rfind("]")
    return t[s:e+1] if 0 <= s < e else None

def loose_parse(txt):
    cand = clean_json_text(txt)
    if cand is None:
        return None
    try:
        return json.loads(cand)
    except json.JSONDecodeError:
        pass
    def esc_str(m):
        return '"' + m.group(1).replace("\n", " ").replace("\r", " ").replace("\t", " ") + '"'
    fixed = re.sub(r'"((?:[^"\\]|\\.)*)"', esc_str, cand)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None

done = set()
if os.path.exists(OUTJ):
    for line in open(OUTJ):
        if line.strip():
            try: done.add(json.loads(line)["shot_id"])
            except Exception: pass
todo = [(s, f) for s, f, _, _ in ITEMS if s not in done]
print("待标:", [s for s, _ in todo])

SCHEMA = ('{"shot_id":"...","shot_scale":"大远景|远景|全景|中景|近景|特写|大特写",'
          '"camera_primitive":"static|pan|tilt|dolly_in|dolly_out|tracking|handheld|crane_up|crane_down|whip_pan",'
          '"camera_speed":"slow|medium|fast","subjects":"画面主体角色(中文)",'
          '"action_detail":"一句话动作描述(中文)","is_jump_cut_split":"该镜是否像是从同一长镜里被人工切出的同构图段(是/否)"}')
prompt_parts = ["任务: 逐镜标注动画视频的镜头语义。每个镜有3张帧图(前/中/后)。对每个镜输出一行JSON(数组内):",
                SCHEMA,
                "背景: 这些镜刚从旧长镜按切点拆分, 需按新窗帧重新判定语义。字符串值内禁止换行。只输出JSON数组, 无其他文字。逐镜条目:"]
for s, f in todo:
    prompt_parts.append(f"镜 {s}: 帧图 {f[0]} / {f[1]} / {f[2]}")
prompt = "\n".join(prompt_parts)

env = dict(os.environ); env["CLAUDE_CONFIG_DIR"] = "/home/kai/.claude-glm"
ok = False
for attempt in range(3):
    try:
        r = subprocess.run("claude -p --model glm-4.6 --allowedTools Read -",
                           input=prompt, capture_output=True, text=True, timeout=420, env=env, shell=True)
        arr = loose_parse(r.stdout or "")
        if isinstance(arr, list):
            got = {x.get("shot_id"): x for x in arr if isinstance(x, dict)}
            with open(OUTJ, "a") as outf:
                for s, f, win, lin in ITEMS:
                    if s in got and s in BY:
                        item = got[s]
                        item["video_time"] = win
                        item["lineage"] = lin
                        item["reannotation_source"] = "rev5_split_0922"
                        outf.write(json.dumps(item, ensure_ascii=False) + "\n")
            ok = True
            print("标注完成:", [x.get("shot_id") for x in arr])
            for x in arr:
                print(" ", json.dumps(x, ensure_ascii=False)[:220])
            break
        print(f"attempt{attempt}: unparseable, head={(r.stdout or '')[:150]!r}")
    except Exception as ex:
        print(f"attempt{attempt}: EXC {str(ex)[:150]}")
    time.sleep(15)
sys.exit(0 if ok else 1)
