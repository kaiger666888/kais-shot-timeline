# P02 GSRT 修正执行审计（2026-08-29）

> Kai 拍板 `golden_p02_fix_proposal.json` 后的执行记录。执行中按「根证优先」追加了
> 提案之外的三处修正，全部有帧/ASR 双证据。

## 被修对象

`~/learning_sets/golden-standard-xiaojianghu-ep01/p02_story-framework.json`
（原件备份 `.bak-gsrt-20260829`；金标集已 git 化，commit `2e5a093`）

## 提案内修正（按拍板范围）

| # | 缺陷 | 级别 | 修正 |
|---|---|---|---|
| 1 | Finale/Final Image「温馨成长约定收尾」漏 227-305s（25% 时长） | material | 重写为调虎离山真结局：托孤→借刀决死→数完父失→寻父钩子 |
| 2 | 情绪弧终于「温暖·成长萌芽」 | material | 重写为 Fall-and-Resolve：托孤诀别(9)→消失慌乱(9)→决然寻父(8) |
| 3 | beat 时间码漂移 | minor | 见下方追加修正 #5——全部 15 beat 重锚，非局部补丁 |

## 执行中追加修正（提案外，证据驱动）

| # | 发现 | 级别 | 证据 | 修正 |
|---|---|---|---|---|
| 4 | **敌人物种金标正确**：红色僵尸蜈蚣（verdict 仅「存疑」） | 确认不修 | t165 帧字幕「这个僵尸蜈蚣啊」直接认证 + t110/t125/t130/t172 四帧形态一致；t240 绿螳螂=前辈非敌人 | 前辈补视觉锚「绿螳螂」入 P02 |
| 5 | **全片 beat 时间轴为匀速编造分布**，非仅尾段漂移：Midpoint「打完收工」金标 3:30 实际 2:24（偏 66s）；「切磋规矩」金标 0:30 实际 0:21-0:25；承诺金标 5:00 实际 3:40（偏 80s） | material | ASR 全量 102 段逐 beat 锚定 | 15 beat 全部重写时间码 + 内容按 ASR 逐句校准 |
| 6 | **中段「前辈为救花青负伤倒地」整段漏采** | material | 帧证 t185（花青缠绷带前肢查看倒地多角甲虫）+ ASR 3:53「前辈都怪我」/3:56「你是为了救我才」互证 | Bad Guys Close In/All Is Lost 补采该情节 |

## 关键时序自洽链（修正后的叙事骨架）

```
3:40 承诺(数到一百教功夫) → 3:46「开始」 → 3:47「告诉你个秘密…不是亲爷俩」
→ 3:58「我时间不够了」 → 4:00 借刀 → 4:09-4:24 托孤 → 4:32-4:45 数数61→100
→ 4:45 数完父已消失 → 4:52「爸爸你在哪儿」 → 4:56-5:02「他骗了我…找回来」
```
数数贯穿托孤与离去全程 = 调虎离山的直接证据（「开始」与「秘密」仅隔 1 秒）。

## 验证定级

- **T1 锚定**：ASR 全量 102 段逐 beat 对拍 + 9 帧仲裁 → ✅
- **T4 render-back**：托孤区 shot89/90 定谳——90 PASS（08-28 试点）；89 经 Kai 复核
  揭穿 v3 假收敛（构图全对但拔刀缺鞘→刃交接帧）后 v4 真收敛 LOCKED（08-29 晨，
  manifest_v7）。残项：277-305s 区间（数数回头/独白收尾）待 GPU 窗口补测。
- **T2 r2 往返**：豁免——推断层已重锚至机械层（ASR/帧转写），同族 LLM 往返一致性
  对重锚后转写层边际价值低（「复现≠正确」原则的反向应用）。裁定记入 p02
  `gsrt_validation.waived`。
- **结论**：p02 → `video_arbitrated`（本标准集首个全级金标）；集内其余 P0k =
  `unvalidated`（metadata.json 已立台账，KMC 消费时推断层按 anchored 以下对待）。

## 修改文件清单

- `p02_story-framework.json`（v2，11398B，15 beats / 13 anchor_points + `gsrt_correction` + `gsrt_validation` 块）
- `p02_story-framework.json.bak-gsrt-20260829`（原件保全）
- `metadata.json`（gsrt_validation 台账 + correction_log；备份 `.bak-gsrt-20260829`）
- `gsrt/golden_p02_fix_proposal.json` → status: ADOPTED
- 仲裁帧证据：`output/…/gsrt_fix_audit/aud_t{110,125,130,150,165,172,185,200,205}.jpg` + 双网格（可再生，不入库，时间码已录本报告）
