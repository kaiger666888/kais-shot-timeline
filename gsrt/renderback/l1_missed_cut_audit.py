#!/usr/bin/env python3
"""算法层更正落实: KST 切点表生成算法 + 渲染单元推导的 L1 审计层固化。

背景: r039 漏切实锤（Kai 盲选 + TNV2 软峰 0.240 + vision CUT 三证）。根因 = 生成管线只有
「TNV2 峰选（>=0.5）+ 0914 盲审票」两条自动/半自动层, 缺一条**反写一致性交叉审计层**:
反写时代把 r039 写成了两段 prompt 拼接（=两拍), 但切点表没有吸收这个信号。

本脚本 = 把 kb6 审计逻辑固化为可复跑的 L1 审计器, 落仓 kais-shot-timeline/gsrt/renderback/。
签名定义:
  S1 (强): 单元 h3_prompt 含 >=2 个风格块 + 窗内(半开区间内缩2帧) TNV2 软峰 [0.15,0.5)
           → 候选漏切, 必须升级逐帧裁决 (r039 实证型)
  S2 (弱): 多段 prompt 但窗内 TNV2 干净 → 一镜多拍描述, 无物理切 (r023/r024/r026 型, 不动表)
  S3 (静默): 窗头/窗尾邻帧峰 → 属相邻镜边界帧, 非本镜漏切 (r023@77.133 属 r022 已知切)
升级裁决协议 = video-shot-boundary-detection skill 的 ±3 帧全分辨率条带 + vision 单问。
"""
import json, sys
import numpy as np

REV_MANIFEST = "/data/workspace/kais-gold-remount/episodes/ep-xiaojianghu-ep01/S3_recipes/batch_manifest_rev4_v3.json"
REV_TABLE = sys.argv[1] if len(sys.argv) > 1 else '/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01/physcut_table_rev5.json'
PROBS_NPY = '/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01/tnv2_probs.npy'
OUT = '/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01/l1_missed_cut_audit.json'
FPS = 30

def prompt_blocks(p): return p.count("3D animation")

def audit():
    man = json.load(open(REV_MANIFEST))
    table = json.load(open(REV_TABLE))
    probs = np.load(PROBS_NPY)
    known_cuts = {round(s['start'], 3) for s in table['shots']} | {round(s['end'], 3) for s in table['shots']}
    findings = []
    for s in man["shots"]:
        uid = s["uid"]; nb = prompt_blocks(s.get("h3_prompt", ""))
        if nb < 2: continue
        i0 = int(s["start"] * FPS) + 2; i1 = int(s["end"] * FPS) - 2
        seg = probs[i0:i1+1]
        peaks = [(round((i0+j)/FPS, 3), round(float(seg[j]), 3))
                 for j in range(1, len(seg)-1)
                 if 0.15 <= seg[j] and seg[j] >= seg[j-1] and seg[j] >= seg[j+1]]
        for t, p in peaks:
            cls = "S1_candidate_missed_cut" if p < 0.5 else "S0_strong_peak_unrecorded" if round(t,3) not in known_cuts else "S3_boundary_known"
            findings.append(dict(uid=uid, t=t, prob=p, prompt_blocks=nb, cls=cls,
                                 action="escalate_frame_adjudication" if cls.startswith("S1") or cls.startswith("S0") else "none"))
    out = dict(
        audit="L1 missed-cut cross-audit (prompt-structure x TNV2 soft peak)",
        table=REV_TABLE, n_shots_audited=len(man["shots"]),
        signature_def={
            "S1": "multi-block prompt + in-window TNV2 soft peak [0.15,0.5) -> escalate per-frame adjudication (r039-proven)",
            "S2": "multi-block prompt + clean window -> one-shot-multi-beat prose, no cut (r023/r024/r026-type)",
            "S3": "peak at window-head/tail neighbor frame -> belongs to adjacent shot boundary, not this shot"},
        findings=findings,
        run_note="固化的 L1 审计层; 切点真值升级仍需 video-shot-boundary-detection skill 的条带裁决+Kai 票, 本层只收敛候选集")
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"audited {len(man['shots'])} shots -> {len(findings)} findings -> {OUT}")
    for f in findings:
        print(" ", f)

if __name__ == "__main__":
    audit()
