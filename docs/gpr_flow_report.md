# GPR-L2 · RAFT 光流运镜/动作量化探针 —— 实测报告

- **工单**: GPR-L2（基线 03f97c7，分支 wt/gpr-flowprobe，GPU 红线 GPU2 全程遵守）
- **日期**: 2026-09-18
- **产物**: `analysis/camera_motion_quant.py`（量化脚本）· `analysis/vendor_sea_raft/`（上游引入）· `analysis/flow_probe/*.json`（实测 4 份）· `requirements-flow.txt`
- **试针对象**: GT 切片（kgr 仓 `g1_rev4_gate/`，只读）；窗口真值 `gsrt/renderback/batch_ep01/physcut_table_rev4.json`

## 0. 结论速览

| 镜 | 窗口(physcut rev4) | 相机判定 | 主通道 | 残差(动作)峰值 | 静止占比 | 一句话运镜语言 |
|---|---|---|---|---|---|---|
| **s064** | #67, 173.60–174.47s (0.87s) | `fast-tilt-up` | tilt-up 28.4°/s (91.8%画面高/s) | **209 px/帧 @ 94% 时位** | ~1% | 低角度急推+快速上摇跟拍；结尾主体直扑镜头(残差爆发) |
| **r071** | #71, 182.90–185.60s (2.70s) | `whip-pan-left` | pan-left 51.0°/s (92.6%画面宽/s) | 71 px/帧 @ 96% 时位 | ~1% | 对峙段缓右摇 → 1/3 处**反向暴力左甩**并持续推近；多段主体爆发 |
| r005 (定标参照) | — | `static` | 全通道 0.0 | 5.3 px/帧 | **89% (min 57%)** | 真静态镜：相机静止、缓速主体动作 |

**核心回答（Kai 终审质询）**：r071 现役 prompt 的 `a red-brown streak blazes across the frame like lightning` 比喻，在数值上是——
pan 方向在 **~33% 时位反转**（右摇 43%画面宽/s → 左甩 **134%画面宽/s**），伴随推近加速（zoom-in 7→18→21 %/s 三分位递增），主体动作能量在 20% / 77% / 88–96% 时位多次爆发（残差 p90 至 71px/帧，5 个帧对强到全局模型都无法拟合=degenerate）。
这组数字可直接替换比喻：**"camera whips left at ~1.3 frame-widths/s starting at 1/3 of the shot, pushing in throughout; the red-brown figure's crossing registers as residual bursts up to 71 px/frame, peaking at the very end."**

## 1. 实现选型：SEA-RAFT（Farneback 降级实测不合格于病灶镜）

**选用 SEA-RAFT-small，vendor 引入**（`analysis/vendor_sea_raft/`，逐文件 diff 见其 README）：

- 上游 `princeton-vl/SEA-RAFT`（ECCV2024 Oral，BSD-3）main 分支，只拷推理必需 6 文件，模型结构零改动（strict=True 全量加载通过；唯一补丁是 `bn3.*`→`downsample.1.*` 键别名，系上游双注册与放出权重的命名漂移）。
- 权重 `MemorySlices/Tartan-C-T-TSKH432x960-S`（官方 README Custom Usage 路线，S 档全程训练含真实数据，通用性最好），经 hf-mirror.com 直连下载（35.6MB，不入 git）。
- 实测 GPU2（RTX 3090）**14.4 ms/帧对**（iters=4，480×270），整镜含模型加载 4.3–4.5s——工单 50ms/对预算内。

**Farneback 交叉对照（r071 同镜，`r071_flow_farneback_check.json`）——失败，且失败得有信息量**：

| 指标 | SEA-RAFT | Farneback |
|---|---|---|
| pan | 92.6%画面宽/s (whip) | **8.1%画面宽/s** |
| 残差峰值 | 71 px/帧 | **12 px/帧** |
| 静止占比 | 1% | 12% |

