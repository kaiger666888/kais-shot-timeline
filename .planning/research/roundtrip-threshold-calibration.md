# Phase 21 Round-trip 阈值校准报告 — ep01 uniform-19 @1344×768 双信号实测分布

> **Deliverable status:** FINAL —— Kai 已裁决（2026-08-20）：**τ_sim = 0.9670**（faithful 桶最大间隙上沿，高保真核路线）+ 抽检 5 镜 approved（无不一致上报）。verdict 已应用（accepted=4 / rejected=15），幂等已证。裁决详情见 §6.3。
> 裁决入口见 §6 Recommendations/裁决记录（候选预演 + 区分度处置选项）；裁决后本报告升 FINAL
> 并回填裁决记录节。**τ 只能由人看分布裁决，机器指标仅参考**（反循环论证声明见 §3.3）。

- **Generated at (UTC):** 2026-08-20T01:42–02:05（scorer/judge 烧录窗口；DRAFT 定稿 02:05Z）
- **Repo HEAD (short):** `b43aa19`（含 shot 19 解析修复；分布数据在该状态烧录）
- **Fixture:** ep01 — `output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。`
  （目录名含全角括号与中文冒号；vch=`ece64d62bcbc534a`）
- **校准集（19 镜，uniform-20 采样减 shot 70）：**
  `#1 / #5 / #10 / #14 / #19 / #24 / #28 / #33 / #38 / #42 / #47 / #52 / #56 / #61 / #66 / #75 / #80 / #84 / #89`
  （shot 70 被 max-shot-sec 跳过：19.7s > 10.0s，`skipped.json` 落盘 duration_over_max）
- **分辨率纯度：** 19/19 条 regen `engine_version=fl2va-int8/euler+simple/15/1344x768`（Pitfall 7——
  896×512 smoke cache 全 miss 重打分；本报告所有数字均出自 1344×768 身份）
- **raw 零改写声明：** 本报告 judge reason 全部为引擎真实输出原文（仅超长截断至 schema 上界 2000，
  实际最长 ~300 字符远未触及）；scorer 数字为 cache 直读（score 钳 [0,1] 后 round 4 位、
  per_position_cos 原始未钳——21-01 决策）。修正类干预只有一处且已单列（§2.3 shot 19
  末尾 `}` 截断修复——传输层修复，判定语义零改动，TDD 3 用例 + 全套件 160 passed）。
- **896×512 对照数据点（21-02 smoke，不进校准集）：** shot 1 sim=0.9309 / shot 47 sim=0.8396，
  双镜 prompt_faithful conf=0.95。同镜 1344×768 重打分：shot 1 → 0.9351、shot 47 → 0.8382
  （差 +0.0042 / -0.0014——分辨率切换下分数稳定，SigLIP 窄带内无分辨率系统性偏移的可信迹象）。

## 1. 头部元数据摘要

| 项 | 值 |
|----|-----|
| 批渲染（21-02 启动 overnight） | 2026-08-19T22:35:11Z 启动 → 2026-08-20T01:28:05Z 收尾（wall ≈2h53m，19 镜实渲 0 cache-hit 0 failed） |
| scorer 全量（本 task） | 2026-08-20T01:42Z，wall 1m19s（SigLIP fp16 @cuda:0，19 miss→19 分） |
| judge 全量（本 task） | 2026-08-20T01:44Z，wall 2m30s（qwen-eye @cuda:1，18 judged + 1 failed→修复后补齐，见 §2.3） |
| 判定引擎 | qwen-eye `qwen3.8-27b-q3@c3949404`（19/19 attempts 一次或重问后 parse-ok） |
| 打分模型 | `siglip-so400m-patch14-384`（transformers-5.6.2，pooler_output 1152d L2 归一余弦） |
| schema gate | `_iter_sidecar_errors` 全量 0 errors（19 条双半边：scores.midframe_sim + scores.judge） |
| pytest | 160 passed（157 基线 + 3 shot 19 修复新用例），3.6s，零回归 |
| roundtrip.json sha256（裁决前） | `84b5d24453609b4e05cbe744b28e46f91b92f7dbec2a706409fcb5cb1b34c3fe` |

