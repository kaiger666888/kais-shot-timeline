---
phase: 21-scorer-threshold-calibration
reviewed: 2026-08-20T03:09:22Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - analysis/roundtrip/scorer.py
  - analysis/roundtrip/judge.py
  - tests/test_scorer.py
  - tests/test_judge.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: fixed
review_iteration: 2 (re-review after fixes 95fadc2..c4fc324)
---

# Phase 21: Code Review Report (Re-review, iteration 2)

**Reviewed:** 2026-08-20T03:09:22Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found（1 个新 Warning——WR-02 修复引入的 WR-03 类回归；CR-01 及其余 4 项修复全部验证正确）
**Review range:** `95fadc2..c4fc324`（6 个 fix commit + 测试）

## Summary

对 6 项修复（CR-01、WR-01~05）做了逐项代码核对 + 共享件契约交叉验证
（`h3_regen.py` 的 `prompt_version_for`/`probe_duration_sec`/`build_sidecar_entries`/
`_atomic_write_json`/`append_roundtrip_warnings` 与 `roundtrip.schema.json` 的
scores 半边 shape），并实跑验证门 + 三组 ad-hoc 探针（no-op 不重写 sidecar /
中断自愈链 / 坏几何回归）。

**门禁（实跑）**：`python3 -m pytest tests/ -q` → **170 passed**（符合预期）；
`python3 spec/validate.py` → **exit 0**（failures=0 全 fixture）。

**结论**：6 项修复中 5 项完全正确；WR-02 的 key 扩展本身有效，但其接线
（几何推导挪入 cache 预判循环）把 `float()` coercion 放在了 per-shot try
**之外**，重新引入了 WR-03 刚修掉的「单条坏数值炸整批」失败形态——
**新 Warning WR-06**，已实验证实（见下）。不是 clean。

## 修复逐项验证（iteration 2）

| 原发现 | 验证结果 |
|---|---|
| CR-01 cache-hit 回填 | **正确**（两接线点 + no-op 不重写均实证通过，见 §探针） |
| WR-01 judge key +prompt_version | **正确**（附 Info 级 provenance 注记 IN-08） |
| WR-02 scorer key +orig_window | **key 本身正确**；接线引入新 Warning **WR-06** |
| WR-03 coercion 进 per-shot try | **正确**（sidecar duration_sec 路径；shots.json 几何路径见 WR-06） |
| WR-04 malformed 驱逐告警+备份 | **正确**（两 writer 同款；同秒双备份边界无害） |
| WR-05 dur≤guard 双循环守卫 | **正确**（probe 后、提取前；测试断言零提取/零判定） |

### CR-01 接线与「no-op 不重写」的实证

- **两接线点齐**：scorer 全命中早退 L573-584 / 批尾 extend L635；judge
  L798-809 / L908。`hit_shots` 只收 key 已装配的镜（`keys[sid]` 先于分类写入，
  `_replay_hit_entries` 无 KeyError 面）。
- **no-op 语义**：`_replay_hit_entries` 先读 sidecar 现存半边做全等比对
  （scorer 恰 {score,model}、judge 恰三件套，与 schema additionalProperties
  false 对齐——不存在多余字段导致假性不等）；`parsed.confidence` int/float
  经 Python `==` 语义相等，JSON round-trip 不破坏全等。
- **探针 1/2（scorer+judge）**：全命中重跑后 `roundtrip.json` mtime_ns 与
  字节内容**完全不变**、零模型加载/零重问——「纯 no-op 重跑不重写 sidecar」
  成立。
- **探针 3（中断自愈链）**：sidecar 半边删除 → 重跑回填（文件确实被重写、
  分数与 cache 一致、零前向）→ 第三跑进入稳定 no-op。中断窗口闭环。
- **cache 手改垃圾**：`score`/`parsed` 缺席或非法 → 回填条目过不了写侧
  ① 本批校验 → sys.exit fail-loud（judge `_replay_hit_entries` docstring 明示
  此语义；scorer 同款）。无静默路径。

### WR-01/WR-02 key 字段获取失败时的行为

- judge：`str(regen.get("prompt_version") or "")` —— 字段缺席/非串一律退化
  稳定空串，读写两侧一致（payload=dict(key) 留档同值），不炸、不假命中。
