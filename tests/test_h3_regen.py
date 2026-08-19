"""h3_regen 测试 —— FakeComfyUI + subprocess fake，零网络零 GPU。

覆盖（20-01 Task 3 行为清单）：
  * workflow 注入：真实模板 deepcopy 注入五组节点；模板磁盘文件不被改动。
  * length 网格：{0.5:124, 5.5:141, 6.73:175, 19.7:362} + 全域网格不变式。
  * seed 确定性：跨调用稳定、异镜/异 vch 不同、值域 < 2**31。
  * 帧提取：ffmpeg argv 无 -vf 无 scale、list-form、dest 在
    route_cache/h3_regen/frames/、尾帧 -ss 前移。
  * 上传：curl -F image=@ + overwrite=true、返回 stdout name。
  * 提交/轮询/下载全链路：FakeHTTP /prompt→/history(success, images 键)→
    _view_download 替身写字节；mp4 落盘 + cache 写入 + prompt_id 进 cache。
  * error 分支 / 超时分支：status=error 或轮询超时 → 单镜失败、批不崩、rc=0。
  * cache：二跑零 /prompt 提交（断点续跑 unit 版）；prompt_text 改一字仅重渲
    该镜；mp4 ≤1KB 判失败不写 cache。
  * 断点续跑：预置 3/5 镜 cache → 重跑只提交缺失 2 镜。
  * --force：客户端自身清 cache/产物后全量重渲。
  * warnings 双形 merge：[vision-seq] str 保留、上一轮 dict strip、新 dict 追加。
  * graceful-degrade：system_stats 非 200 → rc=0 + comfyui_unreachable dict warning。
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "h3_regen", REPO_ROOT / "analysis" / "roundtrip" / "h3_regen.py")
h3m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h3m)


# ── 替身 ────────────────────────────────────────────────────────────────────

class FakeHTTP:
    """记录式 _http_json 替身 —— 按调用序回放预设 (status, body)。

    responses 耗尽后回 (0, None)（模拟瞬态不可达——poll 循环 continue 用）。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []          # (url, payload) 元组

    def __call__(self, url, payload=None, timeout=30.0):
        status, body = self.responses.pop(0) if self.responses else (0, None)
        self.calls.append((url, payload))
        return status, body


class FakeClock:
    """time.time 替身 —— 每次调用前进 step 秒（超时用例不真等）。"""

    def __init__(self, step=5.0):
        self.now = 1000.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


class _FakeProc:
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.returncode = 0


def history_success(prompt_id: str, filename: str) -> dict:
    """live /history 实测形状（Pitfall 3：本 build 的 SaveVideo mp4 在 images 键）。"""
    return {prompt_id: {
        "status": {"status_str": "success", "completed": True},
        "outputs": {"50": {"images": [
            {"filename": filename, "subfolder": "", "type": "output",
             "animated": [True]}]}},
    }}


def ok_responses(n_shots: int) -> list:
    """一次全 miss 成功批的 FakeHTTP 回放序列（gate + 每镜 prompt/history）。"""
    res = [(200, {"system": "ok"})]
    for i in range(n_shots):
        pid = f"pid-{i + 1:03d}"
        res.append((200, {"prompt_id": pid}))
        res.append((200, history_success(pid, f"kst_x_shot{i + 1:03d}_00001_.mp4")))
    return res


