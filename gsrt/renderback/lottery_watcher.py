
#!/usr/bin/env python3
"""watcher: 等 8 个 lottery mp4 全部落盘 或 队列排空但不足8个 (异常早退)"""
import json, subprocess, time, sys

BASE = "http://127.0.0.1:8188"
EXPECT = 8
t0 = time.time()
last_report = 0
while time.time() - t0 < 5400:  # 90min 上限
    try:
        q = json.loads(subprocess.run(["curl","-s","-m","8",f"{BASE}/queue"],capture_output=True,text=True).stdout)
    except Exception:
        time.sleep(60); continue
    r = subprocess.run(["docker","exec","comfyui-primary","ls","/root/ComfyUI/output"],capture_output=True,text=True)
    files = [f for f in r.stdout.split() if f.startswith("gsrt_a2v_s89_lot") and f.endswith(".mp4") and "-audio" not in f]
    run, pend = len(q.get("queue_running",[])), len(q.get("queue_pending",[]))
    now = time.time()
    if now - last_report > 600:  # 每10分钟报一次进度
        print(f"[{int((now-t0)/60)}min] done={len(files)}/{EXPECT} running={run} pending={pend}", flush=True)
        last_report = now
    if len(files) >= EXPECT and run == 0 and pend == 0:
        print(f"ALL_DONE: {len(files)} files after {int((now-t0)/60)}min", flush=True)
        sys.exit(0)
    if run == 0 and pend == 0 and len(files) > 0 and len(files) < EXPECT:
        print(f"PARTIAL: queue drained with only {len(files)}/{EXPECT} — some renders failed", flush=True)
        sys.exit(2)
    time.sleep(45)
print("TIMEOUT after 90min", flush=True)
sys.exit(3)

