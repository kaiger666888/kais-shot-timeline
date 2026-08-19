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

覆盖（20-02 Task 3 行为清单——VRAM guard / 抽样 / 降载，假 nvidia-smi + 假 ss +
假 os.kill）：
  * 批开始严格 gate：free=21000 → 拒整批（rc=0、零提交、vram_insufficient
    detail 含 22528 与 top 占用者 pid）；free=23000 → 提交发生。
  * eye 串行等待超时：total=24576/free=10855（used=13721 达 eye 阈值）+
    --vram-wait-timeout=0 → blocked、零提交、detail 记 eye 等待超时、
    第二次 /free 未发生（五步序中 eye 阻断在其之前）。
  * 每镜 PID 归因（Pitfall 1 反自锁回归锚）：基线含 ComfyUI pid=100、批中
    自身 18432MiB cache 驻留 → 不等待直接提交；新 foreign pid=999 13721MiB →
    等待至超时 → warning + rc=0 优雅终止（cache 保留续跑）。
  * TTS kill 定向：假 ss 含 :5110 pid=111 / :5111 pid=222 → SIGTERM 恰发往
    {111,222}、无 pkill、before/after 双审计 warning；无监听 → 无 kill 调用、
    仍记 after 审计 warning、批继续（no-op 安全）。
  * /free 时机：POST /free 恰 2 次（kill 后 + 批开始前），payload 双布尔，
    首次 /prompt 之后不再有 /free（批中每镜之间不调）。
  * uniform_sample ep01 锚点清单逐项相等 + n≥N 全镜 + 小 n 锚点。
  * 抽样在过滤之前：93 镜 uniform-20 落样含 shot 70（19.7s）→ 被
    --max-shot-sec 10 跳过 → 实渲 19 + skipped.json 条目 + str warning。
  * --regen-resolution：1344x768 跑 1 镜后换 896x512 重跑同镜重渲
    （engine_version 联动 cache 失效 + workflow 宽高下发）；100x100/897x512/
    非 WxH 形 SystemExit。

覆盖（20-03 Task 2 行为清单——roundtrip.json sidecar，fake probe_duration_sec
固定值，不依赖真 ffprobe 速度）：
  * degrade 中间态合法：regen-only + failed 混合（scores/verdict 全缺席）→
    jsonschema 零错；schema_version 取 export_asset 单源 '1.3'。
  * READ-merge：既有同 shot_id 条目的 scores/verdict（Phase 21 未来字段）
    原样保留、regen 半边替换；陌生 shot_id 条目整条不动；JSON 损坏视为
    空重建。
  * 路径穿越拒绝：regen.path 含 .. → schema pattern 拒 → sys.exit 且
    文件未写（T-20-08 写前自校验兜底）。
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
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def history_success(prompt_id: str, filename: str) -> dict:
    """live /history 实测形状（Pitfall 3：本 build 的 SaveVideo mp4 在 images 键）。"""
    return {prompt_id: {
        "status": {"status_str": "success", "completed": True},
        "outputs": {"50": {"images": [
            {"filename": filename, "subfolder": "", "type": "output",
             "animated": [True]}]}},
    }}


def ok_responses(n_shots: int) -> list:
    """一次全 miss 成功批的 FakeHTTP 回放序列（gate + guard 双 /free + 每镜
    prompt/history——20-02 起 guard 在 gate 后消耗两次 /free 响应）。"""
    res = [(200, {"system": "ok"})] + GUARD_FREES
    for i in range(n_shots):
        pid = f"pid-{i + 1:03d}"
        res.append((200, {"prompt_id": pid}))
        res.append((200, history_success(pid, f"kst_x_shot{i + 1:03d}_00001_.mp4")))
    return res


# ── guard 假数据（20-02：假 nvidia-smi / 假 ss / 假 docker）─────────────────

# ss -tlnp 假输出：:5110→pid 111（IndexTTS）/ :5111→pid 222（VoiceDesign），
# 另含一条非 TTS 监听（:8188 ComfyUI——必须不被端口匹配误伤）。
SS_WITH_TTS = (
    "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
    "LISTEN 0 511 127.0.0.1:5110 0.0.0.0:* "
    "users:((\"indextts25-server.py\",pid=111,fd=3))\n"
    "LISTEN 0 511 127.0.0.1:5111 0.0.0.0:* "
    "users:((\"python\",pid=222,fd=4))\n"
    "LISTEN 0 128 127.0.0.1:8188 0.0.0.0:* "
    "users:((\"python\",pid=9999,fd=5))\n")

SS_EMPTY = "State Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"

# nvidia-smi 假 stdout（query-gpu 形 "total, free"；compute-apps 形 "pid, used"）。
NM_TOTAL_FREE_23000 = "24576, 23000"          # used=1576 < eye 阈值 → gate 过
NM_TOTAL_FREE_21000 = "24576, 21000"          # free < 22528 → 批开始 gate 拒
NM_TOTAL_FREE_EYE = "24576, 10855"            # used=13721 → eye lease 在跑
NM_APPS_MUSIC3 = "1234, 676"                  # music3 常驻（top 占用者断言用）
NM_APPS_SELF_18G = "100, 18432"               # ComfyUI 自身 cache 驻留（基线内）
NM_APPS_WITH_FOREIGN = "100, 692\n999, 13721"  # 批中冒出的 foreign（基线外）

# guard 五步序中两次 POST /free（kill 后 + 批开始前）的回放响应。
GUARD_FREES = [(200, {"freed": True}), (200, {"freed": True})]


