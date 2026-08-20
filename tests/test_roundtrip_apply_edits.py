"""roundtrip apply_edits CLI 测试 —— confirmed-only 回写 + idempotent + schema
拒坏（22-02 Task 1，零网络零 GPU）。

覆盖（七断言组，mirror test_judge.py apply/frozen 用例风格）：
  * schema 合法性三态：空 {} valid（操作员无改动）/ UI-SPEC §5 面板 payload
    形状 valid（accept_overrides/reject_overrides/review_notes）；坏 edits 三态
    invalid（字符串 id / 未知属性 / 负数——Draft202012Validator）。
  * confirmed-only 硬门：坏 edits → SystemExit 非零 + sidecar byte 零改动。
  * auto→human 覆盖（语义反转正测——judge.apply_verdict frozen-skip 的反面）：
    预存 auto verdict 的镜被替换为 {decision, source:"human", decided_at}，
    该镜 regen/scores 半边与未命中镜 byte 级保留。
  * idempotent：同 edits 重放第二遍 sidecar byte 级 no-op diff（已 human 且同
    decision 跳过，decided_at 不漂移；汇总 same_decision_replay 计数）。
  * fail-loud：accept/reject 两清单交集 → SystemExit；未知 shot_id → SystemExit
    且列出未知 id（typo 防护）；sidecar 缺席 → SystemExit。
  * 空 {} edits → no-op 退出 0（sidecar 不重写，mtime 不变）。
  * 审计行 `[roundtrip-apply] shot_NNN auto→human/accepted` + 收尾计数汇总
    `完成：applied=N same_decision_replay=K skipped=M`。
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "roundtrip_apply_edits", REPO_ROOT / "analysis" / "roundtrip" / "apply_edits.py")
am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(am)

EDITS_SCHEMA = REPO_ROOT / "spec" / "schemas" / "roundtrip-edits.schema.json"


# ── fixture ─────────────────────────────────────────────────────────────────

def _shot(sid, decision=None, source="auto", with_verdict=True):
    """合成 roundtrip.json 条目：regen + scores 双半 + 可选 verdict。"""
    e = {
        "shot_id": sid,
        "regen": {
            "path": f"roundtrip/shot_{sid:03d}_regen.mp4",
            "video_content_hash": "a" * 16,
            "engine_name": "comfyui-fl2va",
            "engine_version": "fl2va-int8/euler+simple/15/1344x768",
            "prompt_version": f"pv{sid}",
            "duration_sec": 5.0,
            "width": 1344,
            "height": 768,
        },
        "scores": {
            "midframe_sim": {"score": 0.97, "model": "siglip-so400m-patch14-384"},
            "judge": {"attribution": "prompt_faithful", "confidence": 0.95,
                      "reason": "合成 reason"},
        },
    }
    if with_verdict:
        e["verdict"] = {"decision": decision or "accepted", "source": source,
                        "decided_at": "2026-08-20T00:00:00"}
    return e


def make_work_dir(tmp_path, with_sidecar=True):
    """tmp 合成 work_dir：3 镜（1 accepted·auto / 2 rejected·auto / 3 未裁决）。"""
    wd = tmp_path / "wd"
    wd.mkdir()
    if with_sidecar:
        payload = {"schema_version": am.h3s._load_schema_version(),
                   "shots": [_shot(1, "accepted"), _shot(2, "rejected"),
                             _shot(3, with_verdict=False)]}
        (wd / "roundtrip.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return wd


def write_edits(tmp_path, edits):
    p = tmp_path / "roundtrip-edits.json"
    p.write_text(json.dumps(edits, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def read_sidecar(wd):
    return json.loads((wd / "roundtrip.json").read_text(encoding="utf-8"))


# ── 1. schema 合法性三态 ─────────────────────────────────────────────────────

def test_schema_empty_object_valid():
    with open(EDITS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    assert Draft202012Validator(schema).validate({}) is None


def test_schema_panel_payload_valid():
    """UI-SPEC §5 锁定的面板导出 payload 形状必须 schema-valid。"""
    with open(EDITS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    payload = {"accept_overrides": [7, 12], "reject_overrides": [3],
               "review_notes": "Exported from roundtrip review HTML on 2026-08-20T06:00:00"}
    assert Draft202012Validator(schema).validate(payload) is None


@pytest.mark.parametrize("bad", [
    {"accept_overrides": ["3"]},                 # 字符串 id（path-traversal 面）
    {"accept_overrides": [1], "typo_field": 1},  # 未知属性
    {"reject_overrides": [-2]},                  # 负数（minimum 1 违反）
])
def test_schema_rejects_bad_edits(bad):
    with open(EDITS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)


# ── 2. confirmed-only 硬门：坏 edits → 非零退出 + sidecar 零改动 ─────────────

@pytest.mark.parametrize("bad", [
    {"accept_overrides": ["3"]},
    {"accept_overrides": [1], "typo_field": 1},
    {"reject_overrides": [-2]},
])
def test_bad_edits_exit_nonzero_sidecar_untouched(tmp_path, bad):
    wd = make_work_dir(tmp_path)
    before = (wd / "roundtrip.json").read_bytes()
    with pytest.raises(SystemExit) as ei:
        am.main(["--work-dir", str(wd), "--edits", write_edits(tmp_path, bad)])
    assert ei.value.code != 0
    assert (wd / "roundtrip.json").read_bytes() == before


# ── 3. auto→human 覆盖 + 非 verdict 半边 byte 保留（反转正测）──────────────

def test_auto_to_human_override_preserves_other_halves(tmp_path, capsys):
    wd = make_work_dir(tmp_path)
    edits = {"accept_overrides": [2], "reject_overrides": [1]}
    rc = am.main(["--work-dir", str(wd), "--edits", write_edits(tmp_path, edits)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "shot_002 auto→human/accepted" in out
    assert "shot_001 auto→human/rejected" in out
    data = read_sidecar(wd)
    by_id = {s["shot_id"]: s for s in data["shots"]}
    # verdict 半边替换（auto→human，decision 反转）
    assert by_id[2]["verdict"]["decision"] == "accepted"
    assert by_id[2]["verdict"]["source"] == "human"
    assert by_id[2]["verdict"]["decided_at"]
    assert by_id[1]["verdict"]["source"] == "human"
    assert by_id[1]["verdict"]["decision"] == "rejected"
    # 被 human 覆盖镜的 regen/scores 半边 byte 级保留
    orig = {s["shot_id"]: s for s in json.loads(json.dumps(
        [_shot(1, "accepted"), _shot(2, "rejected"), _shot(3, with_verdict=False)]))}
    for sid in (1, 2):
        assert by_id[sid]["regen"] == orig[sid]["regen"]
        assert by_id[sid]["scores"] == orig[sid]["scores"]
    # 未命中镜整条原样（含无 verdict 的镜 3 保持无 verdict）
    assert by_id[3] == orig[3]


# ── 4. idempotent：重放第二遍 byte 级 no-op diff ─────────────────────────────

def test_replay_is_byte_noop(tmp_path, capsys):
    wd = make_work_dir(tmp_path)
    edits_path = write_edits(tmp_path, {"accept_overrides": [2]})
    am.main(["--work-dir", str(wd), "--edits", edits_path])
    first = (wd / "roundtrip.json").read_bytes()
    mtime_first = os.path.getmtime(wd / "roundtrip.json")
    rc = am.main(["--work-dir", str(wd), "--edits", edits_path])
    assert rc == 0
    second = (wd / "roundtrip.json").read_bytes()
    assert first == second, "重放必须 byte-idempotent（decided_at 不漂移）"
    assert os.path.getmtime(wd / "roundtrip.json") == mtime_first, \
        "全跳过时不得重写 sidecar（真 no-op，连 mtime 都不动）"
    out = capsys.readouterr().out
    assert "已 human 同 decision 跳过" in out
    assert "same_decision_replay=1" in out


# ── 5. fail-loud：交集 / 未知 shot_id / sidecar 缺席 ─────────────────────────

def test_intersection_fail_loud(tmp_path):
    wd = make_work_dir(tmp_path)
    before = (wd / "roundtrip.json").read_bytes()
    with pytest.raises(SystemExit) as ei:
        am.main(["--work-dir", str(wd),
                 "--edits", write_edits(tmp_path, {"accept_overrides": [1],
                                                   "reject_overrides": [1]})])
    assert ei.value.code != 0
    assert (wd / "roundtrip.json").read_bytes() == before


def test_unknown_shot_id_fail_loud(tmp_path, capsys):
    wd = make_work_dir(tmp_path)
    with pytest.raises(SystemExit) as ei:
        am.main(["--work-dir", str(wd),
                 "--edits", write_edits(tmp_path, {"accept_overrides": [1, 999]})])
    # sys.exit(str) 的消息在 SystemExit.code 上（未被解释器捕获时才打 stderr）
    assert "999" in str(ei.value.code), "未知 shot_id 必须列出（typo 防护）"


def test_missing_sidecar_fail_loud(tmp_path):
    wd = make_work_dir(tmp_path, with_sidecar=False)
    with pytest.raises(SystemExit) as ei:
        am.main(["--work-dir", str(wd),
                 "--edits", write_edits(tmp_path, {"accept_overrides": [1]})])
    assert ei.value.code != 0


# ── 6. 空 {} edits no-op 退出 0 ──────────────────────────────────────────────

def test_empty_edits_noop_exit_zero(tmp_path, capsys):
    wd = make_work_dir(tmp_path)
    before = (wd / "roundtrip.json").read_bytes()
    mtime = os.path.getmtime(wd / "roundtrip.json")
    rc = am.main(["--work-dir", str(wd), "--edits", write_edits(tmp_path, {})])
    assert rc == 0
    assert (wd / "roundtrip.json").read_bytes() == before
    assert os.path.getmtime(wd / "roundtrip.json") == mtime
    out = capsys.readouterr().out
    assert "applied=0" in out


# ── 7. 审计行 + 收尾汇总格式 ─────────────────────────────────────────────────

def test_audit_and_summary_format(tmp_path, capsys):
    wd = make_work_dir(tmp_path)
    # shot 3 无 verdict → none→human；shot 2 → auto→human（双向源标记覆盖）
    rc = am.main(["--work-dir", str(wd),
                  "--edits", write_edits(tmp_path, {"reject_overrides": [2, 3]})])
    assert rc == 0
    out = capsys.readouterr().out
    assert "shot_002 auto→human/rejected" in out
    assert "shot_003 none→human/rejected" in out
    assert "完成：applied=2 same_decision_replay=0" in out
    data = read_sidecar(wd)
    by_id = {s["shot_id"]: s for s in data["shots"]}
    assert by_id[3]["verdict"]["source"] == "human"
    assert by_id[3]["verdict"]["decision"] == "rejected"
