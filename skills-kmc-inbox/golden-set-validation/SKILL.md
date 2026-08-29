---
name: golden-set-validation
description: "逆向金标(标准集)验证协议 GSRT:让金标数据被迫证明自己,而非内省式检查(schema完整≠内容对)。四层证据阶梯:T1视频锚定审计→T2文本往返注入→T3独立盲重标注→T4消费端渲染回测(Kai 08-28定案主方法:首尾帧从原片提取钉死真相+prompt描述过程+H3预览渲染对比原片,一致=prompt对)。含视频仲裁、判定矩阵、checkpoint注入坑表、修正顺序定案(从管线末端往上游,勿正向依赖序)。触发词:金标验证 标准集验证 逆向验证 渲染回测 render-back GSRT 往返验证"
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [kais, movie-pipeline, golden-standard, validation, reverse-engineering, render-back]
---

# golden-set-validation — 逆向金标验证协议 (GSRT)

回答元问题:「如何确定逆向的金标是经过验证的?」内省式检查(schema 完整/字段非空/引证存在)
只证明"字段填了",不证明"字段是对的"。本协议让每个 slot 的金标被迫证明自己。

## 方法阶梯 (由廉到贵,后层仲裁前层)

| 层 | 方法 | 检验对象 | 定谳力 |
|---|---|---|---|
| T1 锚定审计 | 金标字段 vs 视频证据(时间码/ASR/帧)逐一比对 | 机械层 | 高(直接) |
| T2 文本往返 | 金标 P0k 注入管线正向跑 P0k+1,与金标 P0k+1 diff | 推断层链内自洽 | **单独不足定谳** |
| T3 独立盲标注 | 新 LLM 只看机械层证据重推 emotion/felt_intent,与金标算一致性 | 推断层单采样噪声 | 中(共享先验风险) |
| T4 渲染回测 | **主方法,下节** | prompt 层(最终消费形态) | 高(Kai 08-28 定案) |
| 视频仲裁 | 争议字段抽帧+ASR,匿名盲审 | 一切争议 | 终审 |

## T4 渲染回测 (主方法)

逻辑:金标的最终消费形态就是「首尾帧+prompt→视频」。直接在消费点检验——
首尾帧从**原片**提取(端点钉死在真相),prompt 描述中间过程,H3 预览路径渲染,
与原片段对比。**渲染基本一致 = prompt 是对的**;不一致 = prompt 层失真,修。

1. 选镜:覆盖开场/战斗/空镜/争议区,首试点 5-6 镜
2. ffmpeg 提帧:首帧 t0+0.05s,尾帧 t1-0.12s(防跨界),q:v 2-3
3. manifest: `{shot_id, target_window, first_frame, last_frame, reverse_prompt_under_test, camera/scene/lighting/style/subject/action}`
4. H3 管线预览路径渲染(首尾帧条件模式,REF2VA/I2VA)
5. 对比:同位并排,判"基本一致"(结构/动作/运镜匹配,非像素级)
6. 不一致镜 → prompt 修订 → 重渲染收敛 → prompt 为真值,回写金标 P09 ltx_prompt

## 修正顺序 (Kai 08-28 纠正,勿从上游开始)

**从管线末端往上游推**:先在消费端(P09 prompt/P11 渲染)定谳哪些镜的 prompt 失真,
失真镜反推上游(P02/P03 叙事层)的漏采/编造;而非从 P00 顺依赖链往下猜。
理由:上游文本层自由度大,往返 diff 分不清「管线自由度」vs「金标失真」;
渲染回测直接约束在原片真相上。定谳权始终在视频证据,管线只是一致性探针——
否则金标退化成管线的镜子,基准失效。

## 坑表 (08-28 ep01 试点实战)

| # | 坑 | 解法 |
|---|---|---|
| 1 | 锻造 checkpoint 缺 `current_phase_id` → load_latest_checkpoint 返 None → start_idx=0 重跑 p01 **覆盖注入产物** | 两处 state 文件都写 `current_phase_id`;点火前 `_compute_start_index()` dry-run 验证=期望 idx |
| 2 | 既往 run 的 requirement 被改过(非金标血统),往返对比混入假信号 | 新建干净注入臂,requirement 逐字节拷金标 P00;先做血缘检查(common/identical keys 计数) |
| 3 | 金标 P09(90镜) vs KST prompts(93条) 对齐漂移;对白时间窗抓取 33% mismatch | 跨镜旁白归属是约定差非数据损坏;证据包用金标 dialogue_text 本体(ASR锚定),归属不进判定 |
| 4 | T2 往返相似度低 → 「管线弱 or 金标幻觉」二择一歧义 | T2 单独不定谳;叠视频仲裁或 T4 |
| 5 | 往返相似度高 ≠ 金标对 | 同族 LLM 生成↔标注共享先验=构造性一致;过视频仲裁才算数 |
| 6 | 金标层间自相矛盾(锚定层对,推断层错) | ep01 实锤:P09 锚定层结论一直对,上游 LLM 推断的 P02 错。用锚定层反推推断层 |

## 判定矩阵 (T2×T3)

| T2 往返 | T3 独立标注 | 结论 |
|---|---|---|
| 高 | 高 | 金标推断层可信(仍抽检仲裁) |
| 低 | 高 | 管线弱(金标当零点有效) |
| 低 | 低 | 金标推断层=单采样噪声→多标注集成或降级为参考 |
| 高 | 低 | 词典效应/共享先验污染→人工抽检定谳 |

## 工件与脚本

- 工作区 `/data/workspace/kais-shot-timeline/gsrt/`:`evidence_packs.json`(90镜证据包,被测字段已剥离)、`golden_answers_sealed.json`(封存)、`agreement_report.py`(T3判分:emotion 同义桶三档 + felt_intent role-signal 交并 + shot_type 别名)、`renderback/manifest.json`(T4 首例 ep01 5镜)
- 注入臂模板:worktree `kmc-ab-lab-base` + `phase-ab-lab/run_arm.sh`(见 pipeline-checkpoint-injection,注意坑#1)

## See Also

- `kais-gold-set` — 金标构建与正向 diff(本 skill 是其验证补全;有重叠,curator 候选)
- `kais-movie-pipeline/kst-p09-reverse-supply-diff` — T1 锚定层与 forward_diff 原始方法
- `kais-movie-pipeline/pipeline-checkpoint-injection` — 注入操作手册
- `kais-movie-pipeline/phase-ab-lab` — run_arm.sh 单臂复用
- `references/pilot-xiaojianghu-ep01.md` — 08-28 试点全记录(P02 结尾层 material 失真定谳过程)