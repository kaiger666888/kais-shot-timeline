---
phase: 22-dataset-export-integration
plan: 01
subsystem: ui
tags: [hitl-review, xss-hardening, html-generator, roundtrip, present-01, media-fragments]

requires:
  - phase: 20-h3-regen-client
    provides: roundtrip.json sidecar regen 半边（19 镜 ep01 冻结态）+ roundtrip/shot_NNN_regen.mp4
  - phase: 21-scorer-threshold
    provides: scores{midframe_sim, judge} + verdict{accepted/rejected, auto} + τ_sim=0.9670 裁决值
provides:
  - html/gen_roundtrip_review.py 审阅面板生成器（PRESENT-01 呈现半边：双 video 并排 + sim bar τ tick + 归因色块 + 三态覆盖 + τ 边界 queue + exportEdits 下载）
  - XSS 三层 hardening 机器证明（_esc 全强制清单 / bootstrap </ 转义 / JS 零 inner-HTML——19 个断言 + mutation 探针实证 load-bearing）
  - tests/fixtures/roundtrip_sample.json 六态 schema-valid 合成 sidecar（三注入 payload 内嵌）
  - exportEdits payload 形状契约（accept_overrides/reject_overrides/review_notes——22-02 apply CLI 的消费契约已被测试锁定）
affects: [22-02 apply CLI, 22-03 step_roundtrip wiring, 22-04 e2e harness]

tech-stack:
  added: []  # 零新依赖（Python stdlib + 浏览器原生 Blob/URL.createObjectURL/Media Fragments——UI-SPEC Registry Safety 锁定）
  patterns:
    - "三态 HITL 覆盖（Accept/Reject/维持 auto——维持 auto 显式标记已复核但不产 edit 记录）"
    - "int 升序 numeric comparator 分桶 Set 导出（registry 字典序先例的 shot_id int 变体）"
    - "τ 边界排序 queue key = (信息缺失 ? 0 : 1, |sim − τ| 升序, shot_id 升序)"

key-files:
  created:
    - html/gen_roundtrip_review.py
    - tests/fixtures/roundtrip_sample.json
    - tests/test_roundtrip_review.py
  modified: []

key-decisions:
  - "PRESENT-01 保持未勾选 —— 呈现半边（面板 + XSS + 导出）已交付，apply CLI 回写半边在 22-02 共享同 requirement ID（mirror 18-01/19-01/20-01/21-01 先例）"
  - "regen 失败降级卡保留三态按钮（UI-SPEC Interaction §2 + States 表 vs Copywriting『无按钮』内部张力——按更具体的语义契约收口：human 覆盖是未裁决卡拿到 verdict 的唯一路径）"
  - "bootstrap RT_SHOTS = 完整 shots 数组（mirror registry DRAFT 全量先例——reason/model 等 route 文本进 JS 岛使 </ 转义成为可测攻击面而非空转）"
  - "三态按钮点击已 active 项 = 撤销回未复核默认态（toggle-off 语义，registry toggle 先例一致；『维持 auto』即显式重置位）"

patterns-established:
  - "XSS 断言 + mutation 探针双层验证：剥 _esc / 剥 </ 转义后断言必红（防 vacuous green）"

requirements-completed: []  # PRESENT-01 半边交付，22-02 收口后勾选

duration: 4min
completed: 2026-08-20
---

# Phase 22 Plan 01: 审阅面板 + XSS Hardening Summary

**round-trip HITL 审阅面板生成器（双 video 并排 + 三态覆盖 + exportEdits）落地，XSS 三层 hardening 以 19 个注入/六态/形状断言 + mutation 探针锁定为机器证明而非宣称。**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-08-20T04:32:10Z
- **Completed:** 2026-08-20T04:36:28Z
- **Tasks:** 2/2
- **Files modified:** 3 (all created)

## Accomplishments

- **ep01 真实 sidecar 一次生成可用面板**：19 卡、38 `<video>`、τ 边界排序 queue（首项 shot_084——|0.9674−0.9670| 最贴边界）、header pills 4 accepted/15 rejected/0 human、收尾打印 `[roundtrip-review] wrote ... (19 shots)`
- **XSS 三层全部在场且被断言锁定**（SC3）：`_esc` 5 字符转义覆盖 UI-SPEC 强制清单全部字段、bootstrap `</`→`<\/` 转义、JS 全程 classList/textContent（生成 HTML 全文零 `innerHTML`）
- **22-02 消费契约已锁**：exportEdits payload 形状（int 升序 numeric comparator / 维持 auto 不进 / 同向覆盖照导 / review_notes / roundtrip-edits.json 文件名）有源级断言——apply CLI 落地时以此为契约

## ep01 面板生成实录（命令与输出）

```console
$ EP01=$(ls -d output/虫虫武侠*第01话*/ | head -1) && \
  python3 html/gen_roundtrip_review.py \
    --roundtrip "$EP01/roundtrip.json" --video "$EP01/h264.mp4" \
    --shots "$EP01/shots.json" --prompts "$EP01/prompts.json" \
    --output /tmp/rt_review_ep01.html | tee /tmp/rt_gen.log
[roundtrip-review] wrote /tmp/rt_review_ep01.html (19 shots)

# 空态（roundtrip 指向缺席文件）：
$ python3 html/gen_roundtrip_review.py --roundtrip /nonexistent ... --output /tmp/rt_review_empty.html
[roundtrip-review] wrote /tmp/rt_review_empty.html (0 shots)   # 不 raise，空态面板照常生成
```

