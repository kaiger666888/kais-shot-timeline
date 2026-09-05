#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s064 prompt 迭代 v2: 唯一变量=prompt(0904 Kai 定则)。
冻结集逐字克隆 v1 严格臂(seed 990202 / FL2VA+T8AudioLock / lx9 turbo / 20f floor4 /
网格端点锚 / 源音频截断), 仅将 h3_prompt 换为 vision 地面真值修正版(v1 终点描写
"extreme facial close-up" 与原片实读终点"张嘴吞没镜头"相反)。
复用 render_p11b 全链路(extract_conds→grid_anchor→build_wf→submit→archive→state.jsonl)。
"""
import sys, json
sys.path.insert(0, "/data/workspace/kais-gold-remount/scripts")
import render_p11b as R

PROMPT_V2 = open("/tmp/s064_prompt_v2.txt").read().strip()

_orig_load_unit = R.load_unit
def load_unit_v2(uid):
    u = _orig_load_unit(uid)
    u["h3_prompt"] = PROMPT_V2
    return u
R.load_unit = load_unit_v2

if __name__ == "__main__":
    rec = R.render_unit("s064_p1", seed=990202)
    rec["iter"] = "prompt_v2"
    print(json.dumps(rec, ensure_ascii=False, indent=1))
