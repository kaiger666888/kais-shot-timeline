#!/usr/bin/env python3
"""GSRT render-back 提交器 v2 (T4 消费端渲染回测)

用法: 修改顶部 BASE 后 `python3 submit_renderback_v2.py >> renderback.log 2>&1`
依赖 manifest.json 结构见 golden-set-roundtrip-validation §T4。

教训固化 (2026-08-28 试点):
- KAP i2va 在 VRAM 不足时把 POST 挂在 gpuQueue (最长1800s), 期间不回包
- curl 超时重试 = 僵尸等待者风暴 (每重试一次堆一个, 全部会渲染)
=> v2: 提交只做一次 (curl -m 1900 覆盖锁等待); 空响应不重试, 转容器产物守望模式
- 产物提取绕 KAP output 404: docker cp comfyui-primary:/root/ComfyUI/output/
"""
import json, subprocess, time, sys, os

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"   # ← 按 episode 改
KAP = "http://127.0.0.1:10588"
CONTAINER = "comfyui-primary"
OUT = f"{BASE}/renders"
os.makedirs(OUT, exist_ok=True)

manifest = json.load(open(f"{BASE}/manifest.json"))
jobs_path = f"{BASE}/jobs.json"
if os.path.exists(jobs_path):
    jobs = json.load(open(jobs_path))
else:
    jobs = {str(s["shot_id"]): {"status": "pending", "prompt_id": None} for s in manifest}

def save_jobs():
    json.dump(jobs, open(jobs_path, "w"), indent=1)

def container_file(sid):
    """查容器内该镜产物 (含 _000NN 后缀), 返回最新文件名或 None"""
    r = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
        f"ls -t /root/ComfyUI/output/ | grep '^gsrt_rb_{sid}_' | head -1"],
        capture_output=True, text=True)
    return r.stdout.strip() or None

def submit_once(s):
    """单次提交, 长超时覆盖 KAP 锁等待 (最长1800s) + 管线提交时间"""
    prompt = s["reverse_prompt_under_test"] + " · strictly diegetic in-world sound, unscored scene"
    cmd = [
        "curl", "-s", "-m", "1900", "--noproxy", "*",
        "-X", "POST", f"{KAP}/api/production/minimax-h3/i2va",
        "-F", f"firstFrame=@{s['first_frame']}",
        "-F", f"lastFrame=@{s['last_frame']}",
        "-F", f"prompt={prompt}",
        "-F", "length=" + str(s["length"]),
        "-F", "profile=turbo",
        "-F", "seed=42",
        "-F", "resolution=1344x768",
        "-F", "projectId=901",
        "-F", f"filenamePrefix=gsrt_rb_{s['shot_id']}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1950)
    except subprocess.TimeoutExpired:
        return None, "(client timeout 1950s)"
    raw = r.stdout or "(empty)"
    try:
        d = json.loads(raw)
        pid = (d.get("data") or {}).get("promptId")
        if pid:
            return pid, raw[:200]
        return None, raw[:300]  # 业务错误 (如参数错误), 不重试
    except Exception:
        # 挂起超时无响应: 不重试! 请求可能已被 KAP 收下排队
        return None, "(no response — 可能已入队, 转守望模式)"

def poll_status(pid):
    r = subprocess.run(["curl", "-s", "-m", "10", "--noproxy", "*",
        f"{KAP}/api/production/minimax-h3/status/{pid}"],
        capture_output=True, text=True)
    try:
        return (json.loads(r.stdout).get("data") or {}).get("status", "?")
    except Exception:
        return "?"

def extract(sid):
    fname = container_file(sid)
    if not fname:
        return False, None
    dst = f"{OUT}/gsrt_rb_{sid}.mp4"
    r = subprocess.run(["docker", "cp", f"{CONTAINER}:/root/ComfyUI/output/{fname}", dst],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return True, dst
    return False, None

def mark(sid, status, **kw):
    jobs[str(sid)].update(status=status, **kw)
    save_jobs()
    print(f"shot {sid} -> {status} {kw}", flush=True)

# ─── Phase A: 提交/守望决策 ───
for s in manifest:
    sid = s["shot_id"]; j = jobs.get(str(sid), {})
    if j.get("status") == "done" and j.get("file") and os.path.exists(j["file"]):
        continue
    if j.get("status") == "rendering" and j.get("prompt_id"):
        continue  # Phase B 统一轮询
    if not j.get("prompt_id"):
        mark(sid, "submitting")
        pid, info = submit_once(s)
        if pid:
            mark(sid, "rendering", prompt_id=pid)
        else:
            mark(sid, "watching", submit_info=info)

# ─── Phase B: 统一等待循环 (状态轮询 + 容器产物守望) ───
t0 = time.time()
while True:
    remaining = 0
    for s in manifest:
        sid = s["shot_id"]; j = jobs.get(str(sid), {})
        st = j.get("status")
        if st == "done":
            continue
        remaining += 1
        ok, path = extract(sid)   # 产物先到先收 (rendering/watching 通吃)
        if ok:
            mark(sid, "done", file=path)
            remaining -= 1
            continue
        if st == "rendering" and j.get("prompt_id"):
            ps = poll_status(j["prompt_id"])
            if ps in ("failed", "error"):
                mark(sid, "failed", poll=ps)
                remaining -= 1
    if remaining == 0:
        break
    if time.time() - t0 > 7200:  # 全局 2h 上限
        print("GLOBAL_TIMEOUT", flush=True)
        break
    time.sleep(30)

print("RENDERBACK_V2_DONE", flush=True)
for s in manifest:
    j = jobs[str(s["shot_id"])]
    print(f"  shot {s['shot_id']}: {j['status']} {j.get('file','')}", flush=True)
