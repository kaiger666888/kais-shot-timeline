# Phase 20 Deferred Items (executor discoveries, out of auto-fix scope)

## 20-03 执行期发现（2026-08-20）

### D1: poll 心跳日志在渲染期间不可达（20-01 既有代码，cosmetic）
- **现象**: 真机 smoke 中 `poll_and_fetch` 的 `渲染中 elapsed=Ns` 心跳从未打印——ComfyUI
  `/history/{prompt_id}` 只收录**已完成**的 prompt（执行中查询返回 `{}`），循环在
  `entry is None → continue` 处提前跳过，永远到不了 elapsed print 行。
- **影响**: 长镜渲染（15-20min）期间客户端静默，operator 无法从日志分辨"在渲"与"挂了"。
- **不改的理由**: 修复需改轮询信号源（/queue 或 /prompt 状态），是设计变化非 bug fix；
  正确性零影响（完成/错误/超时三分支全对）。
- **建议**: Phase 21 overnight 批任务前考虑把心跳改挂 /queue 深度或 wall-clock（纯本地计时）。

### D2: 紧接渲染批的重跑，批开始 eye 绝对值检查可瞬时误读自身 cache（20-02 设计内行为）
- **现象**: 首跑结束后**立即**重跑同命令时，guard 步骤③ 读到 used=23255MiB
  （= 24576 − 1321，恰为 shot 47 渲后 post_render_free_mib 的对偶值）——ComfyUI 自身
  ~21GB cache 驻留被绝对值检查误认为 eye lease，进入 15s 等待循环；步骤② 的 /free
  驱逐生效后（约 1 个 poll 周期）used 跌破 13721，自动放行。自愈，无人工干预。
- **影响**: 重跑起批多等 ~15-30s；若 /free 驱逐慢于 --vram-wait-timeout 会误拒（退出 0，
  cache 保留，再跑一次即过）。
- **不改的理由**: CONTEXT 锁定「批开始 eye 检查用绝对值」（此刻无自身 cache 的假设在
  冷启动成立）；这是保守方向的假阳性，fail-safe。PID 归因化 eye 检查属 guard 语义变更。
- **建议**: Phase 21 前若频繁出现，可把步骤③ 也改 PID 归因（mirror 每镜复查）。