## 2. 烧录实录

### 2.1 overnight 批收尾核对（21-02 交接块验收）

pidfile PID 4112729 不存活；日志收尾三行齐：`roundtrip.json 已写入（19 shots，schema 1.3 校验通过）` /
`完成：rendered=19 cache-hit=0 failed=0 sampled=20 skipped=1` / 产物目录行。19 个
`shot_XXX_regen.mp4` @1344×768 在盘、sidecar 19 条 regen 半边全 1344x768（本报告开头断言）。

### 2.2 双信号全量计时

| 步骤 | 调用量 | wall | 备注 |
|------|--------|------|------|
| scorer（GPU0 3060Ti） | 19 镜 × 16 帧 + 2 次前向/镜 | **1m19s** | 含 SigLIP 离线加载 ~10s；cache 19 miss 全写入 |
| judge（GPU1 3090） | 19 镜 × 1 grid 调用（+重问） | **2m30s**（首次全量） | comfy_free 先行；引擎已驻留（owned=False 快路径）；18/19 首轮 judged |
| judge 补齐 shot 19 | 1 镜 | 5.9s | 解析修复后（§2.3）；attempts=[ok] |

### 2.3 烧录期修正：shot 19 末尾 `}` 截断（Rule 1，已 TDD 修复）

首次全量 judge 中 shot 19 三答全部 `no-brace`；重跑仍三连 `no-brace`（确定性 ~2/3+ 截断率）。
字节级归因：引擎在 `。"` 后提前 EOS，**闭括号 `}` 被 token 截断**（raw 以 `"` 收尾、以 `{` 开头），
`\{.*\}` 正则无匹配。修复（commit `b43aa19`）：`{` 开头却无 `}` 收尾的文本补一个 `}` 再解析；
只补括号、不放松 enum/conf/reason 校验（真坏 JSON 仍落 `json:` 码进 retry-with-feedback）。
TDD：3 个失败测试先写（截断修复 / 不掩盖尾逗号坏 JSON / 校验仍生效）→ RED → 修复 → GREEN。
**判定语义零改动**——shot 19 修复后的 reason 与修复前 probe 所见引擎原文一致（model_diverged，
「闭眼」指令未执行）。另注：shot 52 的 attempts=[no-brace, ok] 证明 retry-with-feedback
在修复前就已能自然恢复一次性截断；shot 19 是截断率极高的极端个例。

## 3. Methodology

### 3.1 双信号定义

- **midframe_sim（SCORE-01）：** 两侧各 N=8 帧 @25%-75% 时窗（t_j = dur·(0.25+0.5·j/7)，
  端点 clamp dur-0.2s），SigLIP so400m embedding 逐位余弦的 mean。t=0/t=end 被条件帧
  结构性排除（实测 t=0 余弦 0.983 vs 中段 0.91-0.93，端点混入会虚高——RESEARCH Pitfall 4）。
- **attribution（SCORE-02）：** qwen-eye 看原片 vs regen 的 2×4 grid（左 ORIGINAL 右 REGEN，
  行 t=0/33/66/100% 标签进图）+ prompt_text 三分类判定：prompt_faithful（描述了X且渲染出X）/
  model_diverged（描述了X渲染成Y）/ prompt_underspecified（欠约束 h3 脑补）。判定以
  t=33%/66% 中段行为为主要证据；reason 必须引用 prompt 原文短语。
- **双门槛（硬合取，无置信门）：** `accepted ⇔ midframe_sim ≥ τ_sim ∧ attribution == prompt_faithful`。
  confidence 只留档不参与判定（21-01 决策：19 镜定两阈已勉强，置信门是伪精度）。

### 3.2 校准流程