生成后断言（plan verify 块逐条）：`id="card-shot_` ×19、`<video` ×38、锚 `维持 auto` / `roundtrip-edits.json` / `URL.createObjectURL` / `state-accept` / `state-reject` / `Prompt 快照` / `τ_sim=0.9670` / `#t=` 全在场、零 `innerHTML`、无 `.tmp` 残留——全绿。

## XSS 三层在场证据

| 层 | 实现位置 | 测试锁定 | mutation 探针（剥除后必红） |
|----|---------|---------|---------------------------|
| 1. `_esc()` 5 字符转义 | gen_roundtrip_review.py `_esc`（内联，html/ namespace package 禁 import）；覆盖 reason/attribution(enum)/verdict.decision+source+decided_at/status.error/model/engine_name+engine_version+prompt_version/prompt_text+六 facet/refs/asset_name/regen.path | `test_xss_three_payloads`（3 payload × reason/status.error/model 三注入位 = 9 用例） | `_esc` → identity 后：raw payload 存活 True / `&lt;script&gt;` 缺席 True / `onerror="` 属性存活 True |
| 2. bootstrap `</`→`<\/` | build_html 内 `json.dumps(shots, ensure_ascii=False).replace("</", "<\\/")` | `test_bootstrap_script_breakout`：`alert(1)<\/script>` 转义形态在场 + 原文不存活 | 反向 replace 剥除后：bootstrap 内裸 `</script>` True |
| 3. JS 零 inner-HTML | applyVisualState / queue ✓ 前缀 / 计数 / video 失败占位（textContent 赋值即移除失败 video）全 classList+textContent | `test_no_innerhtml`（全文断言） | — |

三 payload：`<script>alert(1)</script>` / `" onerror="alert(1)" x="` / `PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==`（base64 仅纯文本在场，全文无 `atob`/`eval(` 路径）。

## fixture 六态清单（tests/fixtures/roundtrip_sample.json）

| shot_id | 态 | 关键内容 |
|---------|----|---------|
| 3 | 正常 accepted·auto | 全套 regen+scores+verdict（faithful/sim 0.9731） |
| 7 | rejected·auto + script payload | `scores.judge.reason = "<script>alert(1)</script>"` |
| 10 | status{state:"failed"} 无 regen | `status.error = '" onerror="alert(1)" x="'`（onerror 注入位） |
| 12 | 有 regen 无 scores | 未打分态 |
| 19 | 有 scores 无 verdict | 未裁决态；`midframe_sim.model` = base64 payload（注入位） |
| 84 | verdict source:"human" | accepted·human + decided_at 2026-08-20T06:00:00 |

整体过 `Draft202012Validator(roundtrip.schema.json)` **0 errors**（`test_fixture_schema_valid` 常驻回归）。

## Task Commits

1. **Task 1: 合成 fixture + gen_roundtrip_review.py 生成器** — `0979340` (feat)
2. **Task 2: tests/test_roundtrip_review.py（SC3 三注入 + 六态 + payload 形状）** — `c6f461f` (test)

## Files Created/Modified

- `html/gen_roundtrip_review.py` — 审阅面板生成器（809 行；CLI 六 flag、原子写、swallow-to-empty 空态）
- `tests/fixtures/roundtrip_sample.json` — 六态合成 sidecar（136 行，schema 0 errors）
- `tests/test_roundtrip_review.py` — 19 用例（280 行；importlib 直调 main(argv) 形态）

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] JS 注释含字面 `innerHTML` 违反零 innerHTML 断言**
- **Found during:** Task 1 verify
- **Issue:** JS 注释「零 innerHTML」使生成 HTML 全文含 `innerHTML` 子串，`assert 'innerHTML' not in h` 红
- **Fix:** 注释改写为「禁 inner-HTML 拼接」（语义不变，字面 token 消失）
- **Files modified:** html/gen_roundtrip_review.py
- **Commit:** 0979340（随 Task 1 修复后提交）

**2. [Rule 1 - Bug] reviewed pill class 重复（`pill pill pill-warn`）**
- **Found during:** Task 1 结构抽查
- **Issue:** 模板硬编码 `class="pill {reviewed_cls}"` 而 reviewed_cls 又含 `pill` 前缀
- **Fix:** reviewed_cls 收窄为 `pill-warn`/`pill-ok`
- **Files modified:** html/gen_roundtrip_review.py
- **Commit:** 0979340（随 Task 1 修复后提交）

### Plan 语义澄清（非偏差）

- **TDD RED gate 结构性缺席**：plan 将实现排 Task 1、测试排 Task 2（tdd=true）——测试对既有实现首跑即绿是 plan 设计的机器证明半边，非 vacuous green。以 mutation 探针补足 RED 语义：剥 `_esc` / 剥 `</` 转义后断言全部翻红（证据见上表）。
- **UI-SPEC 内部张力**：Copywriting 表「regen 失败卡无按钮」 vs Interaction §2 + States 表「三态按钮保留」——按更具体的语义契约（human 覆盖是未裁决卡拿到 verdict 的唯一路径）保留按钮。

## Test Evidence

- `python3 -m pytest tests/test_roundtrip_review.py -x -q` → **19 passed**
- `python3 -m pytest tests/ -q` → **190 passed**（基线 171 + 新增 19，零回归）

## Self-Check: PASSED

文件（4/4 FOUND）：html/gen_roundtrip_review.py / tests/fixtures/roundtrip_sample.json / tests/test_roundtrip_review.py / 22-01-SUMMARY.md；commits（2/2 FOUND）：0979340 / c6f461f。
