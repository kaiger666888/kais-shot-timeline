#!/usr/bin/env python3
"""GSRT T4 尾段补测 — manifest_v8 4镜串行渲染. 唯一变量=prompt, 引擎臂恒定.
提交纪律: 单次提交不重试(防gpuQueue僵尸风暴), 空响应转容器产物守望.
tmux提交: tmux new-session -d -s gsrt_t4 "python3 /data/workspace/kais-shot-timeline/gsrt/renderback/run_t4_tail.py > /data/workspace/kais-shot-timeline/gsrt/renderback/t4_tail.log 2>&1"
"""
import json, subprocess, time, os, sys

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
OUT = f"{BASE}/renders_iter"
os.makedirs(OUT, exist_ok=True)
manifest = json.load(open(f"{BASE}/manifest_v8.json"))
KAP = "http://127.0.0.1:10588/api/production/minimax-h3/i2va"

results = {}
for m in manifest:
    sid = m["shot_id"]
    prefix = m["filenamePrefix"]
    if sid in results:
        continue
    print(f"=== [{time.strftime('%H:%M:%S')}] shot{sid} submit (len={m['length']}) ===", flush=True)
    cmd = ["curl", "-s", "-m", "1900", "--noproxy", "*",
        "-X", "POST", KAP,
        "-F", f"firstFrame=@{m['first_frame']}",
        "-F", f"lastFrame=@{m['last_frame']}",
        "-F", f"prompt={m['full_prompt']}",
        "-F", f"length={m['length']}",
        "-F", f"profile={m['profile']}",
        "-F", f"seed={m['seed']}",
        "-F", f"resolution={m['resolution']}",
        "-F", f"projectId={m['projectId']}",
        "-F", f"filenamePrefix={prefix}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1950)
        resp = (r.stdout or "(empty)")[:150]
    except subprocess.TimeoutExpired:
        resp = "(submit timeout 1950s — 转容器守望)"
    print(f"    submit resp: {resp}", flush=True)

    # 容器产物守望（先到先收，30s轮询；每镜上限25min）
    t0 = time.monotonic()
    got = None
    while time.monotonic() - t0 < 1500:
        q = subprocess.run(["docker", "exec", "comfyui-primary", "bash", "-c",
            f"ls -t /root/ComfyUI/output/ | grep '^{prefix}_' | head -1"],
            capture_output=True, text=True)
        f = q.stdout.strip()
        if f:
            dst = f"{OUT}/{f}"
            if not os.path.exists(dst):
                subprocess.run(["docker", "cp", f"comfyui-primary:/root/ComfyUI/output/{f}", dst],
                    capture_output=True, text=True)
            if os.path.exists(dst) and os.path.getsize(dst) > 10000:
                # 等2分钟确认渲染已完成（文件大小稳定）再收
                time.sleep(10)
                sz1 = os.path.getsize(dst)
                time.sleep(110)
                subprocess.run(["docker", "cp", f"comfyui-primary:/root/ComfyUI/output/{f}", dst],
                    capture_output=True, text=True)
                sz2 = os.path.getsize(dst)
                if sz2 >= sz1:
                    got = dst
                    break
        time.sleep(30)
    results[sid] = got
    print(f"    [{time.strftime('%H:%M:%S')}] shot{sid}: {'DONE ' + got if got else 'TIMEOUT_NO_OUTPUT'}", flush=True)

print("\n=== SUMMARY ===", flush=True)
for sid, p in results.items():
    print(f"shot{sid}: {p or 'FAILED'}", flush=True)
json.dump(results, open(f"{BASE}/t4_tail_results.json", "w"), indent=1)
sys.exit(0 if all(results.values()) else 3)
