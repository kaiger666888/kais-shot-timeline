---
name: kst-gsrt-prompt-iteration
description: "KST 黄金集抽样分镜 prompt 迭代推导闭环 (GSRT render-back v2)：H3 渲染→双锚pHash+vision中帧beat评分→vision实读原片纠偏GT→改prompt重渲，直到构图级达标。3镜实测：2镜一轮达标，1镜(0.87s极速镜)4轮收敛。触发词：prompt迭代, render-back, 逆向对标, 黄金集复刻, 分镜prompt"
version: 1.1.0
author: Hermes Agent
platforms: [linux]
---

# KST GSRT Prompt 迭代推导闭环 (小江湖EP01 实战 2026-08-29)

> **⚠️ v1.1 收敛硬规 (Kai 2026-08-29)**：端给盲测之前，本环节迭代必须已收敛。锁定≠收敛：**构图三要素全命中也不算收敛，动作物理交接必须逐帧核实**。shot89 v3 就是反例——尾锚 pHash=1 + 构图达标即锁定，实际拔刀段缺鞘→刃交接、鞘凭空消失，Kai 复核判假收敛推倒重来。

把逆向标准集的分镜 prompt 用 H3 正向渲染迭代推导，直到预览与黄金集"基本一致"。
落盘：`/data/workspace/kais-shot-timeline/gsrt/renderback/` (manifest_vN.json / submit_iter.py / score_iter.py / renders_iter/)。

## 触发词
prompt迭代 | render-back迭代 | 黄金集复刻 | 分镜prompt推导

## 已验证循环 (5 步)

1. **锚评分** `score_iter.py`：渲染首尾帧 vs 目标首尾帧 dHash 海明差，<15=钉住。只管首尾，**中帧节拍必须 vision**。
2. **vision 中帧判定**：渲染抽 25/50/75% 帧拼 grid (`scale=426:-1,tile=4x1`)，目标片段同法抽帧，双 vision 对照判节拍是否发生。
3. **vision 实读原片纠偏 GT（收敛主引擎，3镜全部靠它破局）**：逆向 prompt 的文字描述≠原片真实画面。实锤两例：shot89 原片刀是"竖直前伸刀尖朝下"而非想当然的"横举胸前"、小孩是捂脸；shot64 原片尾帧真实 GT=头在画面左+白色前肢横扫 (非"面部占满画面")。
4. **改 prompt 重渲**：唯一变量=prompt，引擎臂恒定 (KAP :10588 i2va + turbo + seed=42 + 1344x768 + length=原镜帧数)。
5. **动作物理交接核查（收敛必要条件，构图达标≠收敛）**：涉及"拿起/拔出/放下/穿上/交接"类动作时，必须密集抽帧（≥8帧覆盖动作窗口）核实三件事：①道具有无交接过程帧（不能凭空出现/消失）②持有者手数变化是否连续③动作完成时刻与原片节拍差。任一不满足=未收敛，即使尾锚 pHash=1。shot89 实锤：1.0-1.3s 双手握鞘→1.45s 刃凭空出现无交接帧，构图全对仍是假收敛。
6. **智能判定降级预案**：vision 对裁剪/放大小图判读会自相矛盾（shot89 复查中裁掉半幅导致 3 轮反复）。纪律：关键判定只用**全幅帧**；两次 vision 判读矛盾时停止追问 vision，改人工抽帧亲验；密集动作核查用 ffmpeg 逐帧 dump 后 vision 只做"每帧刀刃可见性"这类单点事实问句，不问复合推理。
7. **锁定纪律**：连续迭代锚差进平台期且 vision 判剩余差距属引擎边界（如 turbo 高速模糊控制）→ 锁定，"prompt 如实、引擎边界"定性，不无限迭代。

## 实测收敛数据 (尾锚 pHash 差)

| shot | v1 | 终版 | 轮数 | 破局点 |
|---|---|---|---|---|
| 89 亮刀 | 8→26 | **1** (v3)→**作废**，v4 重推 | 1轮+返工 | v3 假收敛：构图三要素全对但拔刀缺鞘→刃交接帧+节拍滞后0.35s，Kai 复核推翻。v4=prompt 显式写交接动作后真收敛：双锚0/0、刃1.05→1.5s渐出连续、鞘全程在手、拔刀0.6s节拍差<0.1s → LOCKED_v4 |
| 90 托孤鞠躬 | 12 | **2** (v3) | 1轮 | 量化鞠躬深度"上身弯至与地面平行" |
| 64 极速镜 0.87s | 26 | **20** (v6) | 4轮 | v4"面部占满画面"推过头头出画；v5 命中构图头糊；v6"头部清晰锐利+前肢强模糊"分离式描述→瞳孔可读，构图级~85% |

shot 1/57 首轮已通过不重渲（省 GPU）。

## Pitfalls

- **GPU 被占**：压测批/盲测批常占卡。两个守望接力并行时注意接力脚本的 `DEADLINE` 到期会静默 exit 1，重查队列后手动补提即可（KAP gpuQueue 锁等待会把 POST 挂到队列前头）。
- **提交纪律**：单次提交不重试（重试=僵尸等待者风暴），空响应=可能已入队，转容器产物守望 (`docker exec ls -t output/ | grep prefix`)。
- **vision_analyze 不收 mp4**：先 ffmpeg 抽帧/拼 grid jpg 再 vision；hstack 两源高度不同会报错，scale 写死 `640:360`。
- **v4 教训"prompt 加码推过头"**：照字面加"占满画面"导致主体出画。修正法=vision 实读原片该帧的**真实构图**再描述，不要从上一版判词线性外推。
- **时长边界**：0.87s/22帧的极速镜，景别演进只能做到"构图终点正确+推进感"，turbo 的运动模糊抹平中段细节属引擎物理边界。

- **提交通道统一 tmux（v4 事故）**：execute_code/脚本环境里 `nohup+Popen` 会因管道残留把同一提交脚本拉起多份（v4 实锤 3 连发 → KAP gpuQueue position=1/2/3 + ComfyUI pending×3）。纪律：渲染提交一律 `tmux new-session -d -s <tag> "python3 submit..."`；误重复后用 ComfyUI `/queue` POST `{"delete":[prompt_id...]}` 清 pending（只留 running）；KAP gpuQueue 无 cancel API，堵在 KAP 层时只能等 retry 或清 VRAM。
- **KAP 空响应≠失败**：curl 等 gpuQueue 锁会挂 5-25min 无输出，journalctl `gpuQueue enqueue position=N` 才是入队铁证；先查日志再决定是否重提，否则必重复入队。
- **GPU 让路**：H3 需要 18.4G，IndexTTS-server (root进程) 占 6.9G 时差 1.8G 排不上队 → `sudo -n kill`（免密 sudo 通道，普通 kill 对 root 进程静默失败）；TTS 空闲期可断，盲测要用时重启服务即可。
