"""run_pipeline --vision-seq 接线四件套 —— 不跑 pipeline，只验 flag 解析 +
5.5 之后 pre-step 5.6 的静态接线形态（mirror 5.5 的 vision wiring 测试先例）。

覆盖（Phase 19 Plan 19-03 Task 2，全部离线零 GPU 零网络）：
  * --vision-seq 默认 on；--no-vision-seq 关。
  * --no-ear 默认 False、传入后 True（ear 直通子进程 argv）。
  * 5.6 块在 5.5（local_vision）之后、step_reid 调用之前（源码顺序）。
  * --audio-semantic 引用 step 7 产物路径变量（ear 直通，存在性模块自判）。
  * banner 无 numeric 前缀（step-counter grep count 不变 —— [5.6/9] 锁）。
"""
import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


class _StopMain(Exception):
    """argparse spy 短路信号 —— parse_args 返回后立刻中断 main()，不跑管线。"""


def _capture_namespace(argv):
    """跑 run_pipeline.main() 的 argparse 段并捕获 namespace（spy + _StopMain
    异常短路 —— mirror test_pipeline_vision_wiring.py 同款技巧）。"""
    import run_pipeline as rp

    captured = {}
    real_parse = argparse.ArgumentParser.parse_args

    def spy_parse(self, *a, **kw):
        ns = real_parse(self, *a, **kw)
        captured["ns"] = ns
        raise _StopMain()          # parse 完立刻停，不跑 pipeline body

    argparse.ArgumentParser.parse_args = spy_parse
    try:
        sys.argv = ["run_pipeline.py"] + argv
        try:
            rp.main()
        except _StopMain:
            pass
        return captured["ns"]
    finally:
        argparse.ArgumentParser.parse_args = real_parse


def test_flags_exist_in_help():
    """--help 输出含三个新 flag（subprocess 冒烟，不跑 pipeline body）。"""
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "run_pipeline.py"), "--help"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    for flag in ("--vision-seq", "--no-vision-seq", "--no-ear"):
        assert flag in r.stdout, f"{flag} missing from --help"


def test_flags_parse_defaults_and_off():
    """argparse 实测：默认 vision_seq=True、no_ear=False；
    --no-vision-seq → False；--no-ear → True。"""
    ns = _capture_namespace(["--video", "/nonexistent.mp4"])
    assert ns.vision_seq is True          # 默认 on
    assert ns.no_ear is False             # ear 默认开（audio_semantic 在位时）

    ns2 = _capture_namespace(["--video", "/nonexistent.mp4",
                              "--no-vision-seq", "--no-ear"])
    assert ns2.vision_seq is False
    assert ns2.no_ear is True


def test_pre_step_wiring_static():
    """静态断言：5.6 块在 5.5（local_vision）之后、step_reid 之前；
    --audio-semantic 在 vision_seq 子进程调用构造内；banner 是 plain label。"""
    src = (REPO_ROOT / "run_pipeline.py").read_text(encoding="utf-8")
    # 源码顺序三连：5.5 → 5.6 → step 6（re-id）
    idx_lv = src.index("local_vision_facets.py")
    idx_vseq = src.index("vision_seq_facets.py")
    idx_reid = src.index("step_reid(video, work_dir")
    assert idx_lv < idx_vseq, "vision-seq pre-step 必须在 5.5 local_vision 之后"
    assert idx_vseq < idx_reid, "vision-seq pre-step 必须在 step 6 re-id 之前"
    # 触发条件引用 args.vision_seq（--no-vision-seq 可跳过整段）
    assert "args.vision_seq" in src
    # ear 直通：--audio-semantic 参数出现在 5.6 块的 cmd 构造内（vseq 与 reid 之间）
    idx_asem = src.index('"--audio-semantic", audio_semantic_json',
                         idx_vseq)
    assert idx_vseq < idx_asem < idx_reid, \
        "--audio-semantic 必须在 vision_seq 调用构造内（引用 step 7 产物路径变量）"
    # WR-02（19-REVIEW）：--sample-fps 直通子模块 --frame-fps（时窗→帧号换算
    # 与实际抽帧率一致），同样必须在 5.6 调用构造内。
    idx_ffps = src.index('"--frame-fps", str(args.sample_fps)', idx_vseq)
    assert idx_vseq < idx_ffps < idx_reid, \
        "--frame-fps 直通必须在 vision_seq 调用构造内"
    # banner 是 plain label（不带 [N/M] numeric 前缀）—— mirror 5.5 / attach_refs
    assert '"vision seq facets (qwen-eye v2 pre-step)"' in src


def test_step_banner_count_unchanged():
    """step-counter grep count 不变：[N/9] 形式的 banner 仍只来自原 9 步。
    v1 文件的两条既有断言形态全部保留（[5.5/9] 锁继续在位），并加 [5.6/9] 锁。"""
    import re
    src = (REPO_ROOT / "run_pipeline.py").read_text(encoding="utf-8")
    numbered = re.findall(r"\[\d/9\]", src)
    # 原 9 步 × 多处 banner；5.5/5.6 两个 pre-step 都用 plain label —— 数量不因它们增长
    assert "[5.5/9]" not in src and "[6/9" in src
    assert "[5.6/9]" not in src, "5.6 pre-step banner 绝不带数字前缀（grep 锁）"
    assert len(numbered) >= 9
