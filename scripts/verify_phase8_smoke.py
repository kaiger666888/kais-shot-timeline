#!/usr/bin/env python3
"""Phase 8 graceful-degrade + 幂等 + snapshot freeze + integrity + confirmed-only
+ XSS-inert 回归校验 harness（standalone，无 pytest）。

本 harness 锁 Phase 8 六条 verifiable 路径。沿用 scripts/verify_phase7_smoke.py
风格：bracketed prefix tags + sys.exit(0/1) 退出码契约 + 仅 stdlib + 已在 env
的 jsonschema。每个 scenario 独立 temp work_dir（互不污染），finally 块 rmtree 兜底。

6 个 scenarios（mirror Phase 7 五-scenario 结构 + XSS-inert 第六项）：

  attach_no_registry (PROMPT-01 graceful-degrade)
      seed prompts.json (facets 已填) + NO characters.json/props.json →
      run attach_refs.py → exit 0 + refs 空 + prompt_text 重组自 facets 单独
      （无 角色 / 道具 子句）+ schema 合法。

  attach_idempotent (PROMPT-01/02 determinism)
      seed fixture characters.json + props.json + prompts.json → 跑
      attach_refs.py 两次 → byte-diff → 完全一致 + refs 匹配 fixture target
      （shot 1 character_refs == [char_001, char_002]）。

  snapshot_freeze (PROMPT-04 + Pitfall 18)
      build_asset_dict with confirmed registry → snapshot1 in generator；
      mutate characters.json 后重读已写盘的 asset.json → snapshot 不变
      （export-time truth 冻结）。

  integrity_dangling_ref (PROMPT-03 / Pitfall 17)
      seed prompts.json with character_refs:["char_999"]（不在 characters.json）+
      characters.json（不含 char_999）→ _producer_registry_integrity →
      失败信息含 "char_999" + "Pitfall 17"。

  snapshot_confirmed_only (Pitfall 7 leak prevention)
      seed characters.json with 1 confirmed + 1 proposed → _build_registry_snapshot
      → snapshot 仅含 confirmed 条目（char_002 proposed 被过滤）。

  html_xss_inert (PRESENT-01/02 + CR-04 carry + Phase 8 REVIEW CR-01/WR-03)
      Multi-sink × multi-payload XSS matrix —— gen_timeline_html.py 必须把每个
      operator-influenced sink 都中和（_esc 或 JSON-in-script .replace("</", "<\\/"))。
      Sinks & payloads 覆盖：
        (a) gallery name (body context)     payload "</script><script>..."
        (b) gallery name (body context)     payload "<img src=x onerror=alert(1)>"
        (c) page <title> (head context)     payload "</title><script>alert(1)</script>"
        (d) page <h1> (body context)        payload "</h1><script>alert(document.cookie)</script>"
        (e) <source src> (attribute ctx)    payload 'x" onerror="alert(1)'
      断言：原始可执行 payload 模式不出现在生成 HTML 任何位置
      （无 raw <script>alert、无 raw onerror=、无 raw </title><script>、
        无 raw </h1><script>、无 raw src="x" onerror）。
      Phase 8 REVIEW WR-04 fix：原 scenario 6 只测 ONE sink × ONE payload，无法
      检测 CR-01 (title) 或 WR-03 (video_src) 回归 —— 本 broaden 把 XSS posture 锁住。

退出码：
    0 = 6 个 scenario 全绿（"[phase8-smoke] OK: 6/6 scenarios green"）
    1 = 任一 scenario fail

用法：
    python3 scripts/verify_phase8_smoke.py
    python3 scripts/verify_phase8_smoke.py --verbose   # 透传子进程 stdout/stderr
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator


# === 路径常量 ============================================================
# scripts/verify_phase8_smoke.py → repo root
REPO = Path(__file__).parent.parent.resolve()
SCHEMAS_DIR = REPO / "spec" / "schemas"
FIXTURES_V11 = REPO / "spec" / "fixtures" / "v1.1"


# === common helpers（mirror verify_phase7_smoke.py） ====================
def _tmp_work_dir() -> str:
    """mkdtemp(prefix=phase8-smoke-) —— caller finally 块 rmtree。"""
    return tempfile.mkdtemp(prefix="phase8-smoke-")


def _write_synthetic_shots(path: str, count: int = 2) -> None:
    """写合成 shots.json（count 个 1s 镜头，id 从 1 起）。"""
    shots = [
        {"id": i + 1, "start_sec": float(i), "end_sec": float(i + 1),
         "duration": 1.0}
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


def _write_minimal_prompts(path: str, count: int = 2,
                           with_refs: bool = False) -> list:
    """写最小 schema-valid prompts.json（所有 facets 非空，便于测 fill-chip）。

    with_refs=True → shot 1 挂 char_999（dangling，用于 scenario 4）。
    Returns: 写入的 prompts list。
    """
    prompts = []
    for i in range(count):
        sid = i + 1
        entry = {
            "shot_id": sid,
            "start_sec": float(i),
            "end_sec": float(i + 1),
            "duration": 1.0,
            "subject": f"主体{sid}",
            "action": f"动作{sid}",
            "camera": f"中景{sid}",
            "scene": f"场景{sid}",
            "lighting": f"日光{sid}",
            "style": f"风格{sid}",
            "prompt_text": f"旧文本{sid}",
        }
        if with_refs and sid == 1:
            entry["character_refs"] = ["char_999"]
            entry["prop_refs"] = []
        prompts.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    return prompts


# === scenario 1: attach_no_registry (PROMPT-01 graceful-degrade) ========
def scenario_attach_no_registry(verbose: bool = False) -> tuple:
    """无 characters.json/props.json 跑 attach_refs → refs 空 + facets-only 重compose。

    Returns: (ok: bool, detail: str)
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        prompts_path = os.path.join(work_dir, "prompts.json")
        _write_synthetic_shots(shots_json, count=2)
        _write_minimal_prompts(prompts_path, count=2)

        cmd = [
            sys.executable, str(REPO / "prompts" / "attach_refs.py"),
            "--prompts", prompts_path,
            "--work-dir", work_dir,
        ]
        r = _run(cmd, timeout=30)
        if verbose and r.stdout:
            sys.stdout.write(r.stdout)
        if verbose and r.stderr:
            sys.stderr.write(r.stderr)

        # (a) exit 0
        if r.returncode != 0:
            return (False, f"expected exit 0 (graceful-degrade), got "
                          f"{r.returncode}; stderr: {(r.stderr or '').strip()[:300]}")

        # (b) refs 空（每条 prompt）
        out = json.loads(Path(prompts_path).read_text(encoding="utf-8"))
        for entry in out:
            if entry.get("character_refs") != []:
                return (False, f"shot {entry.get('shot_id')}: expected empty "
                               f"character_refs, got {entry.get('character_refs')!r}")
            if entry.get("prop_refs") != []:
                return (False, f"shot {entry.get('shot_id')}: expected empty "
                               f"prop_refs, got {entry.get('prop_refs')!r}")

        # (c) prompt_text 不含 identity 子句（角色 / 道具）
        for entry in out:
            pt = entry.get("prompt_text", "")
            if "角色" in pt or "道具" in pt:
                return (False, f"shot {entry.get('shot_id')}: prompt_text should "
                               f"not contain identity clause (角色/道具); got: {pt!r}")

        # (d) schema-valid（fails loud 逆证明：degrade 仍 emit schema-valid）
        errs = _check_json_valid(out, "prompts.schema.json")
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            return (False, f"prompts.json schema-invalid: /{loc}: {errs[0].message}")

        return (True, f"attach_no_registry OK: {len(out)} shots, refs empty, "
                      f"facets-only prompt_text, schema-valid")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 2: attach_idempotent (PROMPT-01/02 determinism) ===========
