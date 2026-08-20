"""attach_refs 幂等写回归锁（Phase 22 / 22-04 Rule 3）。

背景：attach_refs 在 step_timeline 内无条件重写 prompts.json，而 prompts.json
是 step_roundtrip 外层 cache（roundtrip.json > prompts.json mtime）与
step_export mtime cache 的 input —— 无条件重写让两个 cache 每次跑都 miss。
修复 = 输出与输入等值时跳过原子写（mirror vision_seq_facets changed-guard）。

覆盖：
  1. 首跑（prompt_text 非 recompose 态）→ 正常写出。
  2. 二跑（已是 recompose 态、refs 已挂）→ 零条目变化 → 不重写（字节 + mtime
     双不变）。
  3. registry 变化（characters.json 出现 confirmed 条目）→ 输出真变 → 重写。
"""
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "attach_refs", REPO_ROOT / "prompts" / "attach_refs.py")
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)


def make_workdir(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    prompts = [{
        "shot_id": 1, "start_sec": 0.0, "end_sec": 1.0, "duration": 1.0,
        "subject": "毛毛虫小孩", "action": "奔跑", "camera": "跟随",
        "scene": "森林", "lighting": "白昼", "style": "三维动画",
        "prompt_text": "placeholder（非 recompose 态）",
        "character_refs": [], "prop_refs": [],
    }]
    pp = work / "prompts.json"
    pp.write_text(json.dumps(prompts, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    return work, pp


def run_main(work, pp):
    argv = ["attach_refs.py", "--prompts", str(pp), "--work-dir", str(work)]
    old_argv = sys.argv
    sys.argv = argv
    try:
        ar.main()
    finally:
        sys.argv = old_argv


def test_first_run_writes_and_second_run_skips_rewrite(tmp_path):
    work, pp = make_workdir(tmp_path)
    run_main(work, pp)
    first = json.loads(pp.read_text(encoding="utf-8"))
    assert "placeholder" not in first[0]["prompt_text"]   # 首跑已 recompose

    before_bytes = pp.read_bytes()
    before_mtime = pp.stat().st_mtime_ns
    run_main(work, pp)
    assert pp.read_bytes() == before_bytes            # 二跑零变化 → 字节不变
    assert pp.stat().st_mtime_ns == before_mtime      # 且根本没重写（mtime 不动）


def test_real_change_still_rewrites(tmp_path):
    work, pp = make_workdir(tmp_path)
    run_main(work, pp)
    before_mtime = pp.stat().st_mtime_ns
    # registry 出现 confirmed + appearance_shots=[1] 条目 → refs 挂载 →
    # prompt_text 真变 → 必须重写（schema: id^char_[0-9]{3}$ + review_state 枚举）
    (work / "characters.json").write_text(json.dumps([{
        "id": "char_001", "name": "毛毛",
        "review_state": "confirmed", "appearance_shots": [1],
    }], ensure_ascii=False), encoding="utf-8")
    run_main(work, pp)
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["character_refs"] == ["char_001"]
    assert "毛毛" in out[0]["prompt_text"]
    assert pp.stat().st_mtime_ns != before_mtime     # 真变化 → 重写发生
