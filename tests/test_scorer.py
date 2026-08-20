"""scorer 测试 —— FakeSigLIP + subprocess fake，零网络零 GPU（21-01 Task 3）。

覆盖（行为清单逐项）：
  * 帧窗数学锚点：dur=6.73 的 t 序列（1.6825/5.0475）+ 全序列落在
    [25%dur, 75%dur] + t=0/t=end 结构性不可达；短镜端点 clamp
    （dur=0.5 j=7 → 0.3；dur=0.15 → 0 下限）；plan_frames t_pct 25→75。
  * FakeSigLIP（固定向量替身）：orig_j = e_j、regen_j = cos(θ_j)e_j +
    sin(θ_j)u → per_position_cos == cos(θ_j)（tol 1e-6）+ mean 即 score
    ——打分数学正确性的精确断言，非仅"有值"。
  * cache：同 key 二跑零加载（load_siglip 计数）；regen mp4 字节变了
    （sha16 变）二跑必重打分；帧清单字段齐（frames.orig/regen 各 8 条
    {j, t_pct, t_sec, path} + per_position_cos + score + model，SC2 审计面）。
  * sidecar 浅合并：预存 scores.judge + verdict → scorer 写后两者原样、
    midframe_sim 更新（DATASET-01 merge 语义）。
  * degrade：load_siglip 抛 → rc=0 + scorer_model_missing dict warning +
    sidecar 原样不动（RT-04）。
  * ffmpeg fail-loud：rc!=0 → RuntimeError 附 rc/stderr；提取前旧 dest
    先删（失败无残留）；rc==0 但 dest 未产出同样 fail-loud（WR-05）。
"""
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "scorer", REPO_ROOT / "analysis" / "roundtrip" / "scorer.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


# ── 替身 ────────────────────────────────────────────────────────────────────

