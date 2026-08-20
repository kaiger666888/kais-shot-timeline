r"""roundtrip 审阅面板生成器测试 —— SC3 三注入 + 六态 + payload 形状（22-01 Task 2）。

覆盖（行为清单逐项，mirror test_judge.py 惯例）：
  1. fixture schema-valid：Draft202012Validator(roundtrip.schema.json) 对
     tests/fixtures/roundtrip_sample.json 0 errors；六态 + 三 payload 在场。
  2. SC3 XSS 三 payload × 三注入位（reason / status.error / midframe_sim.model）：
     原文不存活 / _esc 转义态在场 / onerror= 属性注入不存活（排除转义态后）/
     base64 仅以纯文本在场（无 decode/eval 路径）。
  3. bootstrap `</`→`<\/` 破出防护专测：payload 含 </script> 时 bootstrap JSON
     段呈 <\/script>（replace 后形态），全文无裸破出。
  4. 六态呈现：空 sidecar（面板仍生成 + 空 edits 导出 schema 形状在场）/
     regen 失败降级卡（红边 + ⚠ 文案 + 无 video + 三态按钮保留）/ 未打分 /
     未裁决 / human 覆盖（·human 后缀 + decided_at title）。
  5. exportEdits JS 源级形状：int 升序 numeric comparator（a - b）/ 维持 auto
     单 Set 分桶不进 edits / review_notes 键 / 下载文件名 roundtrip-edits.json /
     Blob + URL.createObjectURL + revoke。
  6. 双 video src：左含 #t= Media Fragments；右含 roundtrip/shot_ 相对路径；
     卡 id card-shot_NNN 与 queue 锚点同款。
  7. 零 innerHTML（生成 HTML 全文禁用断言）。
  8. CLI 原子写：产出后无 .tmp 残留、文件 UTF-8 可读、收尾打印含 shot 计数。

模块直调形态：importlib spec_from_file_location("gen_roundtrip_review", ...)
+ main(argv list)（mirror test_judge.py:37-40 先例）；fixture 变体用
json.loads + json.dumps 就地改写注入字段后落 tmp（不回写共享 fixture）。
"""
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "roundtrip_sample.json"
SCHEMA = REPO_ROOT / "spec" / "schemas" / "roundtrip.schema.json"

_spec = importlib.util.spec_from_file_location(
    "gen_roundtrip_review", REPO_ROOT / "html" / "gen_roundtrip_review.py")
gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gr)

# SC3 三类注入 payload（22-RESEARCH §Code Examples 骨架逐字）
PAYLOADS = [
    "<script>alert(1)</script>",           # script 岛注入
    '" onerror="alert(1)" x="',            # 属性破出型（onerror=）
    "PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",  # base64（仅可作纯文本呈现）
]
INJECTION_POSITIONS = ["reason", "status.error", "model"]

# 最小 shots.json（id 与 fixture 对齐——左 video #t= 时窗来源）
MIN_SHOTS = [
    {"id": 3, "start_sec": 1.0, "end_sec": 4.0, "duration": 3.0},
    {"id": 7, "start_sec": 10.0, "end_sec": 13.5, "duration": 3.5},
    {"id": 10, "start_sec": 20.0, "end_sec": 23.0, "duration": 3.0},
    {"id": 12, "start_sec": 30.0, "end_sec": 36.0, "duration": 6.0},
    {"id": 19, "start_sec": 40.0, "end_sec": 45.5, "duration": 5.5},
    {"id": 84, "start_sec": 60.0, "end_sec": 63.0, "duration": 3.0},
]

# 最小 prompts.json（shot 3 带全六 facet + refs；其余缺席 → 快照区 (无) 路径）
MIN_PROMPTS = [
    {
        "shot_id": 3, "start_sec": 1.0, "end_sec": 4.0, "duration": 3.0,
        "prompt_text": "独角仙武士把红浆果递给毛毛虫小孩，小孩抬头望向它。",
        "subject": "独角仙武士与毛毛虫小孩",
        "action": "递红浆果、抬头注视",
        "camera": "中景，缓推",
        "scene": "林间空地",
        "lighting": "午后柔光",
        "style": "三维动画",
        "character_refs": ["char_001"],
        "prop_refs": [],
    },
    {
        "shot_id": 7, "start_sec": 10.0, "end_sec": 13.5, "duration": 3.5,
        "prompt_text": "两名侠客在屋檐上对峙，风卷落叶。",
        "subject": "两名侠客", "action": "对峙", "camera": "全景",
        "scene": "屋檐", "lighting": "黄昏", "style": "水墨",
    },
]


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run_gen(tmp_path, sidecar_obj):
    """落盘 sidecar/shots/prompts/video 到 tmp_path → 直调 gr.main(argv) → 返回 HTML。"""
    rt = tmp_path / "roundtrip.json"
    rt.write_text(json.dumps(sidecar_obj, ensure_ascii=False), encoding="utf-8")
    shots = tmp_path / "shots.json"
    shots.write_text(json.dumps(MIN_SHOTS), encoding="utf-8")
    prompts = tmp_path / "prompts.json"
    prompts.write_text(json.dumps(MIN_PROMPTS, ensure_ascii=False), encoding="utf-8")
    video = tmp_path / "video.mp4"
    video.write_bytes(b"")
    out = tmp_path / "review.html"
    gr.main(["--roundtrip", str(rt), "--video", str(video),
             "--shots", str(shots), "--prompts", str(prompts),
             "--output", str(out)])
    return out.read_text(encoding="utf-8")