def make_workdir(tmp_path, n_shots=5):
    """最小 work_dir：shots.json + prompts.json（顶层是 list）+ 假 h264.mp4
    （帧提取被 fake，几字节即可）。镜 duration 2.0s → length 网格保底 124。"""
    work = tmp_path / "work"
    work.mkdir(parents=True)
    shots = [{"id": i + 1, "start_sec": i * 2.0, "end_sec": i * 2.0 + 2.0,
              "duration": 2.0} for i in range(n_shots)]
    (work / "shots.json").write_text(
        json.dumps(shots, ensure_ascii=False), encoding="utf-8")
    prompts = [{"shot_id": s["id"], "start_sec": s["start_sec"],
                "end_sec": s["end_sec"], "duration": s["duration"],
                "subject": "主体", "action": "动作", "camera": "特写",
                "scene": "场景", "lighting": "自然光", "style": "电影感",
                "prompt_text": f"测试 prompt {s['id']}"}
               for s in shots]
    (work / "prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "h264.mp4").write_bytes(b"fake-h264-bytes-0123456789")
    return work


def run_main(work, extra_args=None):
    """argv 注入调 h3m.main()，返回 rc。"""
    argv = ["h3_regen.py", "--work-dir", str(work)]
    if extra_args:
        argv += extra_args
    old_argv = sys.argv
    sys.argv = argv
    try:
        rc = h3m.main()
    finally:
        sys.argv = old_argv
    return rc


def patch_pipeline(monkeypatch, fake_http, mp4_bytes=b"x" * 2048):
    """打满四个 patch 点：_http_json / subprocess.run（curl+ffmpeg 分发）/
    time.sleep / _view_download（直写产物字节）。返回 subprocess 调用记录。"""
    monkeypatch.setattr(h3m, "_http_json", fake_http)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if cmd[0] == "curl":
            at = [a for a in cmd if a.startswith("image=@")][0][len("image=@"):]
            return _FakeProc(json.dumps({"name": os.path.basename(at),
                                         "subfolder": "", "type": "input"}))
        if cmd[0] == "ffmpeg":
            dest = [a for a in cmd if a.endswith(".jpg")][-1]
            Path(dest).write_bytes(b"\xff\xd8fake-jpeg")
        return _FakeProc("")

    monkeypatch.setattr(h3m.subprocess, "run", fake_run)
    monkeypatch.setattr(h3m.time, "sleep", lambda s: None)   # 不真等 15s
    monkeypatch.setattr(h3m, "_view_download",
                        lambda item, url, dest: Path(dest).write_bytes(mp4_bytes))
    return calls


# ── 渲染链纯函数 ────────────────────────────────────────────────────────────

def test_workflow_injection_five_node_groups():
    """真实模板 deepcopy 注入五组节点；模板对象与磁盘文件均不被改动；
    拓扑锁定值（euler/simple/shift_video）不被注入改写。"""
    disk_before = h3m.TEMPLATE_PATH.read_bytes()
    tpl = h3m.load_template()
    wf = h3m.build_workflow(tpl, "ff_name.jpg", "lf_name.jpg", "中文提示词",
                            1344, 768, 175, 12345, "kst_pre")
    assert wf["14"]["inputs"]["image"] == "ff_name.jpg"
    assert wf["15"]["inputs"]["image"] == "lf_name.jpg"
    assert wf["20"]["inputs"]["prompt"] == "中文提示词"
    assert (wf["20"]["inputs"]["width"], wf["20"]["inputs"]["height"]) == (1344, 768)
    assert wf["20"]["inputs"]["length"] == 175
    assert wf["30"]["inputs"]["seed"] == 12345
    assert wf["50"]["inputs"]["filename_prefix"] == "kst_pre"
    # deepcopy 未污染内存模板
    assert tpl["14"]["inputs"]["image"] == "<FF_FILENAME>"
    assert tpl["20"]["inputs"]["prompt"] == "<PROMPT_TEXT>"
    # 磁盘模板未被改动（byte-identical）
    assert h3m.TEMPLATE_PATH.read_bytes() == disk_before
    # CONTEXT SC1 锁定拓扑不被注入触碰
    assert wf["30"]["inputs"]["sampler_name"] == "euler"
    assert wf["30"]["inputs"]["scheduler"] == "simple"
    assert wf["30"]["inputs"]["steps"] == 15 and wf["30"]["inputs"]["cfg"] == 1.0
    assert wf["21"]["inputs"]["shift_video"] == 12.0


def test_h3_frame_count_grid():
    """锚点值 + 全域网格不变式（n%17==5 且 124<=n<=362）。"""
    assert h3m.h3_frame_count(0.5) == 124      # 短镜保底
    assert h3m.h3_frame_count(5.5) == 141
    assert h3m.h3_frame_count(6.73) == 175
    assert h3m.h3_frame_count(19.7) == 362     # 长镜 cap
    for d10 in range(5, 400):                  # 0.5s..39.9s，0.1s 步进
        n = h3m.h3_frame_count(d10 / 10.0)
        assert n % 17 == 5, (d10 / 10.0, n)
        assert 124 <= n <= 362, (d10 / 10.0, n)


def test_seed_deterministic():
    """seed 跨调用确定（非 hash()）、异镜/异 vch 不同、值域 < 2**31。"""
    assert h3m.derive_seed("ece64d62bcbc534a", 7) == h3m.derive_seed("ece64d62bcbc534a", 7)
    assert h3m.derive_seed("ece64d62bcbc534a", 7) != h3m.derive_seed("ece64d62bcbc534a", 8)
    assert h3m.derive_seed("ece64d62bcbc534a", 7) != h3m.derive_seed("ffffffffffffffff", 7)
    assert h3m.derive_seed("x", 1) < 2 ** 31


def test_extract_frames_no_scale(monkeypatch, tmp_path):
    """ffmpeg argv：list-form、无 -vf 无 scale（Pitfall 4：必须全分辨率重提）、
    dest 落 route_cache/h3_regen/frames/ 确定性名、尾帧 -ss 前移 guard。"""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        dest = [a for a in cmd if a.endswith(".jpg")][-1]
        Path(dest).write_bytes(b"\xff\xd8fake")
        return _FakeProc("")

    monkeypatch.setattr(h3m.subprocess, "run", fake_run)
    shot = {"id": 3, "start_sec": 1.0, "end_sec": 2.5, "duration": 1.5}
    frames_dir = str(tmp_path / "route_cache" / "h3_regen" / "frames")
    ff, lf = h3m.extract_endpoint_frames("/src/h264.mp4", shot,
                                         "ab12cd34ef567890", frames_dir)
    assert len(calls) == 2 and all(c[0] == "ffmpeg" for c in calls)
    for c in calls:
        assert isinstance(c, list)
        assert "-vf" not in c
        # 无 scale 滤镜（argv 元素级检查——tmp 目录名可能恰含 "scale" 字样）
        assert not any(a == "scale" or a.startswith("scale=") or a.startswith("scale:")
                       for a in c)
    assert ff.endswith("kst_ab12cd34ef567890_shot003_ff.jpg")
    assert lf.endswith("kst_ab12cd34ef567890_shot003_lf.jpg")
    assert "route_cache/h3_regen/frames" in ff.replace(os.sep, "/")
    assert float(calls[0][calls[0].index("-ss") + 1]) == pytest.approx(1.0)
    assert float(calls[1][calls[1].index("-ss") + 1]) == pytest.approx(2.5 - 0.04)


def test_upload_curl_args(monkeypatch, tmp_path):
    """curl multipart：-F image=@ + type=input + overwrite=true（Pitfall 5）。"""
    calls = []
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"jpg")

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return _FakeProc(json.dumps({"name": "frame.jpg", "subfolder": "",
                                     "type": "input"}))

    monkeypatch.setattr(h3m.subprocess, "run", fake_run)
    name = h3m.upload_image(str(img), "http://127.0.0.1:8188")
    assert name == "frame.jpg"
    cmd = calls[0]
    assert cmd[:4] == ["curl", "-s", "-X", "POST"]
    assert "http://127.0.0.1:8188/upload/image" in cmd
    assert f"image=@{img}" in cmd
    assert "type=input" in cmd and "overwrite=true" in cmd
    assert cmd.count("-F") == 3


