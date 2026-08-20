# Phase 19 Deferred Items (out-of-scope discoveries)

## 2026-08-19 · 19-01 Task 2

- **v1 `local_vision_facets.py --help` crashes**（pre-existing，非本 plan 引入）：
  `--frames-dir` 的 help 字符串含裸 `%06d`（`f%06d.jpg`），argparse 对 help 做
  `%` 格式化 → `TypeError: %d format: a real number is required, not dict`。
  v2 `vision_seq_facets.py` 同文案已用 `%%` 转义修复（本 task 文件内 Rule 1）；
  v1 文件是零改动红线，不修 —— 留待未来触碰 v1 的 phase 处理（一行 `%%` 转义）。
  验证：`python3 analysis/local_vision_facets.py --help` → Traceback。