def inject(base, position, payload):
    """deep-copy fixture 后把 payload 注入指定位（reason / status.error / model）。

    只改既有对应半边的条目（reason → 有 judge 的条目；status.error → failed
    条目；model → 有 midframe_sim 的条目）——保持 schema-valid。
    """
    doc = json.loads(json.dumps(base))
    for s in doc["shots"]:
        if position == "reason":
            if "scores" in s and "judge" in s["scores"]:
                s["scores"]["judge"]["reason"] = payload
                return doc
        elif position == "status.error":
            if "status" in s:
                s["status"]["error"] = payload
                return doc
        elif position == "model":
            if "scores" in s and "midframe_sim" in s["scores"]:
                s["scores"]["midframe_sim"]["model"] = payload
                return doc
    raise AssertionError(f"fixture 无可注入位: {position}")


# ── 1. fixture schema-valid + 六态/三 payload 在场 ──────────────────────────

def test_fixture_schema_valid():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    doc = load_fixture()
    errors = list(Draft202012Validator(schema).iter_errors(doc))
    assert errors == []


def test_fixture_covers_six_states_with_payloads():
    doc = load_fixture()
    by = {s["shot_id"]: s for s in doc["shots"]}
    assert set(by) == {3, 7, 10, 12, 19, 84}
    # 态 1：正常 accepted·auto（全套 regen/scores/verdict）
    assert by[3]["verdict"] == {"decision": "accepted", "source": "auto",
                                "decided_at": "2026-08-20T02:05:49"}
    # 态 2：rejected 条目携带 script payload（reason 位）
    assert by[7]["verdict"]["decision"] == "rejected"
    assert PAYLOADS[0] in by[7]["scores"]["judge"]["reason"]
    # 态 3：status failed 条目携带 onerror payload（status.error 位）
    assert by[10]["status"]["state"] == "failed"
    assert PAYLOADS[1] in by[10]["status"]["error"]
    # 态 4：有 regen 无 scores（未打分）
    assert "regen" in by[12] and "scores" not in by[12]
    # 态 5：有 scores 无 verdict（未裁决）+ base64 payload（model 位）
    assert "scores" in by[19] and "verdict" not in by[19]
    assert PAYLOADS[2] in by[19]["scores"]["midframe_sim"]["model"]
    # 态 6：human 覆盖条目
    assert by[84]["verdict"]["source"] == "human"


# ── 2. SC3 三 payload × 三注入位 ────────────────────────────────────────────

@pytest.mark.parametrize("payload", PAYLOADS)
@pytest.mark.parametrize("position", INJECTION_POSITIONS)
def test_xss_three_payloads(tmp_path, payload, position):
    doc = inject(load_fixture(), position, payload)
    html = run_gen(tmp_path, doc)
    # _esc 转义态在场（base64 无可转义字符 → 与原文等价的纯文本在场）
    assert gr._esc(payload) in html
    if payload == PAYLOADS[0]:  # script 岛：原文不存活
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
    elif payload == PAYLOADS[1]:  # 属性破出：onerror= 属性注入不存活（排除转义态后）
        assert 'onerror="' not in html.replace("onerror=&quot;", "")
        assert payload not in html
    else:  # base64：仅以纯文本在场，无 decode/eval 路径
        assert "atob" not in html
        assert "eval(" not in html
        assert payload in html


# ── 3. bootstrap </ 转义专测 ────────────────────────────────────────────────

def test_bootstrap_script_breakout(tmp_path):
    doc = inject(load_fixture(), "reason", "<script>alert(1)</script>")
    html = run_gen(tmp_path, doc)
    # 无裸 </script> 破出：payload 原文（含 </script>）不出现在 HTML 任何位置
    assert "<script>alert(1)</script>" not in html
    # bootstrap JSON 段呈 replace 后形态（<\/script>）
    assert "alert(1)<\\/script>" in html


# ── 4. 六态呈现 ─────────────────────────────────────────────────────────────