19 镜双信号实测分布（本报告 §4）→ **Kai 看分布定 τ_sim + 一句理由**（§6 候选预演表）→
`--apply-verdict --tau-sim <τ>` 冻结写入（verdict{decision, source:"auto", decided_at}）→
PROJECT.md Key Decisions 行 + 本报告 FINAL（rejected 占比按归因分桶审计）。HITL 覆盖写
human 是 Phase 22 PRESENT-01；rejected 永不删除（冻结 merge + 同 τ 重跑 byte 级不变证明）。

### 3.3 反循环论证声明（mirror vision-seq-spike-report L63-68 姿态）

**分布指标是素材、人类裁决是定值。** τ_sim 的选择标准（「多严算严」）本身不是机器可推导的
目标函数——任何「自动选 τ 使 accepted 率=X%」的规则都隐含价值预设（数据集规模 vs 纯度的
权衡属业务决策）。SigLIP 余弦高窄带（随机噪声对 0.99，RESEARCH Pitfall 5）使 CLIP 时代的
阈值直觉全部失效，这正是必须看实测分布的原因。本报告 §4 只呈现机器可见事实，§6 给候选
预演与观察，**不预设结论**；τ 由 Kai 裁决，机器侧任何指标（分位数/极值/间隙）仅作参考。

## 4. 机器可见观察（不预判裁决）

### 4.1 sim 分位数表（n=19，线性插值）

| p10 | p25 | p50 | p75 | p90 | min | max | mean | stdev | span |
|-----|-----|-----|-----|-----|-----|-----|------|-------|------|
| 0.9005 | 0.9143 | **0.9457** | 0.9678 | 0.9741 | 0.8382 | 0.9828 | 0.9389 | 0.0372 | 0.1446 |

分数落 RESEARCH 预告的 0.85-0.98 窄带（shot 47 的 0.8382 微出下沿 0.012——per-position
后两位 j7=0.697 拖低，属真实分布信息，只记录不判阈）。

### 4.2 attribution 三桶分布

| 桶 | n | 占比 | 桶内 sim 范围 |
|----|---|------|---------------|
| prompt_faithful | 10 | 52.6% | 0.8382 – 0.9780 |
| model_diverged | 9 | 47.4% | 0.9011 – 0.9828 |
| prompt_underspecified | **0** | 0% | —（空桶） |

### 4.3 19 镜全量排序表（sim 升序）

| # | shot | sim | attribution | confidence | | # | shot | sim | attribution | confidence |
|---|------|-----|-------------|------------|---|---|------|-----|-------------|------------|
| 1 | 47 | 0.8382 | prompt_faithful | 0.95 | | 11 | 14 | 0.9577 | model_diverged | 0.95 |
| 2 | 52 | 0.8979 | prompt_faithful | 0.92 | | 12 | 28 | 0.9612 | model_diverged | 0.95 |
| 3 | 66 | 0.9011 | model_diverged | 0.90 | | 13 | 42 | 0.9654 | model_diverged | 0.90 |
| 4 | 89 | 0.9035 | prompt_faithful | 0.95 | | 14 | 84 | 0.9670 | prompt_faithful | 0.95 |
| 5 | 38 | 0.9047 | model_diverged | 0.85 | | 15 | 10 | 0.9685 | prompt_faithful | 0.95 |
| 6 | 24 | 0.9238 | prompt_faithful | 0.95 | | 16 | 75 | 0.9701 | prompt_faithful | 0.95 |
| 7 | 56 | 0.9298 | model_diverged | 0.95 | | 17 | 33 | 0.9731 | model_diverged | 0.95 |
| 8 | 1 | 0.9351 | prompt_faithful | 0.95 | | 18 | 61 | 0.9780 | prompt_faithful | 0.95 |
| 9 | 5 | 0.9358 | prompt_faithful | 0.95 | | 19 | 80 | 0.9828 | model_diverged | 0.95 |
| 10 | 19 | 0.9457 | model_diverged | 0.90 | | | | | | |

散点图（matplotlib，Noto Sans CJK）：`.planning/research/roundtrip-calibration-scatter.png`
（x=sim、y=attribution 三行抖动、颜色分桶、镜号标注、p50/p25 参考线；与 §4.3 表互为双保险）。

### 4.4 关键观察（事实记录，非结论）