class _FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def make_workdir(tmp_path, n_shots=1, duration=6.73, regen_bytes_by_id=None):
    """最小 work_dir：shots.json + prompts.json（顶层 list 带 prompt_text）+
    假 h264.mp4 + roundtrip/shot_XXX_regen.mp4 假字节 + roundtrip.json 预存
    regen 条目（duration_sec 预置——避免 ffprobe 路径）。"""
    work = tmp_path / "work"
    work.mkdir(parents=True)
    shots = []
    for i in range(n_shots):
        start = i * duration
        shots.append({"id": i + 1, "start_sec": start,
                      "end_sec": start + duration, "duration": duration})
    (work / "shots.json").write_text(json.dumps(shots), encoding="utf-8")
    prompts = [{"shot_id": s["id"], "prompt_text": f"测试 prompt {s['id']}"}
               for s in shots]
    (work / "prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "h264.mp4").write_bytes(b"fake-h264-bytes-0123456789")
    rt = work / "roundtrip"
    rt.mkdir()
    entries = []
    for s in shots:
        mp4 = rt / f"shot_{s['id']:03d}_regen.mp4"
        mp4.write_bytes((regen_bytes_by_id or {}).get(
            s["id"], b"fake-regen-mp4-" + bytes([s["id"]])))
        entries.append({"shot_id": s["id"], "regen": {
            "path": f"roundtrip/shot_{s['id']:03d}_regen.mp4",
            "video_content_hash": "a" * 16,
            "engine_name": "comfyui-fl2va",
            "engine_version": "fl2va-int8/euler+simple/15/896x512",
            "prompt_version": "pv1",
            "duration_sec": duration,
            "width": 896, "height": 512}})
    (work / "roundtrip.json").write_text(
        json.dumps({"schema_version": "1.3", "shots": entries},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return work


def run_main(work, extra_args=None):
    """argv 注入调 sc.main()，返回 rc。"""
    argv = ["scorer.py", "--work-dir", str(work)]
    if extra_args:
        argv += extra_args
    old_argv = sys.argv
    sys.argv = argv
    try:
        rc = sc.main()
    finally:
        sys.argv = old_argv
    return rc


_JPEG_CACHE: dict = {}


def _valid_jpeg_bytes() -> bytes:
    """真 PIL 可读的最小 JPEG（score_shot 的 Image.open 需要——纯假字节会
    UnidentifiedImageError）。同色缓存一次。"""
    if "b" not in _JPEG_CACHE:
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 36), (120, 130, 40)).save(buf, "JPEG")
        _JPEG_CACHE["b"] = buf.getvalue()
    return _JPEG_CACHE["b"]


def patch_scorer(monkeypatch, embed_impl=None, load_impl=None):
    """打满 patch 点：subprocess.run（ffmpeg 写可读假 jpg / 其余回空）+
    load_siglip / embed_frames 替身。返回 (load 计数器, subprocess 调用记录)。"""
    calls = []
    loads = {"n": 0}

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if cmd[0] == "ffmpeg":
            dest = [a for a in cmd if a.endswith(".jpg")][-1]
            Path(dest).write_bytes(_valid_jpeg_bytes())
            return _FakeProc("")
        return _FakeProc("")

    def fake_load(device):
        loads["n"] += 1
        return ("fake-model", "fake-processor", "cpu")

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    monkeypatch.setattr(sc, "load_siglip", load_impl or fake_load)
    if embed_impl is not None:
        monkeypatch.setattr(sc, "embed_frames", embed_impl)
    return loads, calls


def make_fake_embed(work, sid, thetas):
    """FakeSigLIP：embed_frames 替身。扫描 frames 目录按**文件名里的
    side/j 标记**构造固定向量——orig_j = e_j（单位基）、regen_j =
    cos(θ_j)·e_j + sin(θ_j)·e_last（与 e_j 已知夹角 θ_j）→ L2 归一后
    逐位 dot == cos(θ_j) 精确成立。同时断言提取确产出了 16 张约定名帧。"""
    n = len(thetas)
    dim = n + 1

    def fake_embed(model, processor, device, frames):
        frames_dir = os.path.join(str(work), sc.FRAMES_SUBDIR)
        files = sorted(os.listdir(frames_dir))
        expected = sorted(f"shot_{sid:03d}_{side}_{j:02d}.jpg"
                          for side in ("orig", "regen") for j in range(n))
        assert files == expected, files       # 提取产物命名/数量契约
        by_name = {}
        for side in ("orig", "regen"):
            for j in range(n):
                v = np.zeros(dim)
                if side == "orig":
                    v[j] = 1.0
                else:
                    v[j] = math.cos(thetas[j])
                    v[dim - 1] = math.sin(thetas[j])
                by_name[f"shot_{sid:03d}_{side}_{j:02d}.jpg"] = v
        # score_shot 的传入序 = orig 0..n-1 + regen 0..n-1
        ordered = [f"shot_{sid:03d}_orig_{j:02d}.jpg" for j in range(n)] \
            + [f"shot_{sid:03d}_regen_{j:02d}.jpg" for j in range(n)]
        return np.array([by_name[name] for name in ordered])

    return fake_embed


def read_cache(work, sid) -> dict:
    return json.loads((work / sc.SCORER_CACHE_SUBDIR
                       / f"shot_{sid:03d}.json").read_text(encoding="utf-8"))


def read_sidecar(work) -> dict:
    return json.loads((work / "roundtrip.json").read_text(encoding="utf-8"))


def validate_sidecar(data: dict) -> list:
    schema = json.loads(sc.SCHEMA_PATH.read_text(encoding="utf-8"))
    return list(Draft202012Validator(schema).iter_errors(data))


def read_warnings(work) -> list:
    return json.loads((work / "route_cache" / "warnings.json")
                      .read_text(encoding="utf-8"))["warnings"]


# ── 帧窗数学（SCORE-01 锚点）────────────────────────────────────────────────

def test_frame_ts_window_anchors():
    """dur=6.73, n=8：首 1.6825 / 尾 5.0475；全序列落在 [25%dur, 75%dur]
    （t=0 / t=end 结构性不可达——窗口定义本身排除被 condition 的端点帧）。"""
    f = sc.frame_ts
    ts = [f(6.73, j) for j in range(8)]
    assert ts[0] == pytest.approx(6.73 * 0.25, abs=1e-9)
    assert ts[7] == pytest.approx(6.73 * 0.75, abs=1e-9)
    assert all(6.73 * 0.25 - 1e-9 <= t <= 6.73 * 0.75 + 1e-9 for t in ts)
    assert all(0.0 < t < 6.73 for t in ts)          # t=0/t=end 不可达
    assert all(t > 0.0 for t in ts)
    # 步长恒 = dur·50%/7（等距窗位）
    for j in range(7):
        assert ts[j + 1] - ts[j] == pytest.approx(6.73 * 0.5 / 7, abs=1e-9)


def test_frame_ts_endpoint_clamp():
    """短镜端点 clamp（Pitfall 3）：dur=0.5 j=7 → min(0.375, 0.3)=0.3；
    dur=0.15 → max(dur-0.2, 0)=0 下限；dur=0.3 cap=0.1。"""
    assert sc.frame_ts(0.5, 7) == pytest.approx(0.3, abs=1e-12)
    assert sc.frame_ts(0.15, 7) >= 0.0
    assert sc.frame_ts(0.15, 7) == pytest.approx(0.0, abs=1e-12)
    assert sc.frame_ts(0.3, 7) == pytest.approx(0.1, abs=1e-12)
    # n 可参数化（默认 8；n=4 时窗位 25/41.67/58.33/75）
    assert sc.frame_ts(4.0, 0, n=4) == pytest.approx(1.0)
    assert sc.frame_ts(4.0, 3, n=4) == pytest.approx(3.0)


def test_plan_frames_pct_series():
    """plan_frames：t_pct 序列 25.0 → 75.0 单调；j 连续；t_sec 是 clamp 后
    实际时间戳（dur 足够长时无 clamp，t_sec == dur·pct）。"""
    p = sc.plan_frames(6.73, 8)
    assert len(p) == 8
    pcts = [e["t_pct"] for e in p]
    assert pcts[0] == 25.0 and pcts[-1] == 75.0
    assert pcts == sorted(pcts)
    assert [e["j"] for e in p] == list(range(8))
    for e in p:
        # t_sec 是 clamp 后时间戳（round 6 位）；dur 足够长时 == dur·窗位
        assert e["t_sec"] == pytest.approx(
            6.73 * (0.25 + 0.5 * e["j"] / 7), abs=1e-6)
        assert set(e) == {"j", "t_pct", "t_sec"}


# ── FakeSigLIP 数值精确性（打分数学正确性）──────────────────────────────────

def test_fake_siglip_exact_per_position_cos(tmp_path, monkeypatch):
    """FakeSigLIP 固定向量注入：per_position_cos == cos(θ_j)（tol 1e-6）、
    mean 即 score（round 4）；sidecar scores.midframe_sim 同值 + model 标识。"""
    thetas = [0.10 * (j + 1) for j in range(8)]      # θ_j = 0.1..0.8
    work = make_workdir(tmp_path, n_shots=1, duration=6.73)
    loads, _calls = patch_scorer(
        monkeypatch, embed_impl=make_fake_embed(work, 1, thetas))
    assert run_main(work, ["--device", "cpu"]) == 0
    assert loads["n"] == 1
    payload = read_cache(work, 1)
    expected_cos = [math.cos(t) for t in thetas]
    for got, want in zip(payload["per_position_cos"], expected_cos):
        assert got == pytest.approx(want, abs=1e-6)
    assert payload["score"] == pytest.approx(
        round(sum(expected_cos) / 8, 4), abs=1e-9)
    side = read_sidecar(work)
    by = {s["shot_id"]: s for s in side["shots"]}
    assert by[1]["scores"]["midframe_sim"]["score"] == payload["score"]
    assert by[1]["scores"]["midframe_sim"]["model"] == sc.MODEL_LABEL
    assert validate_sidecar(side) == []


def test_cache_manifest_audit_fields(tmp_path, monkeypatch):
    """cache 审计清单字段齐（SC2 硬要求）：frames.orig/regen 各 8 条
    {j, t_pct, t_sec, path}（path 存在且按 side 命名）+ per_position_cos(8)
    + score + model + device + scored_at + key 五字段。"""
    thetas = [0.1 * (j + 1) for j in range(8)]
    work = make_workdir(tmp_path, n_shots=1)
    patch_scorer(monkeypatch, embed_impl=make_fake_embed(work, 1, thetas))
    assert run_main(work) == 0
    payload = read_cache(work, 1)
    for field in ("video_content_hash", "regen_mp4_sha256_16", "model",
                  "n_frames", "window"):
        assert field in payload, field
    assert payload["model"] == sc.MODEL_LABEL
    assert payload["n_frames"] == 8
    assert payload["window"] == [25.0, 75.0]
    for side in ("orig", "regen"):
        frames = payload["frames"][side]
        assert len(frames) == 8
        for e in frames:
            assert set(e) == {"j", "t_pct", "t_sec", "path"}
            assert os.path.isfile(e["path"])
            assert f"_{side}_" in os.path.basename(e["path"])
    assert len(payload["per_position_cos"]) == 8
    assert "device" in payload and "scored_at" in payload
    # regen_mp4_sha256_16 与产物字节对应（分辨率/引擎身份联动维，Pitfall 7）
    mp4 = work / "roundtrip" / "shot_001_regen.mp4"
    h = __import__("hashlib").sha256(mp4.read_bytes()).hexdigest()
    assert payload["regen_mp4_sha256_16"] == h[:16]


# ── cache miss/hit（断点续跑语义）───────────────────────────────────────────

def test_cache_hit_second_run_zero_load(tmp_path, monkeypatch):
    """同 key 二跑：全部 cache 命中 → load_siglip 零调用（SigLIP 不进内存）。"""
    thetas = [0.2 * (j + 1) for j in range(8)]
    work = make_workdir(tmp_path, n_shots=1)
    loads, _ = patch_scorer(monkeypatch,
                            embed_impl=make_fake_embed(work, 1, thetas))
    assert run_main(work) == 0
    assert loads["n"] == 1
    assert run_main(work) == 0                    # 二跑全 hit
    assert loads["n"] == 1                        # 零加载


def test_cache_miss_on_different_regen_bytes(tmp_path, monkeypatch):
    """regen mp4 字节变了（sha16 变）→ cache key 不等 → 必重打分。"""
    thetas = [0.15 * (j + 1) for j in range(8)]
    work = make_workdir(tmp_path, n_shots=1)
    loads, _ = patch_scorer(monkeypatch,
                            embed_impl=make_fake_embed(work, 1, thetas))
    assert run_main(work) == 0
    sha1 = read_cache(work, 1)["regen_mp4_sha256_16"]
    (work / "roundtrip" / "shot_001_regen.mp4").write_bytes(
        b"different-regen-bytes-896x512-vs-1344x768")
    assert run_main(work) == 0
    assert loads["n"] == 2                         # 重打分
    payload2 = read_cache(work, 1)
    import hashlib as _hl
    sha2 = _hl.sha256(
        (work / "roundtrip" / "shot_001_regen.mp4").read_bytes()).hexdigest()
    assert payload2["regen_mp4_sha256_16"] == sha2[:16]
    assert payload2["regen_mp4_sha256_16"] != sha1


# ── CR-01：cache-hit 回填 sidecar（断点续跑完整性）──────────────────────────

def test_cache_hit_backfills_missing_sidecar_half(tmp_path, monkeypatch):
    """CR-01：批末 sidecar 写未发生（cache 已持久、sidecar 无分数）→ 重跑
    全命中也从 cache 回填半边——零模型加载，分数回到 roundtrip.json。"""
    thetas = [0.25 * (j + 1) for j in range(8)]
    work = make_workdir(tmp_path, n_shots=1)
    loads, _ = patch_scorer(monkeypatch,
                            embed_impl=make_fake_embed(work, 1, thetas))
    assert run_main(work) == 0
    cached_score = read_cache(work, 1)["score"]
    # 模拟中断：roundtrip.json 回到只有 regen 半边的状态（cache 保留）
    side = read_sidecar(work)
    side["shots"][0].pop("scores", None)
    (work / "roundtrip.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2), encoding="utf-8")
    assert run_main(work) == 0                     # 全命中重跑
    assert loads["n"] == 1                         # 仍零模型加载
    after = read_sidecar(work)
    assert validate_sidecar(after) == []
    entry = after["shots"][0]
    assert entry["scores"]["midframe_sim"]["score"] == cached_score
    assert entry["scores"]["midframe_sim"]["model"] == sc.MODEL_LABEL


def test_partial_hit_backfills_interrupted_half(tmp_path, monkeypatch):
    """CR-01 命中子集：shot 1 cache 在而 sidecar 半边丢、shot 2 cache 丢 →
    重跑 shot 1 回填（零前向）+ shot 2 重打分，批尾一次写齐两条半边。"""
    thetas = [0.18 * (j + 1) for j in range(8)]

    def embed_by_position(model, processor, device, frames):
        """多镜通用的位置序替身（embed_frames 收到的 frames 恒为 orig 0..7
        + regen 0..7 的 PIL 序列——不依赖 frames 目录的单镜假设）。"""
        dim = 8 + 1
        vecs = []
        for idx in range(16):
            v = np.zeros(dim)
            j = idx % 8
            if idx < 8:
                v[j] = 1.0
            else:
                v[j] = math.cos(thetas[j])
                v[dim - 1] = math.sin(thetas[j])
            vecs.append(v)
        return np.array(vecs)

    work = make_workdir(tmp_path, n_shots=2)
    loads, _ = patch_scorer(monkeypatch, embed_impl=embed_by_position)
    assert run_main(work) == 0
    cached1 = read_cache(work, 1)["score"]
    cached2 = read_cache(work, 2)["score"]
    # 模拟中断：sidecar 两条半边都没落 + shot 2 cache 也没写成功
    side = read_sidecar(work)
    for s in side["shots"]:
        s.pop("scores", None)
    (work / "roundtrip.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2), encoding="utf-8")
    (work / sc.SCORER_CACHE_SUBDIR / "shot_002.json").unlink()
    assert run_main(work) == 0
    assert loads["n"] == 2                         # 只有 shot 2 重打分
    after = read_sidecar(work)
    assert validate_sidecar(after) == []
    by = {s["shot_id"]: s for s in after["shots"]}
    assert by[1]["scores"]["midframe_sim"]["score"] == cached1   # cache 回填
    assert by[2]["scores"]["midframe_sim"]["score"] == cached2   # 重打分


# ── sidecar 浅合并（DATASET-01 merge 语义）──────────────────────────────────

def test_sidecar_shallow_merge_preserves_judge_and_verdict(tmp_path, monkeypatch):
    """预存 scores.judge + verdict → scorer 写后两者原样、midframe_sim 更新
    （scores 子对象浅合并，绝不整体替换）。"""
    thetas = [0.1 * (j + 1) for j in range(8)]
    work = make_workdir(tmp_path, n_shots=1)
    judge_half = {"attribution": "prompt_faithful", "confidence": 0.8,
                  "reason": "运动贴合中段帧"}
    verdict = {"decision": "accepted", "source": "human",
               "decided_at": "2026-08-20T00:00:00"}
    side = read_sidecar(work)
    side["shots"][0]["scores"] = {"judge": judge_half}
    side["shots"][0]["verdict"] = verdict
    (work / "roundtrip.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2), encoding="utf-8")
    patch_scorer(monkeypatch, embed_impl=make_fake_embed(work, 1, thetas))
    assert run_main(work) == 0
    after = read_sidecar(work)
    assert validate_sidecar(after) == []
    entry = after["shots"][0]
    assert entry["scores"]["judge"] == judge_half       # 对侧半边不丢
    assert entry["verdict"] == verdict                  # verdict 原样
    assert "midframe_sim" in entry["scores"]            # 新半边落位
    assert entry["regen"]["engine_version"].startswith("fl2va")  # regen 不动


# ── degrade（RT-04）─────────────────────────────────────────────────────────

def test_scorer_model_missing_degrade(tmp_path, monkeypatch):
    """load_siglip 抛 → rc=0 + scorer_model_missing dict warning + sidecar
    原样不动（绝不 sys.exit 炸批）。"""
    work = make_workdir(tmp_path, n_shots=1)
    before = (work / "roundtrip.json").read_bytes()

    def exploding(device):
        raise RuntimeError("LocalEntryNotFoundError: weights incomplete")

    patch_scorer(monkeypatch, load_impl=exploding)
    assert run_main(work) == 0
    after = (work / "roundtrip.json").read_bytes()
    assert after == before                              # sidecar 原样
    warns = read_warnings(work)
    dict_warns = [w for w in warns if isinstance(w, dict)
                  and w.get("code") == "scorer_model_missing"]
    assert len(dict_warns) == 1
    assert "RuntimeError" in dict_warns[0]["detail"]    # 异常类型进 detail
    assert not (work / sc.SCORER_CACHE_SUBDIR / "shot_001.json").exists()


# ── ffmpeg fail-loud（WR-05）────────────────────────────────────────────────

def test_ffmpeg_failure_no_stale_frame(tmp_path, monkeypatch):
    """rc!=0 → RuntimeError 附 rc/dest/stderr 摘录；提取前旧 dest 已删——
    失败后无残留旧帧可被误当新帧。"""
    dest = tmp_path / "frame.jpg"
    dest.write_bytes(b"stale-old-frame")
    monkeypatch.setattr(sc.subprocess, "run",
                        lambda cmd, **kw: _FakeProc("", returncode=1,
                                                    stderr=b"ffmpeg boom"))
    with pytest.raises(RuntimeError) as ei:
        sc.extract_frame("/src/h264.mp4", 1.5, str(dest))
    msg = str(ei.value)
    assert "ffmpeg 帧提取失败" in msg and "rc=1" in msg and "ffmpeg boom" in msg
    assert not dest.exists()                           # 旧帧已删，无残留


def test_ffmpeg_empty_dest_fails(tmp_path, monkeypatch):
    """rc==0 但 dest 未产出（或空文件）同样 fail-loud。"""
    monkeypatch.setattr(sc.subprocess, "run",
                        lambda cmd, **kw: _FakeProc("", returncode=0))
    with pytest.raises(RuntimeError):
        sc.extract_frame("/src/h264.mp4", 1.5, str(tmp_path / "f.jpg"))
    # rc==0 且写了空文件 → 同样拒绝
    dest = tmp_path / "g.jpg"

    def run_empty(cmd, **kw):
        Path([a for a in cmd if a.endswith(".jpg")][-1]).write_bytes(b"")
        return _FakeProc("", returncode=0)

    monkeypatch.setattr(sc.subprocess, "run", run_empty)
    with pytest.raises(RuntimeError):
        sc.extract_frame("/src/h264.mp4", 1.5, str(dest))