def test_state_empty_sidecar(tmp_path, capsys):
    shots = tmp_path / "shots.json"
    shots.write_text(json.dumps(MIN_SHOTS), encoding="utf-8")
    prompts = tmp_path / "prompts.json"
    prompts.write_text(json.dumps(MIN_PROMPTS, ensure_ascii=False), encoding="utf-8")
    video = tmp_path / "video.mp4"
    video.write_bytes(b"")
    out = tmp_path / "review.html"
    # roundtrip 指向缺席文件：不 raise，产空态面板
    gr.main(["--roundtrip", str(tmp_path / "nonexistent.json"),
             "--video", str(video), "--shots", str(shots),
             "--prompts", str(prompts), "--output", str(out)])
    html = out.read_text(encoding="utf-8")
    assert "(空 roundtrip —— 无 shot 可审阅)" in html
    assert "先运行 step_roundtrip 产出 roundtrip.json，再运行 html/gen_roundtrip_review.py 生成审阅面板" in html
    assert "(无)" in html  # queue 空态
    # 空 edits 导出仍 schema-valid 形状（accept/reject 数组键在场）
    assert "accept_overrides" in html and "reject_overrides" in html
    assert "Array.from(state.accept).sort((a, b) => a - b)" in html
    assert "(0 shots)" in capsys.readouterr().out


def test_state_regen_failed_degraded_card(tmp_path):
    html = run_gen(tmp_path, load_fixture())
    assert "⚠ regen 失败" in html
    assert "card-failed" in html  # 红边降级类
    # failed 卡（shot 10）无 video 行：6 条目中 5 条有 regen → 恰 10 个 <video>
    assert html.count("<video") == 10
    # 三态按钮保留（human 覆盖是这类卡拿到 verdict 的唯一路径）
    assert "setState(10, 'accept')" in html
    # status.error 已转义（onerror payload 不以原文存活）
    assert PAYLOADS[1] not in html


def test_state_unscored_and_pending_and_human(tmp_path):
    html = run_gen(tmp_path, load_fixture())
    assert "未打分" in html       # shot 12：有 regen 无 scores
    assert "未裁决" in html       # shot 12/19：无 verdict
    assert "accepted·human" in html  # shot 84：human 覆盖 badge 后缀
    assert 'title="2026-08-20T06:00:00"' in html  # human 时 title 提示 decided_at


# ── 5. exportEdits JS 源级形状 ──────────────────────────────────────────────

def test_export_edits_js_shape(tmp_path):
    html = run_gen(tmp_path, load_fixture())
    # int 升序必须 numeric comparator（registry 用字典序因其 ID 是字符串）
    assert "Array.from(state.accept).sort((a, b) => a - b)" in html
    assert "Array.from(state.reject).sort((a, b) => a - b)" in html
    # 维持 auto：单 Set 分桶存在、但绝不序列化进 edits payload
    assert "keepAuto: new Set()" in html
    assert "Array.from(state.keepAuto)" not in html
    edits_body = html.split("function exportEdits")[1].split("URL.revokeObjectURL")[0]
    assert "keepAuto" not in edits_body  # edits 构造体内无 keepAuto 引用
    # payload 键契约（schema 文件 22-02 落地）
    assert "review_notes: `Exported from roundtrip review HTML on ${new Date().toISOString()}`" in html
    # Blob + URL.createObjectURL + 下载文件名 + revoke（mirror registry :642-673）
    assert "URL.createObjectURL" in html
    assert "URL.revokeObjectURL" in html
    assert "a.download = 'roundtrip-edits.json'" in html


# ── 6. 双 video src ─────────────────────────────────────────────────────────

def test_video_src(tmp_path):
    html = run_gen(tmp_path, load_fixture())
    # 左：Media Fragments 时窗（shot 3 → MIN_SHOTS 1.0-4.0）
    assert "#t=1.000,4.000" in html
    # 右：regen 相对路径原样
    assert "roundtrip/shot_003_regen.mp4" in html
    # 卡 id 与 queue 锚点同款
    assert 'id="card-shot_003"' in html
    assert 'href="#card-shot_003"' in html


# ── 7. 零 innerHTML ─────────────────────────────────────────────────────────

def test_no_innerhtml(tmp_path):
    html = run_gen(tmp_path, load_fixture())
    assert "innerHTML" not in html


# ── 8. CLI 原子写 ───────────────────────────────────────────────────────────

def test_cli_atomic_write(tmp_path):
    run_gen(tmp_path, load_fixture())
    assert list(tmp_path.glob("*.tmp*")) == []  # 无 .tmp 残留
    raw = (tmp_path / "review.html").read_bytes()
    raw.decode("utf-8")  # UTF-8 可读不 raise
