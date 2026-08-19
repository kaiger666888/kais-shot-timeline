"""qwen_eye_client 生命周期状态机测试 —— 全部 monkeypatch HTTP/子进程，不打真引擎。

覆盖（Phase 1 交付物 4-a）：
  * 健康不拥有：health 先返回 200 → (True, False)，绝不 allocate/stop。
  * VRAM 预检短路：health 挂 + free < 14000MiB → (False, False)，零 HTTP allocate。
  * 顺序陷阱：预检在 health 之后（健康 server 自占 VRAM 不被误杀）。
  * stop_if_owned 只停自己拉起的：未拥有 → 不跑 stop 脚本。
  * 启动成功 → 拥有 → stop_if_owned 跑 kap-llm.sh stop。
  * WR-03：start 发起后超时/加载失败 → (False, True) 且 _owned=True →
    stop_if_owned 停半启动 server（防 13.4GB 泄漏）；allocate 授予的
    lease 在 stop 时配对 POST /llm/release（mirror caller），幂等不重复。
  * observe_single 请求 shape：enable_thinking 恒 False、每图一条 user 消息。
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "analysis" / "engine_clients"))

import qwen_eye_client as qec  # noqa: E402
from qwen_eye_client import QwenEye  # noqa: E402


class FakeHTTP:
    """记录式 _http_json 替身 —— 按调用序回放预设 (status, body)。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []          # (url, payload) 元组

    def __call__(self, url, payload=None, timeout=30.0):
        status, body = self.responses.pop(0) if self.responses else (0, None)
        self.calls.append((url, payload))
        if isinstance(body, str):
            body = body.encode()
        return status, body


@pytest.fixture
def no_engine(monkeypatch):
    """打掉的子进程（kap-llm.sh / nvidia-smi）—— 默认 nvidia-smi 不可用 fail-open。"""
    calls = []
    monkeypatch.setattr(qec.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or _FakeProc())
    return calls


class _FakeProc:
    stdout = "0"
    returncode = 0


# ── 生命周期状态机 ────────────────────────────────────────────────────────

def test_healthy_not_owned(no_engine, monkeypatch):
    """health 200 → (True, False)。绝不 allocate、stop_if_owned 无操作。"""
    fake = FakeHTTP([(200, {"status": "ok"})])
    monkeypatch.setattr(QwenEye, "_http_json",
                        classmethod(lambda cls, url, **kw: fake(url, **kw)))
    eye = QwenEye()
    healthy, owned = eye.ensure_ready()
    assert (healthy, owned) == (True, False)
    # 只探了 health，没碰 KAP allocate
    assert all(":10588" not in url for url, _ in fake.calls)
    eye.stop_if_owned()   # not owned → no-op
    assert all("kap-llm.sh" not in " ".join(c) for c in no_engine)


def test_vram_prefetch_short_circuit(no_engine, monkeypatch):
    """health 挂 + free=1000MiB < 14000 → (False, False)，零 allocate HTTP。"""
    monkeypatch.setattr(QwenEye, "_http_json",
                        classmethod(lambda cls, url, **kw: (0, "connection refused")))
    monkeypatch.setattr(QwenEye, "_vram_free_mib",
                        staticmethod(lambda: 1000))
    eye = QwenEye()
    healthy, owned = eye.ensure_ready(timeout_s=6)
    assert (healthy, owned) == (False, False)
    assert not eye._owned
    # 短路后 stop_if_owned 也不该碰 kap-llm.sh stop
    eye.stop_if_owned()
    assert no_engine == []