1. **两桶几乎完全重叠（区分度不足的如实呈现，A4/Pitfall 5 预警命中）：**
   faithful 桶跨 0.8382-0.9780、diverged 桶跨 0.9011-0.9828，重叠区间 0.9011-0.9780 覆盖
   19 镜中 17 镜。**全量最高分镜（#80 sim=0.9828）是 model_diverged、最低分镜（#47
   sim=0.8382）是 prompt_faithful**——sim 单信号与 judge 归因在两端各自「反向」，τ 无法
   选出与 attribution 对齐的切割点。这正是双门槛设计的实证依据：sim 负责「画面像不像」、
   attribution 负责「是不是 prompt 的锅」，二者不可互相替代。
2. **prompt_underspecified 空桶：** judge 把 9 个不满意归因全部判给模型执行（model_diverged），
   零归因给 prompt 欠约束。两种解释：prompts 确实充分（它们从原片逆推而来，信息密度高）
   或 judge 有 model_diverged 偏好。**这是抽检 5 镜（SC3）要人裁的核心问题之一。**
3. **τ 的实际作用面：** 硬合取下 diverged 镜无论 sim 多高都 rejected（9 镜），τ 只在
   faithful 桶内部再切。faithful 桶 sim 升序：0.8382 / 0.8979 / 0.9035 / 0.9238 / 0.9351 /
   0.9358 / **0.9670** / 0.9685 / 0.9701 / 0.9780——**最大间隙在 0.9358→0.9670（Δ0.0312）**，
   τ 落此间隙得 accepted=4 的「高保真核」；τ ≤ 0.8382 得 accepted=10（全 faithful）。
4. **per-position 分布（诊断面）：** j0-j6 各列跨镜 spread 0.118-0.183，**j7（t=75%）
   spread 0.295 显著最宽**（shot 47 j7=0.697 是全表最低单值）——时窗后段承载最多分化
   信息（动作终点最易走样）。若裁决选「调整窗口/N」处置，此为方向依据（后移窗口或
   加密后段采样），本报告不预设该选项。

### 4.5 per-position cos 全表（SC2 审计面直读，j=0..7 对应 t=25%..75%）

| shot | j0 | j1 | j2 | j3 | j4 | j5 | j6 | j7 | mean=score |
|------|----|----|----|----|----|----|----|----|------------|
| 1 | 0.946 | 0.955 | 0.951 | 0.913 | 0.918 | 0.930 | 0.914 | 0.954 | 0.9351 |
| 5 | 0.929 | 0.940 | 0.926 | 0.928 | 0.929 | 0.928 | 0.954 | 0.953 | 0.9358 |
| 10 | 0.919 | 0.974 | 0.961 | 0.958 | 0.976 | 0.984 | 0.988 | 0.987 | 0.9685 |
| 14 | 0.943 | 0.927 | 0.941 | 0.953 | 0.939 | 0.986 | 0.986 | 0.987 | 0.9577 |
| 19 | 0.955 | 0.940 | 0.935 | 0.944 | 0.931 | 0.940 | 0.964 | 0.956 | 0.9457 |
| 24 | 0.936 | 0.971 | 0.973 | 0.978 | 0.955 | 0.873 | 0.859 | 0.846 | 0.9238 |
| 28 | 0.977 | 0.967 | 0.963 | 0.964 | 0.955 | 0.963 | 0.962 | 0.938 | 0.9612 |
| 33 | 0.977 | 0.984 | 0.981 | 0.977 | 0.962 | 0.966 | 0.967 | 0.972 | 0.9731 |
| 38 | 0.850 | 0.881 | 0.872 | 0.916 | 0.921 | 0.929 | 0.943 | 0.925 | 0.9047 |
| 42 | 0.973 | 0.959 | 0.978 | 0.969 | 0.963 | 0.957 | 0.962 | 0.963 | 0.9654 |
| 47 | 0.927 | 0.884 | 0.854 | 0.829 | 0.858 | 0.805 | 0.852 | **0.697** | 0.8382 |
| 52 | 0.902 | 0.871 | 0.903 | 0.925 | 0.928 | 0.909 | 0.884 | 0.861 | 0.8979 |
| 56 | 0.947 | 0.941 | 0.947 | 0.954 | 0.926 | 0.922 | 0.876 | 0.925 | 0.9298 |
| 61 | 0.975 | 0.981 | 0.980 | 0.973 | 0.965 | 0.977 | 0.987 | 0.986 | 0.9780 |
| 66 | 0.875 | 0.866 | 0.891 | 0.901 | 0.907 | 0.928 | 0.922 | 0.919 | 0.9011 |
| 75 | 0.944 | 0.976 | 0.968 | 0.967 | 0.977 | 0.979 | 0.978 | 0.972 | 0.9701 |
| 80 | 0.990 | 0.981 | 0.972 | 0.981 | 0.971 | 0.987 | 0.988 | 0.992 | 0.9828 |
| 84 | 0.963 | 0.940 | 0.952 | 0.970 | 0.970 | 0.971 | 0.988 | 0.982 | 0.9670 |
| 89 | 0.905 | 0.924 | 0.922 | 0.906 | 0.900 | 0.895 | 0.902 | 0.874 | 0.9035 |

