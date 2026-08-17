"""qwen-eye 引擎客户端（精简复制版）—— 本地 Qwen3.8-27B VL 视觉引擎 (:8125)

上游真源：kais-hermes-skills/plugins/kais_aigc/qwen_eye.py
  @ commit c3949404827db047f1c7b89e1f959a6b3d51a44e
  复制日期：2026-08-17
  同步约定：引擎行为变更（端口/生命周期/请求 shape/硬约束）时**手工同步**本文件
  并更新头部 commit —— KST 是独立仓库，不 import 上游（松耦合，R7）。

本文件相对上游的裁剪：去掉 logging（KST 惯例 print("[stage] ...")）、去掉
observe() 多图入口（local_vision_facets 只用 observe_single 单图问答）。
生命周期 + HTTP call shape + fail-fast guards 与上游逐行等价。

生命周期（按需 LLM 政策，完整保留）：
  1. health 探测 :8125/health —— 已健康 → (True, False) 不拥有、绝不动它。
  2. Guard 1（allocate 前）：GPU1 free VRAM < 14000MiB → 直接 (False, False)
     不启动（ComfyUI 渲染期盲拉起只会让轮询空转满 120s）。nvidia-smi 缺失
     fail-open（视为满足，不挡启动路径）。
     ⚠️ 顺序陷阱：VRAM 预检必须在 health **之后** —— 健康的 q3 自占 13.4GB
     会让 free≈10GB，先预检会误杀健康 server。
  3. KAP allocate: POST :10588/api/production/llm/allocate
     {"variantId": "q3", "caller": "<caller>"}（GpuScheduler lease）。
  4. Fallback（KAP down 时）：bash /opt/qwen-llm/kap-llm.sh start q3。
  5. health 轮询 ≤120s；Guard 2（轮询中）：server.log 自启动前 offset 起的
     新增内容出现 load 失败字样 → 立即放弃 (False, True)。
  6. stop_if_owned() 只停**自己拉起的** server —— 预存在 lease（无论谁的）
     绝不动（幂等，never raises）。

上游硬约束（必须遵守，违反 = 静默劣化）：
  1. **每图一条 user 消息**（llama.cpp 多图丢弃 bug）：单条 user 消息带 N 图
     只算 ceil(N/2) 张 —— 连续多条 user 消息合法。observe_single 单图调用
     天然豁免（只有一张图可丢）。
  2. **恒传 enable_thinking:false** —— 否则 thinking 吃光整个 max_tokens 预算，
     content 返回空串（PARSE_FAIL 根因）。
  3. **单实例串行**（thread-unsafe by design）—— phase/stage 驱动必须顺序调用。

用法：
  from analysis.engine_clients.qwen_eye_client import QwenEye, ENGINE_NAME
  eye = QwenEye(caller="kst:vision_facets")
  healthy, owned = eye.ensure_ready()
  try:
      if healthy:
          answer = eye.observe_single(Path("frame.jpg"), "描述场景")
  finally:
      eye.stop_if_owned()   # 只停自己拉起的；崩溃也不泄漏 13.4GB
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENGINE_NAME = "qwen-eye"
"""Canonical engine name —— 写进 cache _cache_key 与 warnings，便于追溯。"""

ENGINE_VERSION = "qwen3.8-27b-q3@c3949404"
"""引擎身份（模型 + 上游 commit 短 hash）—— cache invalidation 旋钮之一。"""

CALLER = "kst:vision_facets"
"""caller identity —— 流进 KAP allocate lease，做 GPU-scheduler 归因。"""

# KAP allocate API（GpuScheduler 前端）。KAP down 时 fallback 直接跑脚本。
KAP_ALLOCATE_URL = "http://127.0.0.1:10588/api/production/llm/allocate"
LLM_API = "http://127.0.0.1:8125/v1/chat/completions"
LLM_HEALTH = "http://127.0.0.1:8125/health"
KAP_LLM_SH = "/opt/qwen-llm/kap-llm.sh"

LLM_START_TIMEOUT_S = 120
LLM_CALL_TIMEOUT_S = 3600  # CPU-mode fallback 单次调用可 ~5.5min

# ── fail-fast guards（上游 2026-08-15 验收缺陷修补，原样保留）──────────────
# ComfyUI 渲染占满 GPU1 时模型加载必 OOM —— 两道闸：启动前 VRAM 预检 +
# 轮询中 server.log 死因检测。
SERVER_LOG = "/opt/qwen-llm/server.log"
_VRAM_MIN_FREE_MIB = 14000  # q3 需 13.4GB，留 buffer
_VRAM_GPU_INDEX = 1         # RTX 3090, CUDA_VISIBLE_DEVICES=1
_LOAD_FAIL_RE = re.compile(r"failed to load model|model loading error")


class QwenEye:
    """qwen-eye —— 本地 Qwen3.8-27B VL 视觉引擎客户端 (:8125)。

    One instance per caller identity（caller 串流进 KAP allocate lease）。
    Thread-unsafe by design —— 调用方顺序驱动。
    """

    def __init__(self, caller: str = CALLER):
        self.caller = caller
        self._owned = False  # True iff WE brought the server up

    # ── HTTP plumbing（staticmethod —— tests 可 monkeypatch 单一共享副本）──

    @staticmethod
    def _http_json(url: str, payload: dict | None = None,
                   timeout: float = 30.0) -> tuple[int, Any]:
        """极简 JSON POST/GET。返回 (status, parsed-body-or-None)。"""
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300] if exc.fp else ""
            return exc.code, body
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return 0, str(exc)[:300]

    @classmethod
    def _health_ok(cls, timeout: float = 5.0) -> bool:
        status, _ = cls._http_json(LLM_HEALTH, timeout=timeout)
        return status == 200

    # ── 生命周期 ─────────────────────────────────────────────────────────

    @staticmethod
    def _vram_free_mib() -> int | None:
        """qwen-eye GPU 的 free VRAM (MiB)；nvidia-smi 不可用/失败返回 None
        （fail-open：预检绝不阻塞启动路径）。"""
        try:
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free",
                 "--format=csv,noheader,nounits",
                 "-i", str(_VRAM_GPU_INDEX)],
                capture_output=True, text=True, timeout=10,
            )
            return int(proc.stdout.strip().splitlines()[0])
        except (subprocess.SubprocessError, OSError, ValueError, IndexError):
            return None

    @staticmethod
    def _server_log_load_failed(offset: int) -> bool:
        """True 当 server.log 自 *offset* 起的新增内容出现致命模型加载失败
        （OOM'd llama-server 反复退出）。log 不可读返回 False —— best-effort。"""
        try:
            with open(SERVER_LOG, "rb") as fh:
                fh.seek(offset)
                tail = fh.read(2_000_000)  # cap: 只看近期窗口
        except OSError:
            return False
        return bool(_LOAD_FAIL_RE.search(tail.decode(errors="replace")))

    @staticmethod
    def _server_log_size() -> int:
        """当前 server.log 大小 —— Guard 2 的读取起点 offset。
        log 不存在返回 0（检测从 launch 新建文件顶部开始）。"""
        try:
            return Path(SERVER_LOG).stat().st_size
        except OSError:
            return 0

    def ensure_ready(self, timeout_s: int = LLM_START_TIMEOUT_S) -> tuple[bool, bool]:
        """把 qwen-eye server 拉起来。返回 ``(healthy, started_by_us)``。

        ``started_by_us`` 为 False 表示 server 在 allocate 前**已健康** ——
        调用方批次结束后绝不能 stop 它（用完即停只适用于自己拉起的）。
        Never raises。

        Fail-fast：模型加载 OOM 是硬不可用 —— allocate 前预检 VRAM，轮询中
        一旦 server.log 记录 load 失败立即放弃，让调用方降级而非空转满超时。
        """
        if self._health_ok():
            return True, False

        # Guard 1 —— VRAM 预检。必须在 health 之后（见模块 docstring 顺序陷阱）。
        free_mib = self._vram_free_mib()
        if free_mib is not None and free_mib < _VRAM_MIN_FREE_MIB:
            print(f"[vision-engine] insufficient VRAM "
                  f"(free={free_mib} MiB < {_VRAM_MIN_FREE_MIB}), skip start")
            return False, False

        log_offset = self._server_log_size()
        allocated = False
        try:
            status, body = self._http_json(
                KAP_ALLOCATE_URL,
                payload={"variantId": "q3", "caller": self.caller},
                timeout=60.0,
            )
            allocated = status == 200 and isinstance(body, dict) and (
                (body.get("data") or {}).get("granted") is True
            )
        except Exception:  # noqa: BLE001 — allocate 是 best-effort
            allocated = False
        if not allocated:
            # Fallback：直接跑脚本（幂等 start；脚本自身等 ready —— 我们用
            # 自己的 deadline 封顶）。
            try:
                subprocess.run(
                    ["bash", KAP_LLM_SH, "start", "q3"],
                    capture_output=True, timeout=timeout_s,
                )
            except (subprocess.SubprocessError, OSError):
                pass   # best-effort —— 下方 health 轮询给出最终裁决

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._health_ok():
                self._owned = True
                return True, True
            # Guard 2 —— launch 尝试死于模型加载：停止等待。
            if self._server_log_load_failed(log_offset):
                print(f"[vision-engine] model load failed (see {SERVER_LOG}), "
                      f"giving up on start")
                return False, True
            time.sleep(3)
        return False, True

    def stop_if_owned(self) -> None:
        """只停**自己拉起的** server（幂等）。Never raises。

        预存在 server（无论谁的 lease）绝不动 —— 见模块 docstring 生命周期。
        """
        if not self._owned:
            return
        self._owned = False
        try:
            subprocess.run(
                ["bash", KAP_LLM_SH, "stop"],
                capture_output=True, timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            pass   # best-effort；失败只意味着 VRAM 晚点释放

    # ── Chat 调用 ────────────────────────────────────────────────────────

    def _call_llm(self, messages: list[dict], max_tokens: int) -> str:
        """单次 chat completion。瞬态失败重试 1 次（OOM'd server 调用间恢复）。
        失败 raise RuntimeError —— 调用方决定是否降级。"""
        body = {
            "model": "qwen3.8",
            "temperature": 0.1,
            "max_tokens": max_tokens,
            # 硬约束 2：恒传 enable_thinking:false —— 否则 thinking 吃光
            # max_tokens，content 返回空串。
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": messages,
        }
        last_err: str = ""
        for attempt in range(2):
            status, resp = self._http_json(
                LLM_API, payload=body, timeout=LLM_CALL_TIMEOUT_S,
            )
            if status == 200 and isinstance(resp, dict):
                txt = ((resp.get("choices") or [{}])[0]
                       .get("message", {}).get("content") or "").strip()
                if txt:
                    return txt
                last_err = f"empty content (status={status})"
            else:
                last_err = f"HTTP {status}: {str(resp)[:200]}"
            if attempt == 0:
                time.sleep(5)
        raise RuntimeError(f"qwen-eye LLM call failed: {last_err}")

    @staticmethod
    def _b64(path: Path) -> str:
        return base64.b64encode(path.read_bytes()).decode()

    def observe_single(self, image_path: Path, question: str,
                       max_tokens: int = 2000) -> str:
        """单图 + 提问一次调用作答。

        图走自己的 user 消息（硬约束 1），question 作为**同一条**消息的 text
        part 跟随（单图调用豁免多图丢弃 bug —— 只有一张图可丢）。
        """
        messages = [{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": "data:image/jpeg;base64," + self._b64(image_path)}},
            {"type": "text", "text": question},
        ]}]
        return self._call_llm(messages, max_tokens=max_tokens)