def make_workdir(tmp_path, n_shots=5, duration_by_id=None):
    """最小 work_dir：shots.json + prompts.json（顶层是 list）+ 假 h264.mp4
    （帧提取被 fake，几字节即可）。镜 duration 默认 2.0s（→ length 保底 124）；
    duration_by_id 可按 id 覆盖时长（ep01 抽样用例给 shot 70 塞 19.7s）。"""
    work = tmp_path / "work"
    work.mkdir(parents=True)
    shots = []
    for i in range(n_shots):
        dur = float((duration_by_id or {}).get(i + 1, 2.0))
        shots.append({"id": i + 1, "start_sec": i * 2.0,
                      "end_sec": i * 2.0 + dur, "duration": dur})
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


def patch_pipeline(monkeypatch, fake_http, mp4_bytes=b"x" * 2048,
                   ss_stdout="", gpu_mem=None, compute_apps_stdout="",
                   docker_pid=None):
    """打满 patch 点：_http_json / subprocess.run（curl+ffmpeg+ss+nvidia-smi+
    docker 分发）/ time.sleep（不真等 15s）/ _view_download（直写产物字节）。
    guard 相关参数（20-02）：
    - ss_stdout：假 ss -tlnp stdout（None = 抛 OSError 模拟 ss 不可用探测失败）；
    - gpu_mem：query-gpu 假 stdout（None/"" = nvidia-smi 无读数 → fail-open）；
    - compute_apps_stdout：query-compute-apps 假 stdout；传 list = 逐次弹出后
      停在末值（模拟「基线快照时无 foreign、批中冒出」的时序差）；
    - docker_pid：docker inspect 主 PID 假 stdout（None = returncode 1 失败，
      走 best-effort 忽略路径）。
    返回 subprocess 调用记录。"""
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
        if cmd[0] == "ss":
            if ss_stdout is None:
                raise OSError("ss not available")
            return _FakeProc(ss_stdout)
        if cmd[0] == "nvidia-smi":
            if any(a.startswith("--query-compute-apps") for a in cmd):
                if isinstance(compute_apps_stdout, list):
                    if len(compute_apps_stdout) > 1:
                        return _FakeProc(compute_apps_stdout.pop(0))
                    return _FakeProc(compute_apps_stdout[0])
                return _FakeProc(compute_apps_stdout)
            return _FakeProc(gpu_mem if gpu_mem is not None else "")
        if cmd[0] == "docker":
            if docker_pid is None:
                return _FakeProc("", returncode=1)
            return _FakeProc(str(docker_pid))
        if cmd[0] == "pkill":
            return _FakeProc("", returncode=1)     # 默认无命中（returncode 1）
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
        *GUARD_FREES,
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
    fake = FakeHTTP([(200, {"system": "ok"}), *GUARD_FREES,
                     (200, {"prompt_id": "pid-001"})])
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
    fake2 = FakeHTTP([(200, {"system": "ok"}), *GUARD_FREES,
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
    fake2 = FakeHTTP([(200, {"system": "ok"}), *GUARD_FREES] + extra)
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


def test_force_with_engine_down_preserves_everything(tmp_path, monkeypatch, capsys):
    """CR-02 回归锚：--force + system_stats 非 200 → 破坏性清除未执行——
    cache meta / mp4 产物 / roundtrip.json 全部原样保留，rc=0 优雅降级。"""
    work = make_workdir(tmp_path, n_shots=1)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(1)))
    assert run_main(work) == 0
    mp4_before = (work / "roundtrip" / "shot_001_regen.mp4").read_bytes()
    meta_before = (work / "route_cache" / "h3_regen" / "shot_001.json") \
        .read_text(encoding="utf-8")
    fake2 = FakeHTTP([(0, "connection refused")])
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work, ["--force"]) == 0
    out = capsys.readouterr().out
    assert "graceful-degrade" in out and "[force]" not in out   # 清除未执行
    assert len(fake2.calls) == 1                                 # 只有 gate 探测
    # 三个破坏目标全部完好
    assert (work / "roundtrip" / "shot_001_regen.mp4").read_bytes() == mp4_before
    assert (work / "route_cache" / "h3_regen" / "shot_001.json") \
        .read_text(encoding="utf-8") == meta_before
    assert (work / "roundtrip.json").is_file()


def test_force_preserves_verdicts_in_sidecar(tmp_path, monkeypatch, capsys):
    """WR-01 红线：--force 绝不整体删除 roundtrip.json——只剥 regen/status
    半边，scores/verdict（含 rejected）原样保留；批末 READ-merge 回填新 regen。"""
    work = make_workdir(tmp_path, n_shots=1)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(1)))
    assert run_main(work) == 0
    sc = read_sidecar(work)
    sc["shots"][0]["scores"] = {"midframe_sim": {"score": 0.9, "model": "clip"}}
    sc["shots"][0]["verdict"] = {"decision": "rejected", "source": "human"}
    (work / "roundtrip.json").write_text(
        json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8")
    fake2 = FakeHTTP(ok_responses(1))
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work, ["--force"]) == 0
    sc2 = read_sidecar(work)
    by = {s["shot_id"]: s for s in sc2["shots"]}
    assert by[1]["verdict"]["decision"] == "rejected"        # 人工 verdict 保留
    assert by[1]["scores"]["midframe_sim"]["score"] == 0.9
    assert by[1]["regen"]["engine_version"] == "fl2va-int8/euler+simple/15/1344x768"
    assert validate_sidecar(sc2) == []
    out = capsys.readouterr().out
    assert "cache hit" not in out and "rendered=1" in out
    assert "保留 1 条" in out


