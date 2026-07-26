#!/usr/bin/env python3
"""Phase 15 Layered-Reproduction-Prompts 4-scenario smoke 回归校验（standalone）。

本 harness 锁 Phase 15 SC#1-6 verifiable 路径（重点 SC#6 byte-identical
determinism）。沿用 scripts/verify_phase_audio_smoke.py 风格：bracketed
prefix tags + sys.exit(0/1) 退出码契约 + 仅 stdlib + 已在 env 的 jsonschema。
不依赖 output/ 真实产物（synthetic fixtures inline）。

4 scenarios（每个独立 temp work_dir，互不污染）：

  baseline_compose (PROMPT-01 + SC#1)
      从 skeleton-only audio_semantic.json（无 reproduction key）+ 可选
      audio_analysis.json side input 出发，invoke recompose_audio_semantic。
      断言：(a) 每 shot 有 reproduction.{tts,music_gen,foley} keys（值可 null
      或 repro_prompt）；(b) 输出 schema-valid（audio_semantic.schema.json）；
      (c) 非 reproduction 字段（schema_version / word_level_experimental /
      shots[i].{shot_id,start_sec,end_sec,duration,dialogue,sfx}）verbatim 保留
      （T-15-07 mitigation）；(d) 每 non-null layer 含 SPEC §10 locked
      fidelity_disclaimer literal ("AF-01 mitigation" 后缀)。

  byte_identical (SC#6 load-bearing)
      同一 input audio_semantic.json 两次 invoke recompose_audio_semantic →
      两个 output 的 json.dumps(sort_keys=True, ensure_ascii=False) 相等。
      SC#6 LOCKED proof —— 非 deterministic 即违反合约。

  idempotent (SC#1 + composed-fixed-point)
      先 invoke recompose 一次得到 composed payload，再 invoke 第二次（输入
      是已 composed 的输出）→ 第二次输出与第一次 byte-identical。证明
      composed reproduction 是其自身的 fixed-point（不会因重复 apply 漂移）。

  conditional_gate_proof (CONDITIONAL gating 全集)
      4 个 synthetic shots 覆盖：
        Shot A dialogue-only（dialogue.text + emotion + Speech event；无 sfx）
          → tts non-null；music_gen null（无 BGM 信号，无 tempo）；foley null
        Shot B BGM-only（dialogue.events=[BGM] 无 text）
          → tts null（无 text）；music_gen non-null；foley null
        Shot C sfx-only（sfx.events=[Laughter]+description；无 dialogue）
          → tts null；music_gen null；foley non-null
        Shot D empty（仅 shot_id + timing）
          → tts/music_gen/foley 全 null（skeleton-only shot schema-valid）
      全集断言：NO shot 任何字段含乐器名词（case-insensitive grep on full
      output JSON）；NO shot 任何字段含 AF-01 forbidden phrases。

末尾两个 global audits：
  AF-01 grep gate     —— grep -rE '<绝对化复现措辞 forbidden phrases ——
                          SPEC §10.1 enumerated set>' audio/ spec/SPEC.md
                          spec/README.md scripts/ analysis/ 必须 0 matches
                          （exit 1 from grep）。forbidden phrases 在 _af01_grep_gate
                          内 fragment-concat 运行时拼装（避免 harness 自身源码
                          self-match）。
  MUS-04 instruments  —— grep -riE '\binstruments\b|instrument_labels|
                          instruments_detected' audio/ analysis/ spec/schemas/
                          audio_semantic.schema.json spec/fixtures/v1.2/
                          audio_semantic.json 必须 0 matches

退出码：
    0 = 4 scenarios + 2 audits 全绿（"[phase15-smoke] OK: 4/4 + AF-01 + MUS-04"）
    1 = 任一 fail

用法：
    python3 scripts/verify_phase15_repro_smoke.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_SEMANTIC_SCHEMA = REPO_ROOT / "spec" / "schemas" / "audio_semantic.schema.json"


# ============================================================================
# Helpers
# ============================================================================

def _load_composer():
    """Lazy-load audio/gen_audio_prompts.py via importlib.

    Mirror analysis/call_audio_analysis.py:540-558 lazy-import pattern.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_gap_phase15", REPO_ROOT / "audio" / "gen_audio_prompts.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _validate_schema(payload):
    """Schema-validate payload against audio_semantic.schema.json. Raises on fail."""
    import jsonschema
    from jsonschema import Draft202012Validator
    with open(AUDIO_SEMANTIC_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator(schema).validate(payload)


def _af01_grep_gate() -> bool:
    """AF-01 grep gate. Returns True if CLEAN (0 matches).

    Forbidden phrases are assembled from fragments at runtime so the literal
    pattern never appears in this file's source (otherwise this harness's own
    grep would self-match). SPEC §10.1 calls this class 绝对化复现措辞.
    """
    # Assemble at runtime —— source contains no literal forbidden phrase.
    parts = [
        "perfectly" + " reconstruct",
        "exact" + " restoration",
        "完美" + "复刻",
        "精确" + "复原",
    ]
    pattern = "|".join(parts)
    r = subprocess.run(
        ["grep", "-rE", pattern,
         "audio/", "spec/SPEC.md", "spec/README.md", "scripts/", "analysis/"],
        capture_output=True, text=True, cwd=str(REPO_ROOT))
    # grep exit 1 = no matches = CLEAN; exit 0 = matches = FAIL
    return r.returncode != 0


def _mus04_audit() -> bool:
    """MUS-04 instruments audit. Returns True if CLEAN (0 matches)."""
    r = subprocess.run(
        ["grep", "-riE",
         r"\binstruments\b|instrument_labels|instruments_detected",
         "audio/", "analysis/",
         "spec/schemas/audio_semantic.schema.json",
         "spec/fixtures/v1.2/audio_semantic.json"],
        capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.returncode != 0


# ============================================================================
# Synthetic fixtures
# ============================================================================

def _skeleton_payload() -> dict:
    """audio_semantic.json with 2 skeleton-only shots (no reproduction key)."""
    return {
        "schema_version": "1.2",
        "word_level_experimental": False,
        "shots": [
            {
                "shot_id": 1, "start_sec": 0.0, "end_sec": 1.5, "duration": 1.5,
                "dialogue": {
                    "text": "你好世界",
                    "spk_id": "spk_001",
                    "emotion": "HAPPY",
                    "emotion_confidence": 0.9,
                    "events": ["Speech"],
                },
                "sfx": {
                    "events": ["Laughter"],
                    "description": "观众轻笑声",
                },
            },
            {
                "shot_id": 2, "start_sec": 1.5, "end_sec": 3.0, "duration": 1.5,
                "dialogue": {
                    "text": "测试一句",
                    "spk_id": "spk_002",
                    "emotion": "emo_unk",
                    "emotion_confidence": 1.0,
                    "events": [],
                },
            },
        ],
    }


def _conditional_gates_payload() -> dict:
    """4 synthetic shots covering dialogue-only / BGM-only / sfx-only / empty."""
    return {
        "schema_version": "1.2",
        "word_level_experimental": False,
        "shots": [
            # Shot A: dialogue-only (Speech event, no BGM)
            {
                "shot_id": 10, "start_sec": 0.0, "end_sec": 1.0, "duration": 1.0,
                "dialogue": {
                    "text": "纯对白",
                    "emotion": "NEUTRAL",
                    "emotion_confidence": 0.8,
                    "events": ["Speech"],
                },
            },
            # Shot B: BGM-only (no dialogue.text, BGM in events)
            {
                "shot_id": 11, "start_sec": 1.0, "end_sec": 2.0, "duration": 1.0,
                "dialogue": {
                    "events": ["BGM"],
                },
            },
            # Shot C: sfx-only (Laughter + description, no dialogue)
            {
                "shot_id": 12, "start_sec": 2.0, "end_sec": 3.0, "duration": 1.0,
                "sfx": {
                    "events": ["Laughter"],
                    "description": "持续 1 秒的笑声",
                },
            },
            # Shot D: empty (skeleton only)
            {
                "shot_id": 13, "start_sec": 3.0, "end_sec": 4.0, "duration": 1.0,
            },
        ],
    }


# ============================================================================
# Scenarios
# ============================================================================

def scenario_baseline_compose():
    """SC#1 + PROMPT-01/02: from skeleton → recompose → schema-valid + preserved."""
    m = _load_composer()
    work_dir = tempfile.mkdtemp(prefix="phase15-baseline-")
    try:
        in_path = os.path.join(work_dir, "audio_semantic.json")
        skeleton = _skeleton_payload()
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=2)

        # Snapshot non-reproduction fields for preservation check
        original_sv = skeleton["schema_version"]
        original_wle = skeleton["word_level_experimental"]
        original_shot1_dlg_text = skeleton["shots"][0]["dialogue"]["text"]
        original_shot2_dlg_text = skeleton["shots"][1]["dialogue"]["text"]

        m.recompose_audio_semantic(in_path)

        with open(in_path, encoding="utf-8") as f:
            out = json.load(f)

        # (a) every shot has reproduction.{tts,music_gen,foley} keys
        for shot in out["shots"]:
            assert "reproduction" in shot, f"shot {shot.get('shot_id')} missing reproduction"
            repro = shot["reproduction"]
            for key in ("tts", "music_gen", "foley"):
                assert key in repro, f"shot {shot.get('shot_id')} missing reproduction.{key}"

        # (b) schema-valid
        _validate_schema(out)

        # (c) non-reproduction fields preserved verbatim (T-15-07)
        assert out["schema_version"] == original_sv
        assert out["word_level_experimental"] == original_wle
        assert out["shots"][0]["dialogue"]["text"] == original_shot1_dlg_text
        assert out["shots"][1]["dialogue"]["text"] == original_shot2_dlg_text

        # (d) every non-null layer has SPEC §10 fidelity_disclaimer literal
        for shot in out["shots"]:
            for layer_name in ("tts", "music_gen", "foley"):
                layer = shot["reproduction"][layer_name]
                if layer is not None:
                    assert "fidelity_disclaimer" in layer, \
                        f"shot {shot['shot_id']} {layer_name} missing fidelity_disclaimer"
                    assert "AF-01 mitigation" in layer["fidelity_disclaimer"], \
                        f"shot {shot['shot_id']} {layer_name} disclaimer missing AF-01 literal"
                    assert "text" in layer and layer["text"], \
                        f"shot {shot['shot_id']} {layer_name} text empty"
                    assert "confidence" in layer and 0 <= layer["confidence"] <= 1, \
                        f"shot {shot['shot_id']} {layer_name} confidence out of range"
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def scenario_byte_identical():
    """SC#6 load-bearing: two recompose runs produce byte-identical output."""
    m = _load_composer()
    work_dir = tempfile.mkdtemp(prefix="phase15-byte-ident-")
    try:
        path_a = os.path.join(work_dir, "a", "audio_semantic.json")
        path_b = os.path.join(work_dir, "b", "audio_semantic.json")
        os.makedirs(os.path.dirname(path_a))
        os.makedirs(os.path.dirname(path_b))
        # Same input both places
        skeleton = _skeleton_payload()
        for p in (path_a, path_b):
            with open(p, "w", encoding="utf-8") as f:
                json.dump(skeleton, f, ensure_ascii=False, indent=2)

        m.recompose_audio_semantic(path_a)
        m.recompose_audio_semantic(path_b)

        with open(path_a, encoding="utf-8") as f:
            out_a = f.read()
        with open(path_b, encoding="utf-8") as f:
            out_b = f.read()

        # SC#6 byte-identical proof (raw file bytes —— includes key order + indent)
        assert out_a == out_b, (
            "SC#6 FAIL: two recompose runs produced different output bytes; "
            f"len(a)={len(out_a)}, len(b)={len(out_b)}")

        # Stronger: file bytes must also equal re-recompose of same file (idempotent
        # fixed-point —— verified in scenario_idempotent)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def scenario_idempotent():
    """Idempotent fixed-point: re-recompose on composed output is byte-identical."""
    m = _load_composer()
    work_dir = tempfile.mkdtemp(prefix="phase15-idempotent-")
    try:
        path = os.path.join(work_dir, "audio_semantic.json")
        skeleton = _skeleton_payload()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=2)

        m.recompose_audio_semantic(path)
        with open(path, encoding="utf-8") as f:
            first_pass = f.read()

        # Second pass: input is now already composed
        m.recompose_audio_semantic(path)
        with open(path, encoding="utf-8") as f:
            second_pass = f.read()

        assert first_pass == second_pass, (
            "Idempotent FAIL: second recompose on composed output drifted; "
            f"len(first)={len(first_pass)}, len(second)={len(second_pass)}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def scenario_conditional_gate_proof():
    """CONDITIONAL gating全集: 4 synthetic shots cover all null/non-null patterns."""
    m = _load_composer()
    work_dir = tempfile.mkdtemp(prefix="phase15-cond-gate-")
    try:
        path = os.path.join(work_dir, "audio_semantic.json")
        payload = _conditional_gates_payload()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        m.recompose_audio_semantic(path)
        with open(path, encoding="utf-8") as f:
            out = json.load(f)

        # Schema-valid
        _validate_schema(out)

        shots_by_id = {s["shot_id"]: s for s in out["shots"]}

        # Shot A: dialogue-only → tts non-null, music_gen null (no BGM), foley null
        a = shots_by_id[10]
        assert a["reproduction"]["tts"] is not None, "Shot A tts should be non-null"
        assert a["reproduction"]["music_gen"] is None, (
            f"Shot A music_gen should be null (no BGM/tempo); "
            f"got {a['reproduction']['music_gen']}")
        assert a["reproduction"]["foley"] is None, "Shot A foley should be null"

        # Shot B: BGM-only → tts null (no text), music_gen non-null, foley null
        b = shots_by_id[11]
        assert b["reproduction"]["tts"] is None, "Shot B tts should be null (no text)"
        assert b["reproduction"]["music_gen"] is not None, (
            "Shot B music_gen should be non-null (BGM present)")
        assert b["reproduction"]["foley"] is None, "Shot B foley should be null"

        # Shot C: sfx-only → tts null, music_gen null, foley non-null
        c = shots_by_id[12]
        assert c["reproduction"]["tts"] is None, "Shot C tts should be null"
        assert c["reproduction"]["music_gen"] is None, "Shot C music_gen should be null"
        assert c["reproduction"]["foley"] is not None, (
            "Shot C foley should be non-null (events + description)")

        # Shot D: empty → all three null (skeleton-only schema-valid)
        d = shots_by_id[13]
        assert d["reproduction"]["tts"] is None, "Shot D tts should be null"
        assert d["reproduction"]["music_gen"] is None, "Shot D music_gen should be null"
        assert d["reproduction"]["foley"] is None, "Shot D foley should be null"

        # MUS-04 audit on output: no instrument-related field anywhere
        out_str = json.dumps(out, ensure_ascii=False).lower()
        for forbidden in ("instruments", "instrument_labels", "instruments_detected"):
            assert forbidden.lower() not in out_str, \
                f"MUS-04 leakage: output contains '{forbidden}'"

        # AF-01 audit on output: no SPEC §10.1 forbidden phrases in any string
        # value (fragment-concat to avoid self-match in harness source).
        forbidden_phrases = [
            "perfectly" + " reconstruct",
            "exact" + " restoration",
            "完美" + "复刻",
            "精确" + "复原",
        ]
        for phrase in forbidden_phrases:
            assert phrase not in out_str, \
                f"AF-01 leakage: output contains forbidden phrase"
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ============================================================================
# Main
# ============================================================================

def main():
    print("[phase15-smoke] === Phase 15 Reproduction Prompts Smoke ===")
    scenarios = [
        ("baseline-compose",    scenario_baseline_compose),
        ("byte-identical-SC6",  scenario_byte_identical),
        ("idempotent-fixed-pt", scenario_idempotent),
        ("conditional-gate",    scenario_conditional_gate_proof),
    ]
    results = []
    for name, fn in scenarios:
        print(f"[phase15-smoke] --- Scenario: {name} ---")
        try:
            fn()
            print(f"[phase15-smoke] [{name}] PASS")
            results.append(True)
        except AssertionError as e:
            print(f"[phase15-smoke] [{name}] FAIL: {e}")
            results.append(False)
        except Exception as e:
            print(f"[phase15-smoke] [{name}] ERROR: {type(e).__name__}: {e}")
            results.append(False)

    print(f"[phase15-smoke] --- AF-01 grep gate (load-bearing) ---")
    af01_ok = _af01_grep_gate()
    print(f"[phase15-smoke] AF-01 {'CLEAN' if af01_ok else 'FAIL'}")

    print(f"[phase15-smoke] --- MUS-04 instruments audit (load-bearing) ---")
    mus04_ok = _mus04_audit()
    print(f"[phase15-smoke] MUS-04 {'CLEAN' if mus04_ok else 'FAIL'}")

    all_ok = all(results) and af01_ok and mus04_ok
    passed = sum(1 for r in results if r)
    print(f"[phase15-smoke] === Result: {passed}/{len(results)} scenarios + "
          f"AF-01 {'✓' if af01_ok else '✗'} + MUS-04 {'✓' if mus04_ok else '✗'}"
          f" = {'ALL_SCENARIOS_PASS' if all_ok else 'FAIL'} ===")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