（帧清单 `frames.orig/regen` 各 8 条 {j, t_pct, t_sec, path} 在 `route_cache/scorer/shot_XXX.json`
可回放——SC2 审计要求。）

## 5. Evidence（抽检 5 镜素材定位）

### 5.1 抽检 5 镜确定性选择规则（stratified，规则先于结果固定）

按 attribution 桶分层取 sim 极值/中位：① prompt_faithful 桶 sim 最高 1 镜；② 同桶 sim 最低
1 镜；③ model_diverged 桶 sim 中位 1 镜（偶数个取低中位）；④ prompt_underspecified 桶 sim
中位 1 镜——**空桶顺延取全量 sim 次低镜**（若已选则次高镜）；⑤ 第 5 镜 = 全体 sim 中位镜
（已选则向高位相邻顺延）。并列时 sim 升序、shot_id 小者优先。执行代码（python3 -c 直跑，
seed 无关——纯确定性排序）：

```python
rows = sorted([{shot_id, sim, attribution} ...], key=lambda r: r['sim'])   # 升序
median_shot(c) = sorted(c, key=(sim, shot_id))[(len(c)-1)//2]              # 低中位
picked = [max(faithful, key=(sim, -shot_id)), min(faithful, key=(sim, shot_id)),
          median_shot(diverged),
          rows[1] if not under else median_shot(under),                    # 空桶顺延次低
          median_shot(rows)]                                               # 全体中位
```

### 5.2 抽检 5 镜清单（grid 绝对路径 + 原片时窗 + reason 摘录）

EP01 绝对前缀 = `/home/kai/workspace/kais-shot-timeline/output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。`
（`/data/workspace/kais-shot-timeline/...` 同物——镜像路径）。原片 = `<EP01>/h264.mp4`（1920×1080）；
regen = `<EP01>/roundtrip/shot_XXX_regen.mp4`（1344×768）。

| 规则槽 | shot | sim | judge 归因 | conf | 原片时窗 | grid 绝对路径 |
|--------|------|-----|-----------|------|----------|----------------|
| faithful-max | **61** | 0.9780 | prompt_faithful | 0.95 | 168.73–170.30s | `<EP01>/roundtrip/_judge_grids/shot_061.jpg`（385KB） |
| faithful-min | **47** | 0.8382 | prompt_faithful | 0.95 | 129.40–132.60s | `<EP01>/roundtrip/_judge_grids/shot_047.jpg`（347KB） |
| diverged-median | **14** | 0.9577 | model_diverged | 0.95 | 53.37–55.13s | `<EP01>/roundtrip/_judge_grids/shot_014.jpg`（400KB） |
| 空桶顺延·全量次低 | **52** | 0.8979 | prompt_faithful | 0.92 | 138.93–140.20s | `<EP01>/roundtrip/_judge_grids/shot_052.jpg`（356KB） |
| global-median | **19** | 0.9457 | model_diverged | 0.90 | 70.80–72.87s | `<EP01>/roundtrip/_judge_grids/shot_019.jpg`（345KB） |