def test_force_strip_removes_file_when_no_human_data(tmp_path):
    """全 regen/status-only 条目（无 scores/verdict）→ strip 后文件整体移除
    （与旧 unlink 语义等价，但仅在确认无人工数据可保留时发生）。"""
    (tmp_path / "roundtrip.json").write_text(json.dumps(
        {"schema_version": "1.3", "shots": [
            {"shot_id": 1, "regen": {"path": "roundtrip/shot_001_regen.mp4"}},
            {"shot_id": 2, "status": {"state": "failed", "error": "x"}}]},
        ensure_ascii=False), encoding="utf-8")
    assert h3m.strip_sidecar_regen_half(str(tmp_path)) == 0
    assert not (tmp_path / "roundtrip.json").exists()
    # 无文件 → no-op 返回 0
    assert h3m.strip_sidecar_regen_half(str(tmp_path)) == 0


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


# ── VRAM guard：批开始 gate / eye 等待 / 每镜 PID 归因（20-02）──────────────

def read_warnings(work) -> list:
    return json.loads((work / "route_cache" / "warnings.json")
                      .read_text(encoding="utf-8"))["warnings"]


def test_vram_batch_gate_refuses(tmp_path, monkeypatch, capsys):
    """批开始严格 gate：free=21000 < 22528 → rc=0、零提交、vram_insufficient
    warning detail 含 22528 与 top 占用者 pid（Pitfall 9）。"""
    work = make_workdir(tmp_path, n_shots=2)
    fake = FakeHTTP([(200, {"system": "ok"}), *GUARD_FREES])
    patch_pipeline(monkeypatch, fake, gpu_mem=NM_TOTAL_FREE_21000,
                   compute_apps_stdout=NM_APPS_MUSIC3)
    assert run_main(work, ["--gpu-index", "1"]) == 0
    assert not any(u.endswith("/prompt") for u, _ in fake.calls)   # 零提交
    warns = read_warnings(work)
    vram = [w for w in warns if isinstance(w, dict)
            and w["code"] == "vram_insufficient"]
    assert vram and "22528" in vram[-1]["detail"]
    assert "21000" in vram[-1]["detail"] and "1234" in vram[-1]["detail"]  # top 占用者
    out = capsys.readouterr().out
    assert "guard 拒绝" in out and "graceful-degrade" in out


def test_vram_batch_gate_passes(tmp_path, monkeypatch):
    """free=23000（music3/ComfyUI idle 常驻后的实测量级）→ gate 过 → 提交发生。"""
    work = make_workdir(tmp_path, n_shots=1)
    fake = FakeHTTP(ok_responses(1))
    patch_pipeline(monkeypatch, fake, gpu_mem=NM_TOTAL_FREE_23000)
    assert run_main(work, ["--gpu-index", "1"]) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake.calls) == 1
    assert (work / "roundtrip" / "shot_001_regen.mp4").is_file()


def test_vram_batch_eye_wait_timeout(tmp_path, monkeypatch, capsys):
    """批开始 eye 等待分支：used=13721（total-free）达 eye 阈值 +
    --vram-wait-timeout=0 → 立即超时 blocked：rc=0、零提交、detail 记 eye
    等待超时、第二次 /free 未发生（五步序中 eye 阻断在④之前）。"""
    work = make_workdir(tmp_path, n_shots=2)
    fake = FakeHTTP([(200, {"system": "ok"}), (200, {"freed": True})])
    patch_pipeline(monkeypatch, fake, gpu_mem=NM_TOTAL_FREE_EYE)
    assert run_main(work, ["--gpu-index", "1", "--vram-wait-timeout", "0"]) == 0
    assert not any(u.endswith("/prompt") for u, _ in fake.calls)
    assert sum(u.endswith("/free") for u, _ in fake.calls) == 1
    warns = read_warnings(work)
    assert any(isinstance(w, dict) and w["code"] == "vram_insufficient"
               and "eye" in w["detail"] and "13721" in w["detail"]
               for w in warns)
    out = capsys.readouterr().out
    assert "eye lease" in out and "超时" in out


def test_vram_per_shot_own_cache_not_blocking(tmp_path, monkeypatch, capsys):
    """Pitfall 1 反自锁回归锚：基线（compute-apps ∪ 容器主 PID）含 ComfyUI
    pid=100；镜 2 时自身 18432MiB cache 驻留 → 不等待直接提交（PID 归因，
    绝对值 free 复查在此水位下必自锁）。渲后水位 post_render_free_mib 留档。"""
    work = make_workdir(tmp_path, n_shots=2)
    fake = FakeHTTP(ok_responses(2))
    patch_pipeline(monkeypatch, fake, gpu_mem=NM_TOTAL_FREE_23000,
                   compute_apps_stdout=NM_APPS_SELF_18G, docker_pid=100)
    assert run_main(work, ["--gpu-index", "1"]) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake.calls) == 2   # 两镜都直接提交
    out = capsys.readouterr().out
    assert "foreign" not in out                                   # 从未进入等待分支
    assert "rendered=2" in out
    meta = json.loads((work / "route_cache" / "h3_regen" / "shot_001.json")
                      .read_text(encoding="utf-8"))
    assert meta["post_render_free_mib"] == 23000                  # Open Q1 留档


def test_vram_per_shot_foreign_blocks(tmp_path, monkeypatch, capsys):
    """批中冒出 foreign（基线外 pid=999 占 13721MiB）→ 等待循环（sleep 已
    patch）至 --vram-wait-timeout=0 → vram_insufficient warning（detail 含
    foreign pid 与 free）+ rc=0 优雅终止，零提交、cache 保留续跑语义。"""
    work = make_workdir(tmp_path, n_shots=2)
    fake = FakeHTTP(ok_responses(2))
    # list 逐次弹出：基线快照时只有 pid=100；每镜复查时冒出 pid=999
    patch_pipeline(monkeypatch, fake, gpu_mem=NM_TOTAL_FREE_23000,
                   compute_apps_stdout=["100, 692", NM_APPS_WITH_FOREIGN])
    assert run_main(work, ["--gpu-index", "1", "--vram-wait-timeout", "0"]) == 0
    assert not any(u.endswith("/prompt") for u, _ in fake.calls)
    warns = read_warnings(work)
    assert any(isinstance(w, dict) and w["code"] == "vram_insufficient"
               and "999" in w["detail"] and "13721" in w["detail"]
               for w in warns)
    out = capsys.readouterr().out
    assert "foreign GPU 占用" in out and "优雅终止" in out


