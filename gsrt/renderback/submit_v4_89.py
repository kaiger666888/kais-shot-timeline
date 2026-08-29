#!/usr/bin/env python3
"""GSRT v4 — shot89 手术重跑 (假收敛返工). 唯一变量=prompt (显式鞘→刃交接)."""
import json, subprocess, time, os, sys

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
OUT = f"{BASE}/renders_iter"
shot = [s for s in json.load(open(f"{BASE}/manifest_v7.json")) if s["shot_id"] == 89][0]
prompt = shot["prompt_v4"]
full_prompt = prompt + " · strictly diegetic in-world sound, unscored scene"

cmd = ["curl", "-s", "-m", "1900", "--noproxy", "*",
    "-X", "POST", "http://127.0.0.1:10588/api/production/minimax-h3/i2va",
    "-F", f"firstFrame=@{shot['first_frame']}",
    "-F", f"lastFrame=@{shot['last_frame']}",
    "-F", f"prompt={full_prompt}",
    "-F", "length=90",
    "-F", "profile=turbo",
    "-F", "seed=42",
    "-F", "resolution=1344x768",
    "-F", "projectId=901",
    "-F", "filenamePrefix=gsrt_v4_89",
]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=1950)
print("submit resp:", (r.stdout or "(empty)")[:200], flush=True)

# 守望容器产物
t0 = time.monotonic()
while time.monotonic() - t0 < 1500:
    q = subprocess.run(["docker", "exec", "comfyui-primary", "bash", "-c",
        "ls -t /root/ComfyUI/output/ | grep '^gsrt_v4_89_' | head -1"],
        capture_output=True, text=True)
    f = q.stdout.strip()
    if f:
        dst = f"{OUT}/{f}"
        subprocess.run(["docker", "cp", f"comfyui-primary:/root/ComfyUI/output/{f}", dst],
            capture_output=True, text=True)
        if os.path.exists(dst) and os.path.getsize(dst) > 10000:
            print("DONE", dst, flush=True)
            sys.exit(0)
    time.sleep(20)
print("TIMEOUT_NO_OUTPUT", flush=True)
sys.exit(1)
