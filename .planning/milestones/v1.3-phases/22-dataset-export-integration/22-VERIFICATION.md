---
phase: 22-dataset-export-integration
verified: 2026-08-20T13:01:27Z
status: passed
score: 7/8 must-haves verified
overrides_applied: 0
gaps:
  - truth: "ep01 抽样端到端一次跑出 roundtrip.json + regen mp4 + dataset 目录（SC1 live 半边：正本 output/dataset/ 落地 + asset.json 刷新 1.3 挂载 data.roundtrip）"
    status: partial
    reason: >-
      e2e 能力已在 ep01 字节级副本（cp -a 载体）上机器证明（/tmp/p22_e2e.log：S2 pipeline exit 0
      + rendered=2 + asset "1"→"1.3" + data.roundtrip{4,15} + dataset 4 目录 + manifest 分桶 6/9/0 +
      accepted.txt 4 行/rejected.txt 15 行），但副本随 harness cleanup（ALL_PASS → rm -rf WORK）清除；
      正本 output/dataset/ 从未生成，正本 asset.json 仍为 schema_version "1"、data.roundtrip 缺席。
      22-04 PLAN frontmatter 显式声明的 artifact output/dataset/<video-stem>/manifest.json 在仓库中 MISSING。
    artifacts:
      - path: "output/dataset/<video-stem>/manifest.json"
        issue: "MISSING — output/dataset/ 目录不存在"
      - path: "output/虫虫武侠…第01话…/asset.json"
        issue: "schema_version 仍为 '1'、data.roundtrip 键缺席（1.3 挂载只在副本证过）"
    missing:
      - "在 ep01 正本跑 python3 analysis/roundtrip/export_dataset.py --work-dir <EP01>（dataset-root 默认即 output/dataset/）——纯派生只读导出、零红线风险；verifier 已在 /tmp 等价复跑，4 目录/prompt.json 16 字段/分桶 6:9:0/清单 4:15/独立性断言全绿"
      - "asset.json 1.3 刷新：单跑 export 模块（Pattern 4 条件 roundtrip 输入）或在正本走一次管线 export step；若正本管线全量首跑（prompts 归一化 → cache 失效重渲）确属用户 overnight 决策，则显式记录该决策并接受 asset 暂陈旧"
---

# Phase 22: Dataset Export + Integration Verification Report

