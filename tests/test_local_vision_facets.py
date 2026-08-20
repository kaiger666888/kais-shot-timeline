"""local_vision_facets 测试 —— monkeypatch 引擎，不拉真 :8125/:10588。

覆盖（Phase 1 交付物 4-b）：
  * cache 命中：同 _cache_key 二跑零引擎调用；key 不匹配（stale）miss 重拉。
  * graceful-degrade：ensure_ready 失败 → scene 保持 ""、[vision] warning、
    exit 0、prompts.json 仍写出且 schema 合法。
  * 写前 schema 校验：产物过 Draft202012Validator(prompts.schema.json)。
  * subject 填外观描述文本、不越权写角色 ID（char_XXX 禁止）。
  * 已有值的 facet 不被覆盖（additive 语义）。
  * warnings sidecar READ-merge-write：他 step 的条目保留。
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = REPO_ROOT / "analysis"

# local_vision_facets import 时把 analysis/ 塞进 sys.path（为了 engine_clients），
# 直接用 spec 加载保持与其他 test 一致的不污染路径做法。
_spec = importlib.util.spec_from_file_location(
    "local_vision_facets", ANALYSIS / "local_vision_facets.py")
lvf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lvf)

# 引擎客户端也走 engine_clients 目录加载（与 test_qwen_eye_client 同源）。
_sys_path_saved = list(sys.path)
sys.path.insert(0, str(ANALYSIS / "engine_clients"))
import qwen_eye_client as qec  # noqa: E402
sys.path[:] = _sys_path_saved


def make_workdir(tmp_path, n_shots=2, empty_facets=True, scene_values=None):
    """搭一个最小 work_dir：shots.json + prompts.json（scene/subject 空或给定）。
    frames_5fps 每秒 5 帧铺满 [0, 2s) —— 10 帧 f000001..f000010.jpg。"""
    work = tmp_path / "work"
    work.mkdir()
    shots = [{"id": i + 1, "start_sec": i * 1.0, "end_sec": i * 1.0 + 1.0,
              "duration": 1.0} for i in range(n_shots)]
    (work / "shots.json").write_text(
        json.dumps(shots, ensure_ascii=False), encoding="utf-8")
    scene_values = scene_values or [""] * n_shots
    prompts = [{"shot_id": s["id"], "start_sec": s["start_sec"],
                "end_sec": s["end_sec"], "duration": s["duration"],
                "subject": "", "action": "a", "camera": "c",
                "scene": scene_values[i], "lighting": "l", "style": "s",
                "prompt_text": ""} for i, s in enumerate(shots)]
    prompts_path = work / "prompts.json"
    prompts_path.write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    frames = work / "frames_5fps"
    frames.mkdir()
    for i in range(1, 11):
        (frames / f"f{i:06d}.jpg").write_bytes(b"\xff\xd8fake")
    return work, shots, prompts_path


class FakeEngine:
    """替身引擎：observe_single 恒回固定答案；调用数可查。"""

    def __init__(self, answer="苔藓覆盖的原始森林巨树"):
        self.answer = answer
        self.calls = 0
        self._owned = False

    def ensure_ready(self, timeout_s=None):
        return True, False

    def stop_if_owned(self):
        self._stopped = True

    def observe_single(self, path, question, max_tokens=2000):
        self.calls += 1
        return self.answer


def run_main(work, prompts_path, extra_args=None, monkeypatch_engine=None):
    """调 lvf.main()（argv 注入），可选替换 QwenEye 构造。"""
    argv = ["local_vision_facets.py",
            "--shots", str(work / "shots.json"),
            "--frames-dir", str(work / "frames_5fps"),
            "--work-dir", str(work),
            "--output", str(prompts_path)]
    if extra_args:
        argv += extra_args
    old_argv = sys.argv
    sys.argv = argv
    try:
        rc = lvf.main()
    finally:
        sys.argv = old_argv
    return rc


def patch_engine(monkeypatch, fake):
    monkeypatch.setattr(lvf, "QwenEye", lambda: fake)


# ── 填充 + cache ──────────────────────────────────────────────────────────

def test_fills_scene_and_subject(tmp_path, monkeypatch):
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine("苔藓覆盖的原始森林巨树")
    patch_engine(monkeypatch, fake)
    rc = run_main(work, pp)
    assert rc == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["scene"] == "苔藓覆盖的原始森林巨树"
    assert out[0]["subject"] == "苔藓覆盖的原始森林巨树"
    # 每镜 ≤3 帧 × 2 facets
    assert fake.calls <= 3 * 2 * len(shots)


def test_subject_is_appearance_text_not_id(tmp_path, monkeypatch):
    """subject 填外观描述文本，永不写角色 ID（char_XXX）—— re-id 边界。"""
    work, shots, pp = make_workdir(tmp_path)
    patch_engine(monkeypatch, FakeEngine("橙黄色绒毛圆滚身材的毛毛虫小孩"))
    assert run_main(work, pp) == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    for p in out:
        assert p["subject"]
        assert "char_" not in p["subject"]   # 不越权写角色 ID


def test_cache_hit_second_run_zero_engine_calls(tmp_path, monkeypatch):
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine("scene-answer")
    patch_engine(monkeypatch, fake)
    run_main(work, pp)
    first_calls = fake.calls
    assert first_calls > 0
    # 二跑：全 cache 命中 → 零引擎调用
    fake2 = FakeEngine("scene-answer")
    patch_engine(monkeypatch, fake2)
    run_main(work, pp)
    assert fake2.calls == 0
    # cache 文件带 4-tuple _cache_key
    cache = json.loads((work / "route_cache" / "local_vision" / "shot_001.json")
                       .read_text(encoding="utf-8"))
    ck = cache["_cache_key"]
    assert set(ck) == {"video_content_hash", "engine_name",
                       "engine_version", "prompt_version"}


def test_stale_cache_key_miss_refetches(tmp_path, monkeypatch):
    """_cache_key 不匹配（模拟 ENGINE_VERSION bump）→ miss 重拉。"""
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine("old-answer")
    patch_engine(monkeypatch, fake)
    run_main(work, pp)
    # 篡改 cache key → stale
    cache_file = work / "route_cache" / "local_vision" / "shot_001.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    cache["_cache_key"]["engine_version"] = "bumped"
    cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    # 清空 prompts 的 scene 促重填
    prompts = json.loads(pp.read_text(encoding="utf-8"))
    for p in prompts:
        p["scene"] = ""
    pp.write_text(json.dumps(prompts, ensure_ascii=False), encoding="utf-8")
    fake2 = FakeEngine("new-answer")
    patch_engine(monkeypatch, fake2)
    run_main(work, pp)
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["scene"] == "new-answer"


def test_existing_facet_not_overwritten(tmp_path, monkeypatch):
    """已有值的 facet（路由/人工产物）不被覆盖 —— additive 语义。"""
    work, shots, pp = make_workdir(
        tmp_path, scene_values=["人工金标准场景", ""])
    patch_engine(monkeypatch, FakeEngine("engine-answer"))
    run_main(work, pp)
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert out[0]["scene"] == "人工金标准场景"   # 保留
    assert out[1]["scene"] == "engine-answer"    # 空的被填


# ── graceful-degrade ──────────────────────────────────────────────────────

def test_engine_unavailable_degrades(tmp_path, monkeypatch):
    """ensure_ready 失败 → scene 保持 ""、[vision] warning、exit 0、schema 合法。"""

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
        assert p["scene"] == ""
        assert p["subject"] == ""
    warnings = json.loads(
        (work / "route_cache" / "warnings.json").read_text(encoding="utf-8"))
    assert any(w.startswith("[vision]") and "engine unavailable" in w
               for w in warnings["warnings"])


def test_lifecycle_try_finally_stops_engine(tmp_path, monkeypatch):
    """main() try/finally：循环中引擎抛异常也必须 stop_if_owned（防 13.4GB 泄漏）。"""

    class ExplodingEngine(FakeEngine):
        def ensure_ready(self, timeout_s=None):
            self._ready = True
            return True, False

        def stop_if_owned(self):
            self.stopped = True

        def observe_single(self, path, question, max_tokens=2000):
            raise RuntimeError("boom")

    work, shots, pp = make_workdir(tmp_path, n_shots=1)
    boom = ExplodingEngine()
    patch_engine(monkeypatch, boom)
    # 引擎调用失败是 per-shot warning，不是异常 → main 正常走完 finally
    rc = run_main(work, pp)
    assert rc == 0
    assert boom.stopped is True


def test_warnings_sidecar_preserves_other_steps(tmp_path, monkeypatch):
    """READ-merge-write：他 step 的 [semantic] warning 保留；重跑不 self-accumulate。"""
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
    run_main(work, pp)   # 二跑：[vision] 条目不翻倍
    warnings = json.loads(sidecar.read_text(encoding="utf-8"))["warnings"]
    assert any(w.startswith("[semantic]") for w in warnings)
    vision = [w for w in warnings if w.startswith("[vision]")]
    assert len(vision) == 1


# ── schema / 边界 ─────────────────────────────────────────────────────────

def test_output_passes_prompts_schema(tmp_path, monkeypatch):
    from jsonschema import Draft202012Validator
    schema = json.loads((REPO_ROOT / "spec" / "schemas" / "prompts.schema.json")
                        .read_text(encoding="utf-8"))
    work, shots, pp = make_workdir(tmp_path)
    patch_engine(monkeypatch, FakeEngine("深夜霓虹灯下的雨后小巷"))
    assert run_main(work, pp) == 0
    out = json.loads(pp.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(out))


def test_no_subject_flag_only_fills_scene(tmp_path, monkeypatch):
    work, shots, pp = make_workdir(tmp_path)
    fake = FakeEngine()
    patch_engine(monkeypatch, fake)
    run_main(work, pp, extra_args=["--no-subject"])
    out = json.loads(pp.read_text(encoding="utf-8"))
    for p in out:
        assert p["scene"]
        assert p["subject"] == ""


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


# ── 帧选择单元 ────────────────────────────────────────────────────────────

def test_select_frames_first_mid_last():
    """时窗内 >3 帧取首/中/尾；不足 3 帧全取；窗口外帧不取；_ds 变体忽略。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        fd = Path(td)
        for i in range(1, 11):           # t = 0.0 .. 1.8s
            (fd / f"f{i:06d}.jpg").write_bytes(b"x")
        (fd / "f000003_ds1280.jpg").write_bytes(b"x")   # 变体帧应被忽略
        # [0.0, 1.0] → 帧 1..6（t=0,0.2,...,1.0）→ 首/中/尾 = 1,3,6（跳过 _ds）
        picks = lvf.select_frames(str(fd), 0.0, 1.0)
        assert [p.name for p in picks] == [
            "f000001.jpg", "f000003.jpg", "f000006.jpg"]
        # 窄窗只有 1 帧
        assert len(lvf.select_frames(str(fd), 0.0, 0.1)) == 1
        # 窗口外（t > 全部长度）→ 空
        assert lvf.select_frames(str(fd), 99.0, 100.0) == []


def test_zero_change_run_does_not_rewrite_prompts(tmp_path, monkeypatch):
    """22-04 Rule 3 回归锁：全部 facet 已填 → 零改动跑不重写 prompts.json。

    保 mtime 是下游 step_roundtrip 外层 cache（roundtrip.json > prompts.json）
    与 step_export mtime cache 的命中前提（mirror vision_seq changed-guard）。
    """
    work, shots, pp = make_workdir(
        tmp_path, empty_facets=False,
        scene_values=["已填场景一", "已填场景二"])
    prompts = json.loads(pp.read_text(encoding="utf-8"))
    for p in prompts:
        p["subject"] = "已填主体"
    pp.write_text(json.dumps(prompts, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    before_bytes = pp.read_bytes()
    before_mtime = pp.stat().st_mtime_ns
    fake = FakeEngine("不应被问到")
    patch_engine(monkeypatch, fake)
    rc = run_main(work, pp)
    assert rc == 0
    assert fake.calls == 0                          # 全已填 → 零引擎调用
    assert pp.read_bytes() == before_bytes          # 字节不变
    assert pp.stat().st_mtime_ns == before_mtime    # 且根本没重写（mtime 不动）
