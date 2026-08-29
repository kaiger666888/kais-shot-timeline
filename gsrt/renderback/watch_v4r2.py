#!/usr/bin/env python3
import subprocess, time, os, sys
OUT = "/data/workspace/kais-shot-timeline/gsrt/renderback/renders_iter"
t0 = time.monotonic()
while time.monotonic() - t0 < 1800:
    q = subprocess.run(["docker","exec","comfyui-primary","bash","-c",
        "ls -t /root/ComfyUI/output/ | grep '^gsrt_v4r2_89_' | head -1"],
        capture_output=True, text=True)
    f = q.stdout.strip()
    if f:
        dst = f"{OUT}/{f}"
        subprocess.run(["docker","cp",f"comfyui-primary:/root/ComfyUI/output/{f}",dst],
            capture_output=True, text=True)
        if os.path.exists(dst) and os.path.getsize(dst) > 10000:
            print("DONE", dst, flush=True); sys.exit(0)
    time.sleep(20)
print("TIMEOUT", flush=True)
