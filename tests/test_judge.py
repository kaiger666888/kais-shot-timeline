"""judge 测试 —— FakeEye + 解析矩阵 + grid 布局 + verdict 冻结，零网络零 GPU
（21-01 Task 3）。

覆盖（行为清单逐项）：
  * 解析容错矩阵 7 用例：干净 JSON / fence 包裹+前后散文 / 尾逗号坏 JSON
    （json: 码）/ 非法 enum / confidence 越界（数值、字符串、bool 三态）/
    reason 过短 / 完全无花括号——各归各的 verdict 码。
  * FakeEye（observe_single 回放预设文本序列）重问：首答坏次答好 →
    attempts len 2 + 第二问含错误回喂标记；三连坏 → parsed None + str
    warning + rc 0。
  * grid 纯 PIL 布局：尺寸 (1370,1476) + 列头/行标签区域采样像素 ≠ BG
    （标签必须进图——judge 只收一张图，T-21-03）。
  * 引擎编排：全 cache 命中零实例化（QwenEye 构造器 raise 仍 rc 0）；
    ensure_ready 两败 → 30s 重试一次 → str warning + rc=0 degrade。
  * --apply-verdict 硬合取三态（0.95+faithful→accepted；0.95+diverged→
    rejected；0.80+faithful@τ=0.9→rejected）；冻结幂等（预存 rejected
    verdict + τ 变为会 accept → 原样；缺 verdict 镜补写）；信号缺一
    跳过 + warning 列 shot_id。
  * Pitfall 8 双向：--apply-verdict 后跑 h3s.write_roundtrip_sidecar 重写
    regen 半边 → verdict + scores 原样。
  * 预存坏条目剔除 + .bak-<ts> 备份（WR-04）；schema 全字段条目（regen +
    scores 双半 + verdict）过 Draft202012Validator。
  * summarize_scores：19 个手写 (sim, attribution) 对 → 精确分位数 +
    桶计数 + τ 预演计数。
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
    "judge", REPO_ROOT / "analysis" / "roundtrip" / "judge.py")
jm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jm)


# ── 替身 ────────────────────────────────────────────────────────────────────

class _FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class FakeHTTP:
    """记录式 _http_json 替身（默认全 200——comfy_free best-effort 用）。"""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def __call__(self, url, payload=None, timeout=30.0):
        self.calls.append((url, payload))
        if self.responses:
            return self.responses.pop(0)
        return 200, {"ok": True}


def make_fake_eye(answers, ensure_seq=None):
    """FakeEye 替身工厂：observe_single 逐次回放预设文本（Exception 则抛）；
    记录实例数 / questions / ensure_ready 逐次返回 / stop_if_owned 次数。"""
    state = {"instances": 0, "questions": [], "ensures": [], "stopped": 0,
             "answers": list(answers)}

    class FakeEye:
        def __init__(self, *a, **kw):
            state["instances"] += 1

        def ensure_ready(self, timeout_s=120):
            result = ensure_seq[len(state["ensures"])] if ensure_seq \
                else (True, True)
            state["ensures"].append(result)
            return result

        def stop_if_owned(self):
            state["stopped"] += 1

        def observe_single(self, image_path, question, max_tokens=2000):
            state["questions"].append(question)
            if not state["answers"]:
                return ""
            ans = state["answers"].pop(0)
            if isinstance(ans, BaseException):
                raise ans
            return str(ans)

    return FakeEye, state


_JPEG_CACHE: dict = {}


def _valid_jpeg_bytes() -> bytes:
    """真 PIL 可读的最小 JPEG（build_grid 的 Image.open 需要）。"""
    if "b" not in _JPEG_CACHE:
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 36), (90, 110, 160)).save(buf, "JPEG")
        _JPEG_CACHE["b"] = buf.getvalue()
    return _JPEG_CACHE["b"]


def make_workdir(tmp_path, n_shots=1, duration=6.73):
    """最小 work_dir：shots.json + prompts.json（prompt_text）+ 假 h264.mp4 +
    roundtrip/shot_XXX_regen.mp4 假字节 + roundtrip.json 预存 regen 条目。"""
    work = tmp_path / "work"
    work.mkdir(parents=True)
    shots = []
    for i in range(n_shots):
        start = i * duration
        shots.append({"id": i + 1, "start_sec": start,
                      "end_sec": start + duration, "duration": duration})
    (work / "shots.json").write_text(json.dumps(shots), encoding="utf-8")
    prompts = [{"shot_id": s["id"],
                "prompt_text": f"独角仙武士把红浆果递给 {s['id']} 号少女"}
                for s in shots]
    (work / "prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "h264.mp4").write_bytes(b"fake-h264-bytes-0123456789")
    rt = work / "roundtrip"
    rt.mkdir()
    entries = []
    for s in shots:
        (rt / f"shot_{s['id']:03d}_regen.mp4").write_bytes(
            b"fake-regen-mp4-" + bytes([s["id"]]))
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
    """argv 注入调 jm.main()，返回 rc。"""
    argv = ["judge.py", "--work-dir", str(work)]
    if extra_args:
        argv += extra_args
    old_argv = sys.argv
    sys.argv = argv
    try:
        rc = jm.main()
    finally:
        sys.argv = old_argv
    return rc


def patch_judge(monkeypatch, fake_http=None, eye_cls=None):
    """打满 patch 点：subprocess.run（ffmpeg 写可读假 jpg）/ time.sleep
    no-op / h3s._http_json 替身（避免真网络）/ 可选 QwenEye → FakeEye。"""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if cmd[0] == "ffmpeg":
            dest = [a for a in cmd if a.endswith(".jpg")][-1]
            Path(dest).write_bytes(_valid_jpeg_bytes())
            return _FakeProc("")
        return _FakeProc("")

    monkeypatch.setattr(jm.subprocess, "run", fake_run)
    monkeypatch.setattr(jm.time, "sleep", lambda s: None)
    http = fake_http or FakeHTTP()
    monkeypatch.setattr(jm.h3s, "_http_json", http)
    if eye_cls is not None:
        monkeypatch.setattr(jm, "QwenEye", eye_cls)
    return http, calls


def read_sidecar(work) -> dict:
    return json.loads((work / "roundtrip.json").read_text(encoding="utf-8"))


def write_sidecar(work, data) -> None:
    (work / "roundtrip.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_warnings(work) -> list:
    return json.loads((work / "route_cache" / "warnings.json")
                      .read_text(encoding="utf-8"))["warnings"]


def read_cache(work, sid) -> dict:
    return json.loads((work / jm.JUDGE_CACHE_SUBDIR
                       / f"shot_{sid:03d}.json").read_text(encoding="utf-8"))


def validate_sidecar(data: dict) -> list:
    """与 judge/scorer 同源的 schema 校验（h3s 单源）。"""
    return list(jm.h3s._iter_sidecar_errors(data))


def good_answer(attribution="prompt_faithful", confidence=0.85,
                reason="prompt 要求'递红浆果'且 REGEN t=33%/66% 中段帧渲染出该动作"):
    return json.dumps({"attribution": attribution, "confidence": confidence,
                       "reason": reason}, ensure_ascii=False)


def judge_scores_entry(sid, attribution="prompt_faithful", confidence=0.85,
                       reason="运动贴合中段帧证据充分"):
    """scores.judge 半边条目（--apply-verdict 用例的预置素材）。"""
    return {"shot_id": sid, "scores": {"judge": {
        "attribution": attribution, "confidence": confidence,
        "reason": reason}}}


def sim_scores_entry(sid, score):
    """scores.midframe_sim 半边条目。"""
    return {"shot_id": sid, "scores": {"midframe_sim": {
        "score": score, "model": jm.ENGINE_NAME and "siglip-so400m-patch14-384"}}}


# ── 解析容错矩阵（RESEARCH Validation 表 SCORE-02 七行）────────────────────

def test_parse_clean_json():
    obj, code = jm.parse_judge_answer(
        '{"attribution": "prompt_faithful", "confidence": 0.9, '
        '"reason": "prompt 说 X 且 REGEN 渲染出 X"}')
    assert code == "ok"
    assert obj["attribution"] == "prompt_faithful"
    assert obj["confidence"] == 0.9


def test_parse_fence_wrapped_with_prose():
    """markdown fence 包裹 + 前后散文 → 剥离后正常解析。"""
    obj, code = jm.parse_judge_answer(
        "好的，我的判定如下：\n```json\n" + good_answer() + "\n```\n以上。")
    assert code == "ok"
    assert obj["attribution"] == "prompt_faithful"


def test_parse_bad_json_trailing_comma():
    """尾逗号坏 JSON → json: 码。"""
    obj, code = jm.parse_judge_answer(
        '{"attribution": "prompt_faithful", "confidence": 0.5, '
        '"reason": "aaaaaaaaaa",}')
    assert obj is None
    assert code.startswith("json:"), code


def test_parse_bad_enum():
    _, code = jm.parse_judge_answer(
        '{"attribution": "bad", "confidence": 0.5, "reason": "aaaaaaaaaa"}')
    assert code == "enum"


def test_parse_conf_range_three_forms():
    """confidence 越界数值 / 字符串 / bool（bool 是 int 子类，须显式排除）→
    conf-range。"""
    _, c1 = jm.parse_judge_answer(
        '{"attribution": "model_diverged", "confidence": 1.5, '
        '"reason": "aaaaaaaaaa"}')
    assert c1 == "conf-range"
    _, c2 = jm.parse_judge_answer(
        '{"attribution": "model_diverged", "confidence": "0.5", '
        '"reason": "aaaaaaaaaa"}')
    assert c2 == "conf-range"
    _, c3 = jm.parse_judge_answer(
        '{"attribution": "model_diverged", "confidence": true, '
        '"reason": "aaaaaaaaaa"}')
    assert c3 == "conf-range"


def test_parse_reason_short():
    _, code = jm.parse_judge_answer(
        '{"attribution": "model_diverged", "confidence": 0.5, "reason": "短"}')
    assert code == "reason-short"


def test_parse_no_brace():
    _, code = jm.parse_judge_answer("完全不是 JSON")
    assert code == "no-brace"


def test_parse_truncated_final_brace_repaired():
    """末尾 `}` 被 EOS 截断（21-03 shot 19 实测：引擎在 `。"` 后提前停token，
    三个样本全部缺闭括号）→ 补一个 `}` 后应正常解析。"""
    obj, code = jm.parse_judge_answer(
        '{"attribution": "model_diverged", "confidence": 0.9, '
        '"reason": "prompt 明确描述了动作，但 REGEN 中段帧未执行该指令，'
        '属于模型执行走样。"')
    assert code == "ok"
    assert obj["attribution"] == "model_diverged"
    assert obj["confidence"] == 0.9


def test_parse_truncated_brace_does_not_mask_garbage():
    """截断修复不得掩盖真坏 JSON：缺 `}` 且内容本身非法（尾逗号）→ json: 码
    照常进 retry-with-feedback。"""
    _, code = jm.parse_judge_answer(
        '{"attribution": "prompt_faithful", "confidence": 0.5, '
        '"reason": "aaaaaaaaaa",')
    assert code.startswith("json:"), code


def test_parse_truncated_brace_validation_still_applies():
    """截断修复后 enum/conf 校验照常生效（修复只补括号不放松语义校验）。"""
    _, code = jm.parse_judge_answer(
        '{"attribution": "bad_enum", "confidence": 0.5, '
        '"reason": "aaaaaaaaaa"')
    assert code == "enum"


# ── grid 时窗 / 布局（T-21-03 标签进图）────────────────────────────────────

def test_grid_ts_endpoint_clamp():
    """grid_ts：t=100% 在 dur=7.2917 上 clamp 到 7.0917（Pitfall 3 实测锚）；
    t=0% 恒 0；全序列 ∈ [0, dur-0.2]；极短 dur 全 0。"""
    gt = jm.grid_ts(7.2917)
    assert len(gt) == 4
    assert gt[3] == pytest.approx(7.0917, abs=1e-6)
    assert gt[0] == pytest.approx(0.0)
    assert gt[1] == pytest.approx(7.2917 / 3, abs=1e-6)
    assert all(0.0 <= t <= 7.2917 - 0.2 + 1e-9 for t in gt)
    assert jm.grid_ts(0.1) == [0.0, 0.0, 0.0, 0.0]


def test_build_grid_layout_and_labels(tmp_path):
    """2×4 grid：总尺寸 (1370,1476)；两列列头区域与行标签列均有非 BG 像素
    （标签必须进图——judge 列语义只能靠图内文字）。"""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    orig = []
    regen = []
    for j in range(4):
        for side, bucket in (("orig", orig), ("regen", regen)):
            p = frames_dir / f"shot_001_{side}_{j}.jpg"
            p.write_bytes(_valid_jpeg_bytes())
            bucket.append(p)
    dest = str(tmp_path / "_judge_grids" / "shot_001.jpg")
    w, h = jm.build_grid(orig, regen, dest)
    assert (w, h) == (1370, 1476)
    from PIL import Image
    im = Image.open(dest)
    assert im.size == (1370, 1476)
    px = im.load()

    def region_has_ink(x0, x1, y0, y1):
        return any(px[x, y] != jm.BG for y in range(y0, y1)
                   for x in range(x0, x1))

    assert region_has_ink(jm.ROWLBL_W, jm.ROWLBL_W + jm.CELL_W, 0, jm.HDR_H)
    assert region_has_ink(jm.ROWLBL_W + jm.CELL_W, w, 0, jm.HDR_H)
    assert region_has_ink(0, jm.ROWLBL_W, jm.HDR_H, h)     # 行标签列


def test_build_question_contents_and_feedback():
    """提示词含三分类定义逐字 + JSON 模板 + reason 证据指令 + prompt_text；
    重问轮回喂错误码。"""
    q = jm.build_question("独角仙武士递红浆果", None)
    assert "prompt 描述了X且渲染出X" in q
    assert "描述了X渲染成Y" in q
    assert "prompt 欠约束，h3 自行脑补" in q
    assert '"attribution"' in q and '"confidence"' in q and '"reason"' in q
    assert "prompt 原文中的具体短语" in q
    assert "t=33%/66% 中段行为为主要证据" in q
    assert "独角仙武士递红浆果" in q
    assert "上一次回答无效" not in q
    q2 = jm.build_question("独角仙武士递红浆果", "enum")
    assert "上一次回答无效：enum" in q2


# ── run_judge_shot 重问（retry-with-feedback）───────────────────────────────

def test_run_judge_shot_retry_feedback():
    """首答坏 enum、次答好 → parsed ok；attempts len 2 且逐次记 parse 码；
    第二问含错误回喂标记与原错误码。"""
    eye_cls, state = make_fake_eye([
        '{"attribution": "bad", "confidence": 0.5, "reason": "aaaaaaaaaa"}',
        good_answer(),
    ])
    parsed, attempts = jm.run_judge_shot(eye_cls(), "/tmp/grid.jpg",
                                         "测试 prompt")
    assert parsed is not None and parsed["attribution"] == "prompt_faithful"
    assert len(attempts) == 2
    assert attempts[0]["parse"] == "enum"
    assert attempts[1]["parse"] == "ok"
    assert attempts[1]["raw_len"] == len(good_answer())
    assert len(state["questions"]) == 2
    assert "上一次回答无效" not in state["questions"][0]
    assert "上一次回答无效：enum" in state["questions"][1]


def test_run_judge_shot_three_bad_gives_up():
    """三连坏 → parsed None + attempts len 3（1 主问 + 2 重问，绝不超限）。"""
    eye_cls, state = make_fake_eye(["无花括号一", "无花括号二", "无花括号三"])
    parsed, attempts = jm.run_judge_shot(eye_cls(), "/tmp/grid.jpg",
                                         "测试 prompt")
    assert parsed is None
    assert len(attempts) == 3
    assert all(a["parse"] == "no-brace" for a in attempts)
    assert len(state["questions"]) == 3


# ── judge 批 e2e（FakeEye + fake ffmpeg/http）───────────────────────────────

def test_judge_batch_e2e_reason_truncation(tmp_path, monkeypatch):
    """全链：1 镜 miss → 提帧 + grid + FakeEye 一次好答 → cache（parsed/
    attempts/grid 审计）+ sidecar scores.judge（reason 截 2000、T-18-02 上界）
    + comfy_free 发生 + stop_if_owned 恰一次。"""
    work = make_workdir(tmp_path, n_shots=1)
    long_reason = "证据很充分" + "细" * 2100
    answer = json.dumps({"attribution": "model_diverged",
                         "confidence": 0.75, "reason": long_reason},
                        ensure_ascii=False)
    eye_cls, state = make_fake_eye([answer])
    http, _ = patch_judge(monkeypatch, eye_cls=eye_cls)
    assert run_main(work) == 0
    # sidecar：judge 半边落位 + reason 截断 + schema 合法
    side = read_sidecar(work)
    assert validate_sidecar(side) == []
    judge = side["shots"][0]["scores"]["judge"]
    assert judge["attribution"] == "model_diverged"
    assert judge["confidence"] == 0.75
    assert len(judge["reason"]) == 2000
    assert judge["reason"].startswith("证据很充分")
    # cache：attempts + parsed + grid 审计面
    payload = read_cache(work, 1)
    assert payload["attempts"] == [{"parse": "ok", "raw_len": len(answer)}]
    assert payload["parsed"]["attribution"] == "model_diverged"
    assert payload["grid"] == {"path": "roundtrip/_judge_grids/shot_001.jpg",
                               "w": 1370, "h": 1476}
    assert (work / "roundtrip" / "_judge_grids" / "shot_001.jpg").is_file()
    assert payload["judged_at"]
    # 编排：comfy_free 发生（payload 双布尔）+ stop 恰一次
    frees = [c for c in http.calls if c[0].endswith("/free")]
    assert len(frees) == 1
    assert frees[0][1] == {"unload_models": True, "free_memory": True}
    assert state["stopped"] == 1


def test_judge_batch_retry_e2e_attempts_audit(tmp_path, monkeypatch):
    """e2e 重问：首答 conf 越界、次答好 → cache attempts len 2 + 第二问含
    错误回喂（attempts 审计是 cache 与 sidecar 双写面）。"""
    work = make_workdir(tmp_path, n_shots=1)
    eye_cls, state = make_fake_eye([
        '{"attribution": "prompt_faithful", "confidence": 1.5, '
        '"reason": "aaaaaaaaaa"}',
        good_answer(),
    ])
    patch_judge(monkeypatch, eye_cls=eye_cls)
    assert run_main(work) == 0
    payload = read_cache(work, 1)
    assert [a["parse"] for a in payload["attempts"]] == ["conf-range", "ok"]
    assert "上一次回答无效：conf-range" in state["questions"][1]
    side = read_sidecar(work)
    assert side["shots"][0]["scores"]["judge"]["attribution"] == \
        "prompt_faithful"


def test_judge_all_cache_hit_zero_instantiation(tmp_path, monkeypatch):
    """全 cache 命中 → 零引擎实例化：QwenEye 构造器 raise，main 仍 rc 0。"""

    def exploding(*a, **kw):
        raise AssertionError("QwenEye 不应被实例化（全 cache 命中零实例化）")

    work = make_workdir(tmp_path, n_shots=1)
    vch = jm.h3s.video_content_hash(str(work / "h264.mp4"))
    sha16 = jm.regen_sha16(str(work / "roundtrip" / "shot_001_regen.mp4"))
    payload = {
        "video_content_hash": vch, "regen_mp4_sha256_16": sha16,
        "engine_name": jm.ENGINE_NAME, "engine_version": jm.ENGINE_VERSION,
        "prompt_version": "pv1",            # WR-01：key 五字段含 prompt 维
        "grid": {"path": "roundtrip/_judge_grids/shot_001.jpg",
                 "w": 1370, "h": 1476},
        "attempts": [{"parse": "ok", "raw_len": 100}],
        "parsed": {"attribution": "prompt_faithful", "confidence": 0.9,
                   "reason": "cache 中的历史判定"},
        "judged_at": "2026-08-20T00:00:00",
    }
    cache_file = work / jm.JUDGE_CACHE_SUBDIR / "shot_001.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(json.dumps(payload, ensure_ascii=False),
                          encoding="utf-8")
    patch_judge(monkeypatch, eye_cls=exploding)
    assert run_main(work) == 0
    # CR-01：全命中早退不吞 sidecar——judge 半边缺席时从 cache 回填
    side = read_sidecar(work)
    assert validate_sidecar(side) == []
    assert side["shots"][0]["scores"]["judge"]["attribution"] == \
        "prompt_faithful"
    assert side["shots"][0]["scores"]["judge"]["confidence"] == 0.9


def test_judge_cache_hit_backfills_missing_sidecar_half(tmp_path, monkeypatch):
    """CR-01：批末 sidecar 写未发生（cache 已持久、sidecar 无 judge 半边）→
    重跑全命中也从 cache parsed 回填——零引擎实例化，判定回到 roundtrip.json。"""

    def exploding(*a, **kw):
        raise AssertionError("QwenEye 不应被实例化（全 cache 命中零实例化）")

    work = make_workdir(tmp_path, n_shots=1)
    eye_cls, _state = make_fake_eye([good_answer()])
    patch_judge(monkeypatch, eye_cls=eye_cls)
    assert run_main(work) == 0
    # 模拟中断：roundtrip.json 回到只有 regen 半边的状态（cache 保留）
    side = read_sidecar(work)
    side["shots"][0].pop("scores", None)
    write_sidecar(work, side)
    patch_judge(monkeypatch, eye_cls=exploding)     # 零实例化仍必须回填
    assert run_main(work) == 0
    after = read_sidecar(work)
    assert validate_sidecar(after) == []
    judge = after["shots"][0]["scores"]["judge"]
    assert judge["attribution"] == "prompt_faithful"
    assert judge["confidence"] == 0.85
    assert judge["reason"] == json.loads(good_answer())["reason"]


def test_judge_cache_key_prompt_revision_rejudges(tmp_path, monkeypatch):
    """WR-01：prompt_version 变（prompts.json 改稿、regen mp4 字节不变）→
    cache key 不等 → 必重判；cache payload 留档 prompt_version 维。"""
    work = make_workdir(tmp_path, n_shots=1)
    eye_cls, state = make_fake_eye([good_answer(),
                                    good_answer(attribution="model_diverged")])
    patch_judge(monkeypatch, eye_cls=eye_cls)
    assert run_main(work) == 0
    assert len(state["questions"]) == 1                # 首跑判定一次
    # prompts.json 改稿：sidecar regen 半边 prompt_version pv1 → pv2
    #（regen mp4 字节不变——sha16/vch 均不变，只有 prompt 维变）
    side = read_sidecar(work)
    side["shots"][0]["regen"]["prompt_version"] = "pv2"
    write_sidecar(work, side)
    assert run_main(work) == 0
    assert len(state["questions"]) == 2                # 重判（stale 不命中）
    payload = read_cache(work, 1)
    assert payload["prompt_version"] == "pv2"          # key 维进 payload 留档
    after = read_sidecar(work)
    assert validate_sidecar(after) == []
    judge = after["shots"][0]["scores"]["judge"]
    assert judge["attribution"] == "model_diverged"    # 新判定覆盖旧归因


def test_engine_unavailable_degrade(tmp_path, monkeypatch):
    """ensure_ready 两败（重试一次后仍失败）→ str warning + rc=0 + sidecar
    原样；stop_if_owned 仍在 finally 被调用。"""
    work = make_workdir(tmp_path, n_shots=1)
    before = (work / "roundtrip.json").read_bytes()
    eye_cls, _state = make_fake_eye(
        [], ensure_seq=[(False, True), (False, True)])
    patch_judge(monkeypatch, eye_cls=eye_cls)
    assert run_main(work) == 0
    assert (work / "roundtrip.json").read_bytes() == before   # sidecar 原样
    warns = read_warnings(work)
    assert any(isinstance(w, str) and "引擎不可用" in w for w in warns)
    assert not (work / jm.JUDGE_CACHE_SUBDIR / "shot_001.json").exists()


# ── --apply-verdict（SCORE-03 硬合取 / DATASET-01 冻结）─────────────────────

def preset_signals(work, rows):
    """把 {sid: (sim, attribution|None, verdict|None)} 预置进 roundtrip.json。"""
    side = read_sidecar(work)
    by = {s["shot_id"]: s for s in side["shots"]}
    for sid, (sim, attribution, verdict) in rows.items():
        entry = by[sid]
        scores = {}
        if sim is not None:
            scores["midframe_sim"] = {"score": sim,
                                      "model": "siglip-so400m-patch14-384"}
        if attribution is not None:
            scores["judge"] = {"attribution": attribution,
                               "confidence": 0.8, "reason": "预置归因理由"}
        if scores:
            entry["scores"] = scores
        if verdict is not None:
            entry["verdict"] = verdict
    write_sidecar(work, side)


def test_apply_verdict_hard_conjunction_three_states(tmp_path):
    """硬合取三态：0.95+faithful→accepted；0.95+model_diverged→rejected；
    0.80+faithful@τ=0.9→rejected（sim 单低也拒）；source=auto + decided_at。"""
    work = make_workdir(tmp_path, n_shots=3)
    preset_signals(work, {
        1: (0.95, "prompt_faithful", None),
        2: (0.95, "model_diverged", None),
        3: (0.80, "prompt_faithful", None),
    })
    assert run_main(work, ["--apply-verdict", "--tau-sim", "0.9"]) == 0
    side = read_sidecar(work)
    assert validate_sidecar(side) == []
    by = {s["shot_id"]: s for s in side["shots"]}
    assert by[1]["verdict"]["decision"] == "accepted"
    assert by[2]["verdict"]["decision"] == "rejected"
    assert by[3]["verdict"]["decision"] == "rejected"
    for sid in (1, 2, 3):
        v = by[sid]["verdict"]
        assert v["source"] == "auto"
        assert isinstance(v["decided_at"], str) and v["decided_at"]
        # scores 半边原样保留（verdict 写入不碰 scores）
        assert "midframe_sim" in by[sid]["scores"]


def test_apply_verdict_frozen_idempotent(tmp_path):
    """冻结幂等：预存 rejected（source=human）verdict + τ 变为会 accept →
    原样不覆盖；缺 verdict 的镜照常补写。"""
    work = make_workdir(tmp_path, n_shots=2)
    frozen_verdict = {"decision": "rejected", "source": "human",
                      "decided_at": "2026-08-19T00:00:00"}
    preset_signals(work, {
        1: (0.95, "prompt_faithful", frozen_verdict),
        2: (0.95, "prompt_faithful", None),
    })
    assert run_main(work, ["--apply-verdict", "--tau-sim", "0.1"]) == 0
    by = {s["shot_id"]: s for s in read_sidecar(work)["shots"]}
    assert by[1]["verdict"] == frozen_verdict        # 冻结：永不覆盖
    assert by[2]["verdict"]["decision"] == "accepted"  # 缺 verdict 补写
    assert by[2]["verdict"]["source"] == "auto"


def test_apply_verdict_missing_signal_skipped_with_warning(tmp_path):
    """信号缺一（无 judge / 无 midframe_sim）→ 跳过 + str warning 列 shot_id。"""
    work = make_workdir(tmp_path, n_shots=2)
    preset_signals(work, {
        1: (0.95, None, None),      # 只有 sim，无 judge
        2: (None, "prompt_faithful", None),   # 只有 judge，无 sim
    })
    assert run_main(work, ["--apply-verdict", "--tau-sim", "0.9"]) == 0
    side = read_sidecar(work)
    by = {s["shot_id"]: s for s in side["shots"]}
    assert "verdict" not in by[1]
    assert "verdict" not in by[2]
    warns = read_warnings(work)
    assert any(isinstance(w, str) and "shot 1" in w and "双信号缺一" in w
               for w in warns)
    assert any(isinstance(w, str) and "shot 2" in w and "双信号缺一" in w
               for w in warns)


def test_apply_verdict_requires_tau_sim(tmp_path):
    """--apply-verdict 缺 --tau-sim → 中文报错退出（SystemExit）。"""
    work = make_workdir(tmp_path, n_shots=1)
    with pytest.raises(SystemExit):
        run_main(work, ["--apply-verdict"])


# ── Pitfall 8 双向 + WR-04 + schema gate ────────────────────────────────────

def test_pitfall8_h3_regen_rewrite_preserves_verdict(tmp_path):
    """Pitfall 8 双向：--apply-verdict 后跑 h3s.write_roundtrip_sidecar 重写
    regen 半边 → verdict + scores 原样（两写入器互不破坏对方的对偶半边）。"""
    work = make_workdir(tmp_path, n_shots=1)
    preset_signals(work, {1: (0.95, "prompt_faithful", None)})
    assert run_main(work, ["--apply-verdict", "--tau-sim", "0.9"]) == 0
    before = read_sidecar(work)
    # h3_regen 风格重写 regen 半边（Phase 22 重渲场景）
    assert jm.h3s.write_roundtrip_sidecar(str(work), [{
        "shot_id": 1,
        "regen": {"path": "roundtrip/shot_001_regen.mp4",
                  "video_content_hash": "b" * 16,
                  "engine_name": "comfyui-fl2va",
                  "engine_version": "fl2va-int8/euler+simple/15/1344x768",
                  "prompt_version": "pv2",
                  "duration_sec": 7.1, "width": 1344, "height": 768}}]) == []
    after = read_sidecar(work)
    assert validate_sidecar(after) == []
    by = {s["shot_id"]: s for s in after["shots"]}
    assert by[1]["verdict"] == before["shots"][0]["verdict"]     # verdict 原样
    assert by[1]["scores"] == before["shots"][0]["scores"]       # scores 原样
    assert by[1]["regen"]["engine_version"].endswith("1344x768")  # regen 已替换


def test_preexisting_bad_entry_stripped_with_backup(tmp_path, monkeypatch):
    """WR-04：预存坏条目（path 穿越）→ 剔除 + .bak-<ts> 备份 + str warning；
    本批 judge 结果照常落盘。"""
    work = make_workdir(tmp_path, n_shots=1)
    side = read_sidecar(work)
    side["shots"].append({"shot_id": 5, "regen": {
        "path": "roundtrip/../../evil.mp4",      # schema pattern 拒
        "video_content_hash": "a" * 16, "engine_name": "e",
        "engine_version": "v", "prompt_version": "p"}})
    write_sidecar(work, side)
    eye_cls, _ = make_fake_eye([good_answer()])
    patch_judge(monkeypatch, eye_cls=eye_cls)
    assert run_main(work) == 0
    after = read_sidecar(work)
    assert validate_sidecar(after) == []
    assert [s["shot_id"] for s in after["shots"]] == [1]     # 坏条目 5 剔除
    assert after["shots"][0]["scores"]["judge"]["attribution"] == "prompt_faithful"
    baks = list(work.glob("roundtrip.json.bak-*"))
    assert len(baks) == 1                                    # 原文件已备份
    warns = read_warnings(work)
    assert any(isinstance(w, str) and "shot 5" in w and "剔除" in w
               for w in warns)


def test_schema_full_entry_valid(tmp_path):
    """schema gate（独立校验面）：regen + scores 双半 + verdict 全字段条目过
    Draft202012Validator（直接读 spec/schemas/roundtrip.schema.json）。"""
    payload = {"schema_version": "1.3", "shots": [{
        "shot_id": 1,
        "regen": {"path": "roundtrip/shot_001_regen.mp4",
                  "video_content_hash": "ece64d62bcbc534a",
                  "engine_name": "comfyui-fl2va",
                  "engine_version": "fl2va-int8/euler+simple/15/1344x768",
                  "prompt_version": "ab12cd34", "duration_sec": 6.73,
                  "width": 1344, "height": 768},
        "scores": {
            "midframe_sim": {"score": 0.9173,
                             "model": "siglip-so400m-patch14-384"},
            "judge": {"attribution": "prompt_faithful", "confidence": 0.85,
                      "reason": "prompt 要求'递红浆果'且中段帧渲染一致"}},
        "verdict": {"decision": "accepted", "source": "auto",
                    "decided_at": "2026-08-20T12:00:00"}}]}
    schema = json.loads((REPO_ROOT / "spec" / "schemas"
                         / "roundtrip.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    assert list(jm.h3s._iter_sidecar_errors(payload)) == []   # 同源复核


def test_write_judge_sidecar_shallow_merge(tmp_path):
    """scores 浅合并对向用例：judge 写入不丢预存 midframe_sim + verdict。"""
    work = make_workdir(tmp_path, n_shots=1)
    mid = {"score": 0.9, "model": "siglip-so400m-patch14-384"}
    verdict = {"decision": "rejected", "source": "human",
               "decided_at": "2026-08-19T00:00:00"}
    side = read_sidecar(work)
    side["shots"][0]["scores"] = {"midframe_sim": mid}
    side["shots"][0]["verdict"] = verdict
    write_sidecar(work, side)
    warnings = jm.write_judge_sidecar(str(work), [
        {"shot_id": 1, "scores": {"judge": {
            "attribution": "prompt_underspecified", "confidence": 0.6,
            "reason": "prompt 未描述关键动作细节"}}}])
    assert warnings == []
    after = read_sidecar(work)
    assert validate_sidecar(after) == []
    entry = after["shots"][0]
    assert entry["scores"]["midframe_sim"] == mid            # 对侧半边不丢
    assert entry["scores"]["judge"]["attribution"] == "prompt_underspecified"
    assert entry["verdict"] == verdict                       # verdict 不动


# ── summarize_scores（SCORE-03 校准素材汇编器）──────────────────────────────

def test_summarize_scores_known_values():
    """19 个手写 (sim, attribution) 对（覆盖三桶 + 已知排序）→ 精确分位数
    （线性插值）/ 桶计数 / τ 预演计数逐值相等。"""
    sims = [round(0.80 + 0.01 * i, 2) for i in range(19)]    # 0.80..0.98
    attribs = (["prompt_underspecified"] * 3                  # 0.80-0.82
               + ["model_diverged"] * 5                       # 0.83-0.87
               + ["prompt_faithful"] * 11)                    # 0.88-0.98
    pairs = list(zip(sims, attribs))
    summary = jm.summarize_scores(pairs, taus=[0.88, 0.90])
    assert summary["n"] == 19
    # 分位数（inclusive 线性插值：h=(N-1)·p，floor/ceil 内插；N=19）
    assert summary["quantiles"]["p10"] == pytest.approx(0.818, abs=1e-9)
    assert summary["quantiles"]["p25"] == pytest.approx(0.845, abs=1e-9)
    assert summary["quantiles"]["p50"] == pytest.approx(0.89, abs=1e-9)
    assert summary["quantiles"]["p75"] == pytest.approx(0.935, abs=1e-9)
    assert summary["quantiles"]["p90"] == pytest.approx(0.962, abs=1e-9)
    # 三桶计数
    assert summary["buckets"] == {"prompt_faithful": 11,
                                  "model_diverged": 5,
                                  "prompt_underspecified": 3}
    # τ 预演：τ=0.88 → accepted 11（0.88..0.98 faithful）/ rejected 8（5+3）
    t88, t90 = summary["tau_preview"]
    assert t88["tau"] == pytest.approx(0.88)
    assert t88["accepted"] == 11
    assert t88["rejected"] == 8
    assert t88["rejected_by_bucket"] == {"prompt_faithful": 0,
                                         "model_diverged": 5,
                                         "prompt_underspecified": 3}
    # τ=0.90 → accepted 9 / faithful<τ=2 / rejected 10
    assert t90["tau"] == pytest.approx(0.90)
    assert t90["accepted"] == 9
    assert t90["rejected"] == 10
    assert t90["rejected_by_bucket"] == {"prompt_faithful": 2,
                                         "model_diverged": 5,
                                         "prompt_underspecified": 3}


def test_summarize_scores_missing_signals_counted_in_n():
    """信号缺席的镜计入 n（分布分母如实），不进分位数/桶。"""
    summary = jm.summarize_scores(
        [(0.9, "prompt_faithful"), (None, None), (0.8, None), (None, "model_diverged")],
        taus=[0.85])
    assert summary["n"] == 4
    assert summary["buckets"]["prompt_faithful"] == 1
    # 分桶只看归因本身（sim 缺席仍进桶——归因面如实）；tau_preview 只看
    # 双信号齐备对（diverged 无 sim 不进预演）
    assert summary["buckets"]["model_diverged"] == 1
    assert summary["quantiles"]["p50"] == pytest.approx(0.85, abs=1e-9)
    assert summary["tau_preview"][0]["accepted"] == 1
    assert summary["tau_preview"][0]["rejected"] == 0
    assert summary["tau_preview"][0]["rejected_by_bucket"] == {
        "prompt_faithful": 0, "model_diverged": 0,
        "prompt_underspecified": 0}


def test_summarize_mode_readonly(tmp_path):
    """--summarize：只读打印不写盘（sidecar/warnings 均不产生新写入）。"""
    work = make_workdir(tmp_path, n_shots=1)
    preset_signals(work, {1: (0.93, "prompt_faithful", None)})
    before = (work / "roundtrip.json").read_bytes()
    assert run_main(work, ["--summarize"]) == 0
    assert (work / "roundtrip.json").read_bytes() == before
    assert not (work / "route_cache" / "warnings.json").exists()
