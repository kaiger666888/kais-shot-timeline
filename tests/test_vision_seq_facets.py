"""vision_seq_facets 测试 —— monkeypatch 引擎，零网络零 GPU。

覆盖（19-01 Task 3 行为清单）：
  * 采样：窗口 >8 帧恰取 ≤8 且首尾在列；≤8 全取；_ds1280 变体忽略。
  * 只填空缺：action/camera 已有值零改动；空缺被填充。
  * cache 幂等：二跑零引擎调用；prompt_version 篡改 → miss 重拉；
    ear_on/ear_off 双信封隔离共存（切换 ear 重拉、不丢数据）。
  * 合并确定性：temporal/longest 纯归约同输入同输出、零引擎。
  * graceful-degrade：引擎不可用 → [vision-seq] warning + exit 0 + facet 保持 ""。
  * 生命周期：observe 中途抛异常的引擎也被 stop_if_owned。
  * sidecar：他 step 条目保留、重跑不 self-accumulate。
  * ear：有 audio → 提问含音频摘要子串；--no-ear / 无文件 → 不含；
    words/reproduction/spk_id 白名单外字段值永不进提问串。
  * 无 audio 文件运行与显式 --no-ear 运行产出的 prompts.json byte-identical。
  * 零修改短路：全满 prompts.json 跑后文件 bytes/mtime 不变。
  * 预判生命周期：全 cache 命中时 QwenEye 类从未被实例化。
  * llm 策略：ask_text 合并 + merged_B 落 cache（二跑零引擎零文本调用）。
  * camera 单帧镜：无相邻对 → warning + 保持 ""（action 仍填）。
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = REPO_ROOT / "analysis"

# vision_seq_facets import 时把 analysis/ 塞进 sys.path（为了 engine_clients），
# 直接用 spec 加载保持与其他 test 一致的不污染路径做法。
_spec = importlib.util.spec_from_file_location(
    "vision_seq_facets", ANALYSIS / "vision_seq_facets.py")
vsf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vsf)


def make_workdir(tmp_path, n_shots=2, action_values=None, camera_values=None):
    """搭一个最小 work_dir：shots.json + prompts.json（action/camera 空或给定）
    + frames_5fps 10 帧（t=0..1.8s）+ 假视频文件。

    时窗实况（5fps、帧号 1 起）：shot [i, i+1) → 窗口帧号
    [i*5+1, (i+1)*5+1] —— shot1 = 帧 1..6（6 帧 → action 6 问 + camera 5 对），
    shot2 = 帧 6..10（5 帧 → action 5 问 + camera 4 对）。均 ≤8 全取。
    """
    work = tmp_path / "work"
    work.mkdir(parents=True)
    shots = [{"id": i + 1, "start_sec": i * 1.0, "end_sec": i * 1.0 + 1.0,
              "duration": 1.0} for i in range(n_shots)]
    (work / "shots.json").write_text(
        json.dumps(shots, ensure_ascii=False), encoding="utf-8")
    action_values = action_values or [""] * n_shots
    camera_values = camera_values or [""] * n_shots
    prompts = [{"shot_id": s["id"], "start_sec": s["start_sec"],
                "end_sec": s["end_sec"], "duration": s["duration"],
                "subject": "sub", "action": action_values[i],
                "camera": camera_values[i], "scene": "scene",
                "lighting": "l", "style": "s", "prompt_text": ""}
               for i, s in enumerate(shots)]
    prompts_path = work / "prompts.json"
    prompts_path.write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    frames = work / "frames_5fps"
    frames.mkdir()
    for i in range(1, 11):
        (frames / f"f{i:06d}.jpg").write_bytes(b"\xff\xd8fake")
    (work / "video.mp4").write_bytes(b"fake-video-bytes")
    return work, shots, prompts_path


def make_audio_file(work, shot_ids=(1, 2)):
    """demo 级 audio_semantic.json：白名单字段 + 白名单外负测试标记字段。"""
    shots_audio = []
    for sid in shot_ids:
        shots_audio.append({
            "shot_id": sid,
            "dialogue": {
                "text": "完整对白句子",
                "spk_id": "spk_777",
                "emotion": "HAPPY",
                "words": [{"start": 0.0, "end": 0.5, "text": "WORDLEVEL_MARKER"}],
            },
            "sfx": {"events": ["雨声"], "description": "持续的雨声"},
            "reproduction": {"tts": {"text": "REPRO_MARKER"}},
        })
    path = work / "audio_semantic.json"
    path.write_text(json.dumps({"schema_version": "1.2", "shots": shots_audio},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class FakeEngine:
    """替身引擎：observe_single/observe_pair 恒回固定答案，ask_text 回合并
    答案；视觉/文本调用分开计数，全部提问串记录可查（ear 断言用）。"""

    def __init__(self, answer="毛毛虫递浆果", merge_answer=None):
        self.answer = answer
        self.merge_answer = merge_answer if merge_answer is not None else "合并结果"
        self.calls = 0          # 视觉调用（observe_single / observe_pair）
        self.text_calls = 0     # ask_text 调用
        self.questions = []     # 全部提问串
        self._owned = False
        self._stopped = False

    def ensure_ready(self, timeout_s=None):
        return True, False

    def stop_if_owned(self):
        self._stopped = True

    def observe_single(self, path, question, max_tokens=2000):
        self.calls += 1
        self.questions.append(question)
        return self.answer

    def observe_pair(self, img_a, img_b, question, max_tokens=2000):
        self.calls += 1
        self.questions.append(question)
        return self.answer

    def ask_text(self, question, max_tokens=2000):
        self.text_calls += 1
        self.questions.append(question)
        return self.merge_answer


def run_main(work, prompts_path, extra_args=None):
    """调 vsf.main()（argv 注入）。"""
    argv = ["vision_seq_facets.py",
            "--shots", str(work / "shots.json"),
            "--frames-dir", str(work / "frames_5fps"),
            "--work-dir", str(work),
            "--output", str(prompts_path),
            "--video", str(work / "video.mp4")]
    if extra_args:
        argv += extra_args
    old_argv = sys.argv
    sys.argv = argv
    try:
        rc = vsf.main()
    finally:
        sys.argv = old_argv
    return rc


def patch_engine(monkeypatch, fake):
    monkeypatch.setattr(vsf, "QwenEye", lambda: fake)


def reset_facets(prompts_path):
    """把 prompts.json 的 action/camera 清空（模拟重跑/待填状态）。"""
    prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    for p in prompts:
        p["action"] = ""
        p["camera"] = ""
    prompts_path.write_text(json.dumps(prompts, ensure_ascii=False, indent=2),
                            encoding="utf-8")


# ── 填充 + 采样 ────────────────────────────────────────────────────────────

def test_fills_action_and_camera(tmp_path, monkeypatch):
    """action=逐帧问、camera=相邻对问；temporal 默认合并 =「→」join；
    调用量锁：shot1 = 6 帧 action + 5 对 camera，shot2 = 5 + 4。"""
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine("答")
    patch_engine(monkeypatch, fake)
    rc = run_main(work, pp)
    assert rc == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"] == "→".join(["答"] * 6)
    assert out[0]["camera"] == "→".join(["答"] * 5)
    assert out[1]["action"] == "→".join(["答"] * 5)
    assert out[1]["camera"] == "→".join(["答"] * 4)
    assert fake.calls == (6 + 5) + (5 + 4) == 20
    assert fake.text_calls == 0   # temporal 默认零文本合并调用


def test_select_uniform_frames():
    """窗口 >8 帧恰取 ≤8 且首尾在列；窗口 ≤8 全取；_ds 变体忽略；
    窄窗 1 帧；窗口外空。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        fd = Path(td)
        for i in range(1, 21):                 # t = 0.0 .. 3.8s
            (fd / f"f{i:06d}.jpg").write_bytes(b"x")
        (fd / "f000005_ds1280.jpg").write_bytes(b"x")   # 变体帧应被忽略
        # [0, 4.0] → 帧 1..20（20 帧 > 8）→ 均匀 8 帧，首尾恒在列
        picks = vsf.select_uniform_frames(str(fd), 0.0, 4.0)
        assert len(picks) == 8
        assert picks[0].name == "f000001.jpg"
        assert picks[-1].name == "f000020.jpg"
        assert all("_ds" not in p.stem for p in picks)
        assert picks == sorted(picks)          # 时序保序
        # 窗口 ≤8 → 全取：[0, 1.0] → 帧 1..6
        assert [p.name for p in vsf.select_uniform_frames(str(fd), 0.0, 1.0)] == [
            f"f{i:06d}.jpg" for i in range(1, 7)]
        # 窄窗 1 帧
        assert len(vsf.select_uniform_frames(str(fd), 0.0, 0.1)) == 1
        # 窗口外 → 空
        assert vsf.select_uniform_frames(str(fd), 99.0, 100.0) == []


