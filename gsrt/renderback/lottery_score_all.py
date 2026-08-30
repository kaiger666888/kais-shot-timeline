#!/usr/bin/env python3
"""收编全部 lottery 渲染 → 逐 seed 跑 score_qc → 语义/SSIM 排行 → 写 JSON 台账"""
import json, subprocess, sys, os

WD = "/data/workspace/kais-shot-timeline/gsrt/renderback"
TARGET = "/home/kai/shared/2026-08-30/s89_target.mp4"

def main():
    # 1. 收编
    r = subprocess.run([sys.executable, f"{WD}/seed_lottery_s89.py", "collect"],
                       capture_output=True, text=True)
    print(r.stdout)

    # 2. 逐 seed 打分
    results = {}
    import glob
    renders = sorted(glob.glob(f"{WD}/renders_a2v/gsrt_a2v_s89_lot*.mp4"))
    renders = [f for f in renders if "-audio" not in f]
    for f in renders:
        seed = os.path.basename(f).replace("gsrt_a2v_s89_lot", "").split("_")[0]
        outj = f"{WD}/qc_lot_{seed}.json"
        r = subprocess.run([sys.executable, f"{WD}/score_qc.py", TARGET, f, "--json", outj],
                           capture_output=True, text=True)
        try:
            v = json.load(open(outj))
            results[seed] = {
                "ssim_mean": v["ssim"]["mean"], "sem_mean": v["semantic"]["mean"],
                "ssim_pass": v["ssim"]["pass"], "sem_pass": v["semantic"]["pass"],
                "overall": v["overall_pass"],
                "dips": {"ssim": v["ssim"]["dips"], "sem": v["semantic"]["dips"]},
            }
            print(f"seed={seed}: SSIM={v['ssim']['mean']:.3f} SEM={v['semantic']['mean']:.3f} "
                  f"overall={'PASS' if v['overall_pass'] else 'fail'}")
        except Exception as e:
            print(f"seed={seed}: SCORE FAIL {e} | {r.stderr[-200:]}")

    # 3. 排行 + 台账
    ranked = sorted(results.items(), key=lambda kv: (kv[1]["sem_mean"], kv[1]["ssim_mean"]), reverse=True)
    ledger = {
        "shot": 89, "date": "2026-08-30", "gates": {"ssim": 0.55, "semantic": 0.75},
        "lottery": {"n_seeds": len(results), "ranked": [
            {"seed": s, **v} for s, v in ranked]},
        "notes": "v4 配方逐字克隆, 唯一变量=seed; 目标=中段低谷(1.9-3.6s)被某个 seed 的动作时相恰好命中",
    }
    json.dump(ledger, open(f"{WD}/lottery_ledger.json", "w"), ensure_ascii=False, indent=1)
    print("\n=== 排行 (语义相似度优先) ===")
    for i, (s, v) in enumerate(ranked, 1):
        print(f"#{i} seed={s}: SEM={v['sem_mean']:.3f} SSIM={v['ssim_mean']:.3f} "
              f"{'✅PASS' if v['overall'] else ''}")
    # 对照基线
    print("\n基线: v4(seed42) SEM=0.7692 SSIM=0.4873 | v5(seed43) SEM=0.651 SSIM=0.4395")

if __name__ == "__main__":
    main()
