# Phase 4: Cross-Repo Contract Verification - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 2 (1 NEW + 1 RECONCILE)
**Analogs found:** 2 / 2 (every sub-pattern of the new file has a concrete in-repo analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/verify_contract.py` (NEW, this repo, ~250-350 lines) | utility (regression harness) | request-response + batch + transform (3-mode orchestrator) | `scripts/check_range.py` (server lifecycle) + `spec/validate.py` (jsonschema) + `scripts/export_asset.py` (validate_asset_json inline) | exact (3-way composite) |
| `/data/workspace/kst-canvas-consumer/src/types/database.d.ts` (RECONCILE, worktree) | config (generated, dirty noise) | file-I/O (dev-mode regen) | n/a — `git checkout --` revert, not a code-authoring task | n/a (teardown only) |

> The worktree reconcile is **not a coding task** — it is reverting/accepting an auto-regen byproduct (yarn install postinstall `@rmp135/sql-ts`). Planner puts it as a Wave 0 reconcile step (`git checkout -- src/types/database.d.ts`), not a plan that references a code analog. The remainder of this doc focuses on `scripts/verify_contract.py`.

---

## Pattern Assignments

### `scripts/verify_contract.py` (utility, request-response + batch + transform)

**Analog (primary):** `scripts/check_range.py` — exact match for the server-lifecycle shell (subprocess + ephemeral port + try/finally teardown + bracketed `[tag]` print).
**Analog (secondary):** `spec/validate.py` — exact match for the `Draft202012Validator` + `iter_errors` + `_format_errors` pattern.
**Analog (tertiary):** `scripts/export_asset.py:validate_asset_json` L106-127 — exact match for inline asset-shape validation (re-used verbatim if desired).
**Cross-repo analog (consumer mode):** `scripts/verify-canvas-shot-timeline.ts` L1-30 (worktree) — Phase 3 17-assert script the harness shells out to.

The new file is a **3-mode orchestrator** combining three existing patterns. Below, each pattern is anchored with concrete excerpts and line refs the planner can drop into PLAN actions verbatim.

---

#### Imports pattern — `scripts/check_range.py` L20-29

> Single-line stdlib imports + `pathlib.Path` + repo-root resolve. No package init, no `sys.path` manipulation.

```python
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).parent.parent.resolve()  # scripts/ → repo root
```

For Phase 4, extend with: `import json, sqlite3, urllib.error, pathlib` and `from jsonschema import Draft202012Validator` (the jsonschema import can be top-level — system-installed, not optional). Match `spec/validate.py` L18-26 for the jsonschema import shape.

---

#### Standalone-script skeleton + argparse — `scripts/check_range.py` L121-153

> Every `scripts/*.py` in this repo follows: module docstring (purpose + 用法 + 退出码) → `def main():` with `argparse.ArgumentParser(description="...")` → `sys.exit(...)` at the bottom → `if __name__ == "__main__": main()`.

```python
def main():
    """CLI 入口。"""
    ap = argparse.ArgumentParser(
        description="Range-206 自检：启动 serve.py → Range 请求 → assert 206/Content-Range/Accept-Ranges"
    )
    ap.add_argument(
        "asset_root",
        nargs="?",
        default=None,
        help="asset 目录（含 video.mp4）；缺省时自动扫 output/ 下第一个含 video.mp4 的子目录",
    )
    args = ap.parse_args()
    # ... work ...
    sys.exit(check(asset_root))


if __name__ == "__main__":
    main()
```

For Phase 4: argparse gains `--mode {producer,consumer,e2e,all}` (default `all`) + `--consumer-path` + `--e2e-asset-dir` + `--e2e-skip` `action="store_true"`. Follow CLAUDE.md "CLI Argument Conventions": kebab-case flags, Chinese `help=` strings, `choices=[...]` for enum-like flags.

---

#### Server lifecycle: subprocess + ephemeral port + try/finally teardown — `scripts/check_range.py` L32-48, 67-118

> **This is the single most important pattern for Phase 4 e2e mode.** `find_free_port` + `wait_ready` poll + `subprocess.Popen` + `try/finally` with 3-layer teardown (`terminate` → `wait(timeout)` → `kill` → best-effort `wait` to reap zombie). The Phase 4 e2e function should be a near-verbatim copy with two substitutions: (a) `npx tsx src/app.ts` instead of `serve.py`; (b) `urllib.request.urlopen("/health")` instead of TCP `create_connection`.

```python
def find_free_port() -> int:
    """让内核分配一个空闲的 ephemeral 端口（bind 127.0.0.1:0 后读 getsockname）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(port: int, timeout: float = 5.0) -> bool:
    """轮询 TCP 连接到 port；连上即 server ready，超时返回 False。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False
```

The Popen + try/finally shell (substitute the command + swap `wait_ready` for an HTTP `/health` poll):

```python
port = find_free_port()
proc = subprocess.Popen(
    [sys.executable, str(REPO / "scripts" / "serve.py"), asset_root, str(port)],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    if not wait_ready(port):
        print(f"[check-range] FAIL: server did not start on port {port} ...")
        return 1
    # ... do work ...
    return 0 if ok else 1
finally:
    # 沿用 audio/transcribe.py:150-155 的 finally cleanup 惯例
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        # 02-REVIEW WR-06：kill 后必须 wait 收尸
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
```

For Phase 4 e2e: bump timeouts (`wait_ready` 30-45s — backend boot is slower than `serve.py`), swap stdout to a logfile or `subprocess.DEVNULL` per RESEARCH Pitfall 7 (avoid pipe-buffer deadlock), and add the `proc.kill()` reap chain verbatim.

---

#### HTTP request + status assert — `scripts/check_range.py` L79-103

> `urllib.request.Request` + `urlopen` + `.status` + `.headers.get(...)` + body `.read()`. Stdlib only — RESEARCH A8 says use `urllib`, not `requests`.

```python
url = f"http://127.0.0.1:{port}/video.mp4"
req = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
with urllib.request.urlopen(req, timeout=5) as resp:
    status = resp.status
    content_range = resp.headers.get("Content-Range")
    accept_ranges = resp.headers.get("Accept-Ranges")
    body = resp.read()

ok = True
if status != 206:
    print(f"[check-range] FAIL: expected 206, got {status}")
    ok = False
# ... more asserts ...
return 0 if ok else 1
```

For Phase 4: replace GET with `method="POST"`, `data=json.dumps({...}).encode("utf-8")`, `headers={"Content-Type": "application/json"}` (RESEARCH 示例 1 L66-68 already drafts this). Target URL: `http://127.0.0.1:{port}/api/canvas/v2/import-from-dir`.

---

#### jsonschema validation (Draft202012Validator) — `spec/validate.py` L52-94

> Canonical producer-side validation pattern. `load_validator(shape)` is a one-liner factory; `validate_minimal` shows the loop-and-collect-failures pattern with sorted errors. **Phase 4 producer mode should re-use this exact shape**, parameterized over the 6 schemas in `SCHEMAS_DIR`.

```python
from jsonschema import Draft202012Validator

def load_validator(shape: str) -> Draft202012Validator:
    """根据形状名加载对应的 Draft202012Validator。"""
    schema_path = SCHEMAS_DIR / f"{shape}.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    return Draft202012Validator(schema)


def _format_errors(errors: list) -> str:
    """把 jsonschema 错误列表格式化为简短多行字符串。"""
    lines = []
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        lines.append(f"    at {loc}: {err.message}")
    return "\n".join(lines)
```

The validation loop (copy this skeleton — it handles `FileNotFoundError` + `JSONDecodeError` gracefully, exactly what producer-mode needs):

```python
for shape in MINIMAL_ORDER:
    fixture_path = FIXTURE_DIR / SHAPE_TO_FIXTURE[shape]
    try:
        with open(fixture_path, encoding="utf-8") as f:
            instance = json.load(f)
    except FileNotFoundError:
        print(f"[FAIL] {shape}: fixture missing at {fixture_path}")
        failures += 1
        continue
    except json.JSONDecodeError as e:
        print(f"[FAIL] {shape}: invalid JSON in fixture: {e}")
        failures += 1
        continue

    validator = load_validator(shape)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        print(f"[FAIL] {shape}: {len(errors)} error(s)")
        print(_format_errors(errors))
        failures += 1
    else:
        print(f"[valid] {shape}")
```

For Phase 4 producer mode: iterate over 6 shapes (`asset`, `shots`, `audio_analysis`, `transcript`, `frames`, `prompts`) exactly like `MINIMAL_ORDER` (`spec/validate.py` L46). For the asset shape, `instance = manifest` itself; for the 5 data shapes, resolve `instance = json.loads((asset_dir / manifest["data"][shape]).read_text())` (RESEARCH 示例 2 L807-809 drafts this).

---

#### Inline asset-only validation (alternative) — `scripts/export_asset.py` L106-127

> If Phase 4 producer mode wants to validate **just** `asset.json` (not the 5 data shapes), copy `validate_asset_json` verbatim. It loads `asset.schema.json`, runs `iter_errors` sorted by `absolute_path`, and on failure `sys.exit` with a multi-line Chinese error (the project convention for actionable errors per CLAUDE.md "Error Handling").

```python
def validate_asset_json(asset_dict: dict) -> None:
    """inline Draft202012Validator 自校验 asset_dict。

    绝不 subprocess 到 spec/validate.py —— 其 SMOKE_SHAPES 显式排除 asset
    （spec/validate.py:49），subprocess 会让无效 manifest 悄悄通过。
    """
    # lazy import：沿用 CLAUDE.md 的 optional-dep lazy-import 惯例
    from jsonschema import Draft202012Validator

    schema_path = REPO / "spec" / "schemas" / "asset.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(asset_dict),
                    key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"  at {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                 for e in errors]
        sys.exit(
            f"asset.json failed schema validation ({len(errors)} error(s)):\n"
            + "\n".join(lines))
```

Note the comment about **why** inline validation is necessary: `spec/validate.py` `SMOKE_SHAPES` L49 deliberately excludes the `asset` shape (it only validates the 5 data shapes against `output/` producers). RESEARCH §Pattern 5 anchors this. So Phase 4 producer mode cannot just shell out to `spec/validate.py` for asset shape — must inline.

---

#### Subprocess invocation — `run_pipeline.py` L82-86 + L97-99

> Project convention for invoking sibling Python scripts: `subprocess.run([sys.executable, str(HERE / "scripts" / "<name>.py"), ...], check=True)`. The `run_step` helper wraps `subprocess.run(..., check=True)` with a banner + command echo. CLAUDE.md "Subprocess Invocation Pattern" documents this as the canonical form.

```python
HERE = Path(__file__).parent.resolve()


def run_step(cmd: list, label: str):
    """运行子进程，失败时抛出 RuntimeError。"""
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


# Usage:
run_step(
    [sys.executable, str(HERE / "detectors" / "detect_v3b.py"),
     "--video", video, "--frames-dir", frames_dir,
     "--sample-fps", str(sample_fps),
     ...],
    label="[2/6] scene detection")
```

For Phase 4 producer-mode re-export (when `PHASE4_RE_EXPORT=1`): invoke `scripts/export_asset.py` with `--work-dir`, `--video`, `--stems-source-dir`, `--output`, `--force`. Use `subprocess.run(..., capture_output=True, text=True)` instead of `check=True` if you want to capture stderr for diagnostics rather than propagate `CalledProcessError`.

For consumer-mode: `subprocess.run(["npx", "tsx", "scripts/verify-canvas-shot-timeline.ts"], cwd=CANVAS_CONSUMER_PATH, capture_output=True, text=True, timeout=60)`. Anchored in RESEARCH 示例 3 L831-834.

---

#### Bracketed `[tag]` print conventions — `scripts/check_range.py` L64, 75, 89-103

> CLAUDE.md "Logging" mandates `[stage] ...` prefix for every progress line. The convention is short tags (one or two words), lowercase, hyphen-separated: `[check-range]`, `[export-asset]`, `[serve]`, `[validate]`. For Phase 4, use `[verify-contract]` for top-level + `[producer]` / `[consumer]` / `[e2e]` for per-mode lines.

```python
print(f"[check-range] no video.mp4 in {asset_root} — nothing to probe")
print(f"[check-range] FAIL: expected 206, got {status}")
print(f"[check-range] OK: 206 + Content-Range={content_range} + ...")
```

Phase 4 should mirror this style: `[verify-contract] mode=producer starting`, `[producer] asset.json valid`, `[e2e] backend ready on port {port}`, etc.

---

#### Cross-repo consumer mode invocation (target script)

**File:** `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts` (worktree)
**Lines:** L1-30 (shebang + docstring + imports)

The harness shells out to this script — it does NOT re-implement the 17 asserts. The script's own docstring tells you how to invoke it:

```typescript
#!/usr/bin/env tsx
/**
 * verify-canvas-shot-timeline.ts — Phase 3 CANVAS-01/02/03 verify.
 * ...
 * Run: npx tsx scripts/verify-canvas-shot-timeline.ts
 *
 * No backend / DB / HTTP required — imports production pure functions
 * (extractShotTimelineArtifacts, validateGraphNodes) directly.
 */
