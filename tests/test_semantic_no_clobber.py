"""call_shot_analysis 防破坏性覆盖守卫测试 —— offline 全 degrade 场景。

覆盖（ep02 2026-08-19 事故回归）：
  * route 全 degrade + 既有富 prompts.json → 文件字节不变、exit 0、
    warning 落 warnings sidecar。
  * route 全 degrade + 既有空壳 prompts.json → 照常覆盖（守卫不拦空数据）。
  * route 全 degrade + 无既有文件 → 照常写出空壳（原行为）。
全部用 --offline 触发 route_down，零网络、零 monkeypatch。
"""
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "call_shot_analysis", REPO_ROOT / "analysis" / "call_shot_analysis.py")
csa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csa)


def make_workdir(tmp_path, prompts_shots=None):
    """搭最小 work_dir：shots.json（2 镜）+ 可选 prompts.json + 假 video。"""
    work = tmp_path / "work"
    work.mkdir()
    shots = [{"id": i + 1, "start_sec": float(i), "end_sec": float(i + 1),
              "duration": 1.0} for i in range(2)]
    (work / "shots.json").write_text(
        json.dumps(shots, ensure_ascii=False), encoding="utf-8")
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * (3 * 1024 * 1024))   # >2MB → hash 走首尾 1MB
    if prompts_shots is not None:
        (work / "prompts.json").write_text(
            json.dumps(prompts_shots, ensure_ascii=False, indent=2),
            encoding="utf-8")
    return work, shots, video


def run_offline(tmp_path, work, video, monkeypatch):
    """以 --offline 跑 main()（route_down=True，无 route_cache → 全 miss）。"""
    out = work / "prompts.json"
    monkeypatch.setattr(sys, "argv", [
        "call_shot_analysis.py", "--video", str(video),
        "--shots", str(work / "shots.json"), "--work-dir", str(work),
        "--output", str(out), "--offline"])
    rc = csa.main()
    return rc, out


def rich_prompts(shots):
    return [{"shot_id": s["id"], "start_sec": s["start_sec"],
             "end_sec": s["end_sec"], "duration": s["duration"],
             "subject": "独角仙武士:红棕色甲壳", "action": "亮出短刀",
             "camera": "中景推近", "scene": "原始森林", "lighting": "散射光",
             "style": "3D 动画", "prompt_text": "3D 动画，原始森林…"}
            for s in shots]


def empty_prompts(shots):
    return [{"shot_id": s["id"], "start_sec": s["start_sec"],
             "end_sec": s["end_sec"], "duration": s["duration"],
             "subject": "", "action": "", "camera": "", "scene": "",
             "lighting": "", "style": "", "prompt_text": ""}
            for s in shots]


def test_degrade_preserves_rich_prompts(tmp_path, monkeypatch, capsys):
    work, shots, video = make_workdir(tmp_path)
    (work / "prompts.json").write_text(
        json.dumps(rich_prompts(shots), ensure_ascii=False, indent=2),
        encoding="utf-8")
    before = (work / "prompts.json").read_text(encoding="utf-8")

    rc, out = run_offline(tmp_path, work, video, monkeypatch)

    assert rc == 0
    assert out.read_text(encoding="utf-8") == before      # 字节不变
    stdout = capsys.readouterr().out
    assert "[semantic] warning" in stdout and "跳过覆盖" in stdout
    sidecar = json.loads(
        (work / "route_cache" / "warnings.json").read_text(encoding="utf-8"))
    assert any("overwrite SKIPPED" in w for w in sidecar["warnings"])


def test_degrade_overwrites_empty_shell(tmp_path, monkeypatch):
    work, shots, video = make_workdir(tmp_path)
    (work / "prompts.json").write_text(
        json.dumps(empty_prompts(shots), ensure_ascii=False, indent=2),
        encoding="utf-8")

    rc, out = run_offline(tmp_path, work, video, monkeypatch)

    assert rc == 0
    after = json.loads(out.read_text(encoding="utf-8"))
    assert len(after) == 2 and after[0]["subject"] == ""   # 照常写出空壳


def test_degrade_writes_when_absent(tmp_path, monkeypatch):
    work, shots, video = make_workdir(tmp_path)            # 无既有 prompts.json

    rc, out = run_offline(tmp_path, work, video, monkeypatch)

    assert rc == 0
    assert out.exists()                                    # 原行为：写出