# ── 提交/轮询/下载全链路 + 降级分支 ────────────────────────────────────────

def test_submit_poll_download_success(tmp_path, monkeypatch):
    """FakeHTTP 全链路：mp4 落盘 >1KB + cache 写入（含 prompt_id/engine 串/
    prompt_version）；prompt_text 只经 /prompt JSON body 下发（T-20-01）。"""
    work = make_workdir(tmp_path, n_shots=1)
    fake = FakeHTTP(ok_responses(1))
    calls = patch_pipeline(monkeypatch, fake)
    assert run_main(work) == 0
    urls = [u for u, _ in fake.calls]
    assert urls[0].endswith("/system_stats")
    assert sum(u.endswith("/prompt") for u in urls) == 1
    assert any("/history/" in u for u in urls)
    mp4 = work / "roundtrip" / "shot_001_regen.mp4"
    assert mp4.is_file() and mp4.stat().st_size > 1024
    meta = json.loads((work / "route_cache" / "h3_regen" / "shot_001.json")
                      .read_text(encoding="utf-8"))
    assert meta["prompt_id"] == "pid-001"
    assert meta["engine_name"] == "comfyui-fl2va"
    assert meta["engine_version"] == "fl2va-int8/euler+simple/15/1344x768"
    assert meta["prompt_version"] == h3m.prompt_version_for("测试 prompt 1")
    assert "rendered_at" in meta and len(meta["mp4_sha256"]) == 64
    payload = [p for u, p in fake.calls if u.endswith("/prompt")][0]
    assert payload["prompt"]["20"]["inputs"]["prompt"] == "测试 prompt 1"
    assert payload["prompt"]["20"]["inputs"]["length"] == 124   # 2.0s → 保底
    assert payload["prompt"]["30"]["inputs"]["seed"] == meta["seed"]
    # prompt_text 绝不进 subprocess argv（ffmpeg argv 里只有 -ss 值与路径）
    assert all("测试 prompt" not in " ".join(c) for c in calls)


