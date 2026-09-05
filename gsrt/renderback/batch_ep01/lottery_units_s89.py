#!/usr/bin/env python3
"""s089 unit-v2 配方 × turbo 引擎 × seed 彩票批.
依据: s89账本0901定谳"动作时相受seed主导,seed彩票是正路"; 0903 unit-v2锚定验证通过(首帧锚生效),
     缺口=全程动作幅度(直立→拔刀→横刀). 唯一变量=noise_seed, 8发彩票.
"""
import json, subprocess, time, sys, os
import importlib.util

RB = "/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01"
BASE = "http://127.0.0.1:8188"
SEEDS = [7, 5926, 5358, 3141, 2026, 1234, 9793, 777]

# 复用 turbo 臂的 build_wf
spec = importlib.util.spec_from_file_location("tb", f"{RB}/batch_render_ep01_units_turbo.py")
tb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tb)

man = json.load(open(f"{RB}/batch_manifest_units.json"))
s89 = [it for it in man["shots"] if it["sid"] == 89][0]

results = []
for sd in SEEDS:
    wf = tb.build_wf(s89, sd)
    wf["client_id"] = "lottery_units_s89"
    wf["prompt"]["16"]["inputs"]["filename_prefix"] = f"ep01_units_turbo/s089_lot{sd}"
    r = subprocess.run(["curl","-s","-X","POST",f"{BASE}/prompt","-H","Content-Type: application/json",
                        "-d", json.dumps(wf)], capture_output=True, text=True)
    try:
        pid = json.loads(r.stdout)["prompt_id"]
    except Exception:
        print(f"lot{sd} submit FAIL: {r.stdout[:200]}"); continue
    print(f"lot seed={sd} submitted pid={pid}", flush=True)
    t0 = time.time()
    while True:
        time.sleep(15)
        h = json.loads(subprocess.run(["curl","-s",f"{BASE}/history/{pid}"],capture_output=True,text=True).stdout or "{}")
        if pid in h:
            ok = h[pid]["status"].get("status_str") == "success"
            print(f"lot seed={sd} DONE {round(time.time()-t0)}s ok={ok}", flush=True)
            results.append({"seed": sd, "ok": ok})
            break
        if time.time() - t0 > 900:
            print(f"lot seed={sd} TIMEOUT", flush=True)
            results.append({"seed": sd, "ok": False})
            break

json.dump(results, open(f"{RB}/lottery_units_s89_results.json","w"), indent=1)
print("ALL DONE:", sum(1 for r in results if r["ok"]), "/", len(results))
