---
name: kst-gsrt-prompt-iteration
description: "KST 黄金集抽样分镜 prompt 迭代推导闭环 (GSRT render-back v2.1)：H3 渲染→量化判分器(全片SSIM+VGG语义曲线+低谷检测)→改prompt/seed重渲→A2V台词轴(T8 Audio Lock)→seed彩票批→逐段拼接，直到量化门槛+物理交接双达标。触发词：prompt迭代, render-back, 逆向对标, 黄金集复刻, 分镜prompt, A2V台词, 量化判分, seed彩票"
version: 1.2.0
author: Hermes Agent
platforms: [linux]
---

# KST GSRT Prompt 迭代推导闭环 (小江湖EP01 实战 2026-08-29/30)

> **⚠️ v1.1 收敛硬规 (Kai 2026-08-29)**：端给盲测之前，本环节迭代必须已收敛。锁定≠收敛：**构图三要素全命中也不算收敛，动作物理交接必须逐帧核实**。shot89 v3 就是反例——尾锚 pHash=1 + 构图达标即锁定，实际拔刀段缺鞘→刃交接、鞘凭空消失，Kai 复核判假收敛推倒重来。

> **⚠️ v1.2 判别收紧 (Kai 2026-08-30)**：旧四层判别（首尾 dHash 锚 + vision 读 3 帧缩略 grid + 人工自检 + ASR 台词）**判不了帧间相似度**——3.9s 的镜头只看 3 帧，中段 2s 自由发挥全在视野外；缩略 grid 上姿态细节不可辨。Kai 观感「差异还是很大」时量化实锤：dHash 均值 13.8「压线达标」的同一段，SSIM 实际只有 0.479（中段跌到 0.38），VGG 语义 0.621 vs 原片相邻帧自相似基线 0.924。**判定口径必须以量化曲线为准，锚+抽帧判定只能作初筛。**

把逆向标准集的分镜 prompt 用 H3 正向渲染迭代推导，直到量化判分达标。
落盘：`/data/workspace/kais-shot-timeline/gsrt/renderback/`（submit_a2v_s89_vN.py / score_qc.py / seed_lottery_s89.py / renders_a2v/ / a2v_s89_iteration_ledger.json）。

## 触发词
prompt迭代 | render-back迭代 | 黄金集复刻 | 分镜prompt推导 | A2V台词复刻 | 量化收敛判定

## 判别体系 v1.2（量化判分器为主判据）

| 层 | 工具 | 管什么 | 盲区（旧口径教训） |
|---|---|---|---|
| 1 初筛 | dHash 首尾锚 | 构图大框 | 只看首尾两帧，中间全瞎；13.8「压线达标」时 SSIM 已崩 |
| 2 **主判据** | `score_qc.py` 量化判分器 | **全片 24 帧配对** SSIM 曲线(门0.55) + VGG16-fc7 语义余弦(门0.75) + 连续低谷段(≥3帧低于门-0.1) | VGG 偏纹理语义弱，长线换 DINOv3（权重需另下） |
| 3 | vision 单点事实问句 | 节拍/道具交接 | **只看放大原图，不读缩略 grid**（grid 误读实锤见 Pitfalls） |
| 4 | ASR 台词回验 | 逐字比对 | 只管音频轴 |

判定输出必须含：锚值 + 全片 SSIM/语义 mean 与曲线 + 低谷段位置 + 与上一轮差值归因（prompt 域 vs seed 方差 vs 引擎边界）。**曲线低谷的时段定位直接指示该修哪一段。**

## 已验证循环（v1.2 六步）

