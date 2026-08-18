"""canvas_import 三场景测试 —— mock urllib.request.urlopen，零真网络。

覆盖（mirror tests/test_qwen_eye_client.py 的记录式替身 + monkeypatch 模式）：
  * 场景A（复用）：projects 已含同名行 → 复用 id，零 addProject 调用。
  * 场景B（自动创建）：projects 空 → addProject 11 字段（8 空串 + name +
    intro=asset.json video stem + mode="canvas-v2"）→ 回读 projects 拿新 id
    （addProject 响应刻意无 id —— 钉死 kap src/routes/project/addProject.ts:44
    只返 {message} 的真实形状）→ import projectId == 新 id。
  * import body 字段：projectId/episodesId 为 JSON number（int，非 str）、
    workdir == abspath(asset_dir)、mode == "replace"、Content-Type 含
    application/json、raw bytes 可 utf-8 decode 且含 CJK 项目名。
  * 场景B'（拒绝创建）：projects 空 + --no-create-project → SystemExit 非 0，
    零 addProject 调用。
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import canvas_import as ci  # noqa: E402


# ── 替身设施 ───────────────────────────────────────────────────────────────

class _FakeResponse:
    """urlopen 语境管理器替身 —— read() 返回预设 envelope 的 UTF-8 bytes。"""

    def __init__(self, body: dict):
        self._body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(monkeypatch, responses: list) -> list:
    """按调用序回放预设 envelope body；记录 (url, data_bytes, headers) 进 calls。

    直接 mock urllib.request.urlopen 层（脚本唯一 HTTP 出口），顺带覆盖
    UTF-8 编码与 Content-Type header 断言。多余调用 → pop 空 list → IndexError
    → 测试失败（调用次数上限也被钉住）。
    """
    calls = []

    def fake(req, timeout=None):
        body = responses.pop(0)
        calls.append((req.full_url, req.data, dict(req.headers)))
        return _FakeResponse(body)

    monkeypatch.setattr(ci.urllib.request, "urlopen", fake)
    return calls


@pytest.fixture
def asset_dir(tmp_path):
    """最小 asset-dir：只含 asset.json（intro 数据源）。"""
    (tmp_path / "asset.json").write_text(
        json.dumps({"source": {"video_filename":
                               "虫虫武侠小故事《小江湖》第01话：测试.mp4"}},
                   ensure_ascii=False),
        encoding="utf-8")
    return tmp_path


def _run_main(monkeypatch, argv: list):
    """以给定 argv 跑 ci.main()（argparse 读 sys.argv，monkeypatch 负责还原）。"""
    monkeypatch.setattr(sys, "argv", ["canvas_import.py"] + argv)
    ci.main()


def _body_of(call) -> dict:
    """被 capture 到的请求 body：raw bytes → utf-8 decode → JSON。"""
    return json.loads(call[1].decode("utf-8"))


# ── 场景A：复用已有项目 ────────────────────────────────────────────────────

def test_reuse_existing_project(asset_dir, monkeypatch):
    """projects 含 name 精确匹配行 → 复用 id=123，只 2 次 HTTP，零 addProject。"""
    name = "小江湖·逆推资产集(ep01)"
    calls = _fake_urlopen(monkeypatch, [
        {"code": 200, "data": [
            {"id": 999, "name": "别的不相关项目", "mode": "canvas-v2"},
            {"id": 123, "name": name, "mode": "canvas-v2"},
        ]},
        {"code": 200, "data": {"imported": 5, "links": 5, "artifacts": 9,
                               "phases": 3, "mode": "replace",
                               "workdir": "/x"}},
    ])
    _run_main(monkeypatch, ["--asset-dir", str(asset_dir),
                            "--project-name", name])
    assert len(calls) == 2                       # projects + import，仅此两次
    assert calls[0][0].endswith("/api/canvas/projects")
    assert calls[1][0].endswith("/api/canvas/v2/import-from-dir")
    # 零 addProject —— 复用路径全程不建项目
    assert not any(c[0].endswith("/api/project/addProject") for c in calls)
    assert _body_of(calls[1])["projectId"] == 123


# ── 场景B：自动创建（addProject → 回读 → import）─────────────────────────

def test_create_project_when_missing(asset_dir, monkeypatch):
    """projects 空 → addProject 11 字段 → 回读拿新 id=777 → import。"""
    name = "小江湖·逆推资产集(ep01)"
    calls = _fake_urlopen(monkeypatch, [
        {"code": 200, "data": []},
        # 刻意无 id —— kap addProject 响应只含 {message}（源码验证过的事实）
        {"code": 200, "data": {"message": "新增项目成功"}},
        {"code": 200, "data": [{"id": 777, "name": name}]},
        {"code": 200, "data": {"imported": 1, "links": 1, "artifacts": 2,
                               "phases": 1, "mode": "replace",
                               "workdir": "/x"}},
    ])
    _run_main(monkeypatch, ["--asset-dir", str(asset_dir),
                            "--project-name", name])
    # 4 次调用顺序：projects → addProject → 回读 projects → import
    assert len(calls) == 4
    assert calls[1][0].endswith("/api/project/addProject")
    assert calls[2][0].endswith("/api/canvas/projects")   # 回读被钉住
    add_body = _body_of(calls[1])
    for key in ("projectType", "type", "artStyle", "directorManual",
                "videoRatio", "imageModel", "videoModel", "imageQuality"):
        assert add_body[key] == ""               # 8 个可选字段全空串（对齐 ep01 行）
    assert add_body["name"] == name
    assert add_body["intro"] == "虫虫武侠小故事《小江湖》第01话：测试"
    assert add_body["mode"] == "canvas-v2"
    assert len(add_body) == 11                   # 恰好 11 字段（validateFields 契约）
    assert _body_of(calls[3])["projectId"] == 777


# ── import body 字段与编码 ────────────────────────────────────────────────

def test_import_body_fields(asset_dir, monkeypatch):
    """projectId/episodesId 为 int、episodesId==1、workdir==abspath、mode==replace、
    Content-Type 含 application/json、raw bytes utf-8 可解且含 CJK。"""
    name = "小江湖·逆推资产集(ep01)"
    calls = _fake_urlopen(monkeypatch, [
        {"code": 200, "data": [{"id": 123, "name": name}]},
        {"code": 200, "data": {"imported": 0, "links": 0, "artifacts": 0,
                               "phases": 0, "mode": "replace", "workdir": "/x"}},
    ])
    _run_main(monkeypatch, ["--asset-dir", str(asset_dir),
                            "--project-name", name])
    url, data, headers = calls[1]
    body = json.loads(data.decode("utf-8"))
    # zod z.number() —— 必须是 JSON number，字符串会被拒
    assert isinstance(body["projectId"], int)
    assert isinstance(body["episodesId"], int)
    assert body["episodesId"] == 1
    assert body["workdir"] == str(asset_dir)     # abspath（tmp_path 已是绝对）
    assert body["mode"] == "replace"
    lowered = {k.lower(): v for k, v in headers.items()}
    assert "application/json" in lowered.get("content-type", "")
    # UTF-8 编码 + ensure_ascii=False —— CJK 项目名以原文出现在 raw bytes
    assert name in data.decode("utf-8")


# ── 场景B'：--no-create-project 拒绝创建 ─────────────────────────────────

def test_no_create_project_rejects(asset_dir, monkeypatch):
    """projects 空 + --no-create-project → SystemExit 非 0，零 addProject。"""
    calls = _fake_urlopen(monkeypatch, [{"code": 200, "data": []}])
    monkeypatch.setattr(
        sys, "argv",
        ["canvas_import.py", "--asset-dir", str(asset_dir),
         "--project-name", "不存在的项目", "--no-create-project"])
    with pytest.raises(SystemExit) as excinfo:
        ci.main()
    assert excinfo.value.code != 0
    assert len(calls) == 1                       # 只 list 了一次，零 addProject