Farneback 金字塔把甩镜+速度模糊的大位移平滑掉了，**在病灶镜类别上系统性低估一个数量级**。
结论：Farneback 降级仅可用于慢速/清晰镜（r005 类），**涉及快速运动或运动模糊的镜禁止用它的数值做 prompt 证据**——报告与脚本 summary 均已显式标注实现名。

## 2. 方法链（`camera_motion_quant.py`）

```
ffmpeg 精确抽窗内帧(select 滤镜, 480px 宽)
  → 自适应 stride 取 20–40 帧对(0.87s→stride1=26对, 2.7s→stride3=26对)
  → SEA-RAFT 逐对光流 (|流|p90 > 25%画面宽 视为量程饱和 → stride 减半重测)
  → 每对: 全局/残差分解
      ① 平移假设 T0=(median u, median v)   ← 分量中位数, 抗 49% 外点
      ② 平移一致像素(误差<2.5%画面宽)上拟合仿射, MAD 剔野值两轮
      ③ 合理性闸: 帧对级 |s−1|≤25% 且 |rot|≤10°, 越界回退纯平移
         (真相机不会帧间滚 10°; 越界=LSQ 在拿剪切项追视差/主体)
      ④ 平移/仿射按内点数竞争
      残差 = 实测光流 − 全局模型(动作能量, 中位数/p90/p99)
  → 时间轴门控(3.5×MAD)剔除瞬时污染对 → 可靠对中位数 → 分类
  → 三分位相位剖面(运镜随时间变化 = prompt beat 直接证据)
```

**关键数学约定**：光流场拟合得到的线性部分 (a1..a4) 是**雅可比 A=M−I**（纯平移时 A=0），不是变换矩阵本身；尺度 s=1+tr(A)/2，旋转 θ=½·atan2(a3−a2, tr(A)+2)，FOE 解 A·p+t=0。（开发中曾把 tr(A)/2 当尺度、旋转分母漏 +2，导致 s≈0.02、rot≈−44°/帧的荒谬输出——已修并有 r005 全零定标防回归。）

**为什么需要三层稳健化**：大主体运动（s064 结尾直扑镜头占满画面、r071 红影掠过）会把朴素 LSQ 仿射带偏成荒谬旋转/缩放（实测未加闸时 s=0.02、rot=−1300°/s）。①中位数平移假设保证初始锚不被主体污染；②合理性闸+模型竞争压制剪切项吸收视差；③时间门控利用「相机运动跨帧持续一致、主体爆发瞬时」的先验。

## 3. 数值解读

### s064（0.87s，GT: 低角度近景转面部大特写，跟拍急推 + 直扑镜头）

| 时位 | 相机（SEA-RAFT） | 残差 p90 | 解读 |
|---|---|---|---|
| 0–33% | tilt-up **163%画面高/s** + zoom-in 40%/s + pan-right | 92→32 px/帧 | 急推+上摇起手 |
| 33–67% | tilt-up 79%h/s + pan-left 28%w/s | 11–18 px/帧 | 上摇衰减, 转水平跟拍疾冲 |
| 67–100% | pan-left 35%w/s, tilt 22%h/s | **145→209 px/帧** | 跟拍扫尾; 主体直扑镜头(3 对 degenerate) |

整镜判定 `fast-tilt-up`（28.4°/s）+ 次要 pan-left 8.6°/s；zoom 整镜中位数仅 1.45%/s（起手段局部 40%/s 被时间中位数摊薄——**单标签是中位数、相位剖面才是过程**）。与 GT 运镜描述逐段吻合。

### r071（2.70s，病灶镜：对峙→红影掠过）

| 时位 | 相机（SEA-RAFT） | 残差 p90 | 解读 |
|---|---|---|---|
| 0–33% | pan-**right** 43%w/s + zoom-in 7%/s | 16–26 px/帧（20% 处一对 degenerate=70px：红影起爆） | Beat 1 对峙, 缓慢反向铺陈 |
| 33–67% | pan-**left** **134%w/s** + zoom-in 18%/s | 8→45 px/帧 | **甩镜起点(方向反转)**, 跟随红影 |
| 67–100% | pan-left 108%w/s + zoom-in 21%/s | 35→**71** px/帧（77%/88–96% 多对 degenerate） | 持续左甩+推近, 掠过+甩镜模糊叠加 |

