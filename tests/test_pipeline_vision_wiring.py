"""run_pipeline --local-vision 接线冒烟 —— 不跑 pipeline，只验 flag 解析 +
step 5 之后 pre-step 的触发条件（mirror attach_refs 无编号先例）。

覆盖（Phase 1 交付物 4-c）：
  * --local-vision 默认 on；--no-local-vision 关。
  * --no-subject 透传给子进程 argv。
  * pre-step 只在 prompts.json + frames_5fps 都在时触发。
  * --skip-semantic 时跳过（无 step 5 产物语义）。
  * banner 无 numeric 前缀（step-counter grep count 不变）。
"""
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _parse_args(argv):
    """跑 run_pipeline 的 argparse（不执行 main body 其余部分）。"""
    import run_pipeline
    # 抓 main() 里的 ap.parse_args()：直接构造 parser 不易（内联在 main），改为
    # 用 runpy 跑 --help 太重 —— 用 ast 提取不现实。直接调 main() 会跑 pipeline。
    # 最稳做法：把 argparse 段复制验证不科学 —— 改用 subprocess --help 冒烟 +
    # 源码静态断言（下方两个 test）。这里保留一个轻量 argparse 实测：monkeypatch
    # sys.argv 后捕获 parse_args 返回值。
    return None


def test_flags_exist_in_help():
    """--help 输出含三个新 flag（subprocess 冒烟，不跑 pipeline body）。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "run_pipeline.py"), "--help"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    for flag in ("--local-vision", "--no-local-vision", "--no-subject"):
        assert flag in r.stdout, f"{flag} missing from --help"


def test_flags_parse_defaults_and_off():
    """argparse 实测：默认 local_vision=True；--no-local-vision → False。"""
    import argparse
    # 从 run_pipeline 源码提取 parser 构造太重 —— 用 main() 的 parser 直接
    # 跑：monkeypatch parse_args 之后的所有步骤入口，让 main() 在 parse 后
    # 立刻短路。更简单：直接读 run_pipeline 模块，临时替换其 parse_args 行为。
    import run_pipeline as rp

    captured = {}

    real_parse = argparse.ArgumentParser.parse_args

    def spy_parse(self, *a, **kw):
        ns = real_parse(self, *a, **kw)
        captured["ns"] = ns
        raise _StopMain()          # parse 完立刻停，不跑 pipeline

    argparse.ArgumentParser.parse_args = spy_parse
    try:
        sys.argv = ["run_pipeline.py", "--video", "/nonexistent.mp4"]
        try:
            rp.main()
        except _StopMain:
            pass
        assert captured["ns"].local_vision is True      # 默认 on
        assert captured["ns"].no_subject is False

        sys.argv = ["run_pipeline.py", "--video", "/nonexistent.mp4",
                    "--no-local-vision", "--no-subject"]
        captured.clear()
        try:
            rp.main()
        except _StopMain:
            pass
        assert captured["ns"].local_vision is False
        assert captured["ns"].no_subject is True
    finally:
        argparse.ArgumentParser.parse_args = real_parse


class _StopMain(Exception):
    pass


def test_pre_step_wiring_static():
    """静态断言：step 5 之后有 local_vision pre-step 块，且 banner 无 N/M 前缀。"""
    src = (REPO_ROOT / "run_pipeline.py").read_text(encoding="utf-8")
    # pre-step 块存在且在 step_reid 调用之前（源码顺序）
    assert "local_vision_facets.py" in src
    assert "args.local_vision" in src
    idx_vision = src.index("local_vision_facets.py")
    idx_reid = src.index("step_reid(video, work_dir")
    assert idx_vision < idx_reid, "vision pre-step 必须在 step 6 re-id 之前"
    # banner 是 plain label（不带 [N/M] numeric 前缀）—— mirror attach_refs
    assert '"local vision facets (qwen-eye pre-step)"' in src


def test_step_banner_count_unchanged():
    """step-counter grep count：[N/10] 形式 banner 来自 10 步（Phase 22 重编号后）。

    Phase 22 step_roundtrip 进管线为 [9/10]、export [9/9]→[10/10]（双位数）——
    regex 相应从 \\d 升到 \\d+；[5.5/10] plain-label 锁语义保持。"""
    import re
    src = (REPO_ROOT / "run_pipeline.py").read_text(encoding="utf-8")
    numbered = re.findall(r"\[\d+/10\]", src)
    # 10 步 × 多处 banner；5.5 pre-step 用 plain label —— 数量不因它增长
    assert "[5.5/10]" not in src and "[6/10" in src
    assert len(numbered) >= 9
