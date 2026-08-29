# 轨 B 独立盲重标注 Prompt 模板

你是资深动画分镜标注师。对以下镜头，仅根据给出的**画面证据**推断：

1. `emotion` — 该镜头的情绪基调 (4-10 字中文短语)
2. `felt_intent` — 该镜头的叙事意图 (一句中文，以「动词短语」开头，如「建立崇拜」「引爆危机」「交付成长承诺」)
3. `shot_type` — 景别 (特写/近景/中景/中全景/全景/远景)

## 铁律
- 只用证据包内信息，禁止脑补证据外剧情
- 证据间冲突时 (engine_semantic vs kst_subject)，以**画面动作**优先，并在 `notes` 里标注冲突
- 不知道就写「不确定」，不要硬编

## 输出格式
逐镜 JSON 数组：
```json
[{"shot_id": "S1_01", "emotion": "...", "felt_intent": "...", "shot_type": "...", "notes": ""}]
```

## 证据包
{evidence_json}

---
使用说明 (模板外，发 prompt 前删除本节):
1. {evidence_json} 填入 evidence_packs.json (被测字段 emotion/felt_intent 必须已剥离)
2. 金标答案在 golden_answers_sealed.json 封存，判分前不得出现在本 prompt
3. 每次独立 run 换温度/措辞再跑一次 (≥2 次才算数)，完整输入输出存 relabel_runs/
4. 判分: python3 scripts/agreement_report.py relabel_runs/<run>.json