grid 规格统一 1370×1476（2 列 × 4 行：左 ORIGINAL 蓝 `#58a6ff`、右 REGEN (h3) 绿 `#3fb950`
列头进图；行标签 t=0% / 33% / 67% / 100% 竖排左侧）。

**judge reason 摘录（引擎原文，可回溯 `route_cache/judge/shot_XXX.json` raw）：**

- **shot 61**（faithful-max）：「REGEN 忠实呈现了 prompt 中描述的『独角仙武士红棕油亮甲壳』、
  『瞪眼张口满脸惊骇』以及『表情僵住仅眼神微颤』等关键细节。在 t=33% 和 t=66% 的中段帧中，
  角色的面部表情、眼神状态以及甲壳的光泽质感均与 prompt 描述高度一致，且背景符合『虚化翠绿
  森林』的设定，未见模型自行脑补或偏离 prompt 的情况。」（attempts=[ok]）
- **shot 47**（faithful-min）：「REGEN 忠实呈现了 prompt 中的关键要素：『暗红多足巨蜈蚣长身贴地
  疾行横贯画面』…『绿螳螂武士伏低闪避』…『远处独角仙武士观望』…『贴地低角度横移跟拍』…。
  t=33% 和 t=66% 中段帧中，蜈蚣横贯画面、螳螂闪避、独角仙观望等核心动作均与 prompt 描述一致。」
  （attempts=[ok]；注意此镜 sim 全场最低但归因 faithful——观察 1 的反向案例）
- **shot 14**（diverged-median）：「prompt 明确描述角色为『独角仙武士』且『头顶双叉弯角』，但
  REGEN 在 t=33% 和 t=66% 的中段帧中，角色头顶仅渲染出一根巨大的单角（类似犀牛），完全丢失了
  prompt 中强调的『双叉』特征，属于模型执行走样。」（attempts=[ok]）
- **shot 52**（空桶顺延）：「prompt 明确要求『暗红巨型红蜈蚣扬起前身猛然横扫』以及『独角仙武士
  与绿色螳螂武士两侧迎战』。在 t=33% 和 t=66% 的中段帧中，REGEN 准确呈现了红蜈蚣身体弯曲、
  尾部扬起的攻击姿态…模型忠实执行了 prompt 中关于角色站位、动作及场景氛围的描述。」
  （attempts=[no-brace, ok]——§2.3 截断现象的一次性自然恢复实例）
- **shot 19**（global-median）：「prompt 明确描述了『随即闭眼鼓腮大嚼』的动作，但在 t=33% 和
  t=66% 的中段帧中，REGEN 生成的角色眼睛依然处于睁开或半睁状态，未能执行『闭眼』这一关键
  指令，属于模型执行走样。」（attempts=[ok]，经 §2.3 修复后取得）

## 6. Recommendations / 裁决记录（已收口 2026-08-20）

### 6.3 最终裁决记录（Kai, 2026-08-20）

- **τ_sim = 0.9670** —— 理由：faithful 桶最大间隙（0.9358→0.9670）上沿，accepted=4 高保真核，rejected 样本最丰富（15 镜 hard negatives + h3 能力边界测绘数据）
- **抽检 5 镜**（shot 61/47/14/52/19 grid）：approved，一致率按无不一致上报计（SC3 过门）
- **应用结果**（`judge.py --apply-verdict --tau-sim 0.9670`）：
  - accepted = 4：shot 10（sim 0.9685）/ shot 61（0.9780）/ shot 75（0.9701）/ shot 84（0.9670 = τ 边界，≥ 含）
  - rejected = 15：按归因分桶 —— **prompt_faithful<τ = 6**（sim 不足的忠实镜）/ **model_diverged = 9**（模型走样镜）/ underspecified = 0（空桶）
  - verdict source：19/19 = auto（HITL 面板 Phase 22 上线后可覆盖写 human）