1. **量化评分**：`score_qc.py TARGET.mp4 RENDER.mp4 --json out.json`，先跑已判渲染回测复现再信任（v1 遗规）。
2. **A2V 台词轴（声音复刻）**：目标片人声在 demucs vocals stem，按时间窗裁出 GT 音频喂 `MiniMaxH3AudioWindowT8` → `MiniMaxH3AudioConditioningT8` 设 `audio_mode=lock_source, audio_denoise_strength=0.0`（输出音轨=GT 原声逐字保真），`task_type=FL2VA`。首尾帧 Conditioning 接 first_frame/last_frame + `add_source_as_reference=False`（不触发 hybrid shape mismatch）。**实证：v2-v5 四轮台词全程 ASR 逐字锁死，A2V 方法成立。**
3. **vision 实读原片纠偏 GT**（收敛主引擎）：逆向 prompt 的文字≠原片画面。判词文本不可作为修 prompt 依据，必须实读原片中帧量化反写（"上身弯至与地面平行"而非"深深鞠躬"）。
4. **改 prompt 重渲**：唯一变量=prompt，引擎臂全冻结（T8 Audio Lock + FL2VA + LightX2V 768p 9步 + 1344x768 + length=音频窗）。
5. **动作物理交接核查**（构图达标≠收敛，v1.1 遗规全有效）：密集抽帧≥8帧覆盖动作窗口，核道具交接帧/手数连续/节拍差。
6. **锁定纪律**：SSIM 平台期且 prompt 已如实描述动作链 → 定性「时相控制属引擎边界」锁版，剩余差距走 seed/帧重排后处理，不烧 prompt。

## ⚡ H3 时相指令边界（shot89 四轮 A/B 实证 2026-08-30）

**H3 对 prompt 里的时相/百分比节拍指令控制力≈0**："Beat 1 (first 45%)... Beat 2 (from 45% onward)..." 写进 prompt 完全被无视——v3 躬身滞后 1.3s、v4 加"45% 起躬"无效、v5 单一持续指令反而推过头（SEM 0.77→0.65）。动作时相由**首尾帧锚+seed 主导**。四轮数据：SSIM 平台期 0.42-0.49。

推论：**帧内构图可达（首尾锚+量化描述），帧间时相不可达（prompt 域）。** 收敛到平台期后唯一有效路线 = **seed 彩票批量**（同配方唯一变量=seed）+ **逐段拼接**（各 seed 语义曲线峰值段拼全片，接缝选动作静止点），拼完重过 score_qc 门槛。

## Seed 彩票批操作要点（seed_lottery_s89.py 实战沉淀）

- **配方克隆纪律**：从上一锁定版的 submit 脚本逐字克隆，唯一变量=RandomNoise noise_seed；提交前 diff 核对除 seed 外零差异。
- **ComfyUI 直调提交**（绕 KAP）：`POST :8188/prompt`，payload={"prompt": {节点id: {"class_type": ct, "inputs": {...}}}, "client_id": ...}。**陷阱：节点值必须是 dict 不是 list**——v4 脚本里 `n()` 返回元组带 `[1]` 取字典，转录批量脚本时丢了 `[1]`，所有节点变 list → 提交 500 `AttributeError: 'list' object has no attribute 'get'`。日志特征：server.py post_prompt validate_prompt 行。修复=n() 直接返回 dict。
- **GPU 占用判定归属**：`/queue` 里 running 任务的 filename_prefix 暴露身份（如 case08_15s_B=压测批非己任务→不杀，排队等尾）。15s=362帧长跑，容器日志看采样进度条估时。
- **输出收集**：容器 `/root/ComfyUI/output` **无宿主挂载**（v5 实锤 docker inspect），collect 用 `docker exec ls` + `docker cp`，不是 glob 本地 output 目录。
- **看门狗**：8 seed×7min≈55min，挂后台 watcher 每 10min 报 `done=N/8 running=P pending=Q`，全部落盘+队列排空才退；队列排空但文件<预期=部分渲染失败早退信号。
- **结果判读**：逐 seed 跑 score_qc 出排行（语义均值优先）；若全部 <基线 seed → 证实 seed 方差不足以覆盖时相漂移，转逐段拼接。

## 实测收敛数据