def scenario_attach_idempotent(verbose: bool = False) -> tuple:
    """跑 attach_refs.py 两次 → byte-identical + refs 匹配 fixture target。

    Uses spec/fixtures/v1.1/characters.json + props.json as the seed registry.
    """
    fixture_chars = FIXTURES_V11 / "characters.json"
    fixture_props = FIXTURES_V11 / "props.json"
    for p in (fixture_chars, fixture_props):
        if not p.is_file():
            return (False, f"required fixture missing: {p}")

    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        prompts_path = os.path.join(work_dir, "prompts.json")
        _write_synthetic_shots(shots_json, count=2)
        # 用 facets 但无 refs（让 attach 第一次 attach）
        _write_minimal_prompts(prompts_path, count=2)

        # copy fixture registry into work_dir
        shutil.copy(fixture_chars, os.path.join(work_dir, "characters.json"))
        shutil.copy(fixture_props, os.path.join(work_dir, "props.json"))

        cmd = [
            sys.executable, str(REPO / "prompts" / "attach_refs.py"),
            "--prompts", prompts_path,
            "--work-dir", work_dir,
        ]

        # 第一次跑
        r1 = _run(cmd, timeout=30)
        if verbose and r1.stdout:
            sys.stdout.write(r1.stdout)
        if r1.returncode != 0:
            return (False, f"first attach_refs run failed (rc={r1.returncode}); "
                           f"stderr: {(r1.stderr or '').strip()[:300]}")
        out1_text = Path(prompts_path).read_text(encoding="utf-8")
        out1 = json.loads(out1_text)

        # 第二次跑（对第一次的输出再跑一次）
        r2 = _run(cmd, timeout=30)
        if r2.returncode != 0:
            return (False, f"second attach_refs run failed (rc={r2.returncode}); "
                           f"stderr: {(r2.stderr or '').strip()[:300]}")
        out2_text = Path(prompts_path).read_text(encoding="utf-8")
        out2 = json.loads(out2_text)

        # (a) byte-identical（Pitfall 2 idempotency）
        if out1_text != out2_text:
            return (False, f"attach_refs not byte-identical between runs "
                           f"(Pitfall 2 idempotency broken); "
                           f"len1={len(out1_text)} len2={len(out2_text)}")

        # (b) refs 匹配 fixture target —— shot 1 应含 char_001 + char_002
        # （per fixture characters.json: char_001 appearance_shots=[1,2],
        #  char_002 appearance_shots=[1]）
        shot1 = next((e for e in out1 if e.get("shot_id") == 1), None)
        if not shot1:
            return (False, "shot 1 missing from output")
        if shot1.get("character_refs") != ["char_001", "char_002"]:
            return (False, f"shot 1 character_refs mismatch: expected "
                           f"['char_001', 'char_002'], got "
                           f"{shot1.get('character_refs')!r}")

        # (c) shot 2 prop_refs == ["prop_001"]（per fixture props.json:
        #     prop_001 appearance_shots=[2]）
        shot2 = next((e for e in out1 if e.get("shot_id") == 2), None)
        if not shot2:
            return (False, "shot 2 missing from output")
        if shot2.get("prop_refs") != ["prop_001"]:
            return (False, f"shot 2 prop_refs mismatch: expected ['prop_001'], "
                           f"got {shot2.get('prop_refs')!r}")

        # (d) shot 1 prompt_text 含 "角色:[少女, 路人]"（Pattern 2 锁定模板）
        if "角色:[少女, 路人]" not in shot1.get("prompt_text", ""):
            return (False, f"shot 1 prompt_text missing '角色:[少女, 路人]' "
                           f"identity clause; got: {shot1.get('prompt_text')!r}")

        # (e) schema-valid
        errs = _check_json_valid(out1, "prompts.schema.json")
        if errs:
            loc = "/".join(map(str, errs[0].absolute_path)) or "<root>"
            return (False, f"prompts.json schema-invalid: /{loc}: {errs[0].message}")

        return (True, f"attach_idempotent OK: byte-identical ×2 runs, "
                      f"shot 1 refs=[char_001,char_002], shot 2 prop_refs=[prop_001], "
                      f"prompt_text 含 角色:[少女, 路人]")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 3: snapshot_freeze (PROMPT-04 + Pitfall 18) ===============
