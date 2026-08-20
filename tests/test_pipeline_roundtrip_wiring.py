"""run_pipeline step_roundtrip 接线四件套 —— 不跑 pipeline（全离线零 GPU 零
网络），只验 flag 解析默认值 + 编号 step [9/10] 的静态接线形态（mirror
test_pipeline_vision_seq_wiring.py 四测结构先例）。

覆盖（Phase 22 Plan 22-03 Task 2，PIPE-01 / SC1 代码半边）：
  1. --help 六 flag 在场（--skip-roundtrip / --comfy-url / --sample-shots /
     --regen-resolution / --max-shot-sec / --tau-sim）。
  2. argparse 默认值：tau_sim==0.9670（Phase 21 Kai 裁决锁定值进默认）/
     skip_roundtrip is False / comfy_url=='http://127.0.0.1:8188' /
     sample_shots==0 / regen_resolution=='1344x768' / max_shot_sec==10.0；
     传参后全可覆盖。
  3. 静态 wiring：step_roundtrip 定义+调用都在 step_timeline 与 step_export
     之间；四 subprocess 对象（h3_regen/scorer/judge/gen_roundtrip_review）
     list-form argv 构造在窗口内；judge --apply-verdict + --tau-sim 总是显式；
     scorer 不透传 --device；外层 cache 三条件 + video-stamp 在场；cache 命中
     补生成 review HTML；sidecar 缺席降级跳过 scorer/judge。
  4. Pattern 4 条件挂载锁：step_export inputs 内 roundtrip.json 被
     os.path.exists 守卫（绝不无条件 append）+ dataset post-step check=False
     graceful 锁 + banner 重编号（\\[\\d+/10\\] 形态，/9] 零存活）。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

RT_FLAGS = ("--skip-roundtrip", "--comfy-url", "--sample-shots",
            "--regen-resolution", "--max-shot-sec", "--tau-sim")


class _StopMain(Exception):
    """argparse spy 短路信号 —— parse_args 返回后立刻中断 main()，不跑管线。"""


def _capture_namespace(argv):
    """跑 run_pipeline.main() 的 argparse 段并捕获 namespace（spy + _StopMain
    异常短路 —— 逐字 mirror test_pipeline_vision_seq_wiring.py:20-46）。"""
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
    """--help 输出含六个 roundtrip flag（subprocess 冒烟，不跑 pipeline body）。"""
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "run_pipeline.py"), "--help"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    for flag in RT_FLAGS:
        assert flag in r.stdout, f"{flag} missing from --help"


def test_flags_parse_defaults_and_off():
    """argparse 实测：六默认值锁定（τ_sim=0.9670 Phase 21 Kai 裁决值）+ 全可覆盖。"""
    ns = _capture_namespace(["--video", "/nonexistent.mp4"])
    assert ns.skip_roundtrip is False            # 默认跑复现链
    assert ns.comfy_url == "http://127.0.0.1:8188"
    assert ns.sample_shots == 0                  # 0 = 全量
    assert ns.regen_resolution == "1344x768"
    assert ns.max_shot_sec == 10.0
    assert ns.tau_sim == 0.9670                  # Phase 21 Kai 裁决锁定值

    ns2 = _capture_namespace(
        ["--video", "/nonexistent.mp4",
         "--skip-roundtrip", "--comfy-url", "http://127.0.0.1:1",
         "--sample-shots", "2", "--regen-resolution", "896x512",
         "--max-shot-sec", "6.5", "--tau-sim", "0.93"])
    assert ns2.skip_roundtrip is True
    assert ns2.comfy_url == "http://127.0.0.1:1"
    assert ns2.sample_shots == 2
    assert ns2.regen_resolution == "896x512"
    assert ns2.max_shot_sec == 6.5
    assert ns2.tau_sim == 0.93


def test_step_roundtrip_wiring_static():
    """静态断言：编号 step 源码/调用双序 + 四 subprocess argv 形态 + 外层 cache。"""
    src = (REPO_ROOT / "run_pipeline.py").read_text(encoding="utf-8")
    # 源码序：定义在 step_timeline 与 step_export 之间（timeline 零 roundtrip
    # 引用已证 —— 只 export 改号 9→10）
    idx_tl = src.index("def step_timeline")
    idx_rt = src.index("def step_roundtrip")
    idx_ex = src.index("def step_export")
    assert idx_tl < idx_rt < idx_ex, \
        "step_roundtrip 必须插 step_timeline 与 step_export 定义之间"
    # 调用序：main() 内 roundtrip 调用在 export 调用之前（export 挂载依赖顺序）
    idx_rt_call = src.index("step_roundtrip(work_dir, video, shots, prompts_json")
    idx_ex_call = src.index("step_export(work_dir, video, stems_source_dir")
    assert idx_rt < idx_rt_call < idx_ex_call, \
        "main() 内 step_roundtrip 调用必须在 step_export 调用之前"

    window = src[idx_rt:idx_ex]
    # 四 subprocess 对象齐在场（list-form argv —— T-22-11 injection mitigation）
    for mod in ('"h3_regen.py"', '"scorer.py"', '"judge.py"',
                '"gen_roundtrip_review.py"'):
        assert mod in window, f"{mod} 不在 step_roundtrip 窗口内"
    # judge：--apply-verdict + --tau-sim 总是显式（judge default=None 且 apply
    # 无 τ 时 sys.exit —— pipeline 默认 0.9670 并无条件透传）
    assert '"--apply-verdict"' in window
    assert '"--tau-sim", str(tau_sim)' in window
    # scorer 不透传 --device（cuda:0=3060Ti 零竞争是 scorer 刻意默认；
    # pipeline --device cuda:1=3090 是 Demucs/Whisper 共用，分卡不可混）
    idx_scorer = window.index('"scorer.py"')
    idx_judge = window.index('"judge.py"')
    assert '"--device"' not in window[idx_scorer:idx_judge], \
        "scorer argv 绝不含 --device（分卡设计红线）"
    # skip 短路 + 外层 cache 三条件 + video-stamp（mirror step_reid :290-307）
    assert '"[9/10] --skip-roundtrip' in window
    assert "cached roundtrip sidecar" in window
    assert "_safe_mtime(rt_json) > _safe_mtime(shots_json)" in window
    assert "_safe_mtime(rt_json) > _safe_mtime(prompts_json)" in window
    assert 'rt_json + ".video-stamp"' in window
    assert "_video_identity(video)" in window
    # cache 命中路径仍补生成 review HTML（A2 —— HTML 可能尚未存在）
    cached_seg = window[window.index("cached roundtrip sidecar"):
                        window.index('"h3_regen.py"')]
    assert "_gen_review_html()" in cached_seg, \
        "cache 命中短路前必须补生成 review HTML"
    # sidecar 缺席降级：跳过 scorer/judge/HTML（防无 regen 数据空转模型加载）
    assert "if not os.path.exists(rt_json):" in window
    assert "跳过 scorer/judge/审阅 HTML" in window


def test_step_export_conditional_input_and_dataset_post_step():
    """Pattern 4 条件挂载锁 + dataset post-step graceful 锁（本 phase 最重要修补）。"""
    src = (REPO_ROOT / "run_pipeline.py").read_text(encoding="utf-8")
    # Pattern 4：step_export 函数段内 roundtrip.json 条件性入 inputs —— 存在才
    # append（缺席不入 → byte-identical-absent；绝不无条件 append：_safe_mtime
    # 缺席=+inf 永久 miss，每跑重写 asset.json）
    idx_ex = src.index("def step_export")
    export_seg = src[idx_ex:src.index("\ndef main")]
    assert 'roundtrip_json_path = os.path.join(work_dir, "roundtrip.json")' \
        in export_seg
    assert "if os.path.exists(roundtrip_json_path):\n" \
        "        inputs.append(roundtrip_json_path)" in export_seg, \
        "roundtrip.json 必须被 os.path.exists 守卫后条件 append"
    # dataset post-step：export_dataset.py + 自写 check=False（NOT run_step ——
    # post-step 要求 graceful-degrade，mirror canvas-import :926-953）+ τ 透传
    # + 缺席 warning 形态
    assert '"export_dataset.py"' in src
    idx_ds = src.index('"export_dataset.py"')
    ds_seg = src[idx_ds:idx_ds + 900]
    assert "check=False" in ds_seg
    assert '"--tau-sim", str(args.tau_sim)' in ds_seg
    assert "roundtrip.json 不存在" in src, "缺席 warning 文案锁"
    assert "apply_edits.py" in src, "HITL hint 提及独立 apply CLI"


def test_step_banner_count_renumbered():
    """banner 重编号锁：[N/10] 形态 ≥30 处；/9] 零存活；plain-label 锁延续。"""
    src = (REPO_ROOT / "run_pipeline.py").read_text(encoding="utf-8")
    numbered = re.findall(r"\[\d+/10\]", src)
    # 10 步（1-8 重编号 + roundtrip 9 + export 10）× 多处 banner ≥ 30
    assert len(numbered) >= 30, f"[N/10] banner 仅 {len(numbered)} 处（应 ≥30）"
    # 重编号零存活（单位数字 regex 假定已被 [10/10] 双位数打破 —— Pitfall 1）
    assert not re.findall(r"/9\]", src), "run_pipeline.py 仍有 /9] 存活"
    # 两锚在场（e2e/harness grep 锚）
    assert "[9/10] roundtrip" in src
    assert "[10/10] ShotTimelineAsset export" in src
    # plain-label 锁语义延续（5.5/5.6 pre-step 绝不带数字前缀）
    assert "[5.5/10]" not in src and "[6/10" in src
    assert "[5.6/10]" not in src, "5.6 pre-step banner 绝不带数字前缀（grep 锁）"
