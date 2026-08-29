---
name: golden-set-roundtrip-validation
description: "金标/标准集真值验证协议 (GSRT Golden-Set Round-Trip)。内省式验证清单只证『字段填了』不证『字段是对的』——本协议用 T1 视频锚定审计 + T2 checkpoint 锻造往返注入 + T3 独立盲重标注 + 视频仲裁四层让金标推断层被迫证明自己。首例 (xiaojianghu-ep01 P02) 实锤金标 material 级失真。触发词：金标验证、标准集验证、往返验证、GSRT、gold set validation、逆向可信度、零点验证、金标对不对、render-back、渲染回测、消费端验证"
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [kais, movie-pipeline, golden-standard, validation, reverse-engineering, methodology]
---

# GSRT — 金标/标准集往返验证协议

回答元问题：**「如何确定逆向的黄金集是经过验证的？」**——schema 完整性、字段非空等内省式
检查只证明"字段填了"。`kais-gold-set` Step 2 的正向 diff 默认金标忠实 (零点假设)，但金标的
**LLM 推断层** (P00-P02) 可能 material 失真——此时 diff 大会被误归因为"管线弱"。

## 三层验证 + 终审

| 层 | 方法 | 检验对象 |
|---|---|---|
| T1 锚定审计 | 逆向产物 vs 视频证据 (时间码/ASR/帧) | 机械层 (KST 逆向已覆盖) |
| T2 往返注入 | 金标 P0k 注入干净臂正向跑 P0k+1，对比金标 P0k+1 | 推断层链内自洽 |
| T3 独立盲重标注 | 新 LLM 只看机械层证据重推 emotion/felt_intent (金标答案封存)，算一致性 | 推断层单采样噪声 |
| T4 render-back | 首尾帧从原片硬提取+被测逆向 prompt 直灌 → H3 预览路径渲染 → 与原片段同位并排对比 (Kai 盲判) | **prompt 消费端真值** (Kai 08-28 拍板的主验证法) |
| T4 渲染回测 | 首尾帧(原片硬提取)+被测prompt → H3 turbo 渲染 vs 原片 | prompt 层真值 (消费端) |
| 视频终审 | 争议字段抽帧 + ASR 全文仲裁 (Kai 可加匿名盲判) | 破循环性 (同族 LLM 生成↔标注共享先验) |

**判定矩阵**: T2高T3高=可信 | T2低T3高=管线弱(零点有效) | **T2低T3低=金标噪声(降级为参考)** | T2高T3低=先验污染。

## ⚠️ 两条铁律 (试点血泪)

1. **T2 单独不足定谳**：相似度低无法区分「管线创作自由度半径」vs「金标失真」(金标作者全片在手，
   注入臂只见压缩后的上游)。必须叠加 T3 或视频仲裁。
2. **T2 高 ≠ 金标对**：同族 LLM 生成↔标注共享先验，一致性可被构造出来 (Kai 三污染原则之
   "复现≠正确")。

## 首例试点结论 (2026-08-28, xiaojianghu-ep01 P02)

- T2 相似度 median=0.10 (15/15 beat 结构对齐、内容级分叉) → 视频仲裁实锤 **金标 P02 结尾层
  material 失真**：原片真结局 = 「数到一百」是父亲托孤离别的调虎离山装置 (ASR 221-305s：承诺→
  「其实我们不是亲爷俩」→「我时间不够了」→托孤前辈→数完一百父亲消失→「他骗了我，我要去把他
  找回来」)；金标写成温馨成长约定收尾，漏 78s = 25% 时长。铁证：片名《爸爸去哪儿？》只有悲壮版成立。
- **层信任不对称实锤**：KST 逆向 P09 锚定层 (R5「决然开环寻父钩子」) 一直是对的；失真的是上游
  LLM 推断的 P02。越上游越不可信。
- 附带平反：既往 demo run 把 requirement 改成「悲壮/告别」曾被判"不忠实金标"——实为忠实原片，
  金标才失真。**上游被"改坏"的 run 可能反而更忠实，归因前先仲裁视频。**

## T4 — 消费端渲染回测 (render-back, 2026-08-28 试点通过)