# ── TTS kill 定向 + /free 时机（20-02）──────────────────────────────────────

def test_kill_tts_port_pid(tmp_path, monkeypatch):
    """假 ss 含 :5110 pid=111 / :5111 pid=222 → os.kill(SIGTERM) 恰发往
    {111,222}（:8188 ComfyUI 监听不误伤）、无 pkill、before/after 双审计
    warning（detail 含 pid/端口）。"""
    work = make_workdir(tmp_path, n_shots=1)
    fake = FakeHTTP(ok_responses(1))
    calls = patch_pipeline(monkeypatch, fake, ss_stdout=SS_WITH_TTS,
                           gpu_mem=NM_TOTAL_FREE_23000)
    kills = []
    monkeypatch.setattr(h3m.os, "kill", lambda pid, sig: kills.append((pid, sig)))
    assert run_main(work, ["--gpu-index", "1"]) == 0
    assert {p for p, _ in kills} == {111, 222}
    assert all(s == h3m.signal.SIGTERM for _, s in kills)
    assert not any(c[0] == "pkill" for c in calls)          # 定向 kill，无回退
    warns = read_warnings(work)
    tts = [w for w in warns if isinstance(w, dict) and "TTS kill" in w["detail"]]
    assert len(tts) == 2                                    # before + after
    assert "pid=111" in tts[0]["detail"] and "pid=222" in tts[0]["detail"]
    assert "5110" in tts[0]["detail"] and "5111" in tts[0]["detail"]


def test_kill_tts_no_listeners(tmp_path, monkeypatch):
    """假 ss 无 TTS 监听 → 无 os.kill、无 pkill 回退、仍记 after 审计
    warning、批继续提交（TTS 当前未运行的 no-op 安全证明）。"""
    work = make_workdir(tmp_path, n_shots=1)
    fake = FakeHTTP(ok_responses(1))
    calls = patch_pipeline(monkeypatch, fake, ss_stdout=SS_EMPTY,
                           gpu_mem=NM_TOTAL_FREE_23000)
    kills = []
    monkeypatch.setattr(h3m.os, "kill", lambda pid, sig: kills.append((pid, sig)))
    assert run_main(work, ["--gpu-index", "1"]) == 0
    assert kills == []
    assert not any(c[0] == "pkill" for c in calls)
    assert sum(u.endswith("/prompt") for u, _ in fake.calls) == 1   # 批继续
    warns = read_warnings(work)
    assert any(isinstance(w, dict) and w["code"] == "vram_insufficient"
               and "无监听" in w["detail"] for w in warns)


def test_vram_free_called_twice(tmp_path, monkeypatch):
    """POST /free 恰 2 次（kill 后 + 批开始前——CONTEXT 字面语义的机器证明），
    payload 双布尔；首次 /prompt 之后不再有 /free（批中每镜之间不调）。"""
    work = make_workdir(tmp_path, n_shots=2)
    fake = FakeHTTP(ok_responses(2))
    patch_pipeline(monkeypatch, fake, gpu_mem=NM_TOTAL_FREE_23000)
    assert run_main(work, ["--gpu-index", "1"]) == 0
    frees = [p for u, p in fake.calls if u.endswith("/free")]
    assert len(frees) == 2
    assert all(p == {"unload_models": True, "free_memory": True} for p in frees)
    urls = [u for u, _ in fake.calls]
    first_prompt = next(i for i, u in enumerate(urls) if u.endswith("/prompt"))
    assert all(not u.endswith("/free") for u in urls[first_prompt:])   # 批中不调


# ── 抽样 / 跳镜 / 降载（20-02）──────────────────────────────────────────────

def test_uniform_sample_ep01():
    """ep01 锚点（RESEARCH 实算清单）逐项相等 + n≥N 全镜 + 边界 n。"""
    ids = list(range(1, 94))
    exp = [1, 5, 10, 14, 19, 24, 28, 33, 38, 42, 47, 52, 56, 61, 66, 70,
           75, 80, 84, 89]
    assert h3m.uniform_sample(ids, 20) == exp
    assert h3m.uniform_sample(ids, 93) == ids        # n == N → 全镜
    assert h3m.uniform_sample(ids, 200) == ids       # n > N → 全镜
    assert h3m.uniform_sample(ids, 2) == [1, 47]
    assert h3m.uniform_sample(ids, 1) == [1]
    assert h3m.uniform_sample(ids, 0) == ids         # 0 = 不抽样（CLI 默认）
    assert h3m.uniform_sample([9, 3, 7], 2) == [3, 7]  # 非连续 id：先升序再映射


def test_sample_before_filter(tmp_path, monkeypatch, capsys):
    """抽样在 >10s 过滤之前（A6）：93 镜 uniform-20 落样含 shot 70（19.7s）
    → 被 --max-shot-sec 10 跳过 → 实渲 19 + skipped.json 条目 + str warning。"""
    work = make_workdir(tmp_path, n_shots=93, duration_by_id={70: 19.7})
    fake = FakeHTTP(ok_responses(20))                # 20 落样，1 个被跳 → 用 19
    patch_pipeline(monkeypatch, fake, gpu_mem=NM_TOTAL_FREE_23000)
    assert run_main(work, ["--gpu-index", "1", "--sample-shots", "20",
                           "--max-shot-sec", "10"]) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake.calls) == 19
    skipped = json.loads((work / "route_cache" / "h3_regen" / "skipped.json")
                         .read_text(encoding="utf-8"))
    assert [e["shot_id"] for e in skipped] == [70]
    assert skipped[0]["reason"] == "duration_over_max"
    assert skipped[0]["duration_sec"] == pytest.approx(19.7)
    out = capsys.readouterr().out
    assert "[roundtrip] shot 70 skipped: 19.7s > max 10.0s" in out
    assert "rendered=19" in out and "skipped=1" in out and "sampled=20" in out
    assert any(isinstance(w, str) and "shot 70 skipped" in w
               for w in read_warnings(work))


