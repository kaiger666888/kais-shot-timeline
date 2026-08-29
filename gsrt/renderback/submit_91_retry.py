#!/usr/bin/env python3
"""shot91 重提 (vram_insufficient 400 拒绝后的重跑) + 容器守望."""
import json, subprocess, time, os, sys

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
m = [x for x in json.load(open(f"{BASE}/manifest_v8.json")) if x["shot_id"] == 91][0]
prefix = "gsrt_t4_91b"
print(f"[{time.strftime('%H:%M:%S')}] shot91 retry submit (len={m['length']})", flush=True)
cmd = ["curl", "-s", "-m", "1900", "--noproxy", "*",
    "-X", "POST", "http://127.0.0.1:10588/api/production/minimax-h3/i2va",
    "-F", f"firstFrame=@{m['first_frame']}",
    "-F", f"lastFrame=@{m['last_frame']}",
    "-F", f"prompt={m['full_prompt']}",
    "-F", f"length={m['length']}",
    "-F", f"profile={m['profile']}",
    "-F", f"seed={m['seed']}",
    "-F", f"resolution={m['resolution']}",
    "-F", f"projectId={m['projectId']}",
    "-F", f"filenamePrefix={prefix}"]
try:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1950)
    print("submit resp:", (r.stdout or "(empty)")[:200], flush=True)
except subprocess.TimeoutExpired:
    print("submit timeout -> container watch", flush=True)

t0 = time.monotonic()
while time.monotonic() - t0 < 1800:
    q = subprocess.run(["docker", "exec", "comfyui-primary", "bash", "-c",
        f"ls -t /root/ComfyUI/output/ | grep '^{prefix}_' | head -1"], capture_output=True, text=True)
    f = q.stdout.strip()
    if f:
        dst = f"{BASE}/renders_iter/{f}"
        time.sleep(15)
        subprocess.run(["docker", "cp", f"comfyui-primary:/root/ComfyUI/output/{f}", dst], capture_output=True)
        time.sleep(110)
        subprocess.run(["docker", "cp", f"comfyui-primary:/root/ComfyUI/output/{f}", dst], capture_output=True)
        if os.path.exists(dst) and os.path.getsize(dst) > 100000:
            print("DONE", dst, flush=True)
            json.dump({"91": dst}, open(f"{BASE}/t4_91b_result.json", "w"))
            sys.exit(0)
    time.sleep(25)
print("TIMEOUT", flush=True)
sys.exit(1)
