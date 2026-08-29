# Render-back 运维手册 (T4 渲染回测, 2026-08-28 首例实战)

首例: 小江湖第01话 5 镜 (shot 1/57/64/89/90), manifest+frames+targets+renders 全在
`/data/workspace/kais-shot-timeline/gsrt/renderback/`。

## 链路

```
原片 --ffmpeg--> 首尾帧 jpg (1920x1080)
  + KST 逆向 prompt_text (被测对象, 原文直灌)
  → KAP :10588 /api/production/minimax-h3/i2va  (multipart)
     firstFrame/lastFrame/prompt/length/profile=turbo/seed/resolution=1344x768
     projectId=<必填数字,仅进文件名>  filenamePrefix=<产物名前缀>
  → ComfyUI FL2VA (T8 DualClock, 双首尾帧锚)
  → 产物在容器内: comfyui-primary:/root/ComfyUI/output/<prefix>_00001_.mp4
  → docker cp 提取 (KAP output URL 会 404, 老坑)
```

## i2va 参数坑 (2026-08-28 实测)

| 坑 | 症状 | 解法 |
|---|---|---|
| projectId 必填 | `字段 projectId 无效输入: 期望数字 实际接收 NaN` | 任意数字即可 (只用于文件名前缀) |
| duration<4s 拒收 | 0.87s 极速镜被 duration 下限拦 | 用 `length` (帧数) 直传 |
| 帧数网格 | 非 n%17==5 的 length 被静默对齐 | 自己对齐到最近网格点: `while n%17!=5: n+=1` |
| profile 白名单 | lightx2v/preview 等静默降级 | 08-17 API 精简后只收 **turbo \| native-sage** (config.ts H3_EXPOSED_PROFILES) |
| prompt 锚行 | `[i2va] prompt missing 0.00s anchor line — auto-prepended` | KAP 自动补, 无需手工; 日志见到属正常 |
| 音频 bed | H3 CFG=1.0 负面词无效 | prompt 尾巴拼 `strictly diegetic in-world sound, unscored scene`; 禁 `no music` |

## ⚠️ 最大坑: KAP gpuQueue 挂起语义 → 重试风暴

KAP 有 VRAM 门 (need 18GiB for minimax_h3): `free < need` 时 POST 被收下挂进
gpuQueue 每 20s 重试 (最长 1800s), **期间 HTTP 不回包**。journalctl 实锤:
`[gpuQueue] vram_retry minimax_h3 GPU1: free 3706MiB < need 18432MiB`。

- **curl 空响应 ≠ KAP 挂了**: 上传完整到达 (`We are completely uploaded and fine`,
  0 bytes received) = 请求已入队等锁。
- **空响应重试 = 僵尸风暴**: 每重试一次堆一个 waiter, 全部会渲染 (首例 shot64 堆 5 份,
  shot57 渲染 2 份)。同一 filenamePrefix 文件名会互相覆盖, 产物不重复但烧卡。
- **正确姿势 (v2)**: 提交一次 `-m 1900` 覆盖 1800s 锁等待; 无响应转「容器产物守望」
  (30s 轮询 `docker exec comfyui-primary ls /root/ComfyUI/output/ | grep <prefix>`),
  先到先收, 绝不重发。
- **等待者会被 1800s 超时 purge** (日志 `release ... detail` 可辨), purge 后 KAP 状态
  仍显示 queued 但 ComfyUI 队列里没有 → 需重提。
- 管理面 `POST /api/production/gpu-queue/purge-waiters` 可清等待者, 但需
  KAP_ADMIN_TOKEN (未配置时 404 兜底); 观测面 `GET /api/production/gpu-queue`
  无 token, holders/waiters/recentEvents 全景先看它。
- 单卡多任务常态: gpuQueue 是**服务级锁** (持锁≈渲染全程), ComfyUI FIFO 是第二级;
  demo-pixar 管线/root 属主 A/B 批/qwen_eye 都可能占锁, 排队是正常态。

## 首尾帧提取纪律

- ffmpeg 硬提取 (钉死真相): `-ss <t0> -i 原片 -frames:v 1`。
- 尾帧取 `-ss <t1-0.1>` (贴窗口末), 1920x1080 jpg 直出 (KAP 自带降采样, 无需预缩)。

## QC 方法 (像素 + vision 双轨) 及三个假信号

像素锚点差 (`PIL 256x144 均值绝对差`): 条件帧vs原片、渲染锚点vs条件帧, <10=钉住。

1. **mp4 seek 偏移假阴性**: shot64 渲染 t0 vs 条件首帧 diff=22.96, vision 看图却
   「几乎精确复刻」。短镜头/关键帧稀疏时 ffmpeg seek 落帧偏移会制造大 diff —— 像素高
   先抽帧看图再定性, 不要单凭数字判死。
2. **vision 读对比图布局会错行**: 2x3 网格曾被判「序列错位」, 像素指标证明双锚都钉住。
   vision 负责语义 (身份/动作/景别), 帧对位用像素+ffprobe 时长核。
3. **能力边界 ≠ prompt 错**: shot64 (0.87s 极速镜) 身份/场景/冲刺语义全保住, 但原片
   「近景→面部大特写扑面」被渲成「全身掠过」——特写推进是 H3 短时长能力边界, 不构成
   对 prompt 的否证。判定前先分「渲染保住什么/丢什么」, 丢的若属引擎边界则不计 prompt 分。
4. 附加伪影: 原片烧录字幕/角标被条件帧继承、H3 复刻 —— 条件帧污染, 不计入 prompt 判分。

## 判读流程

```
1. ffprobe 渲染时长 vs 目标 (帧数网格对齐后允许 ±0.3s 漂移)
2. 像素锚点: render_t0 vs cond_first, render_tend vs cond_last
3. 抽首/中/尾三行拼图 (PIL hstack/vstack), vision 判身份/动作/景别/构图
4. 分歧仲裁: 像素高但 vision 好 = seek 假象; 像素好但 vision 丢语义 = 中段漂移
5. 汇总表: 每镜 [锚点差 | 身份 | 动作语义 | 景别] + 差异归因 (prompt 错 / 引擎边界 / 条件帧污染)
```

## 多方抢卡协调 (2026-08-28 实况)

同卡同时存在: demo-pixar P11 H3 臂 (cron 10m 盯)、root 属主 H3 A/B 批 (h3_ab_runs/,
kill 不掉也看不到 driver)、qwen_eye 视觉判定、本试点。纪律:
- 提交前 `nvidia-smi --query-compute-apps` + `GET /gpu-queue` 双查, 活锁 (util>50%)
  不打断, FIFO 排队。
- 空转占卡 (util 0%) 才考虑让路 (ComfyUI /free 只清缓存不清队列)。
- 自己的批量渲染走单提交长超时 + 产物守望, 禁短超时重试循环。