- **幂等证明（SC5）**：apply 二跑输出 `applied=0 frozen=19 skipped=0`，roundtrip.json sha256 前后字节级相同（`63543baf…336dd73`）——冻结语义按设计工作，rejected 永不丢失
- **区分度事实（防数据集偏向审计，Pitfall 5）**：rejected 占比 15/19 = 79%；其中 diverged 9 镜 = h3 能力边界直接证据（高 sim 也可能 diverged——#80 sim 0.9828 仍 diverged）；首轮 accepted 偏严是显式选择而非静默筛选，后续扩 τ 的每一步都可从本表预演


### 6.1 τ 候选预演表（全 19 个观测值逐一预演 + 分位数关键档高亮）

accepted ⇔ sim ≥ τ ∧ prompt_faithful（硬合取）；rejected 按归因分桶（faithful<τ = sim 不足的
忠实镜 / diverged = 模型走样镜 / underspecified = 欠约束镜）：

| τ 候选 | accepted | rejected | faithful<τ | diverged | underspecified | 备注 |
|--------|----------|----------|-----------|----------|----------------|------|
| 0.8382（=min） | 10 | 9 | 0 | 9 | 0 | τ≤min：accepted=全 faithful（sim 门不生效） |
| 0.8979 | 9 | 10 | 1 | 9 | 0 | |
| 0.9011 | 8 | 11 | 2 | 9 | 0 | |
| **0.9005（p10）** | 8 | 11 | 2 | 9 | 0 | 分位档：砍掉最低 ~10% faithful |
| 0.9035 | 8 | 11 | 2 | 9 | 0 | |
| 0.9047 | 7 | 12 | 3 | 9 | 0 | |
| **0.9143（p25）** | 7 | 12 | 3 | 9 | 0 | 分位档：砍掉最低 ~25%（faithful 24 保住） |
| 0.9238 | 7 | 12 | 3 | 9 | 0 | |
| 0.9298 | 6 | 13 | 4 | 9 | 0 | |
| 0.9351 | 6 | 13 | 4 | 9 | 0 | |
| 0.9358 | 5 | 14 | 5 | 9 | 0 | 0.9358→0.9670 是 faithful 桶最大间隙（Δ0.0312） |
| **0.9457（p50）** | 4 | 15 | 6 | 9 | 0 | 分位档：高保真核 {84,10,75,61} |
| 0.9577 | 4 | 15 | 6 | 9 | 0 | |
| 0.9612 | 4 | 15 | 6 | 9 | 0 | |
| 0.9654 | 4 | 15 | 6 | 9 | 0 | |
| **0.9678（p75）** | 4 | 15 | 6 | 9 | 0 | 分位档：与 p50 同结果（间隙内等效） |
| 0.9685 | 3 | 16 | 7 | 9 | 0 | |
| **0.9741（p90）** | 2 | 17 | 8 | 9 | 0 | 分位档：仅 {61,80→非,75,80…} 严苛端 |
| 0.9701 | 2 | 17 | 8 | 9 | 0 | |
| 0.9731 | 1 | 18 | 9 | 9 | 0 | |
| 0.9780 | 1 | 18 | 9 | 9 | 0 | |
| 0.9828（=max） | 0 | 19 | 10 | 9 | 0 | τ>max：全拒（无意义端） |

（上表由 `judge.py --summarize` 机器产出 `/tmp/tau_summary.txt` 全量粘贴归约；任取区间内
τ 值结果与左端点行一致——如 τ=0.9400 与 0.9358 行同。）

### 6.2 裁决选项（区分度不足的处置——A4 预案，如实呈现不预选）

观察 1（两桶重叠）意味着 sim 无法复现 attribution 的切割；但硬合取设计下 τ 的职责本就只是
「在 faithful 桶内再设画面保真下限」。据此裁决空间：

