#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s064 修复臂 v3: 终点语义前置 + 唯一变量=prompt (冻结集逐字克隆 v2 严格臂).

v2→v3 证据链 (0904 下午):
  1. vision 轨迹取证: v2 臂 f0→f12 冲刺推进正确, f16-f19 回退停滞 (盲测页"1s跑不完"定性失实)
  2. 细粒度帧条: 原片 174.45s=吞没开始, 174.47s=口腔内部;
     网格末锚 174.3917s(#19)=扫过过渡帧 → 引擎忠实抵达被喂的锚, "吞嘴"语义不在锚里
  3. v3 prompt 策略: 终点态(jaws parting wide → engulfing whole frame)写成
     主句的连续过程, 删除 v2 的 beat 分段(v1/v2 两版 beat 语义在 20f 极短窗无效),
     目标=至少一臂末帧出现牙/口腔/嘴部占满元素 → 达"张嘴吞镜"验收项
输出: state.jsonl (iter=prompt_v3)
"""
import sys, json
sys.path.insert(0, "/data/workspace/kais-gold-remount/scripts")
import render_p11b as R

PROMPT_V3 = open("/tmp/s064_repair/prompt_v3.txt").read().strip()

_orig_load_unit = R.load_unit
def load_unit_v3(uid):
    u = _orig_load_unit(uid)
    u["h3_prompt"] = PROMPT_V3
    return u
R.load_unit = load_unit_v3

if __name__ == "__main__":
    seeds = [int(s) for s in sys.argv[1].split(",")] if len(sys.argv) > 1 else [990202]
    for seed in seeds:
        rec = R.render_unit("s064_p1", seed=seed)
        rec["iter"] = "prompt_v3"
        print(json.dumps(rec, ensure_ascii=False))
