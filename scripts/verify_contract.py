#!/usr/bin/env python3
"""Phase 4 跨仓库契约验证 harness —— 抓 producer / consumer 两端漂移。

背景：v1.0 milestone 的核心价值是「两仓库（kais-shot-timeline = producer /
contract authority；kais-aigc-platform @kais/infinite-canvas = consumer）
独立演进，契约对齐有回归保护」。本 harness 是这张回归网 —— 单一 canonical
home（spec owner 一侧），三种 mode 覆盖两个漂移方向。

三种 mode（e2e 在 Plan 04-02 补完，本 plan 只占位）：
  producer  —— 对真实 ep01 asset 跑 6-schema inline jsonschema 校验
              （Draft202012Validator，绝不 subprocess 到 spec/validate.py ——
               其 SMOKE_SHAPES spec/validate.py:49 显式排除 asset shape，
               subprocess 会让无效 manifest 悄悄通过）
  consumer  —— subprocess shell-out 到 Phase 3 worktree 的
               verify-canvas-shot-timeline.ts（17 asserts A-F + E2 抓
               consumer importer 漂移）
  e2e       —— HTTP-level 端到端：起 Express backend → POST
               /api/canvas/v2/import-from-dir → SQL 直查 o_agentWorkData
               snapshot → 结构断言。Plan 04-02 实现。

opt-in 环境变量：
  PHASE4_RE_EXPORT=1     重导 asset.json（抓「今天 producer 还能产 valid asset」，
                          否则用既有 ep01 产物）
  PHASE4_SELF_TEST=1     self-test：注入 schema_version='v1' 故意漂移，
                          断言 harness fail-loud（Plan 04-01 Task 2 落地）
  PHASE4_RUN_E2E=1       启用 e2e mode（04-02 才会真正起作用）
  PHASE4_E2E_ASSET_DIR   e2e 输入 asset 目录（默认 ep01）

用法：
    python3 scripts/verify_contract.py --mode=producer
    python3 scripts/verify_contract.py --mode=consumer
    python3 scripts/verify_contract.py                  # 默认 --mode=all
    PHASE4_SELF_TEST=1 python3 scripts/verify_contract.py --mode=producer
    CANVAS_CONSUMER_PATH=/path/to/worktree python3 scripts/verify_contract.py --mode=consumer

退出码：
    0 = 选中的 mode 全绿
    1 = 任一 mode fail（schema-invalid / subprocess rc≠0 / guard 拒绝）
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator


# === 路径常量 ============================================================
# scripts/verify_contract.py → repo root（定位 spec/schemas/ + scripts/export_asset.py）
REPO = Path(__file__).parent.parent.resolve()
SCHEMAS_DIR = REPO / "spec" / "schemas"

# cross-repo worktree 默认路径（CONTEXT 锁：feat/canvas-asset-collection 分支）
DEFAULT_CONSUMER_PATH = "/data/workspace/kst-canvas-consumer"

# e2e / producer mode 默认输入：真实 ep01 asset dir
# （CONTEXT 锁：用既有 ep01，避免 GPU/Whisper 重跑；ep03 cache 被 Phase 2 测试破坏过）
DEFAULT_E01_ASSET_DIR = (
    REPO / "output"
    / "虫虫武侠小故事《小江湖》第01话：爸爸去哪儿？（ 画面只是工具，情绪才是目的。"
)

# 6 个 schema 形状（与 spec/validate.py L46 MINIMAL_ORDER 一致）
SIX_SHAPES = ["asset", "shots", "audio_analysis", "transcript", "frames", "prompts"]


# === 04-02 预定义 helper ================================================
# 本 plan（04-01）不用 find_free_port；预定义避免 04-02 e2e mode 需要回头改本文件。
def find_free_port() -> int:
    """让内核分配一个空闲 ephemeral 端口（bind 127.0.0.1:0 后读 getsockname）。

    模板源：scripts/check_range.py:32-36（Phase 2 server-lifecycle）。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# === producer-side helpers ==============================================
def _resolve_canonical_video(asset_dir: Path) -> str:
    """返回 video.mp4 symlink 的 target（或非 symlink 时直接绝对路径）。

    背景：Phase 2 决定 video.mp4 是 symlink，target = --video abs path（原始
    含 audio 流的视频，非 -an 转 h264.mp4）。PHASE4_RE_EXPORT=1 重导时需要
    把原始路径传给 export_asset.py。
    """
    video_link = asset_dir / "video.mp4"
    if video_link.is_symlink():
        return os.readlink(video_link)
    return str(video_link)


