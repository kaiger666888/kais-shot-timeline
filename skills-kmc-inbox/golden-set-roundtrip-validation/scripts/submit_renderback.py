#!/usr/bin/env python3
"""GSRT render-back 提交器: N镜 首尾帧+逆向prompt → H3 turbo → 视频回测对比原片

用法: 复制到 <workdir>/renderback/ 改 BASE; manifest.json 每镜含
shot_id/target_window/duration_sec/first_frame/last_frame/reverse_prompt_under_test/length。
配套外层循环 run_renderback.sh:
  for i in $(seq 1 24); do python3 submit_renderback.py; rc=$?; [ $rc -eq 0 ] && exit 0; [ $rc -eq 2 ] && exit 2; sleep 30; done
退出码: 0=全部完成 2=提交硬失败 3=单镜轮询超时(外层续跑)
"""
import json, subprocess, time, sys, os

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
OUT = f"{BASE}/renders"
os.makedirs(OUT, exist_ok=True)

manifest = json.load(open(f"{BASE}/manifest.json"))
jobs_path = f"{BASE}/jobs.json"
if os.path.exists(jobs_path):
    jobs = json.load(open(jobs_path))
else:
    jobs = {str(s["shot_id"]): {"status": "pending", "prompt_id": None} for s in manifest}
    json.dump(jobs, open(jobs_path, "w"), indent=1)

def save_jobs():
    json.dump(jobs, open(jobs_path, "w"), indent=1)

def submit(s):
    # 被测逆向 prompt + H3 音频 bed 规则词（CFG=1.0 负面无效, 正面 diegetic 词防自带 BGM）
    prompt = s["reverse_prompt_under_test"] + " · strictly diegetic in-world sound, unscored scene"
    cmd = [
        "curl", "-s", "-m", "120", "--noproxy", "*",
        "-X", "POST", "http://127.0.0.1:10588/api/production/minimax-h3/i2va",
        "-F", f"firstFrame=@{s['first_frame']}",
        "-F", f"lastFrame=@{s['last_frame']}",
        "-F", f"prompt={prompt}",
        "-F", "length=" + str(s["length"]),          # 网格 n%17==5, 绕 duration 4s 下限
        "-F", "profile=turbo",                        # H3_EXPOSED_PROFILES 只剩 turbo|native-sage
        "-F", "seed=42",
        "-F", "resolution=1344x768",
        "-F", "projectId=901",                        # 必填数字, 仅用于文件名前缀
        "-F", f"filenamePrefix=gsrt_rb_{s['shot_id']}",
    ]
    last_raw = ""
    for attempt in range(4):  # KAP 偶发空响应重试
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        last_raw = r.stdout or "(empty)"
        try:
            d = json.loads(last_raw)
        except Exception:
            print(f"  提交尝试{attempt+1} 空响应/非JSON, 15s后重试", flush=True)
            time.sleep(15)
            continue
        data = d.get("data") or {}
        if data.get("promptId"):
            return data["promptId"], last_raw[:300]
        if d.get("errors") or d.get("message") == "参数错误":  # 业务错误不重试
            return None, last_raw[:300]
        time.sleep(15)
    return None, last_raw[:300]

def extract_if_present(pid, sid):
    """渲染完成后从容器 docker cp 提取 (绕过 KAP output 404)"""
    fname = f"gsrt_rb_{sid}_00001_.mp4"
    src = f"comfyui-primary:/root/ComfyUI/output/{fname}"
    dst = f"{OUT}/gsrt_rb_{sid}.mp4"
    r = subprocess.run(["docker","cp",src,dst], capture_output=True, text=True)
    return r.returncode == 0, dst

def poll(pid):
    r = subprocess.run(["curl","-s","-m","10","--noproxy","*",
        f"http://127.0.0.1:10588/api/production/minimax-h3/status/{pid}"],
        capture_output=True, text=True)
    try:
        return (json.loads(r.stdout).get("data") or {}).get("status", "?")
    except Exception:
        return "?"

# 串行提交 (ComfyUI 队列本身 FIFO, 避免交错)
for s in manifest:
    sid = str(s["shot_id"])
    if jobs[sid].get("status") == "done" and os.path.exists(jobs[sid].get("file","")):
        continue
    if not jobs[sid].get("prompt_id"):
        pid, raw = submit(s)
        if not pid:
            print(f"shot {sid} 提交失败: {raw}", flush=True)
            jobs[sid]["status"] = "submit_failed"; jobs[sid]["err"] = raw; save_jobs()
            sys.exit(2)
        jobs[sid].update(prompt_id=pid, status="rendering")
        save_jobs()
        print(f"shot {sid} 提交 OK pid={pid} length={s['length']}", flush=True)
    else:
        pid = jobs[sid]["prompt_id"]
        print(f"shot {sid} 续盯 pid={pid}", flush=True)

    t0 = time.time()
    while True:
        st = poll(pid)
        if st in ("completed","done","success"):
            ok, path = extract_if_present(pid, sid)
            if ok:
                jobs[sid]["status"] = "done"; jobs[sid]["file"] = path; save_jobs()
                print(f"shot {sid} 完成+提取 用时{int(time.time()-t0)}s -> {path}", flush=True)
            else:
                jobs[sid]["status"] = "extract_failed"; jobs[sid]["file"] = path; save_jobs()
                print(f"shot {sid} 渲染完成但提取失败", flush=True)
            break
        if st in ("failed","error"):
            jobs[sid]["status"] = "failed"; save_jobs()
            print(f"shot {sid} 渲染失败", flush=True)
            break
        if time.time() - t0 > 2400:  # 40min 单镜上限（含排队）
            print(f"shot {sid} 轮询超时，保持 rendering 状态待下轮", flush=True)
            sys.exit(3)
        time.sleep(20)

print("RENDERBACK_ALL_DONE", flush=True)
