# Milestones

## v1.1 分镜语义深化 — 镜头语言 + 跨镜角色/道具注册表 (Shipped: 2026-07-24)

**Phases completed:** 5 phases, 16 plans, 32 tasks

**Key accomplishments:**

- 3 new registry-flavor schemas + 2 additive schema extensions locking the v1.1 ShotTimelineAsset contract — all pure-additive, v1 minimal fixture still validates 6/6 green.
- Producer-side schema_version lock — `SCHEMA_VERSION = \"1.1\"` single-source constant in export_asset.py; PROJECT.md:83 stale `\"2\"` drift corrected to `\"1.1\"`.
- 9-file self-contained v1.1 fixture sample — exercises every new + extended schema with cross-file-consistent IDs; v1 minimal fixture unaffected (6/6 green).
- Regression harness extended (EIGHT_SHAPES + bidirectional cross-version proof + fixture-consistency check) + SPEC/README v1.1 prose — the v1.1 contract is now locked, documented, and regression-protected.
- Optional `asset.schema.json#generator.warnings: array<string>` added additively under v1.1 (no schema_version bump); `export_asset.py` plumbs a `route_cache/warnings.json` sidecar → `build_asset_dict(warnings=None)` → conditional emit — the channel Plan 02's cinematography route client will populate on graceful-degrade.
- httpx sync client calling kais-aigc-platform `shot-analysis` route, mapping geometry+semantic into prompts.json facets with content-hash per-shot cache, single preflight short-circuit, and graceful-degrade to schema-valid empty facets when the route is down
- Wired step_semantic into run_pipeline.py as pipeline slot 5 of 7 (between transcribe + timeline), renumbered 17 [N/6]→[N/7] labels, added 4 CLI flags (--skip-semantic/--offline/--analysis-url/--analysis-timeout), extended --force to clear prompts.json + route_cache/, and built scripts/verify_phase6_smoke.py (3-scenario regression: route-down / --skip-semantic / cache-hit-offline).
- Draft 2020-12 schema freezing the HITL edits round-trip shape (merge_groups/splits/renames/type_overrides/confirm_ids/reject_ids/review_notes) with strict additionalProperties:false + anti-traversal cluster_id pattern, plus a fixture consistent with the existing 3-cluster registry.draft.json, wired as the 10th v1.1 shape in spec/validate.py
- httpx sync client mirroring Phase 6's call_shot_analysis.py — calls the DEFERRED character-reid route once per video (cross-shot aggregation), normalizes the response into registry.draft.json via shape-agnostic projection (CAST-05: all clusters review_state='proposed'), with per-video cache, single preflight probe, broadened graceful-degrade except, and non-destructive warnings sidecar merge
- Confirmed-only canonical registry producer (`apply_edits.py` with fixed-order deterministic apply + ffmpeg representative PNG) plus first-class HITL review HTML (`gen_registry_review.py` with cosine-sorted queue + three-tier viz + client-side edits export) — closes CAST-06/07/08 producer-side
- 1. [Rule 3 — Blocking issue] Plan's `--help` grep expected 3 matches, actual is 5
- Additive `generator.registry_snapshot` schema property (compact confirmed-only freeze of characters+props) with v1.1 fixture example + SPEC §3/§4 documentation — contract-first layer unblocking Plan 02's producer emission.
- Three independent producer-side files wiring the confirmed Phase-7 registry onto prompts (attach_refs.py — PROMPT-01/02), the asset manifest (export_asset.py registry_snapshot — PROMPT-04), and the integrity gate (verify_contract.py Pitfall 17 — PROMPT-03); all pure JSON post-processing, zero ML, zero new deps.
- Three additive changes closing Phase 8's user-visible surface: `html/gen_timeline_html.py` extended with a character/prop gallery + clickable reference chips + per-shot semantic-fill indicator (PRESENT-01/02/03) carrying Phase 7 CR-04 XSS hardening verbatim; `run_pipeline.py:step_timeline` wired to invoke `prompts/attach_refs.py` as a pre-step with the mtime cache extended to include prompts_json (Pitfall 9 prevented); and a new 6-scenario `scripts/verify_phase8_smoke.py` regression harness mirroring the Phase 7 smoke structure.
- Consumer `@kais/infinite-canvas` made v1.1-aware: recognizes `schema_version:"1.1"`, emits 2 character + 1 prop child nodes as `type:"asset"` (assetType character/prop, NOT delivery) via the §7 buildPhaseTree post-process workaround, renders them with 🧑/🔧 icons, locked by 27 green verify assertions — with the v1.0 ep01 WIP untouched.
- The shot-timeline-side `scripts/verify_contract.py` 3-mode harness is confirmed GREEN for v1.1 across producer + consumer modes — ZERO source changes, the v1.0 bridge infrastructure handled everything Phase 9 needed. E2e mode remains deferred (`--e2e-skip`) as the manual post-merge check. PRESENT-06 closed.

---

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