def test_existing_facet_not_overwritten(tmp_path, monkeypatch):
    """已有值的 action/camera（路由/人工产物）不被覆盖 —— 只填空缺语义。"""
    work, shots, pp = make_workdir(
        tmp_path, action_values=["人工动作", ""], camera_values=["人工运镜", ""])
    fake = FakeEngine("engine-answer")
    patch_engine(monkeypatch, fake)
    run_main(work, pp)
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"] == "人工动作"       # 保留
    assert out[0]["camera"] == "人工运镜"       # 保留
    assert out[1]["action"].startswith("engine-answer")   # 空的被填
    assert out[1]["camera"].startswith("engine-answer")
    # 已满的 shot 1 完全不问引擎（只有 shot 2 的 5+4 次）
    assert fake.calls == 9


# ── cache 幂等 + 双信封 ────────────────────────────────────────────────────

def test_cache_hit_second_run_zero_engine_calls(tmp_path, monkeypatch):
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine("scene-answer")
    patch_engine(monkeypatch, fake)
    run_main(work, pp)
    assert fake.calls > 0
    # 二跑：全 cache 命中 → 零引擎调用（SC4 机器证明）
    fake2 = FakeEngine("不该被问到")
    patch_engine(monkeypatch, fake2)
    run_main(work, pp)
    assert fake2.calls == 0
    # cache 文件双信封结构 + 5 字段 _cache_key（无 audio → ear_off 信封）
    cache = json.loads((work / "route_cache" / "vision_seq" / "shot_001.json")
                       .read_text(encoding="utf-8"))
    assert "ear_off" in cache and "ear_on" not in cache
    env = cache["ear_off"]
    ck = env["_cache_key"]
    assert set(ck) == {"video_content_hash", "engine_name",
                       "engine_version", "prompt_version", "ear"}
    assert ck["ear"] is False
    assert ck["prompt_version"] == "vision-seq-v1"
    # answers 存 RAW 逐帧/逐对答案；temporal 不产 merged_B
    assert env["answers"]["action_frame_1"] == "scene-answer"
    assert env["answers"]["camera_pair_1"] == "scene-answer"
    assert "merged_B" not in env


