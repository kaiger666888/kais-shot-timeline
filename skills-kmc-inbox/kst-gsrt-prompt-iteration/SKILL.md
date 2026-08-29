---
name: kst-gsrt-prompt-iteration
description: "KST 黄金集抽样分镜 prompt 迭代推导闭环 (GSRT render-back v2)：H3 渲染→双锚pHash+vision中帧beat评分→vision实读原片纠偏GT→改prompt重渲，直到构图级达标。3镜实测：2镜一轮达标，1镜(0.87s极速镜)4轮收敛。触发词：prompt迭代, render-back, 逆向对标, 黄金集复刻, 分镜prompt"
version: 1.0.0
author: Hermes Agent
platforms: [linux]
---

# KST GSRT Prompt 迭代推导闭环 (小江湖EP01 实战 2026-08-29)

把逆向标准集的分镜 prompt 用 H3 正向渲染迭代推导，直到预览与黄金集"基本一致"。
落盘：`/data/workspace/kais-shot-timeline/gsrt/renderback/` (manifest_vN.json / submit_iter.py / score_iter.py / renders_iter/)。

## 触发词
prompt迭代 | render-back迭代 | 黄金集复刻 | 分镜prompt推导

## 已验证循环 (5 步)

1. **锚评分** `score_iter.py`：渲染首尾帧 vs 目标首尾帧 dHash 海明差，<15=钉住。只管首尾，**中帧节拍必须 vision**。
2. **vision 中帧判定**：渲染抽 25/50/75% 帧拼 grid (`scale=426:-1,tile=4x1`)，目标片段同法抽帧，双 vision 对照判节拍是否发生。
3. **vision 实读原片纠偏 GT（收敛主引擎，3镜全部靠它破局）**：逆向 prompt 的文字描述≠原片真实画面。实锤两例：shot89 原片刀是"竖直前伸刀尖朝下"而非想当然的"横举胸前"、小孩是捂脸；shot64 原片尾帧真实 GT=头在画面左+白色前肢横扫 (非"面部占满画面")。
4. **改 prompt 重渲**：唯一变量=prompt，引擎臂恒定 (KAP :10588 i2va + turbo + seed=42 + 1344x768 + length=原镜帧数)。
5. **锁定纪律**：连续迭代锚差进平台期且 vision 判剩余差距属引擎边界（如 turbo 高速模糊控制）→ 锁定，"prompt 如实、引擎边界"定性，不无限迭代。

## 实测收敛数据 (尾锚 pHash 差)

| shot | v1 | 终版 | 轮数 | 破局点 |
|---|---|---|---|---|
| 89 亮刀 | 8→26 | **1** (v3) | 1轮 | vision 读原片中帧纠偏刀的方向+捂脸 |
| 90 托孤鞠躬 | 12 | **2** (v3) | 1轮 | 量化鞠躬深度"上身弯至与地面平行" |
| 64 极速镜 0.87s | 26 | **20** (v6) | 4轮 | v4"面部占满画面"推过头头出画；v5 命中构图头糊；v6"头部清晰锐利+前肢强模糊"分离式描述→瞳孔可读，构图级~85% |

shot 1/57 首轮已通过不重渲（省 GPU）。

## Pitfalls

- **GPU 被占**：压测批/盲测批常占卡。两个守望接力并行时注意接力脚本的 `DEADLINE` 到期会静默 exit 1，重查队列后手动补提即可（KAP gpuQueue 锁等待会把 POST 挂到队列前头）。
- **提交纪律**：单次提交不重试（重试=僵尸等待者风暴），空响应=可能已入队，转容器产物守望 (`docker exec ls -t output/ | grep prefix`)。
- **vision_analyze 不收 mp4**：先 ffmpeg 抽帧/拼 grid jpg 再 vision；hstack 两源高度不同会报错，scale 写死 `640:360`。
- **v4 教训"prompt 加码推过头"**：照字面加"占满画面"导致主体出画。修正法=vision 实读原片该帧的**真实构图**再描述，不要从上一版判词线性外推。
- **时长边界**：0.87s/22帧的极速镜，景别演进只能做到"构图终点正确+推进感"，turbo 的运动模糊抹平中段细节属引擎物理边界。