def test_history_error_branch(tmp_path, monkeypatch, capsys):
    """status_str=error → 该镜失败、无产物无 cache、批不崩 rc=0、
    failed 摘要以 [roundtrip] str 落 warnings sidecar。"""
    work = make_workdir(tmp_path, n_shots=1)
    fake = FakeHTTP([
        (200, {"system": "ok"}),
        (200, {"prompt_id": "pid-001"}),
        (200, {"pid-001": {"status": {"status_str": "error",
                                      "messages": ["execution error"]}}}),
    ])
    patch_pipeline(monkeypatch, fake)
    assert run_main(work) == 0
    assert "failed=1" in capsys.readouterr().out
    assert not (work / "roundtrip" / "shot_001_regen.mp4").exists()
    assert not (work / "route_cache" / "h3_regen" / "shot_001.json").exists()
    warns = json.loads((work / "route_cache" / "warnings.json")
                       .read_text(encoding="utf-8"))["warnings"]
    assert any(isinstance(w, str) and "failed shots: [1]" in w for w in warns)


def test_history_timeout(tmp_path, monkeypatch, capsys):
    """history 永不返回完成（瞬态 (0,None) continue）→ 轮询超时 → 单镜失败
    rc=0。FakeClock 前进时间避免真等。"""
    work = make_workdir(tmp_path, n_shots=1)
    fake = FakeHTTP([(200, {"system": "ok"}), (200, {"prompt_id": "pid-001"})])
    patch_pipeline(monkeypatch, fake)
    monkeypatch.setattr(h3m.time, "time", FakeClock(step=5.0))
    assert run_main(work, ["--shot-timeout", "10"]) == 0
    assert "failed=1" in capsys.readouterr().out
    assert any("/history/" in u for u, _ in fake.calls)   # 轮询确实发生过
    assert not (work / "roundtrip" / "shot_001_regen.mp4").exists()


def test_comfyui_unreachable_exit0(tmp_path, monkeypatch, capsys):
    """system_stats 非 200 → rc=0 + comfyui_unreachable dict warning +
    零 curl/ffmpeg/提交动作（graceful-degrade）。"""
    work = make_workdir(tmp_path, n_shots=2)
    fake = FakeHTTP([(0, "connection refused")])
    calls = patch_pipeline(monkeypatch, fake)
    assert run_main(work) == 0
    assert "graceful-degrade" in capsys.readouterr().out
    assert len(fake.calls) == 1                     # 只有 system_stats 探测
    assert not any(c and c[0] == "curl" for c in calls)
    assert not any(c and c[0] == "ffmpeg" for c in calls)
    warns = json.loads((work / "route_cache" / "warnings.json")
                       .read_text(encoding="utf-8"))["warnings"]
    assert any(isinstance(w, dict) and w["code"] == "comfyui_unreachable"
               for w in warns)


# ── cache / 断点续跑 / force ───────────────────────────────────────────────

def test_cache_hit_second_run_zero_submissions(tmp_path, monkeypatch, capsys):
    """断点续跑 unit 版：二跑换新 FakeHTTP，无 /prompt 无 /history，
    stdout 逐镜 cache-hit 行。"""
    work = make_workdir(tmp_path, n_shots=3)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(3)))
    assert run_main(work) == 0
    fake2 = FakeHTTP([(200, {"system": "ok"})])
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work) == 0
    assert not any(u.endswith("/prompt") for u, _ in fake2.calls)
    assert not any("/history/" in u for u, _ in fake2.calls)
    out = capsys.readouterr().out
    assert out.count("cache hit, skipping") == 3
    assert "rendered=0" in out and "cache-hit=3" in out


def test_prompt_version_change_invalidates(tmp_path, monkeypatch, capsys):
    """该镜 prompt_text 改一字（prompt_version 变）→ 仅该镜重渲；
    其余镜仍 cache-hit。"""
    work = make_workdir(tmp_path, n_shots=2)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(2)))
    assert run_main(work) == 0
    prompts = json.loads((work / "prompts.json").read_text(encoding="utf-8"))
    prompts[0]["prompt_text"] += "改"
    (work / "prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    fake2 = FakeHTTP([(200, {"system": "ok"}),
                      (200, {"prompt_id": "pid-001b"}),
                      (200, history_success("pid-001b", "kst_x_shot001_00002_.mp4"))])
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake2.calls) == 1
    out = capsys.readouterr().out
    assert out.count("cache hit, skipping") == 1   # shot 2 仍命中


