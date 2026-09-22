#!/usr/bin/env python3
# P2 rev5 拆件回填 (0922): p2_reannotation_rev5.jsonl → evidence_packs_v2_98phys 两镜
import json, shutil, datetime

GSRT = "/data/workspace/kais-shot-timeline/gsrt"
EV = f"{GSRT}/evidence_packs_v2_98phys.json"
ANN = f"{GSRT}/p2_reannotation_rev5.jsonl"
PATCH = ["shot_scale", "camera_primitive", "camera_speed", "subjects", "action_detail"]

ann = {}
for line in open(ANN):
    if line.strip():
        d = json.loads(line)
        ann[d["shot_id"]] = d

ev = json.load(open(EV))
shutil.copy(EV, EV + ".bak_rev5split")
n = 0
for g in ev:
    es = g.get("engine_semantic")
    if not (isinstance(es, dict) and es.get("needs_reannotation")):
        continue
    a = ann.get(g["shot_id"])
    if not a:
        print(f"WARN {g['shot_id']}: 无标注, 保留 needs_reannotation")
        continue
    for f in PATCH:
        if a.get(f):
            es[f] = a[f]
    es["needs_reannotation"] = False
    es["reannotation"] = {"source": "p2_reannotation_rev5.jsonl (GLM-4.6 新窗三帧)",
                          "date": datetime.date.today().isoformat(),
                          "is_jump_cut_split": a.get("is_jump_cut_split")}
    n += 1
    print(f"回填 {g['shot_id']}: {a.get('shot_scale')}/{a.get('camera_primitive')}/{a.get('camera_speed')} | {a.get('action_detail','')[:40]}")

left = [g["shot_id"] for g in ev if isinstance(g.get("engine_semantic"), dict) and g["engine_semantic"].get("needs_reannotation")]
with open(EV, "w") as f:
    json.dump(ev, f, ensure_ascii=False, indent=1)
print(f"回填 {n} 镜 | 剩余 needs_reannotation: {left} | 备份 .bak_rev5split")
