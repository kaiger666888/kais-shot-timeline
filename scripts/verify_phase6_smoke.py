#!/usr/bin/env python3
"""Phase 6 graceful-degrade + 缓存回归校验 harness（standalone，无 pytest）。

本 harness 锁 Phase 6 四条 verifiable 路径（live route round-trip DEFERRED —
feat/shot-analysis-route unmerged，见 STATE.md blocker + 06-VALIDATION.md
"Manual-Only Verifications"）。沿用 scripts/verify_contract.py 风格：
bracketed prefix tags + sys.exit(0/1) 退出码契约 + 仅 stdlib + 已在 env 的
jsonschema。

4 个 scenarios（每个独立 temp work_dir，互不污染）：

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

  stale_cache_offline (CR-01 regression guard, WR-06)
      预填 cache 含 WRONG _cache_key（video_content_hash 故意不匹配）+ --offline
      跑。断言：exit 0 + route-sourced facets 全空（降级）+ schema 合法 +
      warnings ≥1 且含 "stale-cache"。这是 CR-01（stale-cache + offline 静默降级
      为空 facets 且零 warning）的永久回归守卫 —— 正是当初 3/3 绿漏掉 CR-01 的
      harness 缺口。

退出码：
    0 = 4 个 scenario 全绿（"[phase6-smoke] OK: 4/4 scenarios green"）
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
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator


# === 路径常量 ============================================================
# scripts/verify_phase6_smoke.py → repo root
REPO = Path(__file__).parent.parent.resolve()
SCHEMAS_DIR = REPO / "spec" / "schemas"
EXAMPLES_DIR = REPO / "examples" / "shot_analysis"

# 不可达 URL —— port 1 是 reserved/unroutable，连接立即被拒（不会卡 timeout）。
# scenarios 1 + 3 都用它：s1 证明 degrade，s3 证明 cache hit 时根本不触网。
UNREACHABLE_URL = "http://127.0.0.1:1/api/v1/production/shot-analysis"

# tiny test 文件：用本 harness 自身做 --video。已知存在 + 内容固定 →
# video_content_hash 跨 run 稳定，scenario 3 预填 cache key 才能匹配。
TINY_VIDEO = Path(__file__).resolve()


# === common helpers =====================================================
def _tmp_work_dir() -> str:
    """mkdtemp(prefix=phase6-smoke-) —— caller finally 块 rmtree。"""
    return tempfile.mkdtemp(prefix="phase6-smoke-")


def _write_synthetic_shots(path: str, count: int = 2) -> None:
    """写合成 shots.json（count 个 1s 镜头，id 从 1 起）。

    call_shot_analysis.py 只读 id/start_sec/end_sec/duration；frames/energy
    等字段无关。schema 合法即可。
    """
    shots = [
        {"id": i + 1, "start_sec": float(i), "end_sec": float(i + 1), "duration": 1.0}
        for i in range(count)
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(shots, f, ensure_ascii=False, indent=2)


def _check_prompts_valid(work_dir: str) -> list:
    """对 <work_dir>/prompts.json 跑 Draft202012Validator，返 errors 列表。

    与 scripts/export_asset.py inline validator 同源 + scripts/verify_contract.py
    validate_eight_shapes 同模式（sorted by absolute_path）。空列表 = schema 合法。
    """
    prompts_path = os.path.join(work_dir, "prompts.json")
    schema = json.loads((SCHEMAS_DIR / "prompts.schema.json").read_text(encoding="utf-8"))
    instance = json.loads(Path(prompts_path).read_text(encoding="utf-8"))
    return sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda e: list(e.absolute_path),
    )


def _run(cmd: list, **kw) -> subprocess.CompletedProcess:
    """subprocess.run wrapper；capture_output=True, text=True 默认开。"""
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(cmd, **kw)


# === scenario 1: route-down graceful degrade (CINEMA-03) ===============
def scenario_route_down(verbose: bool = False) -> tuple:
    """对 unreachable URL 跑 call_shot_analysis.py，断言 graceful-degrade。

    Returns: (ok: bool, detail: str)
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        prompts_json = os.path.join(work_dir, "prompts.json")
        _write_synthetic_shots(shots_json, count=2)

        cmd = [
            sys.executable, str(REPO / "analysis" / "call_shot_analysis.py"),
            "--video", str(TINY_VIDEO),
            "--shots", shots_json,
            "--work-dir", work_dir,
            "--output", prompts_json,
            "--analysis-url", UNREACHABLE_URL,
            "--analysis-timeout", "2",   # 短超时保测试快（preflight 5s 上限内）
        ]
        r = _run(cmd, timeout=30)
        if verbose and r.stdout:
            sys.stdout.write(r.stdout)
        if verbose and r.stderr:
            sys.stderr.write(r.stderr)

        # (a) exit 0：graceful-degrade 不 fail
        if r.returncode != 0:
            return (False, f"expected exit 0 (graceful-degrade), got {r.returncode}; "
                           f"stderr: {(r.stderr or '').strip()[:300]}")

        # (b) prompts.json 写出
        if not os.path.isfile(prompts_json):
            return (False, f"prompts.json not written at {prompts_json}")

        # (c) 全部 5 个 route-sourced facets 为空串
        prompts = json.loads(Path(prompts_json).read_text(encoding="utf-8"))
        if len(prompts) != 2:
            return (False, f"expected 2 shots in prompts.json, got {len(prompts)}")
        for p in prompts:
            for facet in ("camera", "action", "lighting", "style", "subject", "scene"):
                val = p.get(facet)
                if val != "":
                    return (False, f"shot {p.get('shot_id')} facet {facet} "
                                   f"expected empty string, got {val!r}")

        # (d) schema 合法
        errs = _check_prompts_valid(work_dir)
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            return (False, f"prompts.json schema-invalid: /{loc}: {errs[0].message}")

        # (e) warnings sidecar 至少 1 条 + 含 preflight/ConnectError 字样
        warnings_path = os.path.join(work_dir, "route_cache", "warnings.json")
        if not os.path.isfile(warnings_path):
            return (False, f"warnings sidecar missing at {warnings_path}")
        warnings_data = json.loads(Path(warnings_path).read_text(encoding="utf-8"))
        warnings_list = warnings_data.get("warnings", [])
        if len(warnings_list) < 1:
            return (False, f"expected ≥1 warning, got {len(warnings_list)}")
        first = warnings_list[0]
        if "preflight" not in first and "ConnectError" not in first:
            return (False, f"warning should mention preflight/ConnectError; got: {first!r}")

        return (True, f"route-down OK: {len(prompts)} shots, all facets empty, "
                      f"{len(warnings_list)} warning(s), schema-valid")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 2: --skip-semantic (CINEMA-06) ==========================
