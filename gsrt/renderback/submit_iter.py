#!/usr/bin/env python3
"""GSRT render-back prompt 迭代轮 v3 — 逐镜迭代提交器.

循环纪律 (Kai 08-29 指令: 迭代推导 prompt 直到 H3 预览基本和黄金集一致):
- manifest_v2.json 里每镜带 prompt_vN; 渲染后双锚评分 + 判词
- 达标 (双锚 + 中帧beat判定过) → 该镜锁定
- 不达标 → 从判词导出 prompt 修正 → 下一轮 (最多 4 轮, 收益停滞即锁)
- 引擎臂恒定: KAP i2va + turbo + seed=42 + 1344x768 (与 v1 严格同参, 唯一变量=prompt)
"""
import json, subprocess, time, os, sys, glob

BASE = "/data/workspace/kais-shot-timeline/gsrt/renderback"
OUT = f"{BASE}/renders_iter"
os.makedirs(OUT, exist_ok=True)

def submit(shot, prompt, tag):
    """单镜单次提交 (v2 教训: 空响应不重试, 转守望)."""
    full_prompt = prompt + " · strictly diegetic in-world sound, unscored scene"
    cmd = [
        "curl", "-s", "-m", "1900", "--noproxy", "*",
        "-X", "POST", "http://127.0.0.1:10588/api/production/minimax-h3/i2va",
        "-F", f"firstFrame=@{shot['first_frame']}",
        "-F", f"lastFrame=@{shot['last_frame']}",
        "-F", f"prompt={full_prompt}",
        "-F", "length=" + str(shot["length"]),
        "-F", "profile=turbo",
        "-F", "seed=42",
        "-F", "resolution=1344x768",
        "-F", "projectId=901",
        "-F", f"filenamePrefix=gsrt_{tag}_{shot['shot_id']}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1950)
    except subprocess.TimeoutExpired:
        return None, "(client timeout 1950s — 可能已入队)"
    raw = r.stdout or "(empty)"
    try:
        d = json.loads(raw)
        pid = (d.get("data") or {}).get("promptId")
        return (pid, raw[:200]) if pid else (None, raw[:300])
    except Exception:
        return None, "(no response — 可能已入队, 转守望)"

def wait_output(prefix, max_wait=1500):
    """守望容器产物: grep output 目录最新匹配文件."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_wait:
        r = subprocess.run(["docker", "exec", "comfyui-primary", "bash", "-c",
            f"ls -t /root/ComfyUI/output/ | grep '^{prefix}_' | head -1"],
            capture_output=True, text=True)
        f = r.stdout.strip()
        if f:
            dst = f"{OUT}/{f}"
            subprocess.run(["docker", "cp",
                f"comfyui-primary:/root/ComfyUI/output/{f}", dst],
                capture_output=True, text=True)
            if os.path.exists(dst) and os.path.getsize(dst) > 10000:
                return dst
        time.sleep(20)
    return None

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "v3"
    manifest = json.load(open(f"{BASE}/manifest_v2.json"))
    results = {}
    for s in manifest:
        sid = s["shot_id"]
        pvar = [k for k in s.keys() if k.startswith("prompt_v")]
        prompt = s[sorted(pvar)[-1]]  # 最高版本 prompt
        print(f"=== shot {sid} submit ({tag}) ===", flush=True)
        pid, info = submit(s, prompt, tag)
        print(f"  pid={pid} info={info[:120]}", flush=True)
        f = wait_output(f"gsrt_{tag}_{sid}")
        results[sid] = {"file": f, "pid": pid}
        print(f"  -> {f}", flush=True)
    json.dump(results, open(f"{OUT}/_{tag}_jobs.json", "w"), indent=1, ensure_ascii=False)
    print("ALL_SUBMITTED", json.dumps({k: bool(v['file']) for k, v in results.items()}))