- **选项 1 —— 接受带 caveat：** 直接从 §6.1 选 τ（例如 p50=0.9457 或最大间隙下沿 0.9358 之上），
  报告 FINAL 记录「sim 与归因弱耦合、τ 仅作 faithful 内部下限」的 caveat。零额外成本，
  Phase 21 今日收口。
- **选项 2 —— 调整 N·窗口·特征层后重校准：** 基于 §4.4 观察 4（j7/t=75% spread 最宽）显式
  重设计（如窗口后移 35%-85%、N=10、或 per-position 加权），重跑 19 镜 scorer（分钟级）出
  新分布再裁决。成本：一次重打分 + 第二轮裁决；收益未保证（SigLIP 窄带是模型本性）。
- **选项 3 —— τ 设宽容值（≤min 或 p10）：** 承认 sim 在该分布下区分力弱，把质量门实质交给
  attribution，τ 只砍极端低分（如 shot 47 类 j7 崩坏镜）。accepted 偏多，Phase 22 HITL 面板
  再人工收紧。

**裁决所需输入（Kai 回复格式）：** `tau=<float>`；抽检结论（approved 或不一致镜号+你认为的
正确归因）；若选选项 2/3 请注明选项号与参数。

### 6.3b 抽检一致率（SC3）—— 已收口

Kai 于裁决 checkpoint（2026-08-20）同场过目 §5.2 五镜 grid 材料，approved、无不一致镜上报——按 5/5 一致计，SC3 过门（裁决详情与最终清单见上文 §6.3 最终裁决记录）。

_（原 §6.3/§6.4 DRAFT 占位节已并入上方「§6.3 最终裁决记录」——编号保留以维持文内引用稳定。）_

## 7. Reproducibility

### 7.1 烧录 argv 全文

```bash
EP01="output/虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
# 批（21-02 启动，本 task 只验收）：
python3 -u analysis/roundtrip/h3_regen.py --work-dir "$EP01" --sample-shots 20
# 双信号全量（本 task）：
python3 analysis/roundtrip/scorer.py --work-dir "$EP01"            # 1m19s，19 miss
python3 analysis/roundtrip/judge.py  --work-dir "$EP01"            # 2m30s，18+1 judged
python3 analysis/roundtrip/judge.py  --work-dir "$EP01" --shots 19 # 5.9s 补齐（b43aa19 后）
python3 analysis/roundtrip/judge.py  --work-dir "$EP01" --summarize > /tmp/tau_summary.txt
```

### 7.2 cache 全命中重跑秒级证明（本 task 实测）

| 命令 | 结果 | wall |
|------|------|------|
| `scorer.py --work-dir $EP01`（重跑） | `全部 cache 命中（hit=19 miss=0）—— 零模型加载，无新分数` | **0.184s** |
| `judge.py --work-dir $EP01`（重跑） | `全部 cache 命中（hit=19 miss=0）—— 零引擎实例化` | **0.103s** |

cache key：scorer 五字段（vch + regen_mp4_sha256_16 + model + n_frames + window）/
judge 四字段（vch + regen_mp4_sha256_16 + engine_name + engine_version）——regen mp4 身份
进 key，任何重渲自然 miss 重打分（Pitfall 7 兑现）。

### 7.3 状态与产物指针

- sidecar：`<EP01>/roundtrip.json`（sha256 见 §1；verdict 半边裁决后由 Task 3 写入）
- scorer cache：`<EP01>/route_cache/scorer/shot_{001..089}.json` ×19 + `frames/` ×304 jpg
- judge cache：`<EP01>/route_cache/judge/shot_{001..089}.json` ×19 + `frames/` + `_judge_grids/` ×19 jpg
- warnings：`<EP01>/route_cache/warnings.json` = `[]`（shot 19 修复前的失败 warning 已随
  strip 语义清除——修复后该镜有 judge 分，旧 warning 不再为真）
- 散点：`.planning/research/roundtrip-calibration-scatter.png`（94KB，150dpi）

---
*Phase: 21-scorer-threshold-calibration · Plan: 21-03 · status: FINAL —— 待 Kai 裁决 τ_sim + 抽检*
*Generated: 2026-08-20（UTC）*