def test_resolution_flag_invalidates_cache(tmp_path, monkeypatch):
    """1344x768 跑 1 镜 → 换 --regen-resolution 896x512 重跑 → 同镜重渲
    （engine_version 联动 cache 整体失效 + workflow 宽高真下发）。"""
    work = make_workdir(tmp_path, n_shots=1)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(1)),
                   gpu_mem=NM_TOTAL_FREE_23000)
    assert run_main(work, ["--gpu-index", "1"]) == 0
    meta1 = json.loads((work / "route_cache" / "h3_regen" / "shot_001.json")
                       .read_text(encoding="utf-8"))
    assert meta1["engine_version"] == "fl2va-int8/euler+simple/15/1344x768"
    assert meta1["width"] == 1344 and meta1["height"] == 768
    fake2 = FakeHTTP(ok_responses(1))
    patch_pipeline(monkeypatch, fake2, gpu_mem=NM_TOTAL_FREE_23000)
    assert run_main(work, ["--gpu-index", "1",
                           "--regen-resolution", "896x512"]) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake2.calls) == 1   # 重渲
    payload = [p for u, p in fake2.calls if u.endswith("/prompt")][0]
    assert payload["prompt"]["20"]["inputs"]["width"] == 896
    assert payload["prompt"]["20"]["inputs"]["height"] == 512
    meta2 = json.loads((work / "route_cache" / "h3_regen" / "shot_001.json")
                       .read_text(encoding="utf-8"))
    assert meta2["engine_version"] == "fl2va-int8/euler+simple/15/896x512"


def test_resolution_invalid_rejected(tmp_path, monkeypatch):
    """畸形分辨率 fail-fast SystemExit（100x100 比例破 / 897x512 非 32 倍 /
    非 WxH 形），且在任何 HTTP 动作之前（零 FakeHTTP 消耗）。"""
    work = make_workdir(tmp_path, n_shots=1)
    for bad in ("100x100", "897x512", "not-a-resolution"):
        fake = FakeHTTP([])
        patch_pipeline(monkeypatch, fake)
        with pytest.raises(SystemExit):
            run_main(work, ["--regen-resolution", bad])
        assert fake.calls == []                      # gate 前退出，零 HTTP


# ── roundtrip.json sidecar（20-03：schema 合法性 / READ-merge / 穿越拒绝）──

VCH_EP01 = "ece64d62bcbc534a"


def read_sidecar(work) -> dict:
    return json.loads((work / "roundtrip.json").read_text(encoding="utf-8"))


def validate_sidecar(data: dict) -> list:
    schema = json.loads(h3m.SCHEMA_PATH.read_text(encoding="utf-8"))
    return list(Draft202012Validator(schema).iter_errors(data))


def sidecar_result(sid: int, mp4: str, **over) -> dict:
    """rendered/cache-hit 镜的 results 元素（cache meta + shot_id + mp4）。"""
    meta = {"video_content_hash": VCH_EP01, "engine_name": "comfyui-fl2va",
            "engine_version": "fl2va-int8/euler+simple/15/896x512",
            "prompt_version": "ab12cd34", "width": 896, "height": 512}
    meta.update(over)
    return dict(meta, shot_id=sid, mp4=mp4)


def test_sidecar_schema_valid_degenerate(tmp_path, monkeypatch):
    """degrade 中间态合法（Open Q2）：regen-only + failed 混合、scores/verdict
    全缺席 → jsonschema 零错；schema_version 取 export_asset 单源 '1.3'；
    duration_sec 来自 probe（fake 固定值）。"""
    monkeypatch.setattr(h3m, "probe_duration_sec", lambda p: 5.25)
    mp4 = tmp_path / "roundtrip" / "shot_001_regen.mp4"
    mp4.parent.mkdir()
    mp4.write_bytes(b"x" * 2048)
    entries = h3m.build_sidecar_entries(
        [sidecar_result(1, str(mp4)), {"shot_id": 2, "error": "render timeout"}],
        VCH_EP01, 896, 512)
    h3m.write_roundtrip_sidecar(str(tmp_path), entries)
    data = read_sidecar(tmp_path)
    assert validate_sidecar(data) == []
    assert data["schema_version"] == "1.3"           # export_asset 单源
    by = {s["shot_id"]: s for s in data["shots"]}
    assert by[1]["regen"]["path"] == "roundtrip/shot_001_regen.mp4"
    assert by[1]["regen"]["duration_sec"] == 5.25
    assert by[1]["regen"]["video_content_hash"] == VCH_EP01
    assert by[2]["status"] == {"state": "failed", "error": "render timeout"}