**Phase Goal:** 闭环进流水线（`step_roundtrip` slot + CLI flags）+ gallery round-trip HITL 审阅面板 + accepted 子集独立 dataset 目录导出——用户对 ep01 跑一次抽样流水线即端到端拿到 (首帧, 尾帧, prompt) 真值数据集。
**Verified:** 2026-08-20T13:01:27Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | `step_roundtrip` 编排五件套：编号 step [9/10] 位于 timeline/export 之间 + 外层 cache + 四 subprocess 串 + Pattern 4 条件 input + dataset post-step | ✓ VERIFIED | run_pipeline.py `def step_roundtrip`(:570 区) 位于 `def step_timeline`(:20947 idx) 与 `def step_export` 之间，main 调用序 rt(:1090)<export(:1096)；`grep -c "/9\]"` = **0**、34 处 `[N/10]`、`[9/10] roundtrip`×5、`[10/10] ShotTimelineAsset export`×1；Pattern 4 = :738-740 `if os.path.exists(roundtrip_json_path): inputs.append(...)`（存在才 append）；post-step :1151-1170 自写 check=False + roundtrip.json keyed-on-file warning |
| 2 | 六 CLI flag + 默认值（--skip-roundtrip / --comfy-url / --sample-shots / --regen-resolution / --max-shot-sec / --tau-sim 默认 0.9670） | ✓ VERIFIED | `run_pipeline.py --help` 六 flag 定义行全在场；argparse 源码逐项核验：tau-sim default 0.9670 / comfy-url http://127.0.0.1:8188 / sample-shots 0 / regen-resolution 1344x768 / max-shot-sec 10.0 / skip-roundtrip store_true；wiring 测试锁死（234 suite 内） |
| 3 | ep01 抽样端到端一次跑出 roundtrip.json + regen mp4 + **dataset 目录**（正本落地） | ✗ FAILED | roundtrip.json ✓（正本 19 镜冻结、schema 1.3、sha `63543baf…`）+ regen mp4 ✓（roundtrip/ 19 个）；**output/dataset/ 不存在**、正本 asset.json 仍 schema "1" 无 data.roundtrip。e2e 能力本身已机器证明——但只在 cp -a 字节级副本上（/tmp/p22_e2e.log 16:48：ALL_SCENARIOS_PASS，S2 asset "1"→"1.3" + dataset 4 目录 + manifest 6/9/0 + 清单 4/15 全 PASS），副本随 harness cleanup 清除。capability ✓ / durable artifact ✗ |
| 4 | 审阅面板（双 video 并排 + 双分数 + 归因标签 + 三态 accept/reject/维持 auto）+ 复核结果可导出回写（confirmed-only + idempotent） | ✓ VERIFIED | verifier 对 ep01 真实数据 live 生成：19 卡 / 38 `<video>` / `#t=` Media Fragments / `roundtrip/shot_` src / sim bar 43 处 / judge confidence ×19 / 三色归因 badge / state-accept·state-reject / queue-check span ×19（CR-01 修复后）；apply_edits live 演示：`shot_005 auto→human/accepted` + `shot_010 auto→human/rejected` 审计行、重放 byte-idempotent（sha 等值 + 已-human-跳过）、坏 edits（字符串 id）exit 1 且 sidecar 零改动；Kai 浏览器走查 6 步 approved（2026-08-20，checkpoint gate=blocking 闭环） |
| 5 | XSS `_esc()` hardening 覆盖 verdict/reason/attribution，注入用例不执行 | ✓ VERIFIED | 9 个参数化注入用例（3 payload × reason/status.error/model 三注入位）+ test_bootstrap_script_breakout + test_no_innerhtml 全绿；verifier live 生成 HTML 复核：零 `innerHTML`、零 `onerror="` 属性、`&lt;script&gt;` 转义态在场；fixture 过 roundtrip.schema.json 0 errors |
| 6 | accepted 子集导出独立 dataset/<video-stem>/：首尾帧 jpg + prompt.json + manifest + 分清单，消费端独立 | ✓ VERIFIED | verifier 对 ep01 正本 live 导出（--dataset-root /tmp/vrfy-ds）：shot_010/061/075/084 四目录、first/last_frame.jpg 非零字节、prompt.json 16 字段齐（scores/attribution/regen{engine,version,prompt_version,vch}）、manifest 分桶 faithful_below_tau=6/diverged=9/underspecified=0 + accepted 4/rejected 15 + verdict_tau/export_tau 双记、accepted.txt 4 行/rejected.txt 15 行（每行 sim+attribution+reason 可 grep）、零 asset.json/roundtrip/ 引用、零 symlink |
| 7 | smoke 回归 harness ≥4 场景全绿 | ✓ VERIFIED | verifier 自跑 `P22_LIVE=0`（离线确定性半边）：S1 全 23 断言 PASS（degrade + absent-不挂载 + 5 JSON md5 等值 + export cache-hit）+ 探测齐备 + ALL_SCENARIOS_PASS exit 0；live 半边：executor 16:48 全量 log ALL_SCENARIOS_PASS（S2 20 断言/S4 6 断言硬绿；S3 GPU1 17331<22528 走 plan 预授权降级分支），S3 live 断言集另有 16:16 rerun log 直接证据（2/93 入样 + rendered=0 cache-hit=2 + scorer 全命中 + judge frozen=19） |
| 8 | 冻结红线：ep01 roundtrip.json 全程 sha 不变 + --force 不清人工数据 + rejected 永不删 | ✓ VERIFIED | 正本 sha `63543baf…` 三点等值（e2e 跑前/跑后/verifier 复核后）；--force 清元组逐项核验不含 roundtrip.json/roundtrip/（注释明文 WR-01 红线 + route_cache rmtree 覆盖三模块 cache）；S1/S2/S4 断言冻结块 byte-equal |