def test_stale_cache_key_miss_refetches(tmp_path, monkeypatch):
    """_cache_key 任一字段不匹配（模拟 PROMPT_VERSION bump）→ miss 重拉。"""
    work, shots, pp = make_workdir(tmp_path)
    patch_engine(monkeypatch, FakeEngine("old-answer"))
    run_main(work, pp)
    # 篡改 prompt_version → stale
    cache_file = work / "route_cache" / "vision_seq" / "shot_001.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    cache["ear_off"]["_cache_key"]["prompt_version"] = "bumped"
    cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    reset_facets(pp)
    fake2 = FakeEngine("new-answer")
    patch_engine(monkeypatch, fake2)
    run_main(work, pp)
    assert fake2.calls > 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"].startswith("new-answer")


def test_ear_envelope_isolation_dual_coexistence(tmp_path, monkeypatch):
    """ear_on 信封不服务 ear_off 运行（miss 重拉）；双信封共存（切换不丢数据）。"""
    work, shots, pp = make_workdir(tmp_path)
    audio = make_audio_file(work)
    fake1 = FakeEngine("ear开答案")
    patch_engine(monkeypatch, fake1)
    run_main(work, pp, extra_args=["--audio-semantic", str(audio)])
    cache_file = work / "route_cache" / "vision_seq" / "shot_001.json"
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "ear_on" in data and "ear_off" not in data
    assert data["ear_on"]["_cache_key"]["ear"] is True
    # 重置 facets → --no-ear 跑：ear_off 信封空 → miss 重拉
    reset_facets(pp)
    fake2 = FakeEngine("ear关答案")
    patch_engine(monkeypatch, fake2)
    run_main(work, pp, extra_args=["--audio-semantic", str(audio), "--no-ear"])
    assert fake2.calls > 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"].startswith("ear关答案")
    # 双信封共存：ear_on 证据保留
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert data["ear_on"]["answers"]["action_frame_1"] == "ear开答案"
    assert data["ear_off"]["answers"]["action_frame_1"] == "ear关答案"
    assert data["ear_off"]["_cache_key"]["ear"] is False