def test_sidecar_merge_preserves_future_fields(tmp_path, monkeypatch):
    """READ-merge：既有同 shot_id 条目的 scores/verdict（Phase 21 未来字段）
    原样保留、regen 半边替换为新值；陌生 shot_id 条目整条不动；JSON 损坏
    视为空重建（Phase 18 决策：挂载前仅 JSON-parse）。"""
    monkeypatch.setattr(h3m, "probe_duration_sec", lambda p: 0.0)
    pre = {"schema_version": "1.3", "shots": [
        {"shot_id": 1,
         "regen": {"path": "roundtrip/shot_001_regen.mp4",
                   "video_content_hash": "0" * 16, "engine_name": "old-engine",
                   "engine_version": "old-version", "prompt_version": "old-pv"},
         "scores": {"midframe_sim": {"score": 0.9, "model": "clip"}},
         "verdict": {"decision": "accepted", "source": "human"}},
        {"shot_id": 7, "scores": {"judge": {
            "attribution": "prompt_faithful", "confidence": 0.8,
            "reason": "运动贴合"}}}]}
    (tmp_path / "roundtrip.json").write_text(
        json.dumps(pre, ensure_ascii=False), encoding="utf-8")
    results = [sidecar_result(1, str(tmp_path / "roundtrip" / "shot_001_regen.mp4"))]
    h3m.write_roundtrip_sidecar(
        str(tmp_path), h3m.build_sidecar_entries(results, VCH_EP01, 896, 512))
    data = read_sidecar(tmp_path)
    assert validate_sidecar(data) == []
    by = {s["shot_id"]: s for s in data["shots"]}
    assert set(by) == {1, 7}
    assert by[1]["scores"] == pre["shots"][0]["scores"]      # Phase 21 字段保留
    assert by[1]["verdict"] == pre["shots"][0]["verdict"]
    assert by[7]["scores"] == pre["shots"][1]["scores"]      # 陌生条目不动
    regen = by[1]["regen"]                                   # regen 半边已替换
    assert regen["engine_version"] == "fl2va-int8/euler+simple/15/896x512"
    assert regen["prompt_version"] == "ab12cd34"
    assert regen["video_content_hash"] == VCH_EP01
    # JSON 损坏 → 空重建（既有条目不救回——Phase 18 挂载前仅 JSON-parse 决策）
    (tmp_path / "roundtrip.json").write_text("{corrupt", encoding="utf-8")
    h3m.write_roundtrip_sidecar(
        str(tmp_path), h3m.build_sidecar_entries(results, VCH_EP01, 896, 512))
    data2 = read_sidecar(tmp_path)
    assert [s["shot_id"] for s in data2["shots"]] == [1]
    assert validate_sidecar(data2) == []


def test_sidecar_refuses_invalid_path(tmp_path, monkeypatch):
    """regen.path 含 ..（路径穿越）→ schema pattern 拒 → sys.exit 且文件
    未写（T-20-08：写前 Draft202012Validator 全量自校验是客户端自构造
    path 之外的兜底）。"""
    monkeypatch.setattr(h3m, "probe_duration_sec", lambda p: 1.0)
    entries = [{"shot_id": 1, "regen": {
        "path": "roundtrip/../../etc/shot_001_regen.mp4",
        "video_content_hash": "a" * 16, "engine_name": "comfyui-fl2va",
        "engine_version": "v", "prompt_version": "p",
        "duration_sec": 1.0, "width": 896, "height": 512}}]
    with pytest.raises(SystemExit):
        h3m.write_roundtrip_sidecar(str(tmp_path), entries)
    assert not (tmp_path / "roundtrip.json").exists()        # 拒绝落盘


# ── WR-04：预存坏条目不阻塞批末落盘（防重试死锁）──────────────────────────

def test_sidecar_preexisting_bad_entry_skipped_not_deadlocked(tmp_path, monkeypatch):
    """WR-04：预存坏条目（hand-edit / 未来 schema 演进产物）不再整批
    sys.exit 卡死重试——per-shot str warning + 剔除 + 原文件 .bak 备份；
    本批结果与合法预存条目照常落盘。"""
    monkeypatch.setattr(h3m, "probe_duration_sec", lambda p: 2.0)
    pre = {"schema_version": "1.3", "shots": [
        {"shot_id": 5, "regen": {
            "path": "roundtrip/../../evil.mp4",        # schema pattern 拒
            "video_content_hash": "a" * 16, "engine_name": "e",
            "engine_version": "v", "prompt_version": "p"}},
        {"shot_id": 6, "scores": {"judge": {
            "attribution": "prompt_faithful", "confidence": 0.8,
            "reason": "运动贴合"}}}]}
    (tmp_path / "roundtrip.json").write_text(
        json.dumps(pre, ensure_ascii=False), encoding="utf-8")
    mp4 = tmp_path / "roundtrip" / "shot_001_regen.mp4"
    mp4.parent.mkdir()
    mp4.write_bytes(b"x" * 2048)
    entries = h3m.build_sidecar_entries([sidecar_result(1, str(mp4))],
                                        VCH_EP01, 896, 512)
    warns = h3m.write_roundtrip_sidecar(str(tmp_path), entries)
    data = read_sidecar(tmp_path)
    assert validate_sidecar(data) == []
    by = {s["shot_id"]: s for s in data["shots"]}
    assert set(by) == {1, 6}                          # 坏条目 5 剔除，其余保留
    assert by[6]["scores"] == pre["shots"][1]["scores"]
    assert any("shot 5" in w and "剔除" in w for w in warns)
    baks = list(tmp_path.glob("roundtrip.json.bak-*"))
    assert len(baks) == 1                             # 原文件已备份（可找回）
    assert json.loads(baks[0].read_text(encoding="utf-8")) == pre


def test_sidecar_bad_preexisting_entry_e2e_warning_flush(tmp_path, monkeypatch):
    """WR-04 e2e：run 2 只处理 shot 1（抽样），shot 2 预存条目坏 → 批不
    sys.exit、正常完成、剔除说明进 warnings.json、原文件有 .bak。"""
    work = make_workdir(tmp_path, n_shots=2)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(2)))
    assert run_main(work) == 0
    sc = read_sidecar(work)
    sc["shots"][1]["regen"]["path"] = "roundtrip/../../evil.mp4"   # shot 2 弄坏
    (work / "roundtrip.json").write_text(
        json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8")
    fake2 = FakeHTTP([(200, {"system": "ok"}), *GUARD_FREES])
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work, ["--sample-shots", "1"]) == 0    # 只 shot 1（cache hit）
    data = read_sidecar(work)
    assert [s["shot_id"] for s in data["shots"]] == [1]    # 坏条目已剔除
    assert validate_sidecar(data) == []
    warns = read_warnings(work)
    assert any(isinstance(w, str) and "shot 2" in w and "剔除" in w
               for w in warns)
    assert list(work.glob("roundtrip.json.bak-*"))