def test_prefetch_runs_after_health(no_engine, monkeypatch):
    """顺序陷阱：VRAM 预检必须在 health 之后 —— 这里只验证两者都被调用且
    health 先于 nvidia-smi（通过调用序断言）。health OK 时预检直接跳过。"""
    order = []

    def fake_health(timeout=5.0):
        order.append("health")
        return True

    def fake_vram():
        order.append("vram")
        return 1000   # 即使 VRAM 极低，健康 server 也不该被预检杀掉

    monkeypatch.setattr(QwenEye, "_health_ok", classmethod(lambda cls, **kw: fake_health(**kw)))
    monkeypatch.setattr(QwenEye, "_vram_free_mib", staticmethod(fake_vram))
    eye = QwenEye()
    healthy, owned = eye.ensure_ready()
    assert (healthy, owned) == (True, False)
    assert order == ["health"]   # 预检根本没跑 —— 健康即短路


def test_start_success_owned_then_stop(no_engine, monkeypatch):
    """health 挂 → allocate fallback → health 转 200 → (True, True) 拥有；
    stop_if_owned 跑 kap-llm.sh stop；再调一次幂等 no-op。"""
    monkeypatch.setattr(QwenEye, "_http_json",
                        classmethod(lambda cls, url, **kw: (0, "down")))
    # health 用独立替身轮转：两次挂 → 一次好
    health_seq = [False, False, True]
    monkeypatch.setattr(QwenEye, "_health_ok",
                        classmethod(lambda cls, **kw: health_seq.pop(0)))
    monkeypatch.setattr(QwenEye, "_vram_free_mib", staticmethod(lambda: 20000))
    monkeypatch.setattr(QwenEye, "_server_log_size", staticmethod(lambda: 0))
    monkeypatch.setattr(QwenEye, "_server_log_load_failed",
                        staticmethod(lambda offset: False))
    monkeypatch.setattr(qec.time, "sleep", lambda s: None)   # 不真等 3s

    eye = QwenEye()
    healthy, owned = eye.ensure_ready(timeout_s=60)
    assert (healthy, owned) == (True, True)
    assert eye._owned

    eye.stop_if_owned()
    stop_calls = [c for c in no_engine if "stop" in c]
    assert len(stop_calls) == 1
    assert "kap-llm.sh" in " ".join(stop_calls[0])
    assert not eye._owned
    eye.stop_if_owned()   # 幂等
    assert len([c for c in no_engine if "stop" in c]) == 1


def test_stop_if_owned_never_touches_preexisting(no_engine):
    """未拥有（预存在 lease）→ stop_if_owned 绝不跑 kap-llm.sh。"""
    eye = QwenEye()
    eye.stop_if_owned()
    assert no_engine == []


# ── WR-03：失败路径的归属 + KAP lease 配对释放 ────────────────────────────

def _patch_start_env(monkeypatch, health_seq=None, load_failed=False):
    """WR-03 测试公用 patch：VRAM 充足 + log guard + sleep 不真等。"""
    if health_seq is None:
        health_seq = [False]
    monkeypatch.setattr(QwenEye, "_health_ok",
                        classmethod(lambda cls, **kw: health_seq.pop(0)
                                    if health_seq else False))
    monkeypatch.setattr(QwenEye, "_vram_free_mib", staticmethod(lambda: 20000))
    monkeypatch.setattr(QwenEye, "_server_log_size", staticmethod(lambda: 0))
    monkeypatch.setattr(QwenEye, "_server_log_load_failed",
                        staticmethod(lambda offset: load_failed))
    monkeypatch.setattr(qec.time, "sleep", lambda s: None)


def test_failed_start_timeout_owned_then_stopped(no_engine, monkeypatch):
    """WR-03 回归：start 已发起但 health 始终不达标（慢启动超时）→
    (False, True) 且 _owned=True —— stop_if_owned 停掉半启动 server，
    不留 13.4GB 无人管理。"""
    _patch_start_env(monkeypatch, health_seq=[False])   # health 恒挂
    monkeypatch.setattr(QwenEye, "_http_json",
                        staticmethod(lambda url, payload=None, timeout=30.0:
                                     (0, "kap down")))
    eye = QwenEye()
    healthy, owned = eye.ensure_ready(timeout_s=1)
    assert (healthy, owned) == (False, True)
    assert eye._owned
    eye.stop_if_owned()
    stop_calls = [c for c in no_engine if "stop" in c]
    assert len(stop_calls) == 1
    assert "kap-llm.sh" in " ".join(stop_calls[0])