**构图域（v1，尾锚 pHash 差）**：shot89 亮刀 8→26→v4 双锚0/0 LOCKED（交接帧核过）；shot90 托孤鞠躬 12→2（量化"上身弯至与地面平行"）；shot64 极速镜 0.87s 26→20 四轮（turbo 运动模糊属引擎边界）；shot1/57 首轮已过不重渲。

**A2V 台词域（v1.2，shot89 数数台词 4.1s）**：

| 版本 | 变量 | SSIM | 语义 | 判读 |
|---|---|---|---|---|
| v2 | audio_lock 打通台词轴 | 0.420 | 0.625 | 台词逐字锁死；中段动作方向相反（举刀端详 vs 收势） |
| v3 | 分拍指令 | 0.486 | 0.770 | 躬身出现但滞后 1.3s（原片 1.9s，渲染 3.2s） |
| v4 锁 | +45%起躬指令 | 0.487 | 0.769 | 指令被无视同 v3；当前最优 |
| v5 | seed+1+单一持续指令 | 0.440 | 0.651 | 推过头全程深躬，反而最差 |

## Pitfalls

- **判词措辞放大陷阱（verdict-prose trap）**：判词是压缩有损摘要。shot89 判词"横刀亮刀"→照写"横举胸前"，实读原片是"刀尖朝下竖直前伸"。修 prompt 前必须 vision 实读原片中帧。
- **vision 高速模糊/缩略图误读**：grid 缩略里运动模糊前肢被读成"嘴和牙齿"。纪律：关键判定只用全幅放大原图+单点事实问句；两次判读矛盾即停，转人工抽帧亲验。
- **评分器先回测再信任**：新判分管线必须先跑上一轮已判渲染复现已知结论。
- **GPU 被占**：先查 `/queue` running 任务的 filename_prefix 归属再决定排队/让路；H3 18.4G，IndexTTS(root) 占 6.9G 时 `sudo -n kill`。
- **提交纪律**：KAP 层 curl 空响应≠失败（gpuQueue 锁挂 5-25min），journalctl enqueue position=N 才是铁证；ComfyUI 直调则 4xx/500 立即回错，查容器日志 `post_prompt validate_prompt` 行定位（dict/list 序列化错是最高频原因）。
- **提交通道统一 tmux**：execute_code 里 nohup+Popen 管道残留会把同一提交拉起多份（v4 实锤 3 连发）。误重复用 `/queue` POST {"delete":[prompt_id...]} 清 pending。
- **v4 教训「prompt 加码推过头」**：从上一版判词线性外推会推离地面真值；每次都回原片实读。
- **时长边界**：0.87s/22帧极速镜只能做到"构图终点正确+推进感"；turbo 运动模糊抹平中段细节属引擎物理边界。

## Scripts

| 文件 | 用途 |
|---|---|
| `score_qc.py` | 量化判分器：全片24帧配对 SSIM+VGG语义曲线+低谷检测，门 0.55/0.75（先回测复现再信任） |
| `submit_a2v_s89_v4.py` | A2V T8 Audio Lock 完整工作流模板（LoadAudio→AudioWindow→AudioConditioningT8 lock_source→FL2VA 首尾帧→AVDecode→OutputTrim） |
| `seed_lottery_s89.py` | seed 彩票批量：v4 配方逐字克隆×8 seed，submit/poll/collect 三命令 |
| `lottery_score_all.py` | 批量收编+逐 seed 打分+排行+台账（lottery_ledger.json） |
| `lottery_watcher.py` | 后台看门狗：10min 报进度，落盘数+队列双条件判完成 |

## See Also

- `renderback-prompt-iteration`（kais-movie-pipeline 域，同闭环的 KMC 侧文档，八条铁律与本文互补）
- `kst-p09-reverse-supply-diff` — 逆向供给链 + 正逆结构 diff
- `h3-t8-audio-lock-tts-driven` — T8 Audio Lock 模式细节
- `comfyui-autogrow-nested-dict-silent-drop-patch` — H3 autogrow 嵌套 ref 丢失（另一类 H3 提交陷阱）
- `kais-gold-set` — 金标逆向解构标准集本体
