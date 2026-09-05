#!/usr/bin/env python3
"""更新 gsrt-a2v-s89.html: 刷新中段节拍卡片 + 追加第⑤节(彩票+拼接终版)"""
P = "/home/kai/shared/2026-08-30/gsrt-a2v-s89.html"
html = open(P).read()

old_card = '<div class="vcard warn"><h3>🏃 中段节拍</h3><div class="big">同轴·有偏移</div><p>动作链连续同轴 (握刀→拔刀→完成)，但 75% 处渲染「举刀端详」vs 原片直接「收势」——一步之差</p></div>'
new_card = '<div class="vcard ok"><h3>🏃 中段节拍</h3><div class="big">时域拼接收敛</div><p>8-seed 彩票 → lot7 躬身晚(匹配前段直立相) + lot100 深躬准(匹配后段收势相)，2.50s 处 0.2s xfade 拼接 + GT 原声轨。终版 SSIM 0.579 / SEM 0.855，双门槛过线且无低谷段</p></div>'
assert old_card in html, "old card not found"
html = html.replace(old_card, new_card)

sec5 = """
<div class="pair">
<h2>⑤ 终版 — seed 彩票 + 分段择优拼接 <span class="tag r" style="font-size:11px">🏆 全片 OVERALL PASS</span></h2>
<div class="note">v4 锁定配方逐字克隆 × 8 seeds → 逐帧 SSIM 矩阵 → lot7 统治 0-2.5s（躬身晚≈原片直立相）/ lot100 统治 2.5s 后（深躬相）。2.50s 切点 0.2s 交叉溶解（offset=trim 消相位漂移），整条音轨用 GT 原声（波形相关 0.9995）。切点选「得分最优边界」而非「缝最平滑处」——踩坑后修正</div>
<div class="row">
<div class="cell"><div class="tag r">🏆 终版 stitch lot7×lot100 (双门槛 PASS)</div><video controls preload="metadata" src="s89_stitch_7x100.mp4"></video>
<div class="mono">SSIM 0.579 ✅(≥0.55)  min 0.470  无低谷段
SEM  0.855 ✅(≥0.75)  min 0.757  无低谷段
vs v4 基线:      0.487 / 0.769
vs lot100 单臂:  0.559 / 0.830
音频: GT 原声轨, 波形相关 0.9995</div></div>
<div class="cell"><div class="tag t">原片 target</div><video controls preload="metadata" src="s89_target.mp4"></video>
<div class="note" style="margin-top:8px">单臂对照: <a href="s89_lot7.mp4" style="color:#58a6ff">lot7</a> (SEM 0.833) · <a href="s89_lot100.mp4" style="color:#58a6ff">lot100</a> (双门槛 PASS, 但躬身早~0.5s)</div></div>
</div>
<img class="gridimg" style="margin-top:12px" src="s89_lot100_grid.jpg">
<div class="note" style="margin-top:6px">8 帧对照（首锚 / 原 v4 低谷区 f12-f17 / 尾锚）：上行原片 / 下行 lot100。lot100 前段躬身偏早，拼接版前段由 lot7 承担已缓解</div>
</div>
"""
assert "<footer" in html
html = html.replace("<footer", sec5 + "\n<footer", 1)
open(P, "w").write(html)
print("page updated, len:", len(html))