T1-T3 之上的最硬验证层，Kai 定案方法论：**首尾帧 ffmpeg 硬提取自原片（端点钉死真相）+ 被测逆向
prompt 原文直灌 + H3 turbo FL2VA 渲染回来与原片并排对比——渲染一致 = prompt 对**。比文本层往返严格
（渲染回测量的是"能不能干同样的活"，不是"像不像"）。

**试点结果 (小江湖第01话, 5镜)**: 4 PASS + 1 边界镜。托孤区 89/90 (金标 P02 漏采的 78s 悲壮段落)
躬身行礼/亮刀迎战动作语义复现成功——逆向 prompt 能干同样的活，且 KST 机械层抓到了金标漏掉的段落。
边界镜 64 (0.87s): 首帧近乎复刻、冲刺语义保住，仅"贴地疾行→面部大特写扑面"的景别推进超出 H3 turbo
能力边界——prompt 如实描述了原片，判 prompt 无罪。**能力边界与 prompt 缺陷必须分流，前者不可归因上游。**

### 工程要点 (KAP i2va)
- multipart 必填 `projectId` (数字, 仅进文件名); 帧数走 n%17==5 网格; duration<4s 用 `length` 绕开
- 08-17 后 profile 白名单仅 `turbo|native-sage` (preview 已废弃); BGM ban 用正面词 `strictly diegetic in-world sound, unscored scene`
- 产物落容器内, KAP output 404 → `docker cp comfyui-primary:/root/ComfyUI/output/<prefix>_00001_.mp4`

### 基建坑: gpuQueue 僵尸等待者风暴 ⚠️
- KAP gpuQueue VRAM 门 (free < 18GB) 会**收下 POST 挂起不回包**，每条最长等 1800s；卡被多方占用时
  (demo-pixar/A-B批/qwen_eye) 门长期不放行
- **curl 超时重试 = 最差应对**：每次重试堆一个僵尸等待者，之后全部会渲染（同镜重复渲染 N 份）
- 正确姿势：**单次提交 `-m 1900` 覆盖最长锁等待；空响应不重试，转容器产物守望模式** (30s 轮询
  `docker exec comfyui-primary ls /root/ComfyUI/output/` 先到先收)
- 清理僵尸需 `POST /api/production/gpu-queue/purge-waiters` + `KAP_ADMIN_TOKEN` (systemd 当前未配置 → 404)

### QC 协议
- 像素锚点差 (256×144 灰度均值): 条件帧 vs 原片 <5 且 渲染 t0/tend vs 条件帧 <10 = 钉住
- 像素高 diff 有假象 (mp4 关键帧 seek 偏移)：必叠加 vision 动作语义判定仲裁 (身份/动作/机位/景别)
- 原片烧录字幕/水印会被条件帧继承并被 H3 复刻 → 标注为条件帧污染，不计入 prompt 判分
- 配套脚本: `scripts/renderback_submit.py` — 参数化提交器 (单次提交覆盖锁等待 + 容器守望 + docker cp 提取), 新 episode 复制改参数即用

## 坑表

| # | 坑 | 症状 | 解法 |
|---|---|---|---|
| 1 | 锻造 checkpoint 缺 `current_phase_id` | 日志 `start_idx=0 (checkpoint=False)`，p01 重跑**覆盖注入产物** | 两处 state 文件都写 `current_phase_id`+phases 条目；点火前 `_compute_start_index()` dry-run 断言=期望 idx；健康日志=`(checkpoint=True)` |
| 2 | 既往 run 的 requirement 被改过 | 往返对比混杂非金标上游信号 | 必须新建干净注入臂 (requirement 逐字节拷金标 P00)；血缘检查 common/identical keys 数 |
| 3 | 金标 P09 ↔ KST prompts.json 90↔93 对齐 | 逐镜时间窗抓 ASR 对白 33% mismatch | 跨镜旁白归属是编辑约定差非数据损坏；证据包对白用金标 dialogue_text 本体，归属不进判定 |
| 4 | 判定量具 | 中文同义改写让 SequenceMatcher 全红 | emotion 用同义聚类三档 (exact/partial/off)；felt_intent 用 role-signal 集合交并比；见 scripts/agreement_report.py |

## 判分与留痕纪律

