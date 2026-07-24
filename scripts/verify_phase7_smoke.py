#!/usr/bin/env python3
"""Phase 7 graceful-degrade + 缓存 + 幂等 + confirmed-only 回归校验 harness
（standalone，无 pytest）。

本 harness 锁 Phase 7 五条 verifiable 路径（live route round-trip + τ 经验
校准 + HITL UX pilot DEFERRED —— character-reid 路由今日不存在，镜像
feat/shot-analysis-route pre-merge 状态；详见 STATE.md blocker + 07-VALIDATION.md
"Manual-Only Verifications"）。沿用 scripts/verify_contract.py +
scripts/verify_phase6_smoke.py 风格：bracketed prefix tags + sys.exit(0/1)
退出码契约 + 仅 stdlib + 已在 env 的 jsonschema。

5 个 scenarios（每个独立 temp work_dir，互不污染）：

  route_down (CAST-09 graceful-degrade)
      对 unreachable URL（http://127.0.0.1:1/）跑 analysis/call_reid.py，
      断言：exit 0（graceful-degrade 不 fail）+ registry.draft.json 写出且
      clusters == []（空 clusters，schema 合法）+ route_cache/warnings.json
      至少 1 条记录（含 "preflight" / "ConnectError" / "character-reid"）。

  skip_reid (CAST-09 flag)
      直接调 run_pipeline.step_reid(skip=True, ...) 并捕获 stdout。断言：
      stdout 含 "--skip-reid: skipping" 标签 + 不含
      "[6/8] cross-shot re-id (character-reid route)" run_step banner
      （证明子进程没被起）+ 返回 registry_draft 路径（若预置）或 None。

  empty_draft_handoff (CAST-05/06/07 boundary)
      seed registry.draft.json 含 clusters:[] → 跑 html/gen_registry_review.py
      （HITL HTML 仍生成 + 空态 placeholder）+ registry/apply_edits.py
      （产空 characters.json/props.json 或文件缺席 —— 无 confirmed 条目）。
      证明端到端 graceful：route-down → 空 draft → 空 canonical → asset 仍 export。

  apply_edits_idempotent (CAST-07 confirmed-only + Pitfall 5 idempotency)
      在两个独立 work_dir 用同一 spec/fixtures/v1.1/registry.draft.json +
      registry.edits.json fixtures 跑 apply_edits.py 两次。断言：两次产物
      byte-identical（characters.json + props.json）+ 全部 review_state="confirmed"
      （Pitfall 7 hard gate）+ schema-valid + appearance_shots ⊆ fixture shots
      IDs [1, 2]。

  cache_hit_offline (CAST-09 + CINEMA-04 analog)
      预填 route_cache/character_reid/video_<vch>.json 含 fixture clusters +
      正确 _cache_key（video_content_hash 匹配 tiny test 文件 + ROUTE_NAME +
      ROUTE_VERSION）。跑 call_reid.py --offline 对 unreachable URL。断言：
      exit 0 + registry.draft.json 用 cache 值（至少 1 个 cluster，含 char_001
      from fixture）+ stdout 含 "[reid] cache hit" + 0 网络调用。

退出码：
    0 = 5 个 scenario 全绿（"[phase7-smoke] OK: 5/5 scenarios green"）
    1 = 任一 scenario fail（detail 行说明哪个 + 为何）

用法：
    python3 scripts/verify_phase7_smoke.py
    python3 scripts/verify_phase7_smoke.py --verbose   # 透传子进程 stdout/stderr

设计要点（mirror verify_phase6_smoke.py）：
  - temp work_dir 用 tempfile.mkdtemp(prefix="phase7-smoke-")，finally 块
    shutil.rmtree(ignore_errors=True) 兜底。
  - tiny --video 用本文件自身（scripts/verify_phase7_smoke.py）—— 已知存在 +
    内容固定（保证 video_content_hash 跨 run 稳定，scenario 5 cache 才能命中）。
    ffmpeg 抽帧会失败（非视频），gen_registry_review.py / apply_edits.py 都
    显式 catch 失败 → placeholder SVG / OMIT representative_image；不影响
    场景断言。
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
# scripts/verify_phase7_smoke.py → repo root
REPO = Path(__file__).parent.parent.resolve()
SCHEMAS_DIR = REPO / "spec" / "schemas"
FIXTURES_V11 = REPO / "spec" / "fixtures" / "v1.1"

# 不可达 URL —— port 1 是 reserved/unroutable，连接立即被拒（不会卡 timeout）。
# scenarios 1 + 5 都用它：s1 证明 degrade，s5 证明 cache hit 时根本不触网。
UNREACHABLE_URL = "http://127.0.0.1:1/api/v1/production/character-reid"

# tiny test 文件：用本 harness 自身做 --video。已知存在 + 内容固定 →
# video_content_hash 跨 run 稳定，scenario 5 预填 cache key 才能匹配。
# 注意：这是一个 .py 文件不是视频；ffmpeg 抽帧会失败 —— 但所有被测脚本
# （gen_registry_review.py / apply_edits.py）都显式 catch ffmpeg 失败。
TINY_VIDEO = Path(__file__).resolve()


# === common helpers =====================================================
def _tmp_work_dir() -> str:
    """mkdtemp(prefix=phase7-smoke-) —— caller finally 块 rmtree。"""
    return tempfile.mkdtemp(prefix="phase7-smoke-")


def _write_synthetic_shots(path: str, count: int = 2) -> None:
    """写合成 shots.json（count 个 1s 镜头，id 从 1 起）。

    call_reid.py 只读 id 字段 + JSON shape；frames/energy 等无关。
    schema 合法即可。
    """
    shots = [
        {"id": i + 1, "start_sec": float(i), "end_sec": float(i + 1), "duration": 1.0}
        for i in range(count)
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(shots, f, ensure_ascii=False, indent=2)


def _run(cmd: list, **kw) -> subprocess.CompletedProcess:
    """subprocess.run wrapper；capture_output=True, text=True 默认开。"""
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(cmd, **kw)


def _check_json_valid(instance, schema_filename: str) -> list:
    """对 instance 跑 Draft202012Validator(<schema_filename>)，返 errors list。"""
    schema = json.loads((SCHEMAS_DIR / schema_filename).read_text(encoding="utf-8"))
    return sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda e: list(e.absolute_path),
    )


# === scenario 1: route-down graceful degrade (CAST-09) =================
def scenario_route_down(verbose: bool = False) -> tuple:
    """对 unreachable URL 跑 analysis/call_reid.py，断言 graceful-degrade。

    Returns: (ok: bool, detail: str)
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        draft_path = os.path.join(work_dir, "registry.draft.json")
        _write_synthetic_shots(shots_json, count=2)

        cmd = [
            sys.executable, str(REPO / "analysis" / "call_reid.py"),
            "--video", str(TINY_VIDEO),
            "--shots", shots_json,
            "--work-dir", work_dir,
            "--output", draft_path,
            "--reid-url", UNREACHABLE_URL,
            "--reid-timeout", "2",   # 短超时保测试快（preflight 5s 上限内）
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

        # (b) registry.draft.json 写出
        if not os.path.isfile(draft_path):
            return (False, f"registry.draft.json not written at {draft_path}")

        # (c) clusters == []（空 clusters —— route-down degrade）
        draft = json.loads(Path(draft_path).read_text(encoding="utf-8"))
        if draft.get("clusters") != []:
            return (False, f"expected empty clusters on route-down degrade, "
                           f"got: {draft.get('clusters')!r}")

        # (d) registry.draft.json schema 合法（fails loud 惯例的逆证明：
        #     degrade 路径仍 emit schema-valid）
        errs = _check_json_valid(draft, "registry.schema.json")
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            return (False, f"registry.draft.json schema-invalid: /{loc}: {errs[0].message}")

        # (e) warnings sidecar 至少 1 条 + 含 preflight / ConnectError / character-reid
        warnings_path = os.path.join(work_dir, "route_cache", "warnings.json")
        if not os.path.isfile(warnings_path):
            return (False, f"warnings sidecar missing at {warnings_path}")
        warnings_data = json.loads(Path(warnings_path).read_text(encoding="utf-8"))
        warnings_list = warnings_data.get("warnings", [])
        if len(warnings_list) < 1:
            return (False, f"expected >=1 warning, got {len(warnings_list)}")
        first = warnings_list[0]
        if not any(k in first for k in ("preflight", "ConnectError", "character-reid")):
            return (False, f"warning should mention preflight/ConnectError/character-reid; "
                           f"got: {first!r}")

        return (True, f"route-down OK: clusters=[], schema-valid, "
                      f"{len(warnings_list)} warning(s)")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 2: --skip-reid (CAST-09 flag) ============================
def scenario_skip_reid(verbose: bool = False) -> tuple:
    """调 run_pipeline.step_reid(skip=True)，断言不子进程。

    直接 Python import 调用（更快 + 更精准 —— 不依赖整个 pipeline 起来）。
    捕获 stdout 验证 banner / label。
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        draft_path = os.path.join(work_dir, "registry.draft.json")
        review_html = os.path.join(work_dir, "registry_review.html")
        _write_synthetic_shots(shots_json, count=1)
        # 预置 registry.draft.json —— 让 skip 路径返回它
        Path(draft_path).write_text(
            json.dumps({"generated_at": "2026-07-25T00:00:00Z",
                        "model": "test", "tau": 0.30, "clusters": []},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        # import run_pipeline as module（不走其 main()）
        sys.path.insert(0, str(REPO))
        try:
            import run_pipeline
        finally:
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ret = run_pipeline.step_reid(
                video=str(TINY_VIDEO),
                work_dir=work_dir,
                shots_json=shots_json,
                registry_draft=draft_path,
                review_html=review_html,
                skip=True,
                offline=False,
                reid_url=UNREACHABLE_URL,
                reid_timeout=2.0,
            )
        out = buf.getvalue()
        if verbose:
            sys.stdout.write(out)

        # (a) 返回 draft_path（预置了 → 应返回它）
        if ret != draft_path:
            return (False, f"expected return {draft_path}, got {ret!r}")

        # (b) stdout 含 --skip-reid label
        if "--skip-reid: skipping" not in out:
            return (False, f"stdout missing '--skip-reid: skipping' label; "
                           f"got: {out.strip()[:200]!r}")

        # (c) stdout 不含 run_step banner（证明子进程没起）
        banner = "[6/8] cross-shot re-id (character-reid route)"
        if banner in out:
            return (False, f"stdout unexpectedly contains run_step banner {banner!r} "
                           f"— subprocess was spawned despite skip=True")

        return (True, "skip-reid OK: returned draft_path, "
                      "--skip-reid label printed, no subprocess banner")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 3: empty-draft handoff (CAST-05/06/07 boundary) ==========
def scenario_empty_draft_handoff(verbose: bool = False) -> tuple:
    """seed 空 clusters[] draft → gen_registry_review 仍产 HTML + apply_edits 产空 canonical。

    证明端到端 graceful degrade：route-down → 空 draft → 仍能生成 HITL HTML
    （空态 placeholder）+ apply_edits 不 crash（产空 characters.json/props.json
    或文件缺席 —— 无 confirmed 条目）。
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        draft_path = os.path.join(work_dir, "registry.draft.json")
        html_path = os.path.join(work_dir, "registry_review.html")
        edits_path = os.path.join(work_dir, "registry.edits.json")
        _write_synthetic_shots(shots_json, count=2)

        # seed empty draft（route-down degrade 输出的 shape）
        Path(draft_path).write_text(
            json.dumps({"generated_at": "2026-07-25T00:00:00Z",
                        "model": "facebook/dinov2-base", "tau": 0.30,
                        "clusters": []}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        # seed 空 edits（confirm_ids=[] 等 —— 操作员对空 draft 无可审）
        Path(edits_path).write_text(
            json.dumps({"merge_groups": [], "splits": {}, "renames": {},
                        "type_overrides": {}, "confirm_ids": [], "reject_ids": [],
                        "review_notes": "empty draft — no clusters to review"},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

        # (a) gen_registry_review.py 仍产 HTML（空态 placeholder）
        cmd1 = [
            sys.executable, str(REPO / "html" / "gen_registry_review.py"),
            "--draft", draft_path, "--video", str(TINY_VIDEO),
            "--shots", shots_json, "--output", html_path,
        ]
        r1 = _run(cmd1, timeout=30)
        if verbose and r1.stdout:
            sys.stdout.write(r1.stdout)
        if verbose and r1.stderr:
            sys.stderr.write(r1.stderr)
        if r1.returncode != 0:
            return (False, f"gen_registry_review.py failed on empty draft "
                           f"(rc={r1.returncode}); stderr: {(r1.stderr or '').strip()[:300]}")
        if not os.path.isfile(html_path):
            return (False, f"review HTML not written at {html_path}")
        html = Path(html_path).read_text(encoding="utf-8")
        # CAST-06 lock: HTML 必须是 self-contained + 有 Export edits button
        if "Export edits" not in html:
            return (False, "review HTML missing 'Export edits' button (CAST-06 contract)")
        # 空 draft 应有空态 placeholder 或 cluster-card class（任一存在）
        if "cluster-card" not in html and "空 draft" not in html:
            return (False, "review HTML missing cluster-card class or empty-state marker")

        # (b) apply_edits.py 仍 exit 0（空 clusters → 空 canonical files 或 absent）
        cmd2 = [
            sys.executable, str(REPO / "registry" / "apply_edits.py"),
            "--draft", draft_path, "--edits", edits_path,
            "--work-dir", work_dir, "--video", str(TINY_VIDEO),
            "--shots", shots_json,
        ]
        r2 = _run(cmd2, timeout=30)
        if verbose and r2.stdout:
            sys.stdout.write(r2.stdout)
        if verbose and r2.stderr:
            sys.stderr.write(r2.stderr)
        if r2.returncode != 0:
            return (False, f"apply_edits.py failed on empty draft "
                           f"(rc={r2.returncode}); stderr: {(r2.stderr or '').strip()[:300]}")

        # (c) characters.json + props.json 存在且为 []（apply_edits 总是写两个文件，
        #     即使空）。无 confirmed 条目 → 列表空。
        chars_path = os.path.join(work_dir, "characters.json")
        props_path = os.path.join(work_dir, "props.json")
        if not os.path.isfile(chars_path):
            return (False, f"characters.json not written at {chars_path}")
        if not os.path.isfile(props_path):
            return (False, f"props.json not written at {props_path}")
        chars = json.loads(Path(chars_path).read_text(encoding="utf-8"))
        props = json.loads(Path(props_path).read_text(encoding="utf-8"))
        if chars != []:
            return (False, f"empty draft should produce [] characters; got: {chars!r}")
        if props != []:
            return (False, f"empty draft should produce [] props; got: {props!r}")

        return (True, f"empty-draft handoff OK: HTML written ({len(html)} bytes), "
                      f"apply_edits exits 0, characters/props == []")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 4: apply_edits idempotent (CAST-07 + Pitfall 5) ==========
def scenario_apply_edits_idempotent(verbose: bool = False) -> tuple:
    """跑 apply_edits.py 两次（独立 work_dir）→ 断言 byte-identical + confirmed-only。

    Uses spec/fixtures/v1.1/registry.draft.json + registry.edits.json + shots.json
    as the deterministic seed.
    """
    fixture_draft = FIXTURES_V11 / "registry.draft.json"
    fixture_edits = FIXTURES_V11 / "registry.edits.json"
    fixture_shots = FIXTURES_V11 / "shots.json"
    for p in (fixture_draft, fixture_edits, fixture_shots):
        if not p.is_file():
            return (False, f"required fixture missing: {p}")

    work_a = _tmp_work_dir()
    work_b = _tmp_work_dir()
    try:
        results = []
        for work_dir in (work_a, work_b):
            cmd = [
                sys.executable, str(REPO / "registry" / "apply_edits.py"),
                "--draft", str(fixture_draft),
                "--edits", str(fixture_edits),
                "--work-dir", work_dir,
                "--video", str(TINY_VIDEO),
                "--shots", str(fixture_shots),
            ]
            r = _run(cmd, timeout=60)
            if verbose and r.stdout:
                sys.stdout.write(r.stdout)
            if verbose and r.stderr:
                sys.stderr.write(r.stderr)
            if r.returncode != 0:
                return (False, f"apply_edits.py failed in {work_dir} "
                               f"(rc={r.returncode}); stderr: {(r.stderr or '').strip()[:300]}")
            results.append(work_dir)

        # (a) byte-identical between two runs（Pitfall 5 idempotency）
        chars_a = Path(work_a) / "characters.json"
        chars_b = Path(work_b) / "characters.json"
        props_a = Path(work_a) / "props.json"
        props_b = Path(work_b) / "props.json"
        for p in (chars_a, chars_b, props_a, props_b):
            if not p.is_file():
                return (False, f"canonical file missing: {p}")
        chars_a_text = chars_a.read_text(encoding="utf-8")
        chars_b_text = chars_b.read_text(encoding="utf-8")
        props_a_text = props_a.read_text(encoding="utf-8")
        props_b_text = props_b.read_text(encoding="utf-8")
        if chars_a_text != chars_b_text:
            return (False, f"characters.json not byte-identical between runs "
                           f"(Pitfall 5 idempotency broken)")
        if props_a_text != props_b_text:
            return (False, f"props.json not byte-identical between runs "
                           f"(Pitfall 5 idempotency broken)")

        # (b) 所有 entries review_state == "confirmed"（Pitfall 7 hard gate）
        chars = json.loads(chars_a_text)
        props = json.loads(props_a_text)
        for entry in chars + props:
            if entry.get("review_state") != "confirmed":
                return (False, f"Pitfall 7 violation: entry {entry.get('id')} has "
                               f"review_state={entry.get('review_state')!r}")

        # (c) schema-valid（characters.schema.json + props.schema.json）
        chars_errs = _check_json_valid(chars, "characters.schema.json")
        if chars_errs:
            loc = "/".join(map(str, chars_errs[0].absolute_path)) or "<root>"
            return (False, f"characters.json schema-invalid: /{loc}: {chars_errs[0].message}")
        props_errs = _check_json_valid(props, "props.schema.json")
        if props_errs:
            loc = "/".join(map(str, props_errs[0].absolute_path)) or "<root>"
            return (False, f"props.json schema-invalid: /{loc}: {props_errs[0].message}")

        # (d) appearance_shots ⊆ fixture shots IDs [1, 2]
        fixture_shots_data = json.loads(fixture_shots.read_text(encoding="utf-8"))
        valid_shot_ids = {s.get("id") for s in fixture_shots_data}
        for entry in chars + props:
            for sid in entry.get("appearance_shots", []) or []:
                if sid not in valid_shot_ids:
                    return (False, f"entry {entry.get('id')} appearance_shots "
                                   f"references unknown shot {sid}")

        # (e) "proposed" cluster 在 fixture 但不在 confirm_ids → 不出现在 canonical
        # fixture draft 有 char_001 / char_002 / prop_001，全部在 confirm_ids。
        # 为硬验证 Pitfall 7 second-line：检查 fixture 真的没有 proposed 泄漏 ——
        # 因为所有 fixture cluster_ids 都 confirm，这里只需确认 canonical IDs 集合
        # ⊆ confirm_ids 集合（不会多）。
        edits_data = json.loads(fixture_edits.read_text(encoding="utf-8"))
        confirm_set = set(edits_data.get("confirm_ids", []))
        canonical_ids = {e.get("id") for e in chars + props}
        if not canonical_ids.issubset(confirm_set):
            extra = canonical_ids - confirm_set
            return (False, f"Pitfall 7 leak: canonical IDs {extra} not in "
                           f"edits.confirm_ids {confirm_set}")

        n_chars = len(chars)
        n_props = len(props)
        return (True, f"apply_edits idempotent OK: byte-identical ×2 runs, "
                      f"all confirmed, schema-valid, {n_chars} chars + {n_props} props, "
                      f"shots ⊆ {sorted(valid_shot_ids)}")
    finally:
        shutil.rmtree(work_a, ignore_errors=True)
        shutil.rmtree(work_b, ignore_errors=True)


# === scenario 5: cache-hit / --offline (CAST-09 + CINEMA-04 analog) ===
def scenario_cache_hit_offline(verbose: bool = False) -> tuple:
    """预填 cache + --offline 跑，断言 cache 值落地 + 无网络。

    Pre-seed route_cache/character_reid/video_<vch>.json with content from
    spec/fixtures/v1.1/registry.draft.json + matching _cache_key.
    """
    fixture_draft = FIXTURES_V11 / "registry.draft.json"
    if not fixture_draft.is_file():
        return (False, f"required fixture missing: {fixture_draft}")

    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        draft_path = os.path.join(work_dir, "registry.draft.json")
        _write_synthetic_shots(shots_json, count=2)

        # import call_reid 拿 video_content_hash + ROUTE_NAME + ROUTE_VERSION
        sys.path.insert(0, str(REPO))
        try:
            from analysis.call_reid import (
                video_content_hash, ROUTE_NAME, ROUTE_VERSION,
            )
        finally:
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))

        vch = video_content_hash(str(TINY_VIDEO))

        # 预填 cache：fixture 是 registry.draft.json shape（含 clusters + cluster_id 等）。
        # call_reid 的 cache 文件 shape 是 route data envelope + _cache_key —— 即
        # {"clusters": [...], ..., "_cache_key": {...}}（route_data is data field of envelope）。
        # fixture draft 的 clusters 也就是 cache 应包含的 clusters。
        fixture = json.loads(fixture_draft.read_text(encoding="utf-8"))
        cache_payload = {
            # route data envelope shape —— call_reid normalize_clusters 读 .clusters
            "clusters": fixture.get("clusters", []),
            "count": len(fixture.get("clusters", [])),
            "outputDir": "/tmp/test-crops",
            "crops": [],
            "_cache_key": {
                "video_content_hash": vch,
                "route_name": ROUTE_NAME,
                "route_version": ROUTE_VERSION,
            },
        }
        cache_dir = os.path.join(work_dir, "route_cache", ROUTE_NAME)
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"video_{vch}.json")
        Path(cache_file).write_text(
            json.dumps(cache_payload, ensure_ascii=False, indent=2),
            encoding="utf-8")

        # 跑 --offline（URL 不可达 —— 但 cache 应命中，根本不触网）
        cmd = [
            sys.executable, str(REPO / "analysis" / "call_reid.py"),
            "--video", str(TINY_VIDEO),
            "--shots", shots_json,
            "--work-dir", work_dir,
            "--output", draft_path,
            "--offline",
            "--reid-url", UNREACHABLE_URL,
            "--reid-timeout", "2",
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

        # (b) registry.draft.json 写出 + uses cache values（至少 1 cluster，含 char_001）
        if not os.path.isfile(draft_path):
            return (False, f"registry.draft.json not written at {draft_path}")
        draft = json.loads(Path(draft_path).read_text(encoding="utf-8"))
        clusters = draft.get("clusters", [])
        if not clusters:
            return (False, f"cache miss: draft has empty clusters; expected "
                           f"fixture values (char_001 etc.)")
        cluster_ids = {c.get("cluster_id") for c in clusters}
        if "char_001" not in cluster_ids:
            return (False, f"cache values not used: char_001 missing from "
                           f"draft clusters {cluster_ids}")

        # (c) registry.draft.json schema-valid
        errs = _check_json_valid(draft, "registry.schema.json")
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            return (False, f"registry.draft.json schema-invalid: /{loc}: {errs[0].message}")

        # (d) stdout 含 cache hit 标签
        if "[reid] cache hit" not in (r.stdout or ""):
            return (False, f"stdout missing '[reid] cache hit'; "
                           f"stdout: {(r.stdout or '').strip()[:300]!r}")

        # (e) stdout 不含 FAIL —— offline + cache hit 不应触网失败
        if "FAIL" in (r.stdout or ""):
            return (False, f"stdout unexpectedly contains 'FAIL'; "
                           f"stdout: {(r.stdout or '').strip()[:300]!r}")

        return (True, f"cache-hit offline OK: {len(clusters)} clusters from cache, "
                      f"schema-valid, cache hit label printed, no FAIL")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === CLI ================================================================
def main():
    """Run 5 scenarios in order; collect (name, ok, detail); exit 0/1."""
    ap = argparse.ArgumentParser(
        description="Phase 7 graceful-degrade + cache + 幂等 + confirmed-only "
                    "回归校验 (route-down / --skip-reid / empty-draft-handoff / "
                    "apply-edits-idempotent / cache-hit-offline)")
    ap.add_argument("--verbose", action="store_true",
                    help="透传子进程 stdout/stderr（debug 用）")
    args = ap.parse_args()

    scenarios = [
        ("route_down", scenario_route_down),
        ("skip_reid", scenario_skip_reid),
        ("empty_draft_handoff", scenario_empty_draft_handoff),
        ("apply_edits_idempotent", scenario_apply_edits_idempotent),
        ("cache_hit_offline", scenario_cache_hit_offline),
    ]

    results = []
    for name, fn in scenarios:
        try:
            ok, detail = fn(verbose=args.verbose)
        except Exception as e:
            ok, detail = False, f"unexpected exception: {type(e).__name__}: {e}"
        tag = "[phase7-smoke] PASS" if ok else "[phase7-smoke] FAIL"
        print(f"{tag} {name}: {detail}")
        results.append((name, ok, detail))

    print()
    all_ok = all(ok for _, ok, _ in results)
    if all_ok:
        print(f"[phase7-smoke] OK: {len(results)}/{len(results)} scenarios green")
        sys.exit(0)
    else:
        fails = [n for n, ok, _ in results if not ok]
        print(f"[phase7-smoke] FAIL: {len(fails)}/{len(results)} scenarios failed "
              f"({', '.join(fails)})")
        sys.exit(1)


if __name__ == "__main__":
    main()
