# KST 黄金集往返验证 (Golden-Set Round-Trip Validation, GSRT)

回答 Kai 的元问题：**「如何确定 KST 逆向的黄金集是经过验证的？」**——内省式检查
(schema 完整/字段非空) 只证明"字段填了"，不证明"字段是对的"。GSRT 用三条独立证据
链让金标被迫证明自己：

| 轨 | 方法 | 检验对象 |
|---|---|---|
| T1 锚定审计 | 逆向产物 vs 视频证据 (时间码/ASR/帧) | 机械层 (已完成，见 kst-p09-reverse-supply-diff) |
| **T2 往返注入** | 金标 P0k 塞进管线正向跑 P0k+1，对比金标 P0k+1 | 推断层链内自洽性 |
| **T3 独立盲重标注** | 新 LLM 只看机械层证据重推 emotion/felt_intent，与金标算一致性 | 推断层单采样噪声 |
| 视频终审 | 争议字段抽帧，Kai 匿名盲判贴合原片者 | 破循环性 (同族 LLM 共享先验) |

## 目录

- 工作区：`/data/workspace/kais-shot-timeline/gsrt/`
  - `evidence_packs.json` — 90 镜证据包 (引擎语义层 + KST subject/action + 金标对白文本；**被测字段已剥离**)
  - `golden_answers_sealed.json` — 被测字段金标答案 (emotion/felt_intent/camera_intent/shot_type)，判分前不得拆封给重标注模型
  - `relabel_prompt_template.md` — 轨 B 重标注 prompt 模板
  - `relabel_runs/` — 每次重标注的完整输入输出 (留痕)
  - `agreement_report_<date>.json` — 一致性判定结果
- 轨 A 注入臂：`/data/workspace/kmc-ab-lab-base/skills/kais-movie-pipeline/episodes/ep-gsrt01/`
  - requirement.json = 金标 P00 **逐字节**；topic-kernel/hook-design/hook-candidates = 金标 P01 字段级忠实映射
  - checkpoint: workdir 根 `.pipeline-state.json` + episode 内同名文件，**必须含 `current_phase_id`** (否则
    `load_latest_checkpoint` 返回 None → start_idx=0 重跑 p01 覆盖注入——实踩，见坑表 #1)

## 坑表 (实战踩过)

| # | 坑 | 症状 | 解法 |
|---|---|---|---|
| 1 | 锻造 checkpoint 缺 `current_phase_id` | 日志 `start_idx=0 (checkpoint=False)`，p01 重跑覆盖注入产物 | 两处 state 文件都写 `current_phase_id`+phases 条目；点火前用 `_compute_start_index()` dry-run 验证=期望 idx |
| 2 | 既往 run 的 requirement 被改过 (mood/角色改写) | 往返对比混杂非金标上游信号 | **必须新建干净注入臂**，requirement 逐字节拷金标 P00；血缘检查：req vs 金标 common keys/identical 数 |
| 3 | 金标 P09 与 KST prompts.json 90↔93 对齐 | 逐镜对白时间窗抓取 33% mismatch | 漂移是跨镜旁白归属约定差，不是数据损坏；证据包对白用金标 dialogue_text 本体 (ASR锚定)，归属不进判定 |
| 4 | 往返相似度低的解读歧义 | 二择一：管线弱 vs 金标推断层幻觉 | T2 低≠管线输：先看 T3 独立标注一致性，再视频终审仲裁。**单独 T2 不能定谳** |
| 5 | 往返相似度高 ≠ 金标对 | 同族 LLM 生成↔标注共享先验，构造性一致 | 循环性警戒：任何"验证通过"结论必须过视频终审或 T3 独立性检查 |

## 判定矩阵

| T2 往返 | T3 独立标注 | 结论 |
|---|---|---|
| 高 | 高 | 金标推断层可信 (仍建议抽检视频终审) |
| 低 | 高 | **管线弱** (原命题成立，金标当零点有效) |
| 低 | 低 | 金标推断层是单采样噪声——需多标注集成或降级为"参考"而非"零点" |
| 高 | 低 | 词典效应或共享先验污染，人工抽检定谳 |

## 裁决纪律

- 一致性指标对 emotion 用加权语义档 (exact/partial/off) 而非编辑距离——情感词表
  同义太多；felt_intent 用 role-signal 集合 (钩子/铺陈/转折/高潮/收束/成长/危机) 交并比
- 轨 B 每个重标注 run 存完整 prompt+输出留痕；≥2 次独立 run (不同温度/措辞) 才算数
- 报告结论必须写明混杂因素与未决项；Kai 视频终审前不得定谳"金标正确"

## 试点结论 (2026-08-28 ep01 P02)

**Kai 假设被证实**: 金标 P02 结尾层 material 级失真。原片真结局 = 「数到一百」是父亲
托孤离别的调虎离山装置 (221s 承诺→227s「其实我们不是亲爷俩」→250s 托孤前辈→数完
一百父亲消失→297s「他骗了我，我要去把他找回来」)；金标 P02 却写成「温馨成长约定收尾」，
漏掉 227-305s 共 78 秒 (25% 时长)。铁证：片名《爸爸去哪儿？》只有悲壮版才成立。

**层间自相矛盾实锤**: KST 逆向 P09 (视频锚定层) 的 R5 结论「金标=决然开环寻父钩子」
一直是对的；失真的是 LLM 推断的 P02。证明层信任不对称：越上游越不可信。
(附带：既往 demo run 的 requirement 被改成「悲壮/告别」实为忠实原片，此前判其
「不忠实」是误判。)

**T2 单独不足定谳** (往返相似度 0.10 无法区分「管线自由度」与「金标失真」)，
T2+视频仲裁首例即抓到金标缺陷——协议路线正确。修正提案
`golden_p02_fix_proposal.json` 已于 2026-08-29 经 Kai 拍板执行（status=ADOPTED），
P02 已重写为 `video_arbitrated` 级（原件备份+集级 git 化），执行审计见
`gsrt/p02_correction_20260829.md`——执行中追加实锤：全片 beat 时间轴为匀速编造
分布（Midpoint 偏 66s）、中段"前辈为救花青负伤"整段漏采（t185 帧证）。

## See Also

- `kais-movie-pipeline/pipeline-checkpoint-injection` — checkpoint 锻造 (注意坑 #1 补丁)
- `kais-movie-pipeline/phase-ab-lab` — run_arm.sh 复用 (KAIS_P09_LOOSE_ASSET_GATES 等环境固化)
- `kais-movie-pipeline/kst-p09-reverse-supply-diff` — T1 锚定层与 forward_diff 原始方法