- 轨 B 每个重标注 run 存完整 prompt+输出；≥2 次独立 run (不同温度/措辞) 才算数
- 金标被测字段 (emotion/felt_intent) 必须从证据包剥离封存，防泄漏
- 结论必须写明混杂因素；Kai 视频终审前不得定谳"金标正确"
- 金标 metadata 建议加 `gsrt_validation` 等级字段: `anchored / roundtrip_ok / video_arbitrated`

## PENDING-PATCH ×3 (farm 真源 git 直写待办, 以下补丁块可直接粘贴)

1. **kais-movie-pipeline/pipeline-checkpoint-injection/SKILL.md** — 其 forge 示例 `state = {"episode": EP, "phases": phases}` 是坑 #1 的源头，需替换为带 `current_phase_id` 的版本 + dry-run 预检 (本文档坑表 #1)。
2. **kais-creative/kais-gold-set/SKILL.md** — 1.3 验证清单前加「内省式警戒」节 + GSRT 三层/判定矩阵/试点结论 (指向本 skill)，并把「已有标准集」表加 gsrt_validation 列。
3. **kais-movie-pipeline/kst-p09-reverse-supply-diff/SKILL.md** — 正逆复刻 diff 节加零点假设警戒：diff 大先分流"金标失真 vs 管线弱"，forward_diff R1-R5 动作项注入管线前核对目标 slot 验证等级。

## T4 渲染回测 (render-back, Kai 2026-08-28 拍板的方法论升级)

消费端验证:金标的最终消费形态 = "首尾帧 + prompt → 视频"。与其从 P00 顺依赖链往下游修,
不如直接在最终消费点检验——首尾帧从原片 ffmpeg 硬提取 (端点钉死在真相上),被测 prompt 描述
中间过程,H3 预览路径渲染回来与原片段同位对比。**渲染一致 = prompt 能干同样的活**,比文本层
往返 (T2) 严格:文本 diff 量"像不像",渲染回测量"能不能"。修正顺序从末端往上游推导,
不从上游往下猜。

试点: 小江湖第01话 5 镜 (开场拉镜/战斗压制/0.87s 极速镜/结尾亮刀/277s 托孤躬身礼)。

### 执行契约 (2026-08-28 试点实证)

| 环节 | 要点 |
|---|---|
| 提交 | KAP i2va multipart: firstFrame+lastFrame+prompt+length+profile=turbo+seed+projectId(**必填数字**,缺失报 NaN 错)+filenamePrefix |
| 短镜 | duration 有 4s 下限,走 length=帧数绕开; 网格 n%17==5 服务端自动对齐, 0.87s 镜=22帧 |
| 韧性 | KAP 偶发空响应→重试4次×15s 自愈; 产物 KAP output 404→docker cp comfyui-primary:/root/ComfyUI/output/<prefix>_00001_.mp4 |
| 托管 | jobs.json 状态机 (done/extract_failed 带文件指针防重复渲染) + 外层循环续跑 (单镜40min上限×24轮,退出码3=续跑/2=硬失败) |
| QC | 像素锚定判据 (256×144 缩放 RGB mean abs diff): 渲染t0 vs 条件首帧 <10=锚定 <20=轻漂移 >25=没钉住; 条件帧 vs 原片对应时刻同判。vision 读对比网格会误读布局(虚报序列错位),像素指标才是硬证据 |

### ⚠️ 条件帧污染 (判分纪律)

原片烧录字幕/角标/水印会被条件帧继承并被 H3 复刻——对比时标注为**条件帧伪影,不计入
prompt 判分**。被测 prompt 的"一致性"只判四项:场景元素/角色身份特征/动作语义/构图机位。

模板脚本: `scripts/submit_renderback.py` (复制改 BASE 即用; 配套 run_renderback.sh 外层
循环见工作区 /data/workspace/kais-shot-timeline/gsrt/renderback/)。

## T4 消费端渲染回测 (render-back, Kai 2026-08-28 拍板)

金标验证的终审层：金标最终消费形态 = 首尾帧 + prompt → 视频，直接在最终消费点检验。