def scenario_snapshot_freeze(verbose: bool = False) -> tuple:
    """build_asset_dict 写 asset.json，之后 mutate characters.json → snapshot 不变。

    证明 export-time truth 冻结（Pitfall 18）：build_asset_dict 读 live files 生成
    snapshot，但写盘后 characters.json 后续变动不会反向改变 asset.json。
    """
    work_dir = _tmp_work_dir()
    try:
        # build_asset_dict 需要 transcript.json（取 duration）+ shots.json
        shots_json = os.path.join(work_dir, "shots.json")
        transcript_path = os.path.join(work_dir, "transcript.json")
        chars_path = os.path.join(work_dir, "characters.json")
        props_path = os.path.join(work_dir, "props.json")
        prompts_path = os.path.join(work_dir, "prompts.json")
        asset_path = os.path.join(work_dir, "asset.json")

        _write_synthetic_shots(shots_json, count=2)
        Path(transcript_path).write_text(
            json.dumps({"source": "test.mp4", "duration": 2.0,
                        "segments": []}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        # minimal schema-valid registry（confirmed）
        Path(chars_path).write_text(
            json.dumps([{"id": "char_001", "name": "少女",
                         "representative_image": "characters/char_001.png",
                         "appearance_shots": [1, 2],
                         "review_state": "confirmed"}], ensure_ascii=False, indent=2),
            encoding="utf-8")
        Path(props_path).write_text(
            json.dumps([{"id": "prop_001", "name": "落叶",
                         "representative_image": "props/prop_001.png",
                         "appearance_shots": [2],
                         "review_state": "confirmed"}], ensure_ascii=False, indent=2),
            encoding="utf-8")
        _write_minimal_prompts(prompts_path, count=2)
        # frames.json（build_asset_dict 不严格验证 frames 内容，只需文件存在）
        Path(os.path.join(work_dir, "frames.json")).write_text("[]", encoding="utf-8")

        # import build_asset_dict + _build_registry_snapshot directly
        sys.path.insert(0, str(REPO))
        try:
            from scripts.export_asset import build_asset_dict
        finally:
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))

        # (a) build asset1 → snapshot 含 char_001 + prop_001
        asset1 = build_asset_dict(work_dir, "/fake/v.mp4", warnings=None)
        if "registry_snapshot" not in asset1.get("generator", {}):
            return (False, "generator.registry_snapshot missing from asset1")
        snapshot1 = asset1["generator"]["registry_snapshot"]
        char_ids_1 = {c.get("id") for c in snapshot1.get("characters", [])}
        if "char_001" not in char_ids_1:
            return (False, f"snapshot1 missing char_001; got chars {char_ids_1}")

        # (b) 写盘 asset1
        with open(asset_path, "w", encoding="utf-8") as f:
            json.dump(asset1, f, ensure_ascii=False, indent=2)

        # (c) mutate characters.json：rename char_001 + add char_003
        Path(chars_path).write_text(
            json.dumps([
                {"id": "char_001", "name": "renamed_after_export",
                 "representative_image": "characters/char_001.png",
                 "appearance_shots": [1, 2],
                 "review_state": "confirmed"},
                {"id": "char_003", "name": "新角色",
                 "representative_image": "characters/char_003.png",
                 "appearance_shots": [2],
                 "review_state": "confirmed"},
            ], ensure_ascii=False, indent=2),
            encoding="utf-8")

        # (d) 重读 asset.json → snapshot 不变（export-time truth 冻结）
        reread = json.loads(Path(asset_path).read_text(encoding="utf-8"))
        snapshot_reread = reread.get("generator", {}).get("registry_snapshot", {})
        # 比较必须用 dict 相等（非字符串 —— 时间戳等会变；但 snapshot 内容固定）
        if snapshot_reread != snapshot1:
            return (False, f"snapshot changed after registry mutation (Pitfall 18 "
                           f"broken). snapshot1={snapshot1!r}, "
                           f"snapshot_reread={snapshot_reread!r}")

        # (e) 反证：再调 build_asset_dict 会读到 LIVE 文件 → 新 snapshot 含 char_003 +
        #     char_001 renamed。证明 freeze 是 export-time truth，不是 build 函数级缓存。
        asset2 = build_asset_dict(work_dir, "/fake/v.mp4", warnings=None)
        snapshot2 = asset2["generator"]["registry_snapshot"]
        char_names_2 = {c.get("name") for c in snapshot2.get("characters", [])}
        if "renamed_after_export" not in char_names_2:
            return (False, f"asset2 snapshot should reflect LIVE mutation; "
                           f"got names {char_names_2}")

        return (True, f"snapshot_freeze OK: asset.json snapshot unchanged after "
                      f"registry mutation (Pitfall 18); live re-build reflects mutation")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 4: integrity_dangling_ref (PROMPT-03 / Pitfall 17) =======