def scenario_skip_semantic(verbose: bool = False) -> tuple:
    """调 run_pipeline.step_semantic(skip=True)，断言不子进程。

    直接 Python import 调用（更快 + 更精准 —— 不依赖整个 pipeline 起来）。
    捕获 stdout 验证 banner / label。
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        prompts_json = os.path.join(work_dir, "prompts.json")
        _write_synthetic_shots(shots_json, count=1)
        # 预置 prompts.json —— 让 skip 路径返回它（证明 cache lookup 不被 skip 跳过）
        Path(prompts_json).write_text("[]\n", encoding="utf-8")

        # import run_pipeline as module（不走其 main()）
        sys.path.insert(0, str(REPO))
        try:
            import run_pipeline
        finally:
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = run_pipeline.step_semantic(
                video=str(TINY_VIDEO),
                work_dir=work_dir,
                shots_json=shots_json,
                prompts_json=prompts_json,
                skip=True,
                offline=False,
                analysis_url=UNREACHABLE_URL,
                analysis_timeout=2.0,
            )
        out = buf.getvalue()
        if verbose:
            sys.stdout.write(out)

        # (a) 返回 prompts_json 路径（预置了 prompts.json → 应返回它）
        if ret != prompts_json:
            return (False, f"expected return {prompts_json}, got {ret!r}")

        # (b) stdout 含 --skip-semantic label
        if "--skip-semantic: skipping" not in out:
            return (False, f"stdout missing '--skip-semantic: skipping' label; "
                           f"got: {out.strip()[:200]!r}")

        # (c) stdout 不含 run_step banner（证明子进程没起）
        banner = "[5/7] cinematography analysis (shot-analysis route)"
        if banner in out:
            return (False, f"stdout unexpectedly contains run_step banner {banner!r} "
                           f"— subprocess was spawned despite skip=True")

        return (True, "skip-semantic OK: returned prompts.json path, "
                      "--skip-semantic label printed, no subprocess banner")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 3: cache-hit / --offline (CINEMA-04) ====================
def scenario_cache_hit_offline(verbose: bool = False) -> tuple:
    """预填 cache + --offline 跑，断言 cache 值落地 + 无网络。

    用 examples/shot_analysis/shot_003.json 作 captured fixture；映射后
    camera 应为 "中景, follow, fast, pan_right"（CONTEXT LOCKED mapping 已对
    shot_003 实测验证）。
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        prompts_json = os.path.join(work_dir, "prompts.json")
        # 1 shot，id=1 —— 与预填 cache 文件名 shot_001.json 对应
        _write_synthetic_shots(shots_json, count=1)

        # 预填 cache：复制 shot_003 fixture → shot_001.json，注入正确 _cache_key
        fixture_src = EXAMPLES_DIR / "shot_003.json"
        if not fixture_src.is_file():
            return (False, f"captured fixture missing: {fixture_src}")
        cache_dir = os.path.join(work_dir, "route_cache", "shot_analysis")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, "shot_001.json")

        # import call_shot_analysis 拿 video_content_hash + ROUTE_VERSION
        sys.path.insert(0, str(REPO))
        try:
            from analysis.call_shot_analysis import (
                video_content_hash, ROUTE_NAME, ROUTE_VERSION,
            )
        finally:
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))

        vch = video_content_hash(str(TINY_VIDEO))
        fixture = json.loads(fixture_src.read_text(encoding="utf-8"))
        # 注入 _cache_key（与 call_shot_analysis 写 cache 时的形状一致）
        fixture["_cache_key"] = {
            "video_content_hash": vch,
            "route_name": ROUTE_NAME,
            "route_version": ROUTE_VERSION,
        }
        Path(cache_file).write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")

        # 跑 --offline（URL 不可达 —— 但 cache 应命中，根本不触网）
        cmd = [
            sys.executable, str(REPO / "analysis" / "call_shot_analysis.py"),
            "--video", str(TINY_VIDEO),
            "--shots", shots_json,
            "--work-dir", work_dir,
            "--output", prompts_json,
            "--offline",
            "--analysis-url", UNREACHABLE_URL,
            "--analysis-timeout", "2",
        ]
        r = _run(cmd, timeout=30)
        if verbose and r.stdout:
            sys.stdout.write(r.stdout)
        if verbose and r.stderr:
            sys.stderr.write(r.stderr)

        # (a) exit 0
        if r.returncode != 0:
            return (False, f"expected exit 0, got {r.returncode}; "
                           f"stderr: {(r.stderr or '').strip()[:300]}")

        # (b) prompts.json 写出 + 1 shot
        if not os.path.isfile(prompts_json):
            return (False, f"prompts.json not written at {prompts_json}")
        prompts = json.loads(Path(prompts_json).read_text(encoding="utf-8"))
        if len(prompts) != 1:
            return (False, f"expected 1 shot, got {len(prompts)}")

        # (c) camera 用 cache 值（shot_003 LOCKED mapping）
        expected_camera = "中景, follow, fast, pan_right"
        actual_camera = prompts[0].get("camera")
        if actual_camera != expected_camera:
            return (False, f"camera: expected {expected_camera!r} (cached), "
                           f"got {actual_camera!r}")

        # (d) schema 合法
        errs = _check_prompts_valid(work_dir)
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            return (False, f"prompts.json schema-invalid: /{loc}: {errs[0].message}")

        # (e) stdout 含 cache hit 标签
        if "[semantic] shot 1: cache hit" not in (r.stdout or ""):
            return (False, f"stdout missing '[semantic] shot 1: cache hit'; "
                           f"stdout: {(r.stdout or '').strip()[:300]!r}")

        # (f) stdout 不含 FAIL —— offline + cache hit 不应触网失败
        if "FAIL" in (r.stdout or ""):
            return (False, f"stdout unexpectedly contains 'FAIL'; "
                           f"stdout: {(r.stdout or '').strip()[:300]!r}")

        return (True, f"cache-hit offline OK: camera={actual_camera!r}, "
                      f"schema-valid, cache hit label printed, no FAIL")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 4: stale-cache + offline (CR-01 regression guard) =======