```

So Phase 4 consumer mode = a `subprocess.run` wrapper + rc check. Anchor in `package.json` scripts `verify:canvas-shot-timeline` if present (matches consumer naming convention); otherwise the direct `npx tsx` form per RESEARCH 示例 3.

---

#### Cross-repo e2e anchors (consumer repo, read-only — the harness queries these)

These are **not analogs** — they are the concrete names/paths the harness must reference. Documented here so the planner's actions can cite exact line numbers.

| What | Where | Exact reference |
|------|-------|-----------------|
| Express entrypoint | `src/app.ts` | L267 `port = ... \|\| 10588`; L269 `server.listen(port, ...)`; L183 `app.get("/health", ...)`; L18 `import { bootReady } from "@/utils/db"`; L276 `await bootReady` (gates listen callback) |
| Auth bypass | `src/app.ts` L214, L225-234 | `/api/*` is auth-bypassed in V6.0 — harness POST needs no token |
| Route body schema | `src/routes/canvas/v2/import-from-dir.ts` L1673-1680 | `projectId: z.number()`, `episodesId: z.number()`, `workdir: z.string()`, `mode` default `"merge"` |
| Persistence call | `src/routes/canvas/v2/import-from-dir.ts` L1756, L1828 | `appendAndSync({projectId, episodesId, events})` — primary event-sourcing path |
| Snapshot query (read-back) | `src/routes/canvas/v2/import-from-dir.ts` L1771-1776 | `db("o_agentWorkData").where("projectId", String(projectId)).andWhere("episodesId", String(episodesId)).andWhere("key", "canvasGraph")` — **the exact column names** the harness must use in its SQL `SELECT` |
| Phase 3 leftover evidence | worktree `data/db2.sqlite` | 1 row in `o_agentWorkData` for (9001, 9001), 290KB JSON blob; `canvas_nodes` / `canvas_links` empty (proves the dual-track persistence) |

For Phase 4 SQL read-back, use exactly: `SELECT data FROM o_agentWorkData WHERE projectId = ? AND episodesId = ? AND key = 'canvasGraph'` with sqlite3 parameterized substitution. RESEARCH Pitfall 1 explains why HTTP `/api/canvas/v2/load-v2` cannot be used (reads the empty relational tables).

---

#### Worktree reconcile (Wave 0 — not a code-analog task)

**File:** `/data/workspace/kst-canvas-consumer/src/types/database.d.ts`
**Action:** `git -C /data/workspace/kst-canvas-consumer checkout -- src/types/database.d.ts`

This is reverting auto-regen noise from `yarn install` postinstall (`@rmp135/sql-ts` recomputes the `@db-hash` comment and infers `score?: any → number | null`). RESEARCH Pitfall 2 + Runtime State Inventory document this. No code-analog needed — the planner just adds it as a one-line Wave 0 reconcile step (or, per RESEARCH Open Question 1, the executor commits it; either is harmless).

---

## Shared Patterns

### Standalone-script skeleton (applies to: the whole new file)
**Source:** `scripts/check_range.py` L1-29, L121-157; `scripts/serve.py` L1-16, L112-125; `spec/validate.py` L1-32, L141-184
**Apply to:** `scripts/verify_contract.py` (top + bottom of file)
**Convention:** Module docstring (purpose + behavior + 用法 + 退出码) → imports → `REPO = Path(__file__).parent.parent.resolve()` → helper functions → `def main():` with argparse → `sys.exit(...)` → `if __name__ == "__main__": main()`. Match `check_range.py` for the harness skeleton (closest structural match).

```python
#!/usr/bin/env python3
"""<one-line purpose>

背景：<why this exists, what it proves>

用法：
    python3 scripts/<name>.py --mode=producer
    python3 scripts/<name>.py --mode=consumer
    PHASE4_RUN_E2E=1 python3 scripts/<name>.py --mode=e2e

退出码：
    0 = all selected modes green
    1 = any mode failed (assert / subprocess rc / schema-invalid)
"""
```

### Subprocess invocation (applies to: producer re-export, consumer verify shell-out, e2e backend start)
**Source:** `run_pipeline.py` L82-86, L97-99; `scripts/check_range.py` L68-72
**Apply to:** all 3 modes of `verify_contract.py`
**Convention:** Always `[sys.executable, "<script>", ...]` for Python children (NEVER bare `"python"`); `cwd=` for cross-repo worktree; `capture_output=True, text=True` to capture stderr for diagnostics; `check=True` only when you want `CalledProcessError` to propagate (the project uses both styles — pick based on whether the harness wants to format the error itself).

### Try/finally subprocess teardown (applies to: e2e mode)
**Source:** `scripts/check_range.py` L104-118
**Apply to:** `run_e2e_check` in `verify_contract.py`
**Convention:** 3-layer teardown (`terminate` → `wait(timeout=10)` → `kill` → best-effort `wait(timeout=2)`). The 02-REVIEW WR-06 comment in `check_range.py` documents why `kill` alone leaks zombies — copy that rationale.

### Error handling — sys.exit with Chinese actionable message
**Source:** `run_pipeline.py` L203, L231; `scripts/export_asset.py` L229-232, L247-249, L287-292
**Apply to:** every guard clause in `verify_contract.py`
**Convention:** `sys.exit(f"<actionable Chinese message>\n  <hint line>\n  <hint line>")`. Multi-line messages with 2-space-indented hint lines are the project's idiomatic form for telling the user **what to do** to fix the problem (see `export_asset.py` L223-232 — names the missing file, explains the schema constraint, gives a remediation hint).

```python
# Example from export_asset.py L229-232 — match this shape for verify_contract.py guards
sys.exit(
    f"{name} 不存在: {p}\n"
    f"  asset.schema.json 的 data.{field} 是 required 字段 —— 不可省略。\n"
    + hint)
```

### jsonschema validation (applies to: producer mode)
**Source:** `spec/validate.py` L52-94 + `scripts/export_asset.py` L106-127
**Apply to:** `run_producer_check` in `verify_contract.py`
**Convention:** `Draft202012Validator(schema).iter_errors(instance)` sorted by `list(e.absolute_path)`; format with `f"at {'/'.join(...)}: {err.message}"`; do NOT shell out to `spec/validate.py` for the asset shape (its `SMOKE_SHAPES` L49 excludes asset — RESEARCH §Pattern 5).

### Bracketed `[tag]` logging (applies to: all modes)
**Source:** `scripts/check_range.py` (throughout), `scripts/export_asset.py` L316-317, `run_pipeline.py` step banners
**Apply to:** every `print` in `verify_contract.py`
**Convention:** Short lowercase hyphenated tags, `[verify-contract]` for top-level, per-mode `[producer]` / `[consumer]` / `[e2e]`. CLAUDE.md "Logging" mandates this — no log levels, no `logging.getLogger`, just bracketed `print`.

### Atomic JSON write (applies to: optional self-test temp files)
**Source:** `scripts/export_asset.py` L308-313
**Apply to:** only if Phase 4 implements `PHASE4_SELF_TEST=1` mode that writes temp invalid-asset fixtures
**Convention:** `tmp = output + ".tmp"; with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, indent=2, ensure_ascii=False); os.replace(tmp, output)`. CLAUDE.md "JSON I/O Conventions" mandates `ensure_ascii=False` for any file that may contain Chinese (ep01 video name has CJK + full-width punctuation).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | Every sub-pattern of `scripts/verify_contract.py` has at least one in-repo analog. The 3-mode orchestrator composition is novel, but each mode individually is anchored. RESEARCH §Code Examples L605-840 drafts full skeletons for all 3 modes — use RESEARCH as the secondary source when the in-repo analog is partial. |

The only truly novel element is the **sqlite3 read-back** (Pattern 3 in RESEARCH) — no in-repo Python script currently queries SQLite directly. But sqlite3 is Python stdlib with a stable, well-known API; the RESEARCH L347-366 draft is a complete drop-in. Planner cites RESEARCH §Pattern 3 + the cross-repo anchors table above for column names.

---

## Metadata

**Analog search scope:**
- `/data/workspace/kais-shot-timeline/scripts/` (3 files: `check_range.py`, `export_asset.py`, `serve.py`)
- `/data/workspace/kais-shot-timeline/spec/` (1 file: `validate.py`; 6 schemas in `spec/schemas/`)
- `/data/workspace/kais-shot-timeline/run_pipeline.py` (subprocess + probe patterns)
- `/data/workspace/kst-canvas-consumer/src/app.ts` (cross-repo: health/port anchors)
- `/data/workspace/kst-canvas-consumer/src/routes/canvas/v2/import-from-dir.ts` (cross-repo: SQL column anchors)
- `/data/workspace/kst-canvas-consumer/scripts/verify-canvas-shot-timeline.ts` (cross-repo: shell-out target)
- `/data/workspace/kst-canvas-consumer/scripts/verify-phase-46-e2e.ts` (cross-repo: env-gate pattern)

**Files scanned:** 9 (3 producer scripts + 1 producer validator + 1 producer orchestrator + 4 cross-repo consumer files for anchors)
**Analogs extracted:** 6 distinct patterns (standalone skeleton, server lifecycle, jsonschema validation, inline asset validate, subprocess invocation, bracketed logging)
**Pattern extraction date:** 2026-07-21