- scorer：`shots_index.get(sid) or {}` 缺席 → orig_window `[0.0, 0.0]` ——
  真实打分不可能产出该值（打分要求 shot 存在），无 stale 命中面；miss 循环
  `shot is None` 守卫先跳过并 warning。
- `prompt_version` 溯源核实：`h3_regen.prompt_version_for` = sha256(prompt_text)
  [:8]，regen 时经 `build_sidecar_entries` 写入 sidecar regen 半边——改稿后
  h3_regen 重跑（其自身 key 含 pv → 必 miss 重渲/刷新 sidecar）→ judge key
  随之失效重判。canonical 流闭环（残留注记见 IN-08）。

## Warnings（新发现）

### WR-06: orig_window key 推导的 `float()` 在 per-shot try 之外 —— 单条坏 shots.json 几何重新炸整批（WR-03 类回归，WR-02 修复引入）

**File:** `analysis/roundtrip/scorer.py:551-554`
**Issue:** WR-02 把 orig 镜几何并入 cache key 时，`float()` coercion 从
`score_shot`（per-shot try 内）**复制**到了 cache 预判循环——该循环在所有
try 守卫之外。hand-edit/损坏的 shots.json 单条非数值（`duration: "6,73"` /
`start_sec: "abc"` / `end_sec: "8,5"`）现在让**整批**在预判阶段 traceback
退出：零模型加载、零镜打分、pending_warnings 未 flush。实证（探针）：

```
File ".../analysis/roundtrip/scorer.py", line 553, in main
    dur = float(shot.get("duration")
ValueError: could not convert string to float: '6,73'
```

修复前（95fadc2）同样的坏值只落在 `score_shot` 的 per-shot try → 单镜失败
+ failed 名单 + 批继续——这正是 WR-03 刚确立并被 fix outcome 明文断言的不变量
（「坏 duration_sec → per-shot except → 批继续」）。且此崩溃是确定性的：
只要有一条坏几何，**每次重跑都在同一位置崩**，连已 cache 镜的 CR-01 回填
也被阻断（预判先于一切）。WR-03 的回归测试只覆盖 sidecar `duration_sec`，
不覆盖 shots.json 几何。judge 侧无此问题（key 无几何维；其 dur/start 推导
在 try 内，judge.py:852-855）。
**Fix:** 预判循环内对几何推导做 per-candidate 容错——失败时用不可能命中的
哨兵（如 `[None, None]`）入 key 强制 miss，让 miss 循环里 `score_shot` 自己
的同款推导在 try 内炸成 per-shot 失败：

```python
for sid, regen, regen_path in candidates:
    shot = shots_index.get(sid) or {}
    try:
        start = float(shot.get("start_sec", 0.0) or 0.0)
        dur = float(shot.get("duration")
                    or (float(shot.get("end_sec", 0.0) or 0.0) - start))
        orig_window = [round(start, 3), round(dur, 3)]
    except (TypeError, ValueError):
        orig_window = [None, None]   # 真实打分不可能产出 → 必 miss
    key = {..., "orig_window": orig_window, ...}
```

（miss 循环照旧：`score_shot` 内同款 `float()` 抛 → per-shot except →
warning + failed + continue，批继续。）补一条回归测试：shots.json 单镜
`duration: "6,73"` → rc=0、其余镜照常打分、坏镜进 failed 名单。

**Outcome (fix):** FIXED — 采纳建议原样：预判循环的几何推导（start/dur
两个 `float()` + `round` 三行）包进 per-candidate `try:`，`(TypeError,
ValueError)` 时落哨兵 `orig_window = [None, None]`——真实打分只产 float
对，`cache_read` 的 `!=` 全等比较下哨兵必 miss 且无异常面，坏镜进 miss
循环后由 `score_shot` 自身的同款推导在 per-shot try 内炸成单镜失败
（WR-03 不变量：打印异常 + failed 名单 + 批继续），CR-01 的 hit 回填不再
被预判崩溃阻断。哨兵永不入 cache（score_shot 在 payload 构造前即抛，
坏镜无 cache_write，run-1 存量 payload 原样）。模块 docstring 步骤 2 同步
补 WR-06 容错语义。judge.py 核查无同款模式（key 无几何维；dur/start 推导
本就在 per-shot try 内 L852-855），未改动。回归锚：
`test_bad_shots_geometry_precheck_tolerant_replay_not_blocked`（2 镜基线
全打分 → shots.json shot 1 `duration="6,73"` + sidecar 半边全丢模拟中断 →
rc=0、shot 1 进 failed 名单、shot 2 从 cache 回填、shot 1 的 run-1 cache
payload 原样未被哨兵覆写）。门禁：pytest **171 passed**（170 基线 + 1 新
锚）；`spec/validate.py` exit 0。