原理：首尾帧从原片 ffmpeg 硬提取 (端点钉死真相) → 被测逆向 prompt 描述中间过程 → H3 预览路径 (KAP i2va, profile=turbo, FL2VA 双锚) 渲染回来 → 与原片同窗对比。**渲染一致 = prompt 对**。比 T2 文本往返严格：文本 diff 量"像不像"，渲染回测量"能不能干同样的活"。修正顺序从管线末端往上游推导，而非从上游往下猜。

工作区 (`gsrt/renderback/`)：manifest.json (shot_id/target_window/duration_sec/first|last_frame/reverse_prompt_under_test/length) · frames/{sid}_first|last.jpg · targets/orig_XXX.mp4 (对比基准) · renders/ (回测成品) · jobs.json (状态机) · renderback.log。

执行要点：
- length 对齐 n%17==5 网格 (6.73s→158 / 0.87s→22)；duration<4s 用 length 绕
- KAP i2va multipart：projectId 必填 (缺失报 `期望 数字 实际接收 NaN`)、seed 固定、prompt 尾加 diegetic-sound 规则词；**单次提交不重试**——挂起语义与重试风暴反模式见 `kais-video/h3-kap-api-surface-complete` gpuQueue 节
- 产物提取绕 KAP output 404：`docker cp comfyui-primary:/root/ComfyUI/output/<prefix>_00001_.mp4`
- QC 像素锚定先于 vision：PIL+numpy 256×144 mean-abs-diff 三组——条件帧 vs 原片 t0/t_end (钉位校验, ~2-5)；渲染 t0 vs 条件首帧、渲染尾 vs 条件尾帧 (锚定服从, <10)。vision 判读对比拼图会误读序列顺序，像素差是硬证据
- 条件帧伪影：原片烧录字幕/角标被条件帧继承、H3 复刻——对比页标注为条件帧污染，不计入 prompt 判分

## Render-back 试点 (2026-08-28, T4 首例, Kai 定谳方法论)

> **Kai 原话逻辑**:「从 KMC 管线末端开始修正——借助目标视频作目标,给提取的首尾帧写 prompt,
> 让 H3 预览路径生成视频,对比生成物与目标视频。一致即证明 prompt 是对的。」
> 修正顺序**从消费端往上游推**,不要从 P00 顺依赖链往下猜。

实例: `/data/workspace/kais-shot-timeline/gsrt/renderback/` (manifest 5镜/frames/targets/renders/
submit_renderback_v2.py),成片 4+1 镜,shot1/57/64 三档锚点 QC 见 `references/renderback-ops.md`。

## 配套文件

- `scripts/submit_renderback_v2.py` — T4 render-back 提交器 v2 (单次提交+容器守望模式, 内嵌 gpuQueue 挂起语义与重试风暴反模式; 改 BASE 后可复跑)
- `scripts/agreement_report.py` — 轨 B 判分器 (emotion 聚类三档 / felt_intent role-signal / shot_type 别名)
- `scripts/submit_renderback.py` — T4 渲染回测提交器 (i2va multipart + 空响应重试 + docker cp 提取 + jobs.json 状态机)
- `scripts/agreement_report.py` — 轨 B 判分器 (emotion 聚类三档 / felt_intent role-signal / shot_type 别名)
- `templates/relabel-prompt.md` — 轨 B 盲重标注 prompt 模板 (证据包占位符)
- 工作区实例: `/data/workspace/kais-shot-timeline/gsrt/` (SKILL.md 含完整试点叙事、evidence_packs.json、golden_answers_sealed.json、pilot_verdict_20260828.json；golden_p02_fix_proposal.json 已 ADOPTED 执行 2026-08-29，审计 gsrt/p02_correction_20260829.md)
- 注入臂实例: worktree `ep-gsrt01` (金标 P00 逐字节 + P01 忠实映射)

## See Also

- `kais-movie-pipeline/pipeline-checkpoint-injection` — T2 的注入机制 (注意坑 #1 补丁待并入)
- `kais-movie-pipeline/phase-ab-lab` — run_arm.sh 单臂执行环境复用
- `kais-movie-pipeline/kst-p09-reverse-supply-diff` — T1 锚定层 + forward_diff (零点警戒待并入)
- `kais-creative/kais-gold-set` — 金标构建与正向 diff 主流程 (GSRT 节待并入)