def test_failed_start_load_failed_owned_then_stopped(no_engine, monkeypatch):
    """WR-03 回归（Guard 2 路径）：server.log 记录 load 失败 → 立即放弃
    (False, True)，同样 _owned=True → stop_if_owned 清理 crash-loop 残留。"""
    _patch_start_env(monkeypatch, health_seq=[False], load_failed=True)
    monkeypatch.setattr(QwenEye, "_http_json",
                        staticmethod(lambda url, payload=None, timeout=30.0:
                                     (0, "kap down")))
    eye = QwenEye()
    healthy, owned = eye.ensure_ready(timeout_s=30)
    assert (healthy, owned) == (False, True)
    assert eye._owned
    eye.stop_if_owned()
    assert len([c for c in no_engine if "stop" in c]) == 1


def test_allocate_lease_released_on_stop(no_engine, monkeypatch):
    """WR-03 配对：KAP allocate 授予的 lease 在 stop_if_owned 时显式
    POST /api/production/llm/release（mirror caller 归因；kap-llm.sh stop
    只 pkill 不触碰 lease）。幂等 —— 二次 stop 不重复 release。"""
    kap_calls = []

    def fake_http(url, payload=None, timeout=30.0):
        kap_calls.append((url, payload))
        return 200, {"data": {"granted": True}}

    _patch_start_env(monkeypatch, health_seq=[False])   # health 恒挂 → 超时
    monkeypatch.setattr(QwenEye, "_http_json", staticmethod(fake_http))
    eye = QwenEye(caller="kst:test_release")
    healthy, owned = eye.ensure_ready(timeout_s=1)
    assert (healthy, owned) == (False, True)
    alloc = [(u, p) for u, p in kap_calls if "allocate" in u]
    assert alloc and alloc[0][1] == {"variantId": "q3",
                                     "caller": "kst:test_release"}
    eye.stop_if_owned()
    rel = [(u, p) for u, p in kap_calls if "release" in u]
    assert len(rel) == 1
    assert rel[0][1] == {"caller": "kst:test_release"}
    n = len(kap_calls)
    eye.stop_if_owned()                                 # 幂等：不重复 release
    assert len(kap_calls) == n


# ── Chat call shape（上游硬约束回归）────────────────────────────────────

def test_observe_single_request_shape(tmp_path, monkeypatch):
    """observe_single：每图一条 user 消息（消息数=1，content 双 part：
    image_url + text）、enable_thinking 恒 False。"""
    img = tmp_path / "f000001.jpg"
    img.write_bytes(b"\xff\xd8fake-jpeg")

    captured = {}

    def fake_call_llm(self, messages, max_tokens):
        captured["messages"] = messages
        captured["max_tokens"] = max_tokens
        return "答"

    monkeypatch.setattr(QwenEye, "_call_llm", fake_call_llm)
    eye = QwenEye()
    out = eye.observe_single(img, "描述场景", max_tokens=800)
    assert out == "答"
    assert len(captured["messages"]) == 1        # 单图单消息
    parts = captured["messages"][0]["content"]
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert parts[1] == {"type": "text", "text": "描述场景"}


