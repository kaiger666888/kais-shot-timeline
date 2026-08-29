# KST 迭代策略与演进路线（对接 kmc-iteration-system）

> 2026-08-29 随 GSRT 三 skill 入库（skills-kmc-inbox/）一并定稿。
> 回答两个问题：① KMC 迭代系统伞的两条循环如何映射到 KST；② 伞的收敛-固化语义如何指导 KST 下一步演进。

## 0. 全景定位：KST 是迭代系统的「金标生产者」

```
┌─────────────────────────┐          ┌──────────────────────────┐
│  KST 逆向生产线（本仓）    │  金标出库  │  KMC 正向生产线            │
│  原片 → 分镜/音轨/转录     │ ───────▶ │  （kais-movie-pipeline）  │
│  → prompt 反推 → 金标打包  │          │  P00→P13 逐节点迭代进化    │
└─────────────────────────┘          └──────────────────────────┘
        ▲                                    │
        └────────── gap 分流仲裁 ─────────────┘
          （金标失真→修 KST；管线弱→改 KMC）
```

- KMC 伞 skill（kmc-iteration-system）定稿的域边界：GSRT 三 skill 归 KST 域
  （`skills-kmc-inbox/`），KMC 只消费「已验证金标」。
- **关键洞察**：KST 循环二的对比目标是**原片本身**（物理真相：帧/ASR/时间码）；
  KMC 循环二的对比目标是 KST 产出的金标（LLM 推断产物）。所以 **KMC 的收敛
  上限被金标可信度封顶**——这就是伞把金标验证剔给 KST 的根本原因：
  KST 做的是迭代系统的**地基工程**，金标不真，KMC 迭代越努力偏得越远
  （实证：ep01 P02 material 失真，金标漏 78s=25% 时长，温馨假结局）。

## 1. 伞两循环 → KST 映射

### 循环二（有金标）在 KST 的实例 = GSRT render-back（已跑通 ✅）

伞的逐节点循环在 KST 的最细粒度 = 逐镜。`kst-gsrt-prompt-iteration` 5 步循环
就是伞循环②③的镜级实例化：

| 伞循环步骤 | KST 实例 | 实测 |
|---|---|---|
| ① gap 分析：达标？完成上游意图？ | dHash 锚差 <15 + vision 中帧节拍判定 + **vision 实读原片纠偏 GT**（3 镜全靠它破局） | shot89 刀向/捂脸纠偏、shot64 构图纠偏 |
| ② 改生产管线 → 重产 | **唯一变量 = prompt**；引擎臂恒定（i2va+turbo+seed42+1344x768+length=原镜帧数） | v1→v6 |
| ③ 有没有进步？ | 锚差走势 + vision 判剩余差距性质 | 见下 |
| ④ 未收敛 → 回退重来 | 平台期 + 剩余差距属引擎边界 → **锁定（"prompt 如实、引擎边界"定性），不无限迭代** | shot64 四轮收敛 |
| ⑤ 收敛 → LOCK | prompt 回写金标 P09 ltx_prompt | 4+1 镜定谳 |

实测收敛数据（小江湖 ep01）：shot 1/57 首轮过（省 GPU）；89/90 一轮收敛；64
（0.87s 极速镜）四轮收敛，v6 分离式描述法（构图终点 + 运动主体分离）破局。

**伞的「意图完成度第一问」在 KST 的形态**：逆向 prompt 的意图锚 = 原片画面本身。
"vision 实读原片纠偏 GT" 本质就是回物理真相处拿意图锚，而不是从上一版判词线性外推
（v4 "占满画面" 推过头出画即反例）。

### 循环一（无金标）在 KST 的实例 = 机械层演进（当前冻结 ❄️）

分镜检测器 V1→V2→V3b 的版本演进史就是循环一实例：无金标时以「上一版最优」为
及格线，新旧版分镜边界对比。**现状 = validated 基线冻结**（v1.3 milestone 完稿，
CLAUDE.md Constraints 明确"不改算法"）。解冻条件见 §5-P2。

## 2. 金标可信度分级（KST 的核心产品规格）

KST 产出的不是"一份金标"，而是**分级信任的资产**。`golden-set-validation` 已定义
`gsrt_validation` 三级，消费规则：

| 等级 | 证据 | KMC 可消费用途 |
|---|---|---|
| `anchored` | T1 锚定审计过（vs 时间码/ASR/帧） | 仅机械层参考（分镜边界/对白/时长）；**不可作推断层收敛目标** |
| `roundtrip_ok` | T2+T3 过判定矩阵 | 剧情结构层收敛目标（仍需抽检仲裁） |
| `video_arbitrated` | + T4 render-back / 视频仲裁 | 全层收敛目标，循环二正式金标 |

实证教训（写进消费规则的理由）：ep01 P02 未过验证即被当真值，正向 diff 的差距被
误归因为"管线弱"；实为金标失真。**层信任不对称**：KST 机械层（锚定层）一直是对的，
失真的是上游 LLM 推断层——越上游越不可信。

## 3. KST 内部逐节点收敛顺序（与伞"下游只能从锁定资产起产"同构）

```
原片 → [分镜边界] → [音轨/转录] → [prompt 反推] → [金标打包出库]
        机械层❄️      机械层❄️       循环二主战场🔥      前序全LOCK才可打包
        v1.3已冻结    validated基线   逐镜render-back     必带gsrt_validation等级
```

出库纪律：金标打包前按 §5-P0b 抽样过 T4 出厂检验；不过检 = 不出库，KMC 不得消费。

