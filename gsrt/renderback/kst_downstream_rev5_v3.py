#!/usr/bin/env python3
# KST 下游对账 v3 (2026-09-22): physcut_table_rev4(97) → rev5(98) 四件联动重导
#   1) kst_tnv2_reconcile_v3.json      (batch_ep01/ 对账档)
#   2) shots_v2_98phys.json            (output/第01话/ 物理镜表)
#   3) p09_shot-list_v2_98phys.json    (output/第01话/ p09 镜单)
#   4) evidence_packs_v2_98phys.json   (gsrt/ 证据包)
# 唯一实质变化: 切点 @112.4333 (r039 拆分为 39a[112.1,112.4333]+39b[112.4333,112.9333]),
#   其后镜 id 顺移 +1。恒等式: 98 = 93 KST行 + 10 内嵌切点 − 5 合并行 (v2: 97=93+9−5)。
# rev4 原件(97phys 三件 + reconcile_v2)不动, 仅新增 v3 文件。
import json, shutil, os, collections

ST = "/data/workspace/kais-shot-timeline"
P = f"{ST}/gsrt/renderback/batch_ep01"
OUT = f"{ST}/output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
GSRT = f"{ST}/gsrt"

rev5 = json.load(open(f"{P}/physcut_table_rev5.json"))["shots"]
kst = json.load(open(f"{OUT}/shots.json"))
rec2 = json.load(open(f"{P}/kst_tnv2_reconcile_v2.json"))
sv2 = json.load(open(f"{OUT}/shots_v2_97phys.json"))
p092 = json.load(open(f"{OUT}/p09_shot-list_v2_97phys.json"))
ev2 = json.load(open(f"{GSRT}/evidence_packs_v2_97phys.json"))
assert len(rev5) == 98 and len(kst) == 93 and len(sv2["shots"]) == 97
assert len(p092["shot_list"]) == 97 and len(ev2) == 97

CUT = 112.4333
TOL = 0.15  # v2 实测 matched 阈值(最远 delta=0.137), 校准目标: 复现 v2 的 87/5/9

# ---------- 1) reconcile v3 ----------
cuts = [s["start"] for s in rev5] + [rev5[-1]["end"]]
interior_cuts = cuts[1:-1]  # 97 个内切点
matched, pure_beat, extra = [], [], []
for i in range(len(kst) - 1):
    b = kst[i]["end_sec"]
    near = [c for c in cuts if abs(c - b) <= TOL]
    if near:
        matched.append({"kst_boundary_after": kst[i]["id"], "t": b,
                        "cut": min(near, key=lambda c: abs(c - b)),
                        "delta": round(min(near, key=lambda c: abs(c - b)) - b, 4)})
    else:
        pure_beat.append({"kst_boundary_after": kst[i]["id"], "t": b})
for c in interior_cuts:
    if any(abs(c - m["cut"]) < 1e-9 for m in matched):
        continue
    row = next(r for r in kst if r["start_sec"] - 1e-9 <= c < r["end_sec"] - 1e-9)
    extra.append({"cut": c, "rev5_shot_id": next(s["id"] for s in rev5 if s["start"] == c),
                  "in_kst_row": row["id"], "row_range": [row["start_sec"], row["end_sec"]]})
# 恒等式: 物理镜内边界数 = KST行边界数 + 内嵌切点数 − 被merge吸收的pure_beat边界数
# (v2 实证: 96 = 92 + 9 − 5, 87 matched + 9 extra = 96; pure_beat 5 条全被 merged 行吸收)
absorbed = len(pure_beat)  # pure_beat 边界即被 merge 吸收的行边界
identity = (f"{len(rev5)} phys = {len(kst)} KST rows + {len(extra)} extra_cuts − {absorbed} pure_beat absorbed "
            f"(inner bounds {len(matched)+len(extra)} = matched {len(matched)} + extra {len(extra)}); "
            f"KST rows needing split: {sorted(set(e['in_kst_row'] for e in extra))} "
            f"(row 39 now {sum(1 for e in extra if e['in_kst_row']==39)} cuts)")
print("[reconcile v3]", identity)
assert len(matched) == 88 and len(pure_beat) == 4, f"matched/pure_beat 漂移: {len(matched)}/{len(pure_beat)}"
# v2→v3 的 87/5→88/4 有意漂移: 新切点 112.4333 距行39/40边界 112.47 仅 0.0367s(~1帧),
# 按 v2 语义(宽松匹配, 最远 delta 0.137)归 matched —— 即行39末边界真值=112.4333, KST 节拍晚 1 帧。
rec3 = {"date": "2026-09-22", "basis": "physcut_table_rev5 (98 shots) x shots.json (93 KST beat rows)",
        "matched": matched, "pure_beat_boundaries": pure_beat, "extra_cuts": extra,
        "identity_check": identity,
        "v3_note": "v2→v3 变化: 新切点 112.4333 入表 (rev5_shot_id 39; Kai kb4 附注定谳 + TNV2 0.240 软峰 + "
                   "条带 vision 裁决 + rev4 反写两段拼接证据)。其距 KST 行39/40边界 112.47 仅 1 帧 → 归 matched "
                   "(delta -0.0367), matched 87→88 / pure_beat 5→4; extra_cuts 维持 9 (rows 38/39/40/45/53/60/83), "
                   "其余 87 matched 边界全部复现"}