def scenario_integrity_dangling_ref(verbose: bool = False) -> tuple:
    """seed prompts.json with char_999 dangling ref → _producer_registry_integrity 报错。

    Pitfall 17：prompt refs 必须全部 ⊆ confirmed registry IDs。char_999 不在
    characters.json → 失败信息含 "char_999" + "Pitfall 17"。
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        chars_path = os.path.join(work_dir, "characters.json")
        prompts_path = os.path.join(work_dir, "prompts.json")
        _write_synthetic_shots(shots_json, count=1)

        # confirmed registry without char_999
        Path(chars_path).write_text(
            json.dumps([{"id": "char_001", "name": "少女",
                         "appearance_shots": [1],
                         "review_state": "confirmed"}],
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

        # prompts.json with dangling char_999 on shot 1
        _write_minimal_prompts(prompts_path, count=1, with_refs=True)

        sys.path.insert(0, str(REPO))
        try:
            from scripts.verify_contract import _producer_registry_integrity
        finally:
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))

        failures = _producer_registry_integrity(Path(work_dir))

        # 至少一条 failure 提到 char_999 + Pitfall 17
        matching = [f for f in failures
                    if "char_999" in f and "Pitfall 17" in f]
        if not matching:
            return (False, f"no failure mentions char_999 + Pitfall 17; "
                           f"got {len(failures)} failures: {failures!r}")

        return (True, f"integrity_dangling_ref OK: {len(matching)} failure(s) "
                      f"mention char_999 + Pitfall 17 (PROMPT-03 detected)")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 5: snapshot_confirmed_only (Pitfall 7) ===================
def scenario_snapshot_confirmed_only(verbose: bool = False) -> tuple:
    """seed 1 confirmed + 1 proposed → _build_registry_snapshot 仅 confirmed 入 snapshot。

    Pitfall 7 consistent —— 与 apply_edits build-time gate + _producer_registry_integrity
    second-line assert 对齐：非-confirmed 绝不进 snapshot。
    """
    work_dir = _tmp_work_dir()
    try:
        chars_path = os.path.join(work_dir, "characters.json")
        Path(chars_path).write_text(
            json.dumps([
                {"id": "char_001", "name": "confirmed_char",
                 "representative_image": "characters/char_001.png",
                 "appearance_shots": [1],
                 "review_state": "confirmed"},
                {"id": "char_002", "name": "proposed_char",
                 "representative_image": "characters/char_002.png",
                 "appearance_shots": [2],
                 "review_state": "proposed"},
            ], ensure_ascii=False, indent=2),
            encoding="utf-8")
        # 不写 props.json —— 测 snapshot 只看 characters

        sys.path.insert(0, str(REPO))
        try:
            from scripts.export_asset import _build_registry_snapshot
        finally:
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))

        snapshot = _build_registry_snapshot(work_dir)
        if snapshot is None:
            return (False, "_build_registry_snapshot returned None despite "
                           "characters.json present")
        chars = snapshot.get("characters", [])
        if len(chars) != 1:
            return (False, f"expected 1 confirmed entry in snapshot (Pitfall 7), "
                           f"got {len(chars)}: {chars!r}")
        if chars[0].get("id") != "char_001":
            return (False, f"expected char_001 (confirmed), got {chars[0].get('id')!r}")
        # char_002 (proposed) must NOT appear
        snapshot_ids = {c.get("id") for c in chars}
        if "char_002" in snapshot_ids:
            return (False, f"Pitfall 7 violation: char_002 (proposed) leaked "
                           f"into snapshot; ids={snapshot_ids}")

        return (True, f"snapshot_confirmed_only OK: snapshot has 1 entry (char_001), "
                      f"char_002 proposed filtered (Pitfall 7)")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === scenario 6: html_xss_inert (PRESENT-01/02 + CR-04 carry + CR-01/WR-03) ==
def scenario_html_xss_inert(verbose: bool = False) -> tuple:
    """Multi-sink × multi-payload XSS matrix → 所有 operator-influenced sink inert。

    Phase 8 REVIEW WR-04 fix：原 scenario 6 只测 ONE sink (gallery name) × ONE
    payload (`</script><script>`)，无法检测 CR-01 (title in <title>/<h1>) 或
    WR-03 (video_src attribute breakout) 回归 —— 这些恰好是 Phase 8 review
    发现的真实漏洞。本 broaden 改为 5-sink × 5-payload matrix：

      Sinks (gen_timeline_html 的 operator-influenced HTML 插值点):
        (a) gallery name — body context (CR-04 carry, _esc 已有)
        (b) gallery name — <img onerror> 变体（CR-04 _esc 应中和）
        (c) page <title> — head context (CR-01 fix: _esc(title))
        (d) page <h1>    — body context (CR-01 fix: _esc(title))
        (e) <source src> — attribute context (WR-03 fix: _esc(video_src))

    断言：以下原始「可执行模式」均不出现在生成 HTML：
      "</script><script>"        (a/b)
      "<script>alert"            (a/b/c/d)
      "onerror=alert"            (b/e，raw onerror=)
      "</title><script>"         (c)
      "src=\"x\" onerror"        (e，attribute breakout)
      "</h1><script>"            (d)
    若任一存活，HTML 解析器会把 payload 当新元素/属性执行 —— XSS posture 失守。

    Defence-in-depth：本 matrix 不只验证当前 fix，还把「未来新插值点漏 _esc」
    的回归锁住（任何一个 payload 存活都会 fail）。
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        chars_path = os.path.join(work_dir, "characters.json")
        html_path = os.path.join(work_dir, "timeline.html")

        _write_synthetic_shots(shots_json, count=1)
        # Gallery name payload：JSON-in-script + body context 两道防线（CR-04 carry）。
        # 用 char_001 携带 (a) `</script><script>` 和 char_002 携带 (b) `<img onerror>`，
        # 同时验证 _esc 的 5-char escape (& < > " ') 都生效。
        Path(chars_path).write_text(
            json.dumps([
                {"id": "char_001",
                 "name": "</script><script>alert(1)</script>",
                 "appearance_shots": [1],
                 "review_state": "confirmed"},
                {"id": "char_002",
                 "name": "<img src=x onerror=alert(1)>",
                 "appearance_shots": [1],
                 "review_state": "confirmed"},
            ], ensure_ascii=False, indent=2),
            encoding="utf-8")

        # Title payload (CR-01)：单 payload 同时打 (c) <title> head sink 和 (d) <h1>
        # body sink —— gen_timeline_html 把同一 title 字符串插值进两处，两处都必须
        # 用 safe_title (_esc 后)。payload 含 </title><script> 试图破出 head。
        title_payload = "</title><script>alert('title')</script><h1>"
        # video_src payload (WR-03)：含 " 试图破出 src="..." 双引号属性，注入 onerror。
        video_src_payload = 'x" onerror="alert(1)'

        cmd = [
            sys.executable, str(REPO / "html" / "gen_timeline_html.py"),
            "--shots", shots_json,
            "--characters", chars_path,
            "--title", title_payload,
            "--video-src", video_src_payload,
            "--output", html_path,
        ]
        r = _run(cmd, timeout=30)
        if verbose and r.stdout:
            sys.stdout.write(r.stdout)
        if verbose and r.stderr:
            sys.stderr.write(r.stderr)

        # (a) exit 0
        if r.returncode != 0:
            return (False, f"gen_timeline_html.py failed (rc={r.returncode}); "
                           f"stderr: {(r.stderr or '').strip()[:300]}")

        html = Path(html_path).read_text(encoding="utf-8")

        # (b) Multi-sink XSS matrix assertions —— 任一存活 = XSS posture 失守。
        # 每个 (pattern, reason) 都对应一个 review-fix 的 sink。
        #
        # 注意：不能简单 grep 全文 raw `<script>` —— inline JSON 块内（CHARACTERS const）
        # 经 JSON-in-script 防御 (.replace("</", "<\\/")) 后，`<script>` 单开标签作为 JS
        # string 文本保留，HTML parser 在 <script> element 内不解析子标签，只看
        # `</script>` 序列结束 block。所以「真正可执行」的 raw pattern 是 breakout
        # sequences（能从当前 context 破出，开新 element/attribute）—— 这些才是断言目标。
        forbidden_patterns = [
            # CR-04 carry (JSON-in-script defense)：raw `</script><script>` 出现 →
            # HTML parser 在 inline JSON 见 `</script>` 即结束 script block，后续
            # `<script>` 真成新 element。Defense: .replace("</", "<\\/") 把首 `</`
            # 转成 JS escape `<\/`，HTML parser 视作文本。
            ("</script><script>",        "raw </script><script> survived (JSON-in-script defense failed, CR-04 carry)"),
            # CR-01 fix (title head sink)：`</title><script>` 会从 <title> 破出注入
            # 可执行 head <script>。Defense: _esc(title) → &lt;/title&gt;&lt;script&gt;。
            ("</title><script>",         "raw </title><script> survived (title head sink, CR-01)"),
            # CR-01 fix (h1 body sink)：`</h1><script>` 同理破出注入可执行 body script。
            ("</h1><script>",            "raw </h1><script> survived (h1 body sink, CR-01)"),
            # WR-03 fix (source attribute)：`src="x" onerror` 中 payload 的 `"` 破出
            # 双引号属性，onerror 成新 attribute。Defense: _esc → `&quot;`。
            ('src="x" onerror',          'raw src="x" onerror survived (source attribute sink, WR-03)'),
            ('onerror="alert(1)',        'raw onerror attribute breakout survived (source sink, WR-03)'),
        ]
        for pat, reason in forbidden_patterns:
            if pat in html:
                idx = html.find(pat)
                ctx = html[max(0, idx - 40):idx + len(pat) + 40]
                return (False, f"XSS pattern {pat!r} SURVIVED in HTML ({reason}) "
                               f"at offset {idx}; context: {ctx!r}")

        # (c) HTML 仍含 gallery-card（payload 在 name 中，但 card 应渲染 —— 只是 escaped）
        if "gallery-card" not in html:
            return (False, "gallery-card missing — card not rendered at all")

        # (d) HTML 仍含 char_001 / char_002 ID（name 被 escape 但 ID 应仍在 anchor）
        if "gallery-char_001" not in html:
            return (False, "gallery-char_001 anchor missing")
        if "gallery-char_002" not in html:
            return (False, "gallery-char_002 anchor missing")

        # (e) 反向 sanity：escaped 形式应在 HTML 中（确认 _esc 真的跑了，不只是
        # payload 被某处其他机制剥掉了）。每个 sink 检查对应 escaped 形式：
        #   - gallery name (CR-04 carry, body sink):  `&lt;script&gt;` 由 _esc 产
        #   - gallery name (img onerror, body sink):  `&lt;img src=x onerror=alert(1)&gt;`
        #   - page <title> (CR-01 head sink):         `&lt;/title&gt;&lt;script&gt;`
        #   - <source src> (WR-03 attribute sink):    `x&quot; onerror=&quot;alert(1)`
        if "&lt;script&gt;" not in html:
            return (False, "expected '&lt;script&gt;' escaped form missing — "
                           "_esc may not have run on gallery name (CR-04 carry)")
        if "&lt;img src=x onerror=alert(1)&gt;" not in html:
            return (False, "expected '&lt;img src=x onerror=alert(1)&gt;' escaped form "
                           "missing — _esc may not have run on char_002 gallery name")
        if "&lt;/title&gt;&lt;script&gt;" not in html:
            return (False, "expected '&lt;/title&gt;&lt;script&gt;' escaped form missing — "
                           "_esc may not have run on title (CR-01 regressed?)")
        if 'x&quot; onerror=&quot;alert(1)' not in html:
            return (False, "expected 'x&quot; onerror=&quot;...' escaped form missing — "
                           "_esc may not have run on video_src (WR-03 regressed?)")

        return (True, f"html_xss_inert OK: 5-sink × multi-payload matrix "
                      f"all neutralized (CR-04 carry + CR-01 title + WR-03 video_src), "
                      f"gallery-cards + anchors still render, _esc escaped forms present")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# === CLI ================================================================