## 4. KMC↔KST 接口契约

1. **金标出库规格**：manifest 必带 `gsrt_validation` 字段（三级语义见 §2）。
2. **gap 分流仲裁协议**：KMC 循环二遇到大 gap，先跑 GSRT 分流「金标失真 vs 管线弱」
   （T2 低时叠加 T3/视频仲裁，勿凭 diff 定罪）。金标失真 → 修 KST 金标；管线弱 →
   改 KMC 管线。ep01 P02 案例即本协议的判例。
3. **台账外键**：KST `gsrt/renderback/manifest_vN.json`（镜级迭代台账）↔ jobs.json
   （渲染状态机）↔ KMC exp-ledger 的 render-back 实验条目，decision_id 链与伞的
   三账本视图（exp-ledger → forge-manifest → blind-votes）对齐。
4. **PENDING-PATCH ×3**（`golden-set-roundtrip-validation` SKILL.md 尾部，落点在
   kais-movie-pipeline 仓，下次进该仓时施补）：pipeline-checkpoint-injection 坑 #1
   补丁 / kais-gold-set 内省式警戒节 / kst-p09-reverse-supply-diff 零点假设警戒。
5. **KST 仓领先 origin 的提交积压**：按 push-gate 纪律攒批一次性 push，收尾必查
   `git rev-list --left-right --count main...origin/main` 归零。

## 5. 演进路线（消费需求拉动，优先级序）

### P0 — 金标可信度基建（KMC 循环二的地基）— ✅ EP01 全链完成（2026-08-29）

- [x] **a) P02 失真修复收口**（08-29）：P02 → 首个 `video_arbitrated`；执行中追加实锤×2
  （全 beat 时间轴编造 / 前辈负伤漏采）。审计：`gsrt/p02_correction_20260829.md`
- [x] **b) 全链 T1 锚定 + 同源污染清除**（08-29）：P00-P07×8 件修正（含 P04「黑头前辈
  =绿螳螂」名字误导编造实锤），尾段补采 +5 镜（S1_91-95，时间轴 308.6s 闭合原片），
  T3 尾段盲标 PASS（族内警示在案）。**EP01 成为首部全链锚定、可整集出库的标准集。**
  收官报告：`gsrt/ep01_fullchain_closure_20260829.md`；金标集 git `~/learning_sets`（a8ab2dd）
- [x] c) T4 尾段 4 镜 render-back 回收 + QC 判收敛（2026-08-29 收官 **4/4 PASS**，manifest_v8）：
  92 节拍后移~10%备注 PASS / 93 拉远一镜到底 ANCHORED / 94 航拍全对（条件帧字幕伪影在案不计判分）/
  91b 躬身复现 PASS（d_last=11.3 临界同 92 族；原片窗口内本就未离开，渲染如实复现）。
  QC 纪律：vision 单点 FAIL 判读必须末端加密采样复核（92 翻案 + 91 原片对照双实证）。台账
  `gsrt/renderback/t4_tail_qc_verdicts.json`（判定+infra 救回记录）/ `t4_tail_results.json`
- [ ] d) T4 出厂检验常态化：新 episode 金标打包前抽样 5-6 镜（≈5 镜 × 40min GPU）

### P1 — prompt 层规模化（循环二从抽样到全覆盖的路径）

- [x] **a) 全镜批量锚评分**（2026-08-29 完成，三级协议）：①dHash 全量预筛 93 镜
  （71 过/17 红/5 轻）→ ②RED 密集重采样甄别（11 假红=超短镜边界抖动，窗口内有锚定帧）
  → ③3 CONFIRMED vision 触表终审全清白（高动态运动模糊 dHash 极限假红）。
  **终版：85 ANCHORED / 8 LIGHT 灰区 / 0 确认失真** —— 金标机械层锚定全量实测成立。
  台账 `gsrt/renderback/p1a_anchor_scan/`（scan_93 / red_recheck / p1a_final_ledger +
  confirmed_contact_sheet.jpg）；审计脚本 p1a_*.py ×3。
  附带实锤：frames.json 全帧 base64 带 16 字节垃圾前缀（ffmpeg 系容忍/PIL 系必炸），
  canonical 修复待拍板；尾段编号双轨（shot-list 93 镜 vs manifest_v8 局部编号）已记录。
- [ ] **b) 逆向 prompt 生成器沉淀**：v6 分离式描述法（构图终点 + 运动主体分离描述）
  回写 `prompts/` 反推生成器，让新一轮金标天生携带已验证的描述模式。

### P2 — 机械层（冻结中，解冻需走循环一）

- [ ] **a) 检测器 V4 候选**（仅当下游消费暴露边界问题）：必须新旧版分镜边界对比 +
  下游 prompt 反推质量作最终裁判，走完整循环一（改→对比→收敛→LOCK）。
- [ ] **b) 仓卫生**：requirements.txt 锁定（GSD 审计已指出缺 lockfile）、
  `gsrt/` 二进制证据已 ignore（可再生：ffmpeg 提帧 / H3 渲染产物）。

## 6. 评估纪律在 KST 的适用（从伞收拢，不重述）

- 进程独立盲测：vision 判定不得带生成侧上下文；条件帧污染（烧录字幕/水印）不计入判分。
- 感知类终审 = Kai 本人（render-back 对比页人工定谳）；自动化指标只做预筛。
- 复现 ≠ 正确：T2 高相似不采信为金标正确证据（同族 LLM 共享先验）。