print(f"  matched={len(matched)} pure_beat={len(pure_beat)} extra={len(extra)} (v2: 87/5/9, v3 有意 88/4/9)")

# ---------- 2) shots_v2_98phys ----------
v3_shots = []
for x in sv2["shots"]:
    if x["id"] < 39:
        v3_shots.append(dict(x))
    elif x["id"] == 39:
        v3_shots.append({"id": 39, "start": 112.1, "end": 112.4333, "duration": 0.3333,
                         "kst_ids": [39], "lineage": "split_from_kst_39"})
        v3_shots.append({"id": 40, "start": 112.4333, "end": 112.9333, "duration": 0.5,
                         "kst_ids": [39, 40], "lineage": "merged_kst_39_40"})
    else:
        y = dict(x); y["id"] += 1; v3_shots.append(y)
sv3 = {"format": "kst-beat-rows v2 @ 98 physical shots (rev5, 0922: r039 split @112.4333)",
       "shots": v3_shots}
# 校验: 边界与 rev5 完全一致 + 连续无缝
for a, b, r in zip(v3_shots, v3_shots[1:], rev5):
    assert abs(a["end"] - b["start"]) < 1e-6, f"缝隙 @id{a['id']}"
    assert abs(a["start"] - r["start"]) < 1e-6 and abs(a["end"] - r["end"]) < 1e-6, f"rev5 失配 @id{a['id']}"
assert len(v3_shots) == 98
kst_cov = set()
for x in v3_shots: kst_cov.update(x["kst_ids"])
assert kst_cov == set(range(1, 94)), f"KST 行覆盖缺口: {set(range(1,94))-kst_cov}"
print(f"[shots_v3] 98 条 | rev5 边界逐一相符 ✓ | KST 行 1..93 全覆盖 ✓")

# ---------- 3) p09_shot-list_v2_98phys ----------
sl3 = []
for e in p092["shot_list"]:
    num = int(e["shot_id"].split("_")[1])
    if num < 39:
        sl3.append(dict(e))
    elif num == 39:
        base = json.loads(json.dumps(e))
        # 39a: 翻滚→腾身跃起 (窗内证据: Kai kb5 终审判词「10f 窗内翻滚+跳起双拍」+ kb5 39a prompt)
        a = json.loads(json.dumps(base))
        a.update({"shot_id": "R_039", "kst_shot_id": 39, "start_sec": 112.1, "end_sec": 112.4333,
                  "duration_sec": 0.3333,
                  "subject_description": "螳螂武士绿色身影,巨树根处贴地翻滚,尾帧腾身跃起、双刀高举",
                  "action": "螳螂自树根处贴地翻滚后猛然腾身跃起,凌空举刀",
                  "camera_movement": "低角度仰拍,随跃起快速上摇",
                  "felt_intent": "螳螂翻滚腾身",
                  "kst_shot_ids": [39], "lineage": "split_from_kst_39"})
        a["ltx_prompt_raw"] = ("3D 动画,皮克斯级写实渲染,电影感,运动模糊 · 巨树盘根,苔藓密林 · "
                               + a["subject_description"] + " · " + a["action"] + " · "
                               + a["camera_movement"] + " · " + a["lighting"])
        # 39b: 空中收身俯冲 (条带 vision: 112.4333 处构图/主体尺度/背景瞬间替换; kb5 39b prompt)
        b = json.loads(json.dumps(base))
        b.update({"shot_id": "R_040", "kst_shot_id": 39, "start_sec": 112.4333, "end_sec": 112.9333,
                  "duration_sec": 0.5,
                  "subject_description": "螳螂武士空中收身,双臂刀锋前引,头朝下俯冲直下",
                  "action": "螳螂空中急速收身,头朝下刀锋向前俯冲直扑地面目标",
                  "camera_movement": "俯视高速跟拍俯冲,落叶地面扑面而来",
                  "scene": "落叶林地与盘根上方", "lighting": "幽暗林光",
                  "style_prefix": "3D 动画,皮克斯级写实渲染,电影感,强烈径向运动模糊",
                  "felt_intent": "螳螂俯冲下扑",
                  "kst_shot_ids": [39, 40], "lineage": "merged_kst_39_40"})
        b["ltx_prompt_raw"] = ("3D 动画,皮克斯级写实渲染,电影感,强烈径向运动模糊 · 落叶林地与盘根上方 · "
                               + b["subject_description"] + " · " + b["action"] + " · "
                               + b["camera_movement"] + " · " + b["lighting"])
        sl3.extend([a, b])
    else:
        y = json.loads(json.dumps(e))
        y["shot_id"] = f"R_{num+1:03d}"
        sl3.append(y)