**Score:** 7/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `html/gen_roundtrip_review.py` | 审阅面板生成器（min 450 行） | ✓ VERIFIED | 828 行；_esc×27 / 维持 auto×7 / URL.createObjectURL / roundtrip-edits.json×5；live 生成 19 卡全锚通过 |
| `tests/fixtures/roundtrip_sample.json` | 六态 + 三注入 payload fixture | ✓ VERIFIED | 136 行，shot_id 在场，schema 0 errors（pytest 常驻） |
| `tests/test_roundtrip_review.py` | XSS/六态/payload 单测（min 150 行） | ✓ VERIFIED | 323 行、21 用例全绿（PAYLOADS×8） |
| `spec/schemas/roundtrip-edits.schema.json` | edits 契约 | ✓ VERIFIED | 26 行，accept_overrides 在场；坏 edits live 拒绝验证 |
| `analysis/roundtrip/apply_edits.py` | confirmed-only 回写 CLI（min 200 行） | ✓ VERIFIED | 283 行；roundtrip-apply / Draft202012Validator×3 / source:human×4；live 双向覆盖 + 幂等重放通过 |
| `analysis/roundtrip/export_dataset.py` | dataset 导出（min 200 行） | ✓ VERIFIED | 459 行；verdict_tau/export_tau 双记（WR-03）；live 导出全绿 |
| `tests/test_roundtrip_apply_edits.py` / `tests/test_export_dataset.py` | 单测（min 120 行） | ✓ VERIFIED | 241 / 427 行；15+10 用例含 11 个 review-fix 回归锚 |
| `run_pipeline.py` | step_roundtrip + flags + banner | ✓ VERIFIED | 见 Truth 1/2；`contains` 三锚全在场 |
| `tests/test_pipeline_roundtrip_wiring.py` 等 3 wiring 测试 | 静态锁 | ✓ VERIFIED | 187 行 + vision/seq 两测试更新；regex `\[\d+/10\]` 形态在源码 :177 |
| `tests/test_phase22_e2e.sh` | 四场景 harness（min 180 行） | ✓ VERIFIED | 636 行；ALL_SCENARIOS_PASS×4；verifier 自跑 P22_LIVE=0 通过 |
| `output/…第01话…/roundtrip_review.html` | ep01 真实面板 | ✓ VERIFIED | 19 卡 / 38 video / 19 queue-check span（CR-01 后重生成）/ 零 innerHTML |
| **`output/dataset/<video-stem>/manifest.json`** | **ep01 正式 dataset 导出** | ✗ MISSING | **output/dataset/ 不存在**——S2 在 /tmp 副本证过后被 harness cleanup 清除，正本从未落地（Truth 3） |
| `output/…第01话…/asset.json`（schema 1.3） | e2e 刷新产物 | ⚠️ STALE | 正本仍 schema "1"、无 data.roundtrip（只在副本证过；与上同一根因） |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| roundtrip.json reason/attribution | HTML 卡片 | 内联 `_esc()` | ✓ WIRED（转义态断言 + live HTML 复核） |
| prompts.json prompt_text + 六 facet | `<details>` 快照 | `_esc` 全覆盖 | ✓ WIRED |
| 三态按钮 JS | state-accept/reject + 计数 | classList/textContent only | ✓ WIRED（零 innerHTML） |
| exportEdits JS | Blob 下载 roundtrip-edits.json | createObjectURL + int 升序 | ✓ WIRED |
| 面板导出 edits | sidecar verdict | apply_edits schema 预校验 + READ-merge | ✓ WIRED（live 演示 + 幂等） |
| 冻结 verdict（accepted 4） | dataset shot_NNN/ | export_dataset 分桶 + 帧直拷 | ✓ WIRED（live 4 目录） |
| route_cache 帧缓存 | dataset jpg | copy2 直拷优先 | ✓ WIRED（live 非零字节） |
| step_roundtrip | h3_regen/scorer/judge/gen_review 四模块 | subprocess list-form argv | ✓ WIRED（源码 + S2 log） |
| step_export | roundtrip.json 条件 input | os.path.exists 守卫 append | ✓ WIRED（:738-740） |
| dataset post-step | export_dataset.py | check=False graceful | ✓ WIRED（:1151-1170 + S1a 跳过警告 live） |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| gen_roundtrip_review.py | shots/cards | ep01 roundtrip.json + shots.json + prompts.json | 是（19 镜真实 sim/attribution/reason 渲染进 HTML） | ✓ FLOWING |
| export_dataset.py | accepted 子集 | sidecar verdict + prompts + route_cache 帧 | 是（真实 jpg 字节直拷） | ✓ FLOWING |
| apply_edits.py | verdict 覆写 | edits 文件 + sidecar | 是（live 写回 + 审计行） | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 全套件零回归 | `python3 -m pytest tests/ -q` | 234 passed (4.15s) | ✓ PASS |
| 面板 live 生成 | gen_roundtrip_review 对 ep01 → /tmp | `[roundtrip-review] wrote … (19 shots)`；15 项锚全过 | ✓ PASS |
| dataset live 导出 | export_dataset 对 ep01 → /tmp | 4 目录/分桶 6:9:0/清单 4:15/独立性 | ✓ PASS |
| apply live + 幂等 + 拒坏 | apply_edits 对 ep01 副本 | 审计行 + 重放 byte 等值 + 坏 edits exit 1 | ✓ PASS |
| 六 flag + 默认值 | `run_pipeline.py --help` + argparse 源码 | 6 flag、默认值逐项吻合 | ✓ PASS |
| 正本零副作用 | sha256 roundtrip.json（verifier 跑前后） | `63543baf…` 等值 | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| tests/test_phase22_e2e.sh（离线确定性半边） | `P22_LIVE=0 bash tests/test_phase22_e2e.sh`（verifier 自跑） | S1 全 23 断言 PASS + 探测 + ALL_SCENARIOS_PASS，exit 0 | ✓ PASS |
| tests/test_phase22_e2e.sh（live 全量 S2-S4） | 未由 verifier 重跑 | 需 ComfyUI + GPU 真渲（分钟级）+ ep01 多 GB cp -a；executor 当日 log `/tmp/p22_e2e.log` ALL_SCENARIOS_PASS + S3-live 证据 `/tmp/p22_e2e_rerun.log` 已逐锚对照 harness 源核验 | ? SKIP（环境重载；离线半边 + 模块级 live 已覆盖矩阵） |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| RT-05 | 22-02, 22-04 | accepted 子集独立 dataset 目录导出，消费端不依赖 asset 契约 | ✓ SATISFIED（模块 + live 证明；正本落地见 Gap 1） | Truth 6 |
| DATASET-02 | 22-02 | manifest + hard-negative 索引（分清单/引擎版本/可审计） | ✓ SATISFIED | Truth 6（buckets 6/9/0 + rejected.txt 可 grep 行） |
| PIPE-01 | 22-03, 22-04 | step_roundtrip slot + flags + banner + --force 处理 | ✓ SATISFIED | Truth 1/2/8 |
| PIPE-02 | 22-04 | smoke harness ≥4 场景 | ✓ SATISFIED | Truth 7 |
| PRESENT-01 | 22-01, 22-02 | 面板 + HITL 硬门 + XSS hardening | ✓ SATISFIED | Truth 4/5（走查 approved） |