# ── WR-05：ffmpeg/curl 返回码 fail-loud（stderr 进 error detail）───────────

def test_ffmpeg_failure_no_stale_frame_survives(tmp_path, monkeypatch):
    """WR-05：ffmpeg rc!=0 → RuntimeError 附 rc/dest/stderr；提取前旧 dest
    已删——失败后无残留旧帧可被误当新帧上传。"""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    stale = frames_dir / "kst_ab12cd34ef567890_shot003_ff.jpg"
    stale.write_bytes(b"stale-old-frame")

    def fake_run(cmd, **kw):
        return _FakeProc("", returncode=1, stderr=b"ffmpeg decode error boom")

    monkeypatch.setattr(h3m.subprocess, "run", fake_run)
    shot = {"id": 3, "start_sec": 1.0, "end_sec": 2.5, "duration": 1.5}
    with pytest.raises(RuntimeError) as ei:
        h3m.extract_endpoint_frames("/src/h264.mp4", shot,
                                    "ab12cd34ef567890", str(frames_dir))
    msg = str(ei.value)
    assert "ffmpeg 帧提取失败" in msg and "rc=1" in msg
    assert "ffmpeg decode error boom" in msg            # stderr 进 detail
    assert not stale.exists()                           # 旧帧已删，无残留


def test_ffmpeg_empty_dest_fails(tmp_path, monkeypatch):
    """WR-05：rc==0 但 dest 未产出（或空文件）同样 fail-loud。"""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    monkeypatch.setattr(h3m.subprocess, "run",
                        lambda cmd, **kw: _FakeProc("", returncode=0))
    shot = {"id": 1, "start_sec": 0.0, "end_sec": 1.0, "duration": 1.0}
    with pytest.raises(RuntimeError):
        h3m.extract_endpoint_frames("/src/h264.mp4", shot,
                                    "ab12cd34ef567890", str(frames_dir))


def test_upload_failures_fail_loud(tmp_path, monkeypatch):
    """WR-05：curl rc!=0（stderr 进 detail）/ 响应非 JSON / 响应无 name
    （服务器 error body 原文进 detail）三种失败都 RuntimeError，不再以
    裸 JSONDecodeError / KeyError 面目出现。"""
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"jpg")
    cases = [
        (_FakeProc("", returncode=7, stderr="curl: connection refused"),
         "rc=7", "connection refused"),
        (_FakeProc("not-json-at-all", returncode=0),
         "非 JSON", "not-json-at-all"),
        (_FakeProc(json.dumps({"error": "disk full"}), returncode=0),
         "无 name", "disk full"),
    ]
    for proc, *needles in cases:
        monkeypatch.setattr(h3m.subprocess, "run", lambda cmd, **kw: proc)
        with pytest.raises(RuntimeError) as ei:
            h3m.upload_image(str(img), "http://127.0.0.1:8188")
        for needle in needles:
            assert needle in str(ei.value), (needle, str(ei.value))


def test_ffmpeg_failure_e2e_shot_failed_with_detail(tmp_path, monkeypatch, capsys):
    """WR-05 e2e：批中 ffmpeg 失败 → 单镜 failed（不崩批）、sidecar
    status.error 含 ffmpeg stderr 片段、无 cache 写入。"""
    work = make_workdir(tmp_path, n_shots=1)
    fake = FakeHTTP([(200, {"system": "ok"}), *GUARD_FREES])
    patch_pipeline(monkeypatch, fake)
    patched_run = h3m.subprocess.run

    def failing_ffmpeg(cmd, **kw):
        if cmd[0] == "ffmpeg":
            return _FakeProc("", returncode=1, stderr=b"Invalid data found")
        return patched_run(cmd, **kw)

    monkeypatch.setattr(h3m.subprocess, "run", failing_ffmpeg)
    assert run_main(work, ["--gpu-index", "1"]) == 0
    out = capsys.readouterr().out
    assert "failed=1" in out and "rendered=0" in out
    sc = read_sidecar(work)
    assert sc["shots"][0]["status"]["state"] == "failed"
    assert "Invalid data found" in sc["shots"][0]["status"]["error"]
    assert not (work / "route_cache" / "h3_regen" / "shot_001.json").exists()


# ── CR-01：下载原子性 + stale meta/截断产物的 cache-hit 拦截 ────────────────

def test_view_download_atomic_on_mid_transfer_failure(tmp_path, monkeypatch):
    """下载中途异常（IncompleteRead 形）→ dest 不存在、.part 清理、异常上抛
    ——半截文件永不占住最终路径（CR-01 主张）。"""
    dest = tmp_path / "shot_001_regen.mp4"

    class _Boom(Exception):
        pass

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            raise _Boom("IncompleteRead(0 bytes read)")

    monkeypatch.setattr(h3m.urllib.request, "urlopen",
                        lambda url, timeout=None: _Resp())
    with pytest.raises(_Boom):
        h3m._view_download({"filename": "a.mp4", "subfolder": ""},
                           "http://127.0.0.1:8188", str(dest))
    assert not dest.exists()                          # 最终路径从未被触碰
    assert not (tmp_path / "shot_001_regen.mp4.part").exists()   # .part 已清理


