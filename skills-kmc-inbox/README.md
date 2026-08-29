# skills-kmc-inbox — KST 域托管的 GSRT skill 集

域边界（2026-08-29 Kai 定稿）：

- **GSRT 是生产金标的迭代流程，归 KST（本仓）单独管理**。本目录即真源。
- KMC 迭代系统（kais-kmc-iteration / `kmc-iteration-system` 伞）**只消费已验证金标，不负责生产它**。
- Hermes 侧 `~/.hermes/skills/` 通过 symlink 指向本目录保持可发现（farm 模式），修改真源即生效。

## 内容

| skill | 职责 |
|---|---|
| `golden-set-validation` | 金标验证协议总纲：T1 锚定→T2 文本往返→T3 独立盲标注→T4 渲染回测证据阶梯、T2×T3 判定矩阵、修正顺序定案（从管线末端往上游推） |
| `golden-set-roundtrip-validation` | GSRT 执行层：T2 注入臂坑表、T3 盲重标注判分器（agreement_report.py）、T4 render-back 提交器（submit_renderback_v2.py）、首例试点结论（ep01 P02 material 失真实锤）、PENDING-PATCH ×3 |
| `kst-gsrt-prompt-iteration` | T4 的 prompt 迭代推导闭环实战：dHash 锚评分 + vision 中帧节拍 + vision 实读原片纠偏 GT，小江湖 5 镜实测（4 PASS + 1 引擎边界镜） |

## KMC 侧消费入口

金标 metadata 的 `gsrt_validation` 等级字段（`anchored` / `roundtrip_ok` / `video_arbitrated`）。
消费规则与 KMC↔KST 接口契约见仓根 `ITERATION.md`。