def test_observe_pair_request_shape(tmp_path, monkeypatch):
    """observe_pair：恰两条 user 消息（每图一条，规避 llama.cpp 多图丢弃
    bug）、每条恰 1 个 image_url part + 1 个 text part、问句只在第 2 条、
    第 1 条 text 含「前一帧」标记、两图 base64 互不相同且对应 a/b。"""
    img_a = tmp_path / "f000001.jpg"
    img_a.write_bytes(b"\xff\xd8fake-jpeg-A")
    img_b = tmp_path / "f000002.jpg"
    img_b.write_bytes(b"\xff\xd8fake-jpeg-B")

    captured = {}

    def fake_call_llm(self, messages, max_tokens):
        captured["messages"] = messages
        captured["max_tokens"] = max_tokens
        return "答"

    monkeypatch.setattr(QwenEye, "_call_llm", fake_call_llm)
    eye = QwenEye()
    out = eye.observe_pair(img_a, img_b, "镜头怎么运动了", max_tokens=1500)
    assert out == "答"
    assert captured["max_tokens"] == 1500

    messages = captured["messages"]
    assert len(messages) == 2                          # 恰两条消息
    assert all(m["role"] == "user" for m in messages)  # 都是 user（硬约束 1）

    urls = []
    for m in messages:                                # 每条恰 1 图 + 1 文本
        parts = m["content"]
        img_parts = [p for p in parts if p["type"] == "image_url"]
        txt_parts = [p for p in parts if p["type"] == "text"]
        assert len(parts) == 2
        assert len(img_parts) == 1
        assert len(txt_parts) == 1
        urls.append(img_parts[0]["image_url"]["url"])
    # 两图 base64 互不相同且顺序对应 a → b
    prefix = "data:image/jpeg;base64,"
    assert all(u.startswith(prefix) for u in urls)
    import base64 as _b64
    assert _b64.b64decode(urls[0].removeprefix(prefix)) == b"\xff\xd8fake-jpeg-A"
    assert _b64.b64decode(urls[1].removeprefix(prefix)) == b"\xff\xd8fake-jpeg-B"
    assert urls[0] != urls[1]

    texts = [p["text"] for m in messages for p in m["content"] if p["type"] == "text"]
    assert "镜头怎么运动了" not in texts[0]      # 问句只在第 2 条
    assert "镜头怎么运动了" in texts[1]
    assert "前一帧" in texts[0]                  # 第 1 条含前一帧标记
    assert "当前帧" in texts[1]


def test_ask_text_request_shape(monkeypatch):
    """ask_text：单条 user 消息、纯 text part、零 image_url part
    （无图 = 豁免多图丢弃 bug，策略 B 纯文本合并入口）。"""
    captured = {}

    def fake_call_llm(self, messages, max_tokens):
        captured["messages"] = messages
        captured["max_tokens"] = max_tokens
        return "合并答"

    monkeypatch.setattr(QwenEye, "_call_llm", fake_call_llm)
    eye = QwenEye()
    out = eye.ask_text("把逐帧答案合并成一句", max_tokens=900)
    assert out == "合并答"
    assert captured["max_tokens"] == 900

    messages = captured["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    parts = messages[0]["content"]
    assert not isinstance(parts, str)          # 必须是 part list
    assert len(parts) == 1
    assert parts[0]["type"] == "text"
    assert parts[0]["text"] == "把逐帧答案合并成一句"
    assert all(p["type"] != "image_url" for p in parts)   # 零图


def test_call_llm_always_disables_thinking(monkeypatch):
    """硬约束 2：请求体恒带 chat_template_kwargs.enable_thinking=False。"""
    bodies = []

    def fake_http(url, payload=None, timeout=30.0):
        bodies.append(payload)
        return 200, {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(QwenEye, "_http_json", staticmethod(fake_http))
    eye = QwenEye()
    assert eye._call_llm([{"role": "user", "content": "hi"}], 100) == "ok"
    assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert bodies[0]["model"] == "qwen3.8"


def test_call_llm_retry_then_raise(monkeypatch):
    """两次都失败 → RuntimeError（调用方降级）；中间 sleep 1 次。"""
    monkeypatch.setattr(QwenEye, "_http_json",
                        staticmethod(lambda url, payload=None, timeout=30.0:
                                     (0, "conn refused")))
    slept = []
    monkeypatch.setattr(qec.time, "sleep", lambda s: slept.append(s))
    eye = QwenEye()
    with pytest.raises(RuntimeError):
        eye._call_llm([{"role": "user", "content": "hi"}], 100)
    assert len(slept) == 1   # attempt 0 之后 sleep 5s，attempt 1 失败即 raise