def test_view_download_success_leaves_no_part(tmp_path, monkeypatch):
    """成功路径：字节经 .part 落位 dest，无 .part 残留。"""
    dest = tmp_path / "shot_001_regen.mp4"

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"mp4-bytes" * 512

    monkeypatch.setattr(h3m.urllib.request, "urlopen",
                        lambda url, timeout=None: _Resp())
    h3m._view_download({"filename": "a.mp4", "subfolder": ""},
                       "http://127.0.0.1:8188", str(dest))
    assert dest.read_bytes() == b"mp4-bytes" * 512
    assert not (tmp_path / "shot_001_regen.mp4.part").exists()


def test_truncated_mp4_rejected_as_cache_hit(tmp_path, monkeypatch, capsys):
    """CR-01 三步序列回归锚：Run A 渲染成功 → mp4 被外改/截断（size 仍 >1KB）
    → Run C 虽 4-tuple 全等、size 过线，mp4_sha256 不一致 → miss 重渲
    （旧实现在此 true false-hit，坏视频流入 roundtrip.json）。"""
    work = make_workdir(tmp_path, n_shots=1)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(1)))
    assert run_main(work) == 0
    mp4 = work / "roundtrip" / "shot_001_regen.mp4"
    mp4.write_bytes(b"y" * 4096)                      # 截断/外改（>1KB 过 size 线）
    fake2 = FakeHTTP(ok_responses(1))
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake2.calls) == 1   # miss → 重渲
    out = capsys.readouterr().out
    assert "cache hit" not in out and "rendered=1" in out


# ── WR-02：length 参与命中比对——重分割不复用旧边界渲染 ─────────────────────

def test_resegmentation_same_prompt_invalidates(tmp_path, monkeypatch, capsys):
    """WR-02：同源视频（vch 不变）重分割——shot 1 边界 2.0s→5.5s（length
    124→141）而 prompt_text 恰未变 → 4-tuple 全等也 miss 重渲（旧实现复用
    旧 start/end_sec 首/尾帧渲染）。"""
    work = make_workdir(tmp_path, n_shots=2)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(2)))
    assert run_main(work) == 0
    # 模拟重分割：只动 shots.json 边界/时长；prompts.json 的 prompt_text 不动
    shots = json.loads((work / "shots.json").read_text(encoding="utf-8"))
    shots[0]["start_sec"] = 0.0
    shots[0]["end_sec"] = 5.5
    shots[0]["duration"] = 5.5
    (work / "shots.json").write_text(
        json.dumps(shots, ensure_ascii=False), encoding="utf-8")
    fake2 = FakeHTTP([(200, {"system": "ok"}), *GUARD_FREES,
                      (200, {"prompt_id": "pid-001b"}),
                      (200, history_success("pid-001b",
                                            "kst_x_shot001_00002_.mp4"))])
    patch_pipeline(monkeypatch, fake2)
    assert run_main(work) == 0
    assert sum(u.endswith("/prompt") for u, _ in fake2.calls) == 1   # 边界变了 → 重渲
    payload = [p for u, p in fake2.calls if u.endswith("/prompt")][0]
    assert payload["prompt"]["20"]["inputs"]["length"] == 141       # 5.5s 网格值
    out = capsys.readouterr().out
    assert out.count("cache hit, skipping") == 1                    # 未变镜仍命中


# ── WR-03：批级互斥锁 + PID 后缀 tmp（并发防护）────────────────────────────

def test_atomic_write_tmp_pid_stamped(tmp_path, monkeypatch):
    """WR-03(d)：原子写 tmp 名带 PID——并发写同一目标不共享 tmp，杜绝互相
    replace 半截内容。"""
    replaced = {}
    real_replace = h3m.os.replace

    def fake_replace(src, dst):
        replaced["src"] = src
        return real_replace(src, dst)

    monkeypatch.setattr(h3m.os, "replace", fake_replace)
    target = tmp_path / "x.json"
    h3m._atomic_write_json(str(target), {"a": 1})
    assert replaced["src"].endswith(f".tmp.{os.getpid()}")
    assert json.loads(target.read_text(encoding="utf-8"))["a"] == 1
    assert not any(p.name == f"x.json.tmp.{os.getpid()}"
                   for p in tmp_path.iterdir())          # tmp 已消费


def test_batch_lock_second_instance_degrades(tmp_path, monkeypatch, capsys):
    """WR-03：另一实例持锁 → 本实例 str warning + rc=0 优雅退出——gate 已过、
    guard 未跑（不白杀 TTS）、零提交。"""
    import fcntl
    work = make_workdir(tmp_path, n_shots=1)
    lock_dir = work / "route_cache"
    lock_dir.mkdir(parents=True)
    lf = open(lock_dir / "h3_regen.lock", "w")
    fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        fake = FakeHTTP([(200, {"system": "ok"})])
        calls = patch_pipeline(monkeypatch, fake)
        assert run_main(work, ["--gpu-index", "1"]) == 0
        assert sum(u.endswith("/prompt") for u, _ in fake.calls) == 0   # 零提交
        assert not any(c and c[0] == "ss" for c in calls)               # guard 未执行
        out = capsys.readouterr().out
        assert "另一 h3_regen 实例" in out
        warns = read_warnings(work)
        assert any(isinstance(w, str) and "h3_regen.lock" in w
                   and "实例" in w for w in warns)
    finally:
        fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        lf.close()


def test_batch_lock_released_after_run(tmp_path, monkeypatch):
    """WR-03：main 结束后锁被释放（finally）——同进程顺序二跑（断点续跑
    单元测试的形态）不被自己的残留锁卡死。"""
    work = make_workdir(tmp_path, n_shots=1)
    patch_pipeline(monkeypatch, FakeHTTP(ok_responses(1)))
    assert run_main(work) == 0
    # 锁已释放：再次 acquire 应成功
    handle = h3m.acquire_batch_lock(str(work))
    assert handle is not None
    h3m.release_batch_lock(handle)