REQUIREMENTS.md 映射到 Phase 22 的 5 个 ID 与各 PLAN frontmatter 声明并集完全一致，无 orphan。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| run_pipeline.py | 83/85/416 | `shot_XXX.json` 字样 | ℹ️ Info | 文件名模式占位（shot_001…），非 debt marker，先例存量 |
| tests/test_phase22_e2e.sh | 51/258 | mktemp `XXXXXX` 模板 / fixture `"placeholder"` prompt_text | ℹ️ Info | 语义正当（mktemp 模板 / 测试 fixture） |

零 TBD/FIXME/XXX debt marker；零真 stub（所有动态数据 live 验证 FLOWING）。Code review 1C+4W 全修且复审 clean（commits 6cc0cde..bc51e50 在 git log 核实）；IN-01..IN-08 Info findings 公开挂账（out of scope）。

### Human Verification Required

无新增待人工项——plan 的 blocking 走查 checkpoint（Task 3：双 video 同步/三态/export edits 下载）已由 Kai 于 2026-08-20 执行并 approved（22-04-SUMMARY 记录）。Gap 1 的处置（override 接受 vs 30 秒落地导出）是开发者决策，经 gaps_found 上升，非测试项。

### Gaps Summary

单一 gap，单一根因（SC1 live 的载体决策）：e2e 四场景与 SC1 live 证明为保正本冻结 overnight cache（Rule-1：正本 prompts.json 未归一化，管线首跑会 invalidate cache 改写冻结半边）全部落在 cp -a 字节级副本上执行——功能与断言全绿（log 在案、verifier 已逐锚对照 harness 源核验，且离线 S1 半边由 verifier 独立复跑通过、export/apply/面板三模块由 verifier 在 ep01 真实数据上 live 复验全绿），但副本产物随 harness 自身 cleanup 契约清除，**正本 output/dataset/ 从未落地、asset.json 仍为陈旧 schema "1"**。

