# Milestones

## v1.0 ShotTimelineAsset Contract (Shipped: 2026-07-20)

**Phases completed:** 4 phases, 7 plans, 13 tasks

**Key accomplishments:**

- One-liner:
- 455-line bilingual prose contract at `spec/SPEC.md` that makes the 6 machine-checkable schemas from Plan 01-01 navigable end-to-end — covers all 4 phase success criteria (5 data shapes, schema_version + graceful-degrade, canonical media + Range-aware 206 + serve.py, self-describing asset.json manifest), quotes the graceful-degrade rule verbatim from `asset.schema.json`, and was approved on first human review.
- Task 1 端到端
- Root cause (verified live against `/usr/lib/python3.12/http/server.py:681`):
- 让 `@kais/infinite-canvas` 的现有 import-from-dir 入口识别 ShotTimelineAsset 目录,折叠成 1 zone + N storyboard + 3 audio + 1 video collection 子图,storyboard 间按 shot_id 升序 emit sequence edges,所有子节点通过 per-type Zod 且前端零改动。
- Single-file Python harness that gates producer↔consumer contract alignment via 6-schema inline validation (producer) + Phase 3 17-assert shell-out (consumer) + deliberate-drift self-test (fail-loud proof).
- Real-producer-asset e2e (backend lifecycle + POST import-from-dir + SQL read-back on o_agentWorkData + structural asserts + 3-layer teardown) + capstone report formally accepting WR-01/04 and recording SC-1 scope reduction.

---
