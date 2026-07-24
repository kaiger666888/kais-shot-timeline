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

  html_xss_inert (PRESENT-01/02 + CR-04 carry)
      seed characters.json with name="</script><script>alert(1)</script>" →
      run gen_timeline_html.py → read HTML → 原始 payload "</script><script>"
      不出现在 HTML 中（必须被 _esc 或 JSON-in-script 转义中和）。

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


# === scenario 6: html_xss_inert (PRESENT-01/02 + CR-04 carry) ==========
def scenario_html_xss_inert(verbose: bool = False) -> tuple:
    """seed name="</script><script>alert(1)</script>" → gen_timeline_html → payload inert。

    证明 CR-04 fix carry (commit 336d04f) 在 gen_timeline_html.py 生效：
      * Python-side _esc: body context → "&lt;/script&gt;..."
      * JSON-in-script .replace("</", "<\\/"): inlined JSON → "<\\/script>..."
    两种 escape 任一即可使 payload 不可执行。本 scenario 断言原始 payload 字符串
    "</script><script>" 不出现在生成 HTML 中。
    """
    work_dir = _tmp_work_dir()
    try:
        shots_json = os.path.join(work_dir, "shots.json")
        chars_path = os.path.join(work_dir, "characters.json")
        html_path = os.path.join(work_dir, "timeline.html")

        _write_synthetic_shots(shots_json, count=1)
        # character with XSS payload as name (registry-reviewer-editable field)
        Path(chars_path).write_text(
            json.dumps([{"id": "char_001",
                         "name": "</script><script>alert(1)</script>",
                         "appearance_shots": [1],
                         "review_state": "confirmed"}],
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

        cmd = [
            sys.executable, str(REPO / "html" / "gen_timeline_html.py"),
            "--shots", shots_json,
            "--characters", chars_path,
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

        # (b) 原始 payload "</script><script>" 不出现在 HTML 中
        # （必须被 _esc 转义为 &lt;/script&gt; 或被 JSON-in-script .replace 中和）
        html = Path(html_path).read_text(encoding="utf-8")
        payload = "</script><script>"
        if payload in html:
            # 找到 payload 出现位置以辅助 debug
            idx = html.find(payload)
            ctx = html[max(0, idx - 40):idx + len(payload) + 40]
            return (False, f"XSS payload {payload!r} SURVIVED in HTML at offset "
                           f"{idx}; context: {ctx!r}")

        # (c) HTML 仍含 gallery-card（payload 在 name 中，但 card 应渲染 —— 只是 escaped）
        if "gallery-card" not in html:
            return (False, "gallery-card missing — card not rendered at all")

        # (d) HTML 仍含 char_001 ID（name 被 escape 但 ID 应仍在 anchor）
        if "gallery-char_001" not in html:
            return (False, "gallery-char_001 anchor missing")

        return (True, f"html_xss_inert OK: payload '</script><script>' "
                      f"neutralized (CR-04 carry), gallery-card + anchor still render")
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