def test_merge_deterministic_temporal_longest():
    """纯归约合并：同输入同输出（确定性）、零引擎依赖。"""
    vals = ["甲", "乙乙", "丙"]
    assert vsf.merge_answers(vals, "temporal") == "甲→乙乙→丙"
    assert vsf.merge_answers(list(vals), "temporal") == "甲→乙乙→丙"
    assert vsf.merge_answers(vals, "longest") == "乙乙"
    assert vsf.merge_answers([], "temporal") == ""
    assert vsf.merge_answers([], "longest") == ""


# ── graceful-degrade / 生命周期 / sidecar ──────────────────────────────────

def test_engine_unavailable_degrades(tmp_path, monkeypatch):
    """ensure_ready 失败 → facet 保持 ""、[vision-seq] warning、exit 0。"""

    class DeadEngine:
        def ensure_ready(self, timeout_s=None):
            return False, False

        def stop_if_owned(self):
            pass

    work, shots, pp = make_workdir(tmp_path)
    patch_engine(monkeypatch, DeadEngine())
    rc = run_main(work, pp)
    assert rc == 0   # graceful-degrade 不 fail pipeline
    out = json.loads(pp.read_text(encoding="utf-8"))
    for p in out:
        assert p["action"] == ""
        assert p["camera"] == ""
    warnings = json.loads(
        (work / "route_cache" / "warnings.json").read_text(encoding="utf-8"))
    assert any(w.startswith("[vision-seq]") and "engine unavailable" in w
               for w in warnings["warnings"])


def test_lifecycle_try_finally_stops_engine(tmp_path, monkeypatch):
    """main() try/finally：循环中引擎抛异常也必须 stop_if_owned（防泄漏）。"""

    class ExplodingEngine(FakeEngine):
        def observe_single(self, path, question, max_tokens=2000):
            raise RuntimeError("boom")

        def observe_pair(self, img_a, img_b, question, max_tokens=2000):
            raise RuntimeError("boom")

    work, shots, pp = make_workdir(tmp_path, n_shots=1)
    boom = ExplodingEngine()
    patch_engine(monkeypatch, boom)
    rc = run_main(work, pp)
    assert rc == 0
    assert boom._stopped is True
    warnings = json.loads(
        (work / "route_cache" / "warnings.json").read_text(encoding="utf-8"))
    assert any("engine call failed" in w for w in warnings["warnings"])


def test_warnings_sidecar_preserves_other_steps(tmp_path, monkeypatch):
    """READ-merge-write：他 step 的 [semantic] warning 保留；重跑不翻倍。"""
    work, shots, pp = make_workdir(tmp_path)
    sidecar = work / "route_cache" / "warnings.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps({"warnings": [
        "[semantic] shot 1: offline/cache-miss → empty facets"]},
        ensure_ascii=False), encoding="utf-8")

    class DeadEngine:
        def ensure_ready(self, timeout_s=None):
            return False, False

        def stop_if_owned(self):
            pass

    patch_engine(monkeypatch, DeadEngine())
    run_main(work, pp)
    run_main(work, pp)   # 二跑：[vision-seq] 条目不 self-accumulate
    warnings = json.loads(sidecar.read_text(encoding="utf-8"))["warnings"]
    assert any(w.startswith("[semantic]") for w in warnings)
    vseq = [w for w in warnings if w.startswith("[vision-seq]")]
    assert len(vseq) == 1