def scenario_stale_cache_offline(verbose: bool = False) -> tuple:
    """预填 cache 含 WRONG _cache_key + --offline 跑，断言 warning 被记。

    CR-01 回归守卫（WR-06 补的 harness 缺口 —— 正是 CR-01 当初未被 3/3 绿捉住
    的原因）：cache 文件存在但 _cache_key 不匹配（video 换 / ROUTE_VERSION bump /
    route_name 异）+ offline → 旧实现静默降级为空 facets 且零 warning（操作员
    毫无察觉，正是 Pitfall 4 要防的）。现必须：
      (a) exit 0（graceful-degrade 不 fail）
      (b) route-sourced facets 全空（降级）
      (c) schema 合法
      (d) warnings ≥1 且含 "stale-cache"（不静默 —— 操作员必须看见输出被降级）
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        prompts_json = os.path.join(work_dir, "prompts.json")
        # 1 shot，id=1 —— 与预填 cache 文件名 shot_001.json 对应
        _write_synthetic_shots(shots_json, count=1)

        # 预填 cache：复制 shot_003 fixture → shot_001.json，但注入 WRONG
        # video_content_hash（故意不匹配 tiny test 文件 → stale miss）。
        fixture_src = EXAMPLES_DIR / "shot_003.json"
        if not fixture_src.is_file():
            return (False, f"captured fixture missing: {fixture_src}")
        cache_dir = os.path.join(work_dir, "route_cache", "shot_analysis")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, "shot_001.json")

        sys.path.insert(0, str(REPO))
        try:
            from analysis.call_shot_analysis import ROUTE_NAME, ROUTE_VERSION
        finally:
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))

        fixture = json.loads(fixture_src.read_text(encoding="utf-8"))
        # 注入 WRONG _cache_key（video_content_hash 故意不匹配 —— 模拟 video 文件
        # 被换 / ROUTE_VERSION bump 后未刷 cache 的场景）。
        fixture["_cache_key"] = {
            "video_content_hash": "WRONG_HASH_VALUE_STALE_CACHE_TEST",
            "route_name": ROUTE_NAME,
            "route_version": ROUTE_VERSION,
        }
        Path(cache_file).write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")

        # 跑 --offline（URL 不可达；cache 文件存在但 stale）
        cmd = [
            sys.executable, str(REPO / "analysis" / "call_shot_analysis.py"),
            "--video", str(TINY_VIDEO),
            "--shots", shots_json,
            "--work-dir", work_dir,
            "--output", prompts_json,
            "--offline",
            "--analysis-url", UNREACHABLE_URL,
            "--analysis-timeout", "2",
        ]
        r = _run(cmd, timeout=30)
        if verbose and r.stdout:
            sys.stdout.write(r.stdout)
        if verbose and r.stderr:
            sys.stderr.write(r.stderr)

        # (a) exit 0（graceful-degrade 不 fail）
        if r.returncode != 0:
            return (False, f"expected exit 0 (graceful-degrade), got {r.returncode}; "
                           f"stderr: {(r.stderr or '').strip()[:300]}")

        # (b) prompts.json 写出 + route-sourced facets 全空（降级）
        if not os.path.isfile(prompts_json):
            return (False, f"prompts.json not written at {prompts_json}")
        prompts = json.loads(Path(prompts_json).read_text(encoding="utf-8"))
        if len(prompts) != 1:
            return (False, f"expected 1 shot, got {len(prompts)}")
        for facet in ("camera", "action", "lighting", "style"):
            val = prompts[0].get(facet)
            if val != "":
                return (False, f"stale-cache should degrade facet {facet} to '', "
                               f"got {val!r}")

        # (c) schema 合法
        errs = _check_prompts_valid(work_dir)
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            return (False, f"prompts.json schema-invalid: /{loc}: {errs[0].message}")

        # (d) warnings ≥1 且含 "stale-cache"（CR-01 核心：不静默降级）
        warnings_path = os.path.join(work_dir, "route_cache", "warnings.json")
        if not os.path.isfile(warnings_path):
            return (False, f"warnings sidecar missing at {warnings_path}")
        warnings_list = json.loads(
            Path(warnings_path).read_text(encoding="utf-8")).get("warnings", [])
        if len(warnings_list) < 1:
            return (False, f"CR-01 regression: stale-cache + offline produced "
                           f"0 warnings (silent degrade); expected ≥1")
        if not any("stale-cache" in w for w in warnings_list):
            return (False, f"CR-01 regression: no warning mentions 'stale-cache'; "
                           f"got: {warnings_list!r}")

        return (True, f"stale-cache offline OK: degraded to empty facets + "
                      f"{len(warnings_list)} warning(s) (no silent degrade)")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === CLI ================================================================
def main():
    """Run 4 scenarios in order; collect (name, ok, detail); exit 0/1."""
    ap = argparse.ArgumentParser(
        description="Phase 6 graceful-degrade + cache 回归校验 "
                    "(route-down / --skip-semantic / cache-hit-offline / "
                    "stale-cache-offline)")
    ap.add_argument("--verbose", action="store_true",
                    help="透传子进程 stdout/stderr（debug 用）")
    args = ap.parse_args()

    scenarios = [
        ("route_down", scenario_route_down),
        ("skip_semantic", scenario_skip_semantic),
        ("cache_hit_offline", scenario_cache_hit_offline),
        ("stale_cache_offline", scenario_stale_cache_offline),
    ]

    results = []
    for name, fn in scenarios:
        try:
            ok, detail = fn(verbose=args.verbose)
        except Exception as e:
            ok, detail = False, f"unexpected exception: {type(e).__name__}: {e}"
        tag = "[phase6-smoke] PASS" if ok else "[phase6-smoke] FAIL"
        print(f"{tag} {name}: {detail}")
        results.append((name, ok, detail))

    print()
    all_ok = all(ok for _, ok, _ in results)
    if all_ok:
        print(f"[phase6-smoke] OK: {len(results)}/{len(results)} scenarios green")
        sys.exit(0)
    else:
        fails = [n for n, ok, _ in results if not ok]
        print(f"[phase6-smoke] FAIL: {len(fails)}/{len(results)} scenarios failed "
              f"({', '.join(fails)})")
        sys.exit(1)


if __name__ == "__main__":
    main()