def main():
    """Run 6 scenarios in order; collect (name, ok, detail); exit 0/1."""
    ap = argparse.ArgumentParser(
        description="Phase 8 graceful-degrade + 幂等 + snapshot freeze + integrity "
                    "+ confirmed-only + XSS-inert 回归校验 "
                    "(attach_no_registry / attach_idempotent / snapshot_freeze / "
                    "integrity_dangling_ref / snapshot_confirmed_only / html_xss_inert)")
    ap.add_argument("--verbose", action="store_true",
                    help="透传子进程 stdout/stderr（debug 用）")
    args = ap.parse_args()

    scenarios = [
        ("attach_no_registry", scenario_attach_no_registry),
        ("attach_idempotent", scenario_attach_idempotent),
        ("snapshot_freeze", scenario_snapshot_freeze),
        ("integrity_dangling_ref", scenario_integrity_dangling_ref),
        ("snapshot_confirmed_only", scenario_snapshot_confirmed_only),
        ("html_xss_inert", scenario_html_xss_inert),
    ]

    results = []
    for name, fn in scenarios:
        try:
            ok, detail = fn(verbose=args.verbose)
        except Exception as e:
            ok, detail = False, f"unexpected exception: {type(e).__name__}: {e}"
        tag = "[phase8-smoke] PASS" if ok else "[phase8-smoke] FAIL"
        print(f"{tag} {name}: {detail}")
        results.append((name, ok, detail))

    print()
    all_ok = all(ok for _, ok, _ in results)
    if all_ok:
        print(f"[phase8-smoke] OK: {len(results)}/{len(results)} scenarios green")
        sys.exit(0)
    else:
        fails = [n for n, ok, _ in results if not ok]
        print(f"[phase8-smoke] FAIL: {len(fails)}/{len(results)} scenarios failed "
              f"({', '.join(fails)})")
        sys.exit(1)


if __name__ == "__main__":
    main()