def validate_asset_json(asset_path) -> list:
    """对单份 asset.json 跑 spec/schemas/asset.schema.json 校验，返回 errors 列表。

    与 scripts/export_asset.py:106-127 的 inline validator 同源 —— 但 RETURN
    errors list（不 sys.exit），让 harness 收集后统一报告 + 让 self-test
    断言数量。模板源：scripts/export_asset.py L106-127；sort key 沿用项目惯例。

    绝不 subprocess 到 spec/validate.py —— 其 SMOKE_SHAPES（spec/validate.py:49）
    显式排除 asset shape，subprocess 会让无效 manifest 悄悄通过。
    """
    asset_path = Path(asset_path)
    schema = json.loads((SCHEMAS_DIR / "asset.schema.json").read_text(encoding="utf-8"))
    instance = json.loads(asset_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda e: list(e.absolute_path),
    )
    return errors


def validate_six_shapes(asset_dir: Path, manifest: dict) -> list:
    """对 asset + 5 data shapes 跑 6-schema 校验，返回 failures 列表（空=全绿）。

    模板源：spec/validate.py L52-94（_format_errors + sorted iter_errors 模式）。
    每个 shape 失败时只记第一条错误（actionable + 不刷屏）；self-test / 深度
    debug 走 validate_asset_json 拿完整列表。
    """
    failures = []
    for shape in SIX_SHAPES:
        schema_path = SCHEMAS_DIR / f"{shape}.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if shape == "asset":
            instance = manifest
        else:
            rel = manifest["data"][shape]
            instance_path = asset_dir / rel
            try:
                instance = json.loads(instance_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                failures.append(f"{shape}: data file missing at {instance_path}")
                continue
            except json.JSONDecodeError as e:
                failures.append(f"{shape}: invalid JSON in {instance_path}: {e}")
                continue
        errs = sorted(
            Draft202012Validator(schema).iter_errors(instance),
            key=lambda e: list(e.absolute_path),
        )
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            failures.append(f"{shape} at /{loc}: {errs[0].message}")
    return failures


def run_producer_check(args) -> tuple:
    """producer mode：对真实 ep01 asset 跑 6-schema inline 校验。

    流程：
      1. 定位 asset.json（默认 ep01；可 PHASE4_E2E_ASSET_DIR 覆盖）
      2. （opt-in）PHASE4_RE_EXPORT=1 调 scripts/export_asset.py 重导
      3. 加载 manifest
      4. validate_six_shapes 跑 6 个 schema
      5. 全绿返 (True, "...")；任一失败返 (False, "shape: reason; ...")

    返回 tuple[bool, str] —— 让 main() 统一格式化输出 + exit code。
    """
    asset_dir = Path(args.e2e_asset_dir)
    asset_path = asset_dir / "asset.json"
    if not asset_path.is_file():
        return (
            False,
            f"ep01 asset.json missing at {asset_dir}\n"
            f"  run `python3 run_pipeline.py --video <path>` + export first, or set\n"
            f"  PHASE4_E2E_ASSET_DIR=<path-to-asset-dir>",
        )

    # (可选) 重导抓 producer 漂移 —— CONTEXT 锁：本仓库 output/ 可覆盖，
    # worktree pinned golden（scripts/fixtures/shot-timeline-ep01/）绝不动。
    if os.environ.get("PHASE4_RE_EXPORT") == "1":
        print(f"[producer] PHASE4_RE_EXPORT=1 —— 重导 asset.json")
        video = _resolve_canonical_video(asset_dir)
        stems_src = asset_dir / "stems" / "htdemucs" / asset_dir.name
        rc = subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "export_asset.py"),
                "--work-dir", str(asset_dir),
                "--video", video,
                "--stems-source-dir", str(stems_src),
                "--output", str(asset_path),
                "--force",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if rc.returncode != 0:
            return (
                False,
                f"export_asset.py failed (rc={rc.returncode}):\n"
                f"  stderr: {rc.stderr.strip()[:400] or '(empty)'}",
            )

    manifest = json.loads(asset_path.read_text(encoding="utf-8"))
    failures = validate_six_shapes(asset_dir, manifest)
    if failures:
        return (False, "; ".join(failures))
    return (True, "asset.json + 5 data shapes all schema-valid")