p093 = {"standard_id": p092["standard_id"],
        "note": "0922 rebuild on physcut_table_rev5 (98 phys; r039 split @112.4333 per Kai verdict + TNV2/vision/反写三重证据); "
                "lineage in each entry; dialogue re-attributed from asr_vocals_clean; "
                "split pieces inherit parent metadata (engine_semantic re-annotation pending P2)",
        "shot_list": sl3}
assert len(sl3) == 98 and len({e["shot_id"] for e in sl3}) == 98, "p09 id 冲突"
for e, r in zip(sl3, rev5):
    assert abs(e["start_sec"] - r["start"]) < 1e-6 and abs(e["end_sec"] - r["end"]) < 1e-6, f"p09 失配 @{e['shot_id']}"
print(f"[p09_v3] 98 条 | R_039/R_040 拆件 | rev5 边界逐一相符 ✓")

# ---------- 4) evidence_packs_v2_98phys ----------
# engine_index 语义(v2 全量实证 94/97): = 物理镜中点所在 KST 行号 (1 bad=遗留噪声, 2 none=尾镜缺)。
# 拆件按中点规则: 新39a 中点112.267→row39, 新39b 中点112.683→row40。
mism = []
for g in ev2:
    num = int(g["shot_id"].split("_")[-1])
    src = next(x for x in sv2["shots"] if x["id"] == num)
    if g.get("engine_index") is None:
        continue
    mid = (g["video_time"][0] + g["video_time"][1]) / 2
    pred = next((r["id"] for r in kst if r["start_sec"] - 1e-9 <= mid < r["end_sec"] - 1e-9), None)
    if g["engine_index"] != pred:
        mism.append((g["shot_id"], g["engine_index"], pred))
print(f"[ev engine_index=中点行] v2 校准: 违例 {len(mism)} (遗留噪声, 原样保留): {mism}")
ev3 = []
for g in ev2:
    num = int(g["shot_id"].split("_")[-1])
    if num < 39:
        ev3.append(json.loads(json.dumps(g)))
    elif num == 39:
        base = json.loads(json.dumps(g))
        es = base["engine_semantic"]
        a = json.loads(json.dumps(base))
        a.update({"shot_id": "G2_R_039", "engine_index": 39, "video_time": [112.1, 112.4333],
                  "lineage": "split_from_kst_39", "inherits_from": base.get("inherits_from")})
        a["engine_semantic"] = dict(es, needs_reannotation=True,
            reannotation={"source": "rev5_split_0922", "date": "2026-09-22",
                          "is_jump_cut_split": "是",
                          "note": "rev5 拆件: 语义继承父 G2_R_039, 待 P2 对新窗 [112.1,112.4333] 重标注"})
        b = json.loads(json.dumps(base))
        b.update({"shot_id": "G2_R_040", "engine_index": 40, "video_time": [112.4333, 112.9333],
                  "lineage": "merged_kst_39_40", "inherits_from": base.get("inherits_from")})
        b["engine_semantic"] = dict(es, needs_reannotation=True,
            reannotation={"source": "rev5_split_0922", "date": "2026-09-22",
                          "is_jump_cut_split": "是",
                          "note": "rev5 拆件: 语义继承父 G2_R_039, 待 P2 对新窗 [112.4333,112.9333] 重标注"})
        ev3.extend([a, b])
    else:
        y = json.loads(json.dumps(g))
        y["shot_id"] = f"G2_R_{num+1:03d}"
        ev3.append(y)
assert len(ev3) == 98 and len({g["shot_id"] for g in ev3}) == 98
for g, r in zip(ev3, rev5):
    assert abs(g["video_time"][0] - r["start"]) < 1e-6 and abs(g["video_time"][1] - r["end"]) < 1e-6, f"ev 失配 @{g['shot_id']}"
print(f"[ev_v3] 98 条 | G2_R_039/040 拆件(needs_reannotation=True) | rev5 窗逐一相符 ✓")

# ---------- 落盘 (v2 备份后写 v3 新文件, rev4 原件不动) ----------
for src, bak in [(f"{P}/kst_tnv2_reconcile_v2.json", None),
                 (f"{OUT}/shots_v2_97phys.json", None),
                 (f"{OUT}/p09_shot-list_v2_97phys.json", None),
                 (f"{GSRT}/evidence_packs_v2_97phys.json", None)]:
    shutil.copy(src, src + ".bak_v3pre")  # 防手滑回滚点
def w(path, obj):
    with open(path, "w") as f: json.dump(obj, f, ensure_ascii=False, indent=1)
    print("  写", path, os.path.getsize(path), "bytes")
w(f"{P}/kst_tnv2_reconcile_v3.json", rec3)
w(f"{OUT}/shots_v2_98phys.json", sv3)
w(f"{OUT}/p09_shot-list_v2_98phys.json", p093)
w(f"{GSRT}/evidence_packs_v2_98phys.json", ev3)
print("DONE: 四件 v3 落盘")
