# Render-Back 消费端回测配方 (2026-08-28 试点实跑)

方法论: 首尾帧从原片 ffmpeg 硬提取 (端点钉死真相) + 被测逆向 prompt 直灌 + H3 预览路径渲染 →
与原片段同位并排对比。**渲染一致 = prompt 能干同样的活**。解决 T2 文本往返的"相似度低无法区分
金标失真 vs 管线弱"死结——渲染回测绕过文本量具，直接检验消费端产出。

## H3 KAP i2va API 实测修正 (2026-08-28, 修正 h3-kap-api-surface-complete 过时项)

- **profile 白名单只剩 `turbo | native-sage`** (config.ts:674 `H3_EXPOSED_PROFILES`, 08-17 API 精简)。
  skill 里 preview/production/native/lightx2v-* 全部 4xx 拒绝。预览= turbo (~3min/镜)。
- **projectId 必填数字** (`z.coerce.number()`)，缺失报 `字段 projectId 无效输入：期望 数字，实际接收 NaN`。
  无实际校验语义，传任意数字即可 (试点用 901)。
- multipart/form-data 字段: `firstFrame` / `lastFrame` (文件, FL2VA 双锚), `prompt` (string),
  `length` (帧数), `profile`, `seed`, `resolution` (如 1344x768), `projectId`, `filenamePrefix`。
- 返回 `{data:{promptId, status}}` → 轮询 `GET /api/production/minimax-h3/status/{promptId}`。
- curl 必带 `--noproxy '*'` (本机 15721 代理劫持回环)。
- 状态轮询注意: KAP 视角 `queued` ≠ ComfyUI 在渲; GPU 真值看 `nvidia-smi` util。
  ComfyUI `/history/{pid}` 空 = 还没完成 (完成才有输出记录)。

## 帧数与时长的坑

- H3 帧数网格: **n % 17 == 5** (5/22/39/56/73/90/107/124/141/158/...)。`length` 会自动
  `alignH3FrameCount()` 向上对齐——但自己先算最近网格点 (round 而非 ceil) 更贴近目标时长。
- `duration` 参数有 4s 下限语义; **短镜 (如 0.87s) 必须用 `length=22` 绕开**。
- 目标时长→帧数: `length = round(target_sec × 24)` 后对齐到最近网格点。
- 首/尾帧分辨率无需预缩 (1920×1080 实测直传 OK, KAP 内部处理)。

## 提交与托管脚本 (试点可复用)

位置: `/data/workspace/kais-shot-timeline/gsrt/renderback/`
- `submit_renderback.py` — 串行提交+轮询, 单镜 40min 上限 (含排队), jobs.json 断点续跑,
  exit 0=全完成 / 2=提交硬失败 / 3=轮询超时待续
- `run_renderback.sh` — 外层 24 轮续跑循环 (适配 Hermes terminal 前台超时, 必须 background+notify)
- `manifest.json` — 每镜: shot_id / target_window / first_frame / last_frame /
  reverse_prompt_under_test / length; `targets/orig_XXX.mp4` 为 ffmpeg 裁出的原片对照段

## 共享 GPU 排队纪律 (实测)

- 3090 ComfyUI (:8188) 是 FIFO 串行队列: 他人 A/B 批在渲 (util 97%) 时直接排队提交即可,
  **不打断在飞任务**; 排队时长 = 剩余臂 × 单臂耗时。
- 提交前查队列: `curl -s :8188/queue` (queue_running 的 item=[num, pid, prompt_dict,...],
  prompt_dict 的 class_type 可辨工作流归属)。
- 谁在占卡: `nvidia-smi --query-compute-apps` + ComfyUI queue 交叉定位; 无 cron 看门狗的
  批次目录 mtime 停滞 = 疑似僵尸臂。

## 试点判定协议 (待渲染完成执行)

1. 对比页: 原片段 vs 渲染段 同位并排 (kais-html case 模式, 视频默认有声)
2. Kai 盲看哪边是原片; 逐镜记录: 身份/动作/运镜/场景一致性
3. 一致 → KST 逆向 prompt 定谳"能干同样的活"; 不一致 → 归因 prompt 缺陷 vs 引擎半径
   (换 seed/profile 重渲一次再判, 单次渲染差异≠prompt 错)