收口成本极低且零红线：`python3 analysis/roundtrip/export_dataset.py --work-dir <EP01>` 是纯派生只读导出（verifier 已在 /tmp 等价验证产物全绿），一条命令即落 output/dataset/<video-stem>/；asset.json 1.3 刷新可单跑 export 模块或随正本管线 overnight 首跑。**若维持现状（接受副本证明即满足 SC1），请在本 frontmatter 加 override 条目**（must_have: "ep01 抽样端到端一次跑出 … dataset 目录"，reason: COPY 载体 Rule-1 决策 + /tmp/p22_e2e.log 机器证明，accepted_by/accepted_at 填实际值）——建议同时把「正本 dataset 落地 + asset 1.3」记为用户 overnight 首跑的预期产物，避免悬空。

---

_Verified: 2026-08-20T13:01:27Z_
_Verifier: Claude (gsd-verifier)_

---

## Gap Closure Addendum (2026-08-20, orchestrator)

**Gap #1 CLOSED by direct materialization**（verifier 建议的单命令路径，非 plan--gaps 周期——机械性补齐）:

- `export_dataset.py --work-dir <EP01>` → 正本 dataset/ 物化（4 shot 目录 + manifest buckets 6/9/0 + accepted.txt 4 / rejected.txt 15）
- `export_asset.py`（stems canonical symlinks 修复后）→ 正本 asset.json schema "1"→"1.3" + data.roundtrip{path: roundtrip.json, accepted_count: 4, rejected_count: 15}
- 冻结红线全程保持：roundtrip.json sha256 `63543baf…` 三次复验不变
- 注：第一次调用 stems-source-dir 指错造成自引用 canonical symlinks，已修复指回 stems/htdemucs/<stem>/ 真实文件；manifest verdict_tau=null（verdict 先于 WR-03 τ 留档机制——文档化 null）
- spec/validate.py exit 0 复验通过