# ── schema / 边界 ──────────────────────────────────────────────────────────

def test_output_passes_prompts_schema(tmp_path, monkeypatch):
    from jsonschema import Draft202012Validator
    schema = json.loads((REPO_ROOT / "spec" / "schemas" / "prompts.schema.json")
                        .read_text(encoding="utf-8"))
    work, shots, pp = make_workdir(tmp_path)
    patch_engine(monkeypatch, FakeEngine("深夜雨巷中的追逐"))
    assert run_main(work, pp) == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(out))


def test_missing_prompts_fails_loud(tmp_path):
    """prompts.json 不存在 → sys.exit（本步骤是 additive，step 5 必须先跑）。"""
    work = tmp_path / "work"
    work.mkdir()
    (work / "shots.json").write_text(
        json.dumps([{"id": 1, "start_sec": 0.0, "end_sec": 1.0,
                     "duration": 1.0}]), encoding="utf-8")
    frames = work / "frames_5fps"
    frames.mkdir()
    (frames / "f000001.jpg").write_bytes(b"x")
    with pytest.raises(SystemExit):
        run_main(work, work / "prompts.json")


# ── ear（SC3 单元级）───────────────────────────────────────────────────────

def test_ear_injects_whitelist_audio_context(tmp_path, monkeypatch):
    """有 audio → 每次提问含「该镜音频：」+ 对白/情绪/音效白名单子串；
    words/reproduction/spk_id 白名单外字段值永不出现（负测试）。"""
    work, shots, pp = make_workdir(tmp_path)
    audio = make_audio_file(work)
    fake = FakeEngine("答")
    patch_engine(monkeypatch, fake)
    run_main(work, pp, extra_args=["--audio-semantic", str(audio)])
    assert fake.questions
    assert all("该镜音频：" in q for q in fake.questions)   # 每镜都有对白
    assert any("完整对白句子" in q for q in fake.questions)
    assert any("HAPPY" in q for q in fake.questions)
    assert any("雨声" in q for q in fake.questions)
    assert all("spk_777" not in q for q in fake.questions)
    assert all("WORDLEVEL_MARKER" not in q for q in fake.questions)
    assert all("REPRO_MARKER" not in q for q in fake.questions)


def test_no_ear_flag_excludes_audio(tmp_path, monkeypatch):
    """--no-ear 显式关：文件在位也不注入音频上下文。"""
    work, shots, pp = make_workdir(tmp_path)
    audio = make_audio_file(work)
    fake = FakeEngine("答")
    patch_engine(monkeypatch, fake)
    run_main(work, pp, extra_args=["--audio-semantic", str(audio), "--no-ear"])
    assert fake.questions
    assert all("该镜音频：" not in q for q in fake.questions)
    assert all("完整对白句子" not in q for q in fake.questions)


def test_audio_file_absent_silent_no_ear(tmp_path, monkeypatch):
    """无 --audio-semantic 文件 → 自动无 ear 且零 warning（静默 degrade：
    sidecar 不创建），提问不含音频子串。"""
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine("答")
    patch_engine(monkeypatch, fake)
    rc = run_main(work, pp)
    assert rc == 0
    assert all("该镜音频：" not in q for q in fake.questions)
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"]   # 正常填充
    assert not (work / "route_cache" / "warnings.json").exists()


def test_ear_absent_vs_no_ear_byte_identical(tmp_path, monkeypatch):
    """无 audio 文件运行与显式 --no-ear 运行产出的 prompts.json
    byte-identical（同 ear_off 信封路径）。"""
    work_a, _, pp_a = make_workdir(tmp_path / "runA")
    work_b, _, pp_b = make_workdir(tmp_path / "runB")
    audio_b = make_audio_file(work_b)
    patch_engine(monkeypatch, FakeEngine("同样答案"))
    run_main(work_a, pp_a)   # 无 audio 文件
    patch_engine(monkeypatch, FakeEngine("同样答案"))
    run_main(work_b, pp_b, extra_args=["--audio-semantic", str(audio_b), "--no-ear"])
    assert pp_a.read_bytes() == pp_b.read_bytes()


