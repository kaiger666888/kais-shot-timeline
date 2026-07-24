#!/usr/bin/env python3
"""Phase 6 graceful-degrade + 缓存回归校验 harness（standalone，无 pytest）。

本 harness 锁 Phase 6 三条 verifiable 路径（live route round-trip DEFERRED —
feat/shot-analysis-route unmerged，见 STATE.md blocker + 06-VALIDATION.md
"Manual-Only Verifications"）。沿用 scripts/verify_contract.py 风格：
bracketed prefix tags + sys.exit(0/1) 退出码契约 + 仅 stdlib + 已在 env 的
jsonschema。

3 个 scenarios（每个独立 temp work_dir，互不污染）：

  route_down (CINEMA-03)
      对 unreachable URL（http://127.0.0.1:1/）跑 call_shot_analysis.py，
      断言：exit 0（graceful-degrade 不 fail）+ prompts.json 写出且全部 5 个
      route-sourced facets 为空串（schema 合法）+ route_cache/warnings.json
      至少 1 条记录（含 "preflight" 或 "ConnectError" 字样）。

  skip_semantic (CINEMA-06)
      直接调 run_pipeline.step_semantic(skip=True, ...) 并捕获 stdout。断言：
      stdout 含 "--skip-semantic: skipping" 标签 + 不含
      "[5/7] cinematography analysis (shot-analysis route)" run_step banner
      （证明子进程没被起）+ 返回 prompts.json 路径（若预置）或 None。

  cache_hit_offline (CINEMA-04)
      预填 route_cache/shot_analysis/shot_001.json 含 captured fixture 内容
      （examples/shot_analysis/shot_003.json）+ 正确 _cache_key（video_content_hash
      匹配 tiny test 文件 + ROUTE_VERSION）。跑 call_shot_analysis.py --offline
      对 unreachable URL。断言：exit 0 + prompts.json 用 cache 值
      （camera="中景, follow, fast, pan_right"）+ stdout 含
      "[semantic] shot 1: cache hit" + 0 网络调用（offline + cache hit 双保险）。

退出码：
    0 = 3 个 scenario 全绿（"[phase6-smoke] OK: 3/3 scenarios green"）
    1 = 任一 scenario fail（detail 行说明哪个 + 为何）

用法：
    python3 scripts/verify_phase6_smoke.py
    python3 scripts/verify_phase6_smoke.py --verbose   # 透传子进程 stdout/stderr

设计要点：
  - temp work_dir 用 tempfile.mkdtemp(prefix="phase6-smoke-")，finally 块
    shutil.rmtree(ignore_errors=True) 兜底（T-06-15 mitigation）。
  - tiny --video 用本文件自身（scripts/verify_phase6_smoke.py）—— 已知存在 +
    内容固定（保证 video_content_hash 跨 run 稳定）。
  - 跨 scenario 不共享 temp dir；每 scenario 独立 mkdtemp + cleanup。
"""
import argparse
import sys


def main():
    # RED placeholder —— GREEN 实现见下一 commit。
    print("[phase6-smoke] FAIL: verify_phase6_smoke.py not yet implemented")
    sys.exit(1)


if __name__ == "__main__":
    main()
