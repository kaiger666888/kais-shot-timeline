---
phase: 22
plan: 22-04
status: complete
requirements: [PIPE-02, PIPE-01, RT-05]
created: 2026-08-20
---

# Plan 22-04: e2e harness + ep01 真跑 + 走查 checkpoint — SUMMARY

**Status:** 3/3 complete — Task 3 走查 approved（Kai, 2026-08-20：双 video 同步/三态/export edits 全部正常）

## 执行实录（429 中断后 orchestrator inline 续跑）

- 429 中断点：harness v1 已 commit（7d0b48f）+ mtime fix（41d19b3）；中断前 executor 完成 COPY 载体 rework 的主体（+160/−57 未提交——Rule-1 发现：ep01 prompts.json 从未 attach_refs 归一化的前提下在正本跑管线会 invalidate h3_regen cache → 重渲改写冻结半边；S2/S3/S4 改 `cp -a` 副本载体 + 正本 sha 三点零触碰断言）
- 续跑：harness 语法核验 → 全量执行 → **ALL_SCENARIOS_PASS** → harness commit（e2e harness COPY-carrier rework）→ 正本生成 review HTML（gen 只读 sidecar + 新增文件，roundtrip.json sha 63543baf… 不变）→ serve.py :8765 供走查

## Task 1-2 结果（四场景 + 冻结红线）

### SC1 断言汇总（S1 23 项 / S2 20 项 / S3 降级 / S4 6 项全 PASS）

- **S1 ComfyUI down（fixture + dead-port）**：全链 graceful-degrade（探活降级日志 + scorer/judge 不空转 + roundtrip.json/HTML absent + warnings 记 comfyui_unreachable）+ 5 个 v1.2 数据文件 md5 不变 + absent-不挂载（asset.json 无 data.roundtrip 键——RT-01 红线 pipeline 级证明）+ export cache-hit md5 等值
- **S2 ep01 副本 --sample-shots 2 端到端**（SC1 live 证明）：attach_refs no-op（已归一化）→ h3_regen 真渲 2 镜零失败 → scorer 全量补分 19（直调时代五字段旧 cache 对 WR-02 orig_window key 全 stale——预期失效）→ judge `applied=0 frozen=19`（**verdict 在新渲染上仍冻结——比 cache-hit 更强的冻结证明**）→ review HTML 19 卡 → asset.json **schema "1"→"1.3" + data.roundtrip{accepted:4, rejected:15}** → dataset 4 目录（010/061/075/084，prompt.json + first_frame.jpg 等）+ manifest 分桶 {faithful_below_tau:6, diverged:9, underspecified:0} + τ=0.9670 + accepted.txt 4 行 / rejected.txt 15 行
- **S3 抽样直调**：GPU1 渲后驻留 17331 < 22528 gate → **文档化降级分支 PASS-with-note**（plan 预案；模块级 cache 已由 Phase 20 pytest + S2 链路覆盖）
- **S4 VRAM-guard 拒提交**（--gpu-index 0 = 3060Ti 结构性 <22GB）：guard 拒绝日志 + warnings 记 vram_insufficient + exit 0 + cache 保留二跑可续
- **冻结红线三点证明**：正本 roundtrip.json sha256 `63543baf…` 在 S2 后/S4 后/全场景收尾三次等值（零触碰）

### Task 3 走查材料

- 面板：**http://100.124.72.88:8765/roundtrip_review.html**（serve.py :8765，19 卡 ep01 正本数据）
- regen mp4 HTTP 200 验证通过（Range 服务正常）

## Key Files

- created: tests/test_phase22_e2e.sh（harness，636 行四场景 + 冻结红线）
- created: output/…第01话…/roundtrip_review.html（走查面板，19 shots）
- evidence: /tmp/p22_e2e.log（ALL_SCENARIOS_PASS 全断言输出）

## Decisions

- COPY 载体（Rule-1 plan bug 修正）：正本管线首跑会因 prompts.json 未归一化 invalidate 19 镜 overnight cache——在正本重渲=改写冻结半边（红线）；副本载体 + 正本 sha 三点断言是最小正确解
- S2 的 scorer 全量 stale 重打分是 WR-02 cache key 加强的正确后果（分数可更新、verdict 冻结不受影响——正是设计）
- 走查 HTML 生成在正本（gen 只读 sidecar；sha 复验不变）

## Task 3（human-verify）

✓ approved — Kai, 2026-08-20，走查 6 步全过（同步播放/三态覆盖/queue 跳转/edits Blob 导出）。serve 已清理。