## Info

### IN-07: degrade 路径不回填 cache-hit 半边 —— 自愈推迟到引擎可用的下一次全流程

**File:** `analysis/roundtrip/scorer.py:586-595`、`analysis/roundtrip/judge.py:823-829`
**Issue:** 模型加载失败 / 引擎不可用的 degrade `return 0` 发生在批尾 replay
之前——部分命中场景下 sidecar 半边缺席时本次不回填（回填本不需要引擎，纯
cache 读 + sidecar 写）。非静默（有显式 warning + rc=0），cache 数据不丢，
下一次引擎可用的成功运行即自愈；但「引擎长期不可用 + 部分镜未 cache」时
回填被无限期推迟。可在 degrade return 前补一次 `_replay_hit_entries`。

### IN-08: WR-01 的 prompt_version 溯源为 sidecar regen 半边 —— 跳过 h3_regen 的改稿流不失效（契约外场景）

**File:** `analysis/roundtrip/judge.py:787-789`
**Issue:** key 的 pv 取自 sidecar regen 半边（= 渲染时 prompt_text 的 hash）。
若操作者改 prompts.json 但**不重跑 h3_regen**（sidecar regen 半边不动），
judge key 不变 → stale 命中仍在。该流程违反 pipeline 契约（「改一字即重渲
该镜」），且 miss 路径会用新 prompt_text 审旧 regen——语义本就错位（prompt_text
provenance 起自 load_shot_prompts，先于本 phase）。canonical 流（改稿→h3_regen
重跑→sidecar pv 刷新→judge 重判）已验证闭环；如需覆盖契约外场景，可改用
`h3s.prompt_version_for(shot["prompt_text"])`（现稿 text 的 hash）入 key。

### IN-09: 空候选时全命中分支打印误导性「全部 cache 命中」（沿袭，非本次引入）

**File:** `analysis/roundtrip/scorer.py:582-583`、`analysis/roundtrip/judge.py:807-808`
**Issue:** `candidates == []` 时 `misses` 也为空 → 打印「全部 cache 命中
（hit=0 miss=0）」。行为无害（rc=0、不写盘、warnings 照 flush），修复前即如此；
措辞可改为区分「零候选」。

## 修复验证明细（WR-03/04/05 补充核对）

- **WR-03**：coercion + probe 三行确在 per-shot try 内（scorer L605-610），与
  judge L839-842 逐行对齐，两模块不再漂移；回归测试断言 rc=0 + 好镜照常打分
  + failed 名单 + 坏条目经既有 schema-invalid 层剔除（.bak 保全）。
- **WR-04**：两 writer 的 malformed 收集 → 驱逐前 `shutil.copy2` 备份 → 逐条
  str warning（含内容截 120 字 + 备份名）；测试断言恰一份 .bak + 本批照常
  落盘。边界核对：malformed 非空 ⇔ sidecar 文件必存在且可解析（损坏 JSON
  走 `existing=None` 重建，不产 malformed）→ 备份守卫恒真、warning 引用的
  .bak 恒存在；malformed 与 schema-invalid 两分支同秒触发时 `.bak-<ts>` 同名
  互写——两份都是写前原文件、内容相同，覆盖无害。
- **WR-05**：守卫位于 probe 之后、任何帧提取/引擎调用之前（scorer L611-619 /
  judge L843-851）；warning 含实测时长；`failed.append` + continue；
  `probe_duration_sec` 失败返 0.0 契约核实（h3_regen L724-735）。测试断言
  零 ffmpeg 调用 / 零归因提问 / 无 cache / sidecar 无 scores。
- **门禁**：pytest 170 passed（6 个新回归测试全绿）；`spec/validate.py`
  exit 0。

---

_Reviewed: 2026-08-20T03:09:22Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Iteration: 2 (re-review of 95fadc2..c4fc324)_
