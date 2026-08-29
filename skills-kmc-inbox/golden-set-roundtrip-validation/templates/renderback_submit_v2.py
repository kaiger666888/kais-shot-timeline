#!/usr/bin/env python3
"""H3 render-back 批量提交器 v2 模板 (从 GSRT 试点提炼, 复制后改 BASE/manifest 即用)

核心纪律 (2026-08-28 实战教训):
- KAP i2va 在 VRAM 不足时把 POST 挂在 gpuQueue (每20s重试, 最长1800s), 期间不回包
- 空响应重试 = 僵尸等待者风暴 (每次堆一个, 全部会渲染) → 提交只发一次
- 产物提取绕 KAP output 404: docker cp comfyui-primary:/root/ComfyUI/output/
- 帧数 n%17==5 网格; duration<4s 用 length 绕; profile 只收 turbo|native-sage
"""
import json, subprocess, time, sys, os

BASE = "/path/to/renderback"          # ← 改: 含 manifest.json 的目录
CONTAINER = "comfyui-primary"          # ← 改: ComfyUI 容器名
PREFIX_FMT = "gsrt_rb_{sid}"           # ← 改: filenamePrefix 模板
OUT = f"{BASE}/renders"
os.makedirs(OUT, exist_ok=True)

manifest = json.load(open(f"{BASE}/manifest.json"))
jobs_path = f"{BASE}/jobs.json"
jobs = json.load(open(jobs_path)) if os.path.exists(jobs_path) else {
    str(s["shot_id"]): {"status": "pending"} for s in manifest}

def save_jobs():
    json.dump(jobs, open(jobs_path, "w"), indent=1)

def container_file(sid):
    r = subprocess.run(["docker","exec",CONTAINER,"bash","-c",
        f"ls -t /root/ComfyUI/output/ | grep '^{PREFIX_FMT.format(sid=sid)}_' | head -1"],
        capture_output=True, text=True)
    return r.stdout.strip() or None

def submit_once(s):
    """单次提交, 长超时覆盖 KAP 锁等待; 无响应不重试 (可能已入队)"""
    prompt = s["prompt"] + " · strictly diegetic in-world sound, unscored scene"
    cmd = ["curl","-s","-m","1900","--noproxy","*",
        "-X","POST","http://127.0.0.1:10588/api/production/minimax-h3/i2va",
        "-F",f"firstFrame=@{s['first_frame']}","-F",f"lastFrame=@{s['last_frame']}",
        "-F",f"prompt={prompt}","-F","length="+str(s["length"]),
        "-F","profile=turbo","-F","seed=42","-F","resolution=1344x768",
        "-F","projectId=901","-F",f"filenamePrefix={PREFIX_FMT.format(sid=s['shot_id'])}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1950)
    except subprocess.TimeoutExpired:
        return None, "(client timeout)"
    raw = r.stdout or "(empty)"
    try:
        d = json.loads(raw)
        pid = (d.get("data") or {}).get("promptId")
        return (pid, raw[:200]) if pid else (None, raw[:300])
    except Exception:
        return None, "(no response — 可能已入队, 转守望模式)"

def extract(sid):
    fname = container_file(sid)
    if not fname: return False, None
    dst = f"{OUT}/{PREFIX_FMT.format(sid=sid)}.mp4"
    r = subprocess.run(["docker","cp",f"{CONTAINER}:/root/ComfyUI/output/{fname}",dst],
                       capture_output=True, text=True)
    return (r.returncode == 0 and os.path.getsize(dst) > 10000), dst

# Phase A: 未完成镜头提交一次 (失败转守望, 不硬退)
for s in manifest:
    sid = str(s["shot_id"]); j = jobs.setdefault(sid, {})
    if j.get("status") == "done" and os.path.exists(j.get("file","")): continue
    if j.get("prompt_id"): continue  # 已有 pid, Phase B 轮询
    pid, info = submit_once(s)
    if pid:
        j.update(status="rendering", prompt_id=pid)
    else:
        j.update(status="watching", submit_info=info)
    save_jobs(); print(f"shot {sid}: {j['status']}", flush=True)

# Phase B: 统一等待 (产物先到先收 + KAP 状态兜底)
t0 = time.time()
while True:
    remaining = 0
    for s in manifest:
        sid = str(s["shot_id"]); j = jobs[sid]
        if j.get("status") == "done": continue
        remaining += 1
        ok, path = extract(sid)
        if ok:
            j.update(status="done", file=path); save_jobs()
            remaining -= 1; print(f"shot {sid} done -> {path}", flush=True)
            continue
        if j.get("prompt_id"):
            r = subprocess.run(["curl","-s","-m","10","--noproxy","*",
                f"http://127.0.0.1:10588/api/production/minimax-h3/status/{j['prompt_id']}"],
                capture_output=True, text=True)
            try: st = (json.loads(r.stdout).get("data") or {}).get("status","?")
            except Exception: st = "?"
            if st in ("failed","error"):
                j.update(status="failed"); save_jobs()
                remaining -= 1; print(f"shot {sid} {st}", flush=True)
    if remaining == 0: break
    if time.time() - t0 > 7200:
        print("GLOBAL_TIMEOUT"); break
    time.sleep(30)

print("ALL_DONE")