整镜 `whip-pan-left`（51°/s 中位数；峰值段 134%w/s）、拟合内点率 0.612（混叠运动镜的诚实低置信）、5/26 对 degenerate（主体+甩镜强到全局模型不可分）。
**验证工单命题**：量化输出确实把「多体快速运动+复杂运镜」拆成了可写进 prompt 的两轴——相机轴（反转时刻、甩镜速度、推近加速）与主体轴（爆发时位、强度、次数），比喻可退役。

## 4. 静止判定阈值定标建议

现用阈值（脚本 `--static-px` 与常量区可调）及定标依据：

| 阈值 | 现值 | 定标锚 |
|---|---|---|
| 像素级静止: \|光流\|<τ | 0.6 px/帧 | r005 真静态镜静止占比 **89%**（min 57%）；快速镜 ~1%——分离度足够 |
| 相机 pan/tilt 静止 | 0.5 %画面/s | r005 全通道=0.0；s064 次通道 8.6–15.7%w/s 仍远大于之 |
| 相机 zoom 静止 | 1.0 %/s | s064 整镜 1.45%/s 属临界(起手段 40%/s 的余晖)——**建议下版把整镜 zoom 判定改为"相位剖面任一段超阈即非静止"** |
| 相机旋转静止 | 0.5 °/s | r005=0；两快速镜 rot 11–14°/s 疑含残余剪切串扰, 见 §5 |
| 时间门控 | 3.5×MAD | s064 26 对剔 6、r071 剔 5——剔的恰是 lunge/streak 瞬时对 |

建议的定标扩展（下批）：挑 10 镜已知"纯固定机位对话"（g1_rev4_gate 里 class=short 且 ssim 高者）批量跑，取静止占比分布的 p5 做 τ 的二次校准；再挑 3 镜"纯缓推"验证 zoom 通道幅值线性。

## 5. 已知限制（报告如实）

1. **deg/s 换算假设 hfov=55°**（动画机位无 EXIF）；跨镜比较请用 %画面/s 主指标。
2. **zoom 与 push（光变 vs 推轨）2D 光流不可分**：现用「散度+显著平移」组合判 push-in，FOE 偏心量（s064 1.12, r071 见 JSON `foe_offset_pct_frame`）作辅助证据；定标未做。
3. **rot 通道在剪切/视差强时可能吸收串扰**（两快速镜 11–14°/s 的滚转存疑， truths 是动画滚转少见）——建议 prompt 侧只信 |rot|>20°/s 的强信号。
4. **degenerate 对**（主体占满画面）只出残差不出相机参数——这是特性不是缺陷：它本身就是"该时刻主体运动压倒一切"的证据。
5. Farneback 降级在快运动镜失效（§1），其 summary 仅供慢镜参考。

## 6. 复现

```bash
export CUDA_VISIBLE_DEVICES=2   # 红线: 仅 GPU2
.venv_flow/bin/pip install -r requirements-flow.txt   # 首次
.venv_flow/bin/python analysis/camera_motion_quant.py \
  --video /data/workspace/kais-gold-remount/episodes/ep-xiaojianghu-ep01/S4_closures/g1_rev4_gate/r071_p1_gt_precise.mp4 \
  --label r071 --out analysis/flow_probe/r071_flow.json
python3 -m py_compile analysis/camera_motion_quant.py   # 工单验证项, 通过
```

窗口对齐说明：s064 用 GT 切片 `r067_p1_gt_precise.mp4`（physcut #67 = legacy 单元 s064 的 173.60–174.47s 窗；gate rid 与 physcut id 1:1，legacy s 编号与 prompt sid 为另一套——r064≠s064，勿混）。