# === consumer-side helper ===============================================
def run_consumer_check(args) -> tuple:
    """consumer mode：subprocess shell-out 到 Phase 3 verify-canvas-shot-timeline.ts。

    流程：
      1. guard：CANVAS_CONSUMER_PATH 存在 + 是 git worktree（防 T-04-01-T1 恶意指向）
      2. guard：verify script 存在
      3. subprocess.run([npx, tsx, scripts/verify-canvas-shot-timeline.ts],
                        cwd=consumer, timeout=60)
      4. 透传 stdout（17 asserts 进度）
      5. rc==0 → (True, "...")；rc≠0 → (False, "...")

    模板源：04-RESEARCH.md §Code Examples 示例 3（L821-838）。
    """
    consumer = args.consumer_path

    if not os.path.isdir(consumer):
        return (
            False,
            f"CANVAS_CONSUMER_PATH 不存在: {consumer}\n"
            f"  set CANVAS_CONSUMER_PATH=<worktree> 或 clone kais-aigc-platform\n"
            f"  + checkout feat/canvas-asset-collection",
        )
    if not os.path.isdir(os.path.join(consumer, ".git")) and not os.path.isfile(
        os.path.join(consumer, ".git")
    ):
        return (False, f"not a git worktree: {consumer}")

    verify_script = os.path.join(consumer, "scripts", "verify-canvas-shot-timeline.ts")
    if not os.path.isfile(verify_script):
        return (
            False,
            f"Phase 3 verify script missing: {verify_script}\n"
            f"  ensure worktree is on feat/canvas-asset-collection branch\n"
            f"  (cd {consumer} && git checkout feat/canvas-asset-collection)",
        )

    try:
        rc = subprocess.run(
            ["npx", "tsx", "scripts/verify-canvas-shot-timeline.ts"],
            cwd=consumer, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return (False, f"verify-canvas-shot-timeline.ts timeout (>60s)")
    except FileNotFoundError:
        return (
            False,
            "npx not found —— Node.js / npm 未安装或不在 PATH\n"
            f"  consumer worktree expects `npx tsx ...`",
        )

    # 透传 Phase 3 17 asserts 输出（含 PASS/FAIL 行）
    if rc.stdout:
        sys.stdout.write(rc.stdout)
        if not rc.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if rc.returncode != 0:
        return (
            False,
            f"verify-canvas-shot-timeline.ts exit {rc.returncode}\n"
            f"  stderr: {(rc.stderr or '').strip()[:400] or '(empty)'}",
        )
    return (True, "Phase 3 17 asserts all green (importer accepts golden asset)")


# === CLI ================================================================
def main():
    """CLI 入口。"""
    ap = argparse.ArgumentParser(
        description="Phase 4 跨仓库契约验证 harness —— 抓 producer / consumer 两端漂移"
    )
    ap.add_argument(
        "--mode", choices=["producer", "consumer", "e2e", "all"], default="all",
        help="验证模式（producer=导出端 schema, consumer=消费端 importer, "
             "e2e=端到端, all=全部；e2e 当前为 placeholder，04-02 实现）",
    )
    ap.add_argument(
        "--consumer-path",
        default=os.environ.get("CANVAS_CONSUMER_PATH", DEFAULT_CONSUMER_PATH),
        help="consumer worktree 路径（kais-aigc-platform feat/canvas-asset-collection）",
    )
    ap.add_argument(
        "--e2e-asset-dir",
        default=os.environ.get("PHASE4_E2E_ASSET_DIR", str(DEFAULT_E01_ASSET_DIR)),
        help="e2e 用的真实 asset 目录（默认 ep01）",
    )
    ap.add_argument(
        "--e2e-skip", action="store_true",
        help="跳过 e2e mode（CI-friendly；e2e 起 backend 重，默认就跳过）",
    )
    args = ap.parse_args()

    results = []  # list of (mode_name, ok, detail)

    # producer mode
    if args.mode in ("producer", "all"):
        print("[verify-contract] mode=producer starting")
        ok, detail = run_producer_check(args)
        tag = "[producer] OK" if ok else "[producer] FAIL"
        print(f"{tag}: {detail}")
        results.append(("producer", ok, detail))

    # consumer mode
    if args.mode in ("consumer", "all"):
        print("[verify-contract] mode=consumer starting")
        ok, detail = run_consumer_check(args)
        tag = "[consumer] OK" if ok else "[consumer] FAIL"
        print(f"{tag}: {detail}")
        results.append(("consumer", ok, detail))

    # e2e mode —— Plan 04-01 占位（防 --mode=all 默认值挂掉）
    if args.mode in ("e2e", "all") and not args.e2e_skip:
        if args.mode == "e2e":
            print("[verify-contract] e2e mode 在 Plan 04-02 实现；当前仅占位")
            results.append((
                "e2e", False,
                "e2e not implemented yet — see Plan 04-02 "
                "(set --e2e-skip to silence in --mode=all)",
            ))
        else:
            # --mode=all 时 e2e placeholder 跳过（不 fail）
            print("[verify-contract] e2e mode 在 Plan 04-02 实现；--mode=all 跳过 "
                  "(set --e2e-skip to silence)")

    # 汇总表
    print()
    print("[verify-contract] summary:")
    for name, ok, detail in results:
        status = "OK  " if ok else "FAIL"
        # 截断长 detail（self-test / schema error 可能很长）
        short = detail if len(detail) <= 120 else detail[:117] + "..."
        print(f"  {status}  {name:9s} {short}")

    any_fail = any(not ok for _, ok, _ in results)
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