# ── 零修改短路 + 预判生命周期 ──────────────────────────────────────────────

def test_zero_modification_short_circuit(tmp_path, monkeypatch):
    """全满 prompts.json：文件 bytes/mtime 不变、不建 cache 目录、不建
    sidecar、QwenEye 从未被实例化。"""
    work, shots, pp = make_workdir(
        tmp_path, action_values=["已有动作"] * 2, camera_values=["已有运镜"] * 2)
    before_bytes = pp.read_bytes()
    before_mtime = os.path.getmtime(pp)

    def _boom():
        raise AssertionError("QwenEye 不该被实例化（零待填 facet）")

    monkeypatch.setattr(vsf, "QwenEye", _boom)
    rc = run_main(work, pp)
    assert rc == 0
    assert pp.read_bytes() == before_bytes
    assert os.path.getmtime(pp) == before_mtime
    assert not (work / "route_cache" / "vision_seq").exists()
    assert not (work / "route_cache" / "warnings.json").exists()


def test_full_cache_hit_never_instantiates_engine(tmp_path, monkeypatch):
    """全 cache 命中（pending 空）→ 完全不进入引擎生命周期（SC4 预判断言）。"""
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine("缓存答案")
    patch_engine(monkeypatch, fake)
    run_main(work, pp)
    assert fake.calls > 0
    reset_facets(pp)

    def _boom():
        raise AssertionError("QwenEye 不该被实例化（全 cache 命中）")

    monkeypatch.setattr(vsf, "QwenEye", _boom)
    rc = run_main(work, pp)
    assert rc == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"] == "→".join(["缓存答案"] * 6)   # cache 合并回填


# ── llm 合并策略（策略 B）──────────────────────────────────────────────────

def test_llm_merge_strategy_caches_merged_b(tmp_path, monkeypatch):
    """--merge-strategy llm：ask_text 二次合并 → merged_B 落 cache；
    二跑 RAW + merged_B 全命中 → 零引擎零文本调用。"""
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine("帧答", merge_answer="连贯合并描述")
    patch_engine(monkeypatch, fake)
    rc = run_main(work, pp, extra_args=["--merge-strategy", "llm"])
    assert rc == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"] == "连贯合并描述"
    assert out[0]["camera"] == "连贯合并描述"
    assert fake.text_calls == 2 * len(shots)   # 每镜 action+camera 各一次
    cache = json.loads((work / "route_cache" / "vision_seq" / "shot_001.json")
                       .read_text(encoding="utf-8"))
    assert cache["ear_off"]["merged_B"]["action"] == "连贯合并描述"
    # 二跑：全命中（含 merged_B）
    reset_facets(pp)
    fake2 = FakeEngine("不该被问")
    patch_engine(monkeypatch, fake2)
    rc = run_main(work, pp, extra_args=["--merge-strategy", "llm"])
    assert rc == 0
    assert fake2.calls == 0 and fake2.text_calls == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"] == "连贯合并描述"


def test_camera_single_frame_degrades(tmp_path, monkeypatch):
    """窗口仅 1 帧 → camera 无相邻对可问：warning + 保持 ""（action 仍填）。"""
    work, shots, pp = make_workdir(tmp_path, n_shots=1)
    shots = [{"id": 1, "start_sec": 0.0, "end_sec": 0.1, "duration": 0.1}]
    (work / "shots.json").write_text(json.dumps(shots), encoding="utf-8")
    prompts = [{"shot_id": 1, "start_sec": 0.0, "end_sec": 0.1, "duration": 0.1,
                "subject": "sub", "action": "", "camera": "",
                "scene": "scene", "lighting": "l", "style": "s",
                "prompt_text": ""}]
    pp.write_text(json.dumps(prompts, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    fake = FakeEngine("单帧答")
    patch_engine(monkeypatch, fake)
    rc = run_main(work, pp)
    assert rc == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["action"] == "单帧答"
    assert out[0]["camera"] == ""
    warnings = json.loads((work / "route_cache" / "warnings.json")
                          .read_text(encoding="utf-8"))["warnings"]
    assert any("camera pair question impossible" in w for w in warnings)