def test_cache_requires_mp4_over_1kb(tmp_path, monkeypatch, capsys):
    """下载产物 ≤1KB → 判失败不写 cache；修复后重跑重新提交并成功。"""
    work = make_workdir(tmp_path, n_shots=1)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(1)), mp4_bytes=b"x" * 500)
    assert run_main(work) == 0
    assert "failed=1" in capsys.readouterr().out
    assert not (work / "route_cache" / "h3_regen" / "shot_001.json").exists()
    fake2 = FakeHTTP(ok_responses(1))
    patch_pipeline(monkeypatch, fake2, mp4_bytes=b"x" * 2048)
    assert run_main(work) == 0
    assert any(u.endswith("/prompt") for u, _ in fake2.calls)   # cache 未写 → 重提交
    assert (work / "roundtrip" / "shot_001_regen.mp4").stat().st_size > 1024


def test_resume_only_missing(tmp_path, monkeypatch, capsys):
    """断点续跑：预置 3/5 镜 cache（镜 4/5 产物+元数据丢失）→ 重跑只提交
    缺失 2 镜。"""
    work = make_workdir(tmp_path, n_shots=5)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(5)))
    assert run_main(work) == 0
    for sid in (4, 5):
        (work / "route_cache" / "h3_regen" / f"shot_{sid:03d}.json").unlink()
        (work / "roundtrip" / f"shot_{sid:03d}_regen.mp4").unlink()
    extra = []
    for sid in (4, 5):
        extra.append((200, {"prompt_id": f"pid-{sid:03d}"}))
        extra.append((200, history_success(f"pid-{sid:03d}",
                                           f"kst_x_shot{sid:03d}_00001_.mp4")))
    fake2 = FakeHTTP([(200, {"system": "ok"})] + extra)
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake2.calls) == 2   # 只补缺失 2 镜
    out = capsys.readouterr().out
    assert out.count("cache hit, skipping") == 3
    assert "rendered=2" in out and "cache-hit=3" in out


def test_client_force_rerenders_all(tmp_path, monkeypatch, capsys):
    """客户端 --force：清 route_cache/h3_regen/ + roundtrip/ 后全量重渲
    （零 cache-hit）。"""
    work = make_workdir(tmp_path, n_shots=2)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(2)))
    assert run_main(work) == 0
    fake2 = FakeHTTP(ok_responses(2))
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work, ["--force"]) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake2.calls) == 2
    out = capsys.readouterr().out
    assert "[force]" in out
    assert "cache hit" not in out


# ── warnings 双形 merge ─────────────────────────────────────────────────────

def test_warnings_dual_shape_merge(tmp_path):
    """strip 规则：dict 且 code ∈ 三码 enum，或 str 以 [roundtrip] 开头；
    [vision-seq] 等陌生 str 条目原样保留（Pitfall 6：不丢 dict 也不误伤他 step）。"""
    sc = tmp_path / "route_cache"
    sc.mkdir()
    (sc / "warnings.json").write_text(json.dumps(
        {"warnings": ["[vision-seq] old",
                      {"code": "comfyui_unreachable", "detail": "stale"}]},
        ensure_ascii=False), encoding="utf-8")
    h3m.append_roundtrip_warnings(str(tmp_path),
                                  [{"code": "vram_insufficient", "detail": "now"}])
    got = json.loads((sc / "warnings.json").read_text(encoding="utf-8"))["warnings"]
    assert "[vision-seq] old" in got
    assert any(isinstance(x, dict) and x["code"] == "vram_insufficient" for x in got)
    assert not any(isinstance(x, dict) and x["code"] == "comfyui_unreachable"
                   for x in got)                     # 上一轮 roundtrip dict 被 strip
    # str 形 [roundtrip] 条目同样按「上一轮」strip，本轮新 str 追加
    h3m.append_roundtrip_warnings(str(tmp_path), ["[roundtrip] 新事件说明"])
    got2 = json.loads((sc / "warnings.json").read_text(encoding="utf-8"))["warnings"]
    assert "[roundtrip] 新事件说明" in got2
    assert not any(isinstance(x, dict) for x in got2)
    h3m.append_roundtrip_warnings(str(tmp_path), [])
    got3 = json.loads((sc / "warnings.json").read_text(encoding="utf-8"))["warnings"]
    assert got3 == ["[vision-seq] old"]              # 只剩陌生 str 条目
