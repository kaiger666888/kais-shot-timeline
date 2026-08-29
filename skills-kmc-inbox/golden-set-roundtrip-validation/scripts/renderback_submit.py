#!/usr/bin/env python3
"""GSRT render-back 提交器 (T4 配套, 参数化 v2, 2026-08-28 试点验证)

关键纪律 (违反 = 僵尸等待者风暴):
- KAP gpuQueue VRAM 门会收下 POST 挂起不回包 (每条最长 1800s, free VRAM < 18GB 时触发)
- 提交只发一次 (--submit-timeout 覆盖最长锁等待); 空响应**不重试** (每次重试堆一个僵尸,
  放行后全部会渲染 → 同镜重复渲染 N 份), 转**容器产物守望模式**
- 产物落容器内 (KAP output 路径 404), docker cp 提取

manifest 条目字段: shot_id, first_frame, last_frame, length, reverse_prompt_under_test
jobs.json 持久化状态: done(rendering→done 含 file) / rendering / watching / failed
可断点续跑: done 且 file 存在的镜自动跳过。

用法:
  python3 renderback_submit.py --manifest gsrt/renderback/manifest.json \
      --jobs gsrt/renderback/jobs.json --out gsrt/renderback/renders \
      --prefix gsrt_rb [--container comfyui-primary] [--kap http://127.0.0.1:10588]
"""
import argparse, json, os, subprocess, time

ap = argparse.ArgumentParser()
ap.add_argument("--manifest", required=True)
ap.add_argument("--jobs", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--container", default="comfyui-primary")
ap.add_argument("--kap", default="http://127.0.0.1:10588")
ap.add_argument("--prefix", default="rb", help="filenamePrefix, 产物名 <prefix>_<sid>_00001_.mp4")
ap.add_argument("--project-id", type=int, default=901, help="必填数字, 只进文件名")
ap.add_argument("--profile", default="turbo", help="白名单: turbo | native-sage")
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--resolution", default="1344x768")
ap.add_argument("--submit-timeout", type=int, default=1900, help="覆盖 gpuQueue 1800s 最长锁等待")
ap.add_argument("--global-timeout", type=int, default=7200)
ap.add_argument("--poll", type=int, default=30)
A = ap.parse_args()
os.makedirs(A.out, exist_ok=True)
manifest = json.load(open(A.manifest))
jobs = json.load(open(A.jobs)) if os.path.exists(A.jobs) else {}

def save():
    json.dump(jobs, open(A.jobs, "w"), indent=1)

def mark(sid, st, **kw):
    jobs.setdefault(str(sid), {}).update(status=st, **kw)
    save(); print(f"shot {sid} -> {st} {kw}", flush=True)

def cfile(sid):
    r = subprocess.run(["docker","exec",A.container,"bash","-c",
        f"ls -t /root/ComfyUI/output/ | grep '^{A.prefix}_{sid}_' | head -1"],
        capture_output=True, text=True)
    return r.stdout.strip() or None

def extract(sid):
    f = cfile(sid)
    if not f:
        return None
    dst = os.path.join(A.out, f"{A.prefix}_{sid}.mp4")
    r = subprocess.run(["docker","cp",f"{A.container}:/root/ComfyUI/output/{f}",dst],
                       capture_output=True, text=True)
    return dst if r.returncode == 0 and os.path.getsize(dst) > 10000 else None

def status(pid):
    r = subprocess.run(["curl","-s","-m","10","--noproxy","*",
        f"{A.kap}/api/production/minimax-h3/status/{pid}"], capture_output=True, text=True)
    try:
        return (json.loads(r.stdout).get("data") or {}).get("status", "?")
    except Exception:
        return "?"

# Phase A: 提交 (每镜一次, 无重试)
for s in manifest:
    sid = str(s["shot_id"]); j = jobs.get(sid, {})
    if j.get("status") == "done" and j.get("file") and os.path.exists(j["file"]):
        continue
    if j.get("prompt_id"):
        mark(sid, "rendering", prompt_id=j["prompt_id"]); continue
    prompt = s["reverse_prompt_under_test"] + " · strictly diegetic in-world sound, unscored scene"
    cmd = ["curl","-s","-m",str(A.submit_timeout),"--noproxy","*","-X","POST",
        f"{A.kap}/api/production/minimax-h3/i2va",
        "-F",f"firstFrame=@{s['first_frame']}","-F",f"lastFrame=@{s['last_frame']}",
        "-F",f"prompt={prompt}","-F",f"length={s['length']}",
        "-F",f"profile={A.profile}","-F",f"seed={A.seed}",
        "-F",f"resolution={A.resolution}","-F",f"projectId={A.project_id}",
        "-F",f"filenamePrefix={A.prefix}_{sid}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=A.submit_timeout + 50)
    except subprocess.TimeoutExpired:
        r = None
    pid = None
    if r and r.stdout:
        try:
            pid = (json.loads(r.stdout).get("data") or {}).get("promptId")
        except Exception:
            pass
    if pid:
        mark(sid, "rendering", prompt_id=pid)
    else:
        mark(sid, "watching",
             submit_info=(r.stdout if r and r.stdout else "(no response — 可能已入队)")[:200])

# Phase B: 统一等待 (容器产物先到先收 + KAP 状态兜底)
t0 = time.time()
while True:
    remaining = 0
    for s in manifest:
        sid = str(s["shot_id"]); j = jobs.get(sid, {})
        if j.get("status") == "done":
            continue
        remaining += 1
        path = extract(sid)
        if path:
            mark(sid, "done", file=path); remaining -= 1; continue
        if j.get("status") == "rendering" and j.get("prompt_id"):
            if status(j["prompt_id"]) in ("failed", "error"):
                mark(sid, "failed"); remaining -= 1
    if remaining == 0:
        print("ALL_DONE", flush=True); break
    if time.time() - t0 > A.global_timeout:
        print("GLOBAL_TIMEOUT", flush=True); break
    time.sleep(A.poll)

for s in manifest:
    j = jobs.get(str(s["shot_id"]), {})
    print(f"  shot {s['shot_id']}: {j.get('status')} {j.get('file','')}", flush=True)
