# Roadmap: kais-shot-timeline

## Milestones

- ✅ **v1.0 ShotTimelineAsset Contract** — Phases 1-4 (shipped 2026-07-20) — [archived](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 分镜语义深化** — Phases 5-9 (shipped 2026-07-25) — 镜头语言 + 跨镜角色/道具注册表 + prompt 引用 + 契约 minor bump 1→1.1 + 双端展示 — [archived](milestones/v1.1-ROADMAP.md)
- 🟢 **v1.2 音频语义深化 (Active)** — Phases 10-17 — route-based 三模态音频语义（对白/音乐/音效）+ 分层复现 prompt (TTS/music-gen/foley) + 说话人↔角色 HITL + 契约 minor bump 1.1→1.2 + 双端展示

## Phases

<details>
<summary>✅ v1.0 ShotTimelineAsset Contract (Phases 1-4) — SHIPPED 2026-07-20</summary>

A repo-agnostic **ShotTimelineAsset** format contract: the canonical "asset collection shape" (5-JSON canonical form + media reference conventions + self-describing manifest) that `kais-shot-timeline` exports and `@kais/infinite-canvas` (in repo `kais-aigc-platform`) consumes as a first-class collection.

- [x] **Phase 1: ShotTimelineAsset Specification** — repo-agnostic contract (6 schemas + version + media refs + manifest) both repos implement against — COMPLETE 2026-07-20
- [x] **Phase 2: shot-timeline Exporter (Producer)** — pipeline output → ShotTimelineAsset artifact, versioned + self-describing, Range-served — COMPLETE 2026-07-20
- [x] **Phase 3: Canvas Consumer** — canvas ingestion via structural parent node reusing existing 5 renderers (no contract bump) — COMPLETE 2026-07-21 *(code in kais-aigc-platform `feat/canvas-asset-collection`)*
- [x] **Phase 4: Cross-Repo Contract Verification** — end-to-end flow + regression protection against schema/media-reference drift — COMPLETE 2026-07-21

**Audit:** 12/12 requirements satisfied, 4/4 phases verified, integration complete — [v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md)

</details>

<details>
<summary>✅ v1.1 分镜语义深化 (Phases 5-9) — SHIPPED 2026-07-25</summary>

Strict-additive, contract-first minor bump on v1.0. Adds two new pipeline stages calling ML HTTP routes in `kais-aigc-platform` (cinematography analysis + cross-shot re-id), three new optional data files (`characters.json`, `props.json`, enriched `prompts.json`), a first-class HITL review HTML deliverable, and a canvas consumer extension. Mirrors v1.0's contract-first sequencing that worked.

- [x] **Phase 5: Contract v1.1** — 3 new registry schemas + 2 additive schema extensions + SPEC + 9-file v1.1 fixture + verify harness (no route dependency) — COMPLETE 2026-07-24
- [x] **Phase 6: Cinematography Auto-Fill (`step_semantic`)** — httpx client + graceful-degrade + per-shot cache + generator.warnings — COMPLETE 2026-07-24
- [x] **Phase 7: Cross-Shot Re-ID Registry + HITL Review (`step_reid`)** — producer client + HITL review HTML + `apply_edits.py` confirmed-only gate — COMPLETE 2026-07-25
- [x] **Phase 8: Prompt Reference System + shot-timeline HTML Gallery** — `attach_refs.py` + `registry_snapshot` freeze + gallery/chips/indicator — COMPLETE 2026-07-25
- [x] **Phase 9: Canvas Consumer Integration (cross-repo)** — consumer recognizes `"1.1"` + emits character/prop `asset` nodes (no renderer / no Zod bump) — COMPLETE 2026-07-25

**Audit:** 34/34 requirements satisfied, 5/5 phases verified — [v1.1-MILESTONE-AUDIT.md](milestones/v1.1-MILESTONE-AUDIT.md)

**Full phase details:** [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

</details>

### v1.2 音频语义深化 (Phases 10-17) — ACTIVE

Route-based audio semantic deepening: a third sibling of the v1.1 route-pattern family (`call_shot_analysis.py` per-shot, `call_reid.py` per-video → new `call_audio_analysis.py` per-shot). Adds 3 modalities (dialogue/music/sfx) + layered reproduction prompts (TTS/music-gen/foley) + closes the v1.1 SPEAKER-01 deferral via a new `spk_NNN` ID space + HITL linking. Schema bump `1.1 → 1.2` is pure-additive. Mirrors v1.1's "先证模型、再立契约" sequencing (Phase 7 DINOv2 τ spike pattern → Phase 10 audio model spike).

- [x] **Phase 10: Risk-Validation Spike + Route Stub** — validate SenseVoice/MERT/pyannote/WhisperX on 1 ep BEFORE contract; CUDA 12.8 decision; route stub envelope (completed 2026-07-25)
- [x] **Phase 11: Contract v1.2** — 3 new schemas + 12-file fixture + SCHEMA_VERSION="1.2" + bidirectional cross-version proof (completed 2026-07-25)
- [x] **Phase 12: Producer Route Client** — `call_audio_analysis.py` thin httpx + per-shot cache + poisoned-cache + read-merge-write [audio] warnings + graceful-degrade (completed 2026-07-25)
- [x] **Phase 13: SPEAKER-01 Linkage HITL** — `link_speakers.py` confirmed-only + `gen_speaker_review.py` → `speakers.json` (closes v1.1 SPEAKER-01 deferral) (completed 2026-07-25)
- [x] **Phase 14: Pipeline Integration** — `step_audio_semantic` slot 7 of 9 + `[N/8]→[N/9]` renumber + 4 CLI flags + 5-scenario smoke harness (completed 2026-07-26)
- [x] **Phase 15: Layered Reproduction Prompts** — promote `gen_audio_prompts.py` spike → in-place `reproduction.{tts,music_gen,foley}` + `--offline` fallback + table-stakes & differentiator modality enrichment + CONDITIONAL fields gated on Phase 10
- [x] **Phase 16: HTML Gallery** — dialogue/music/sfx chips + speaker→character chip + reproduction panel ("estimated" labels) + XSS hardening (completed 2026-07-25) (completed 2026-07-26)
- [x] **Phase 17: Canvas Consumer (deferrable)** — `import-from-dir.ts` v1.2 + audio asset nodes via §7 post-process (no renderer / no Zod bump) (completed 2026-07-26)

## Phase Details

### Phase 10: Risk-Validation Spike + Route Stub
**Goal**: Empirically de-risk the 4 highest unknowns of v1.2 (Chinese SER cross-domain on animation, polyphonic instrument recognition on Demucs stems, WhisperX word-level drift, CUDA 12.8 upgrade compatibility) on 1 episode of 《小江湖》 BEFORE any contract locks — mirroring v1.1 Phase 7 DINOv2 τ spike ("先证模型、再立契约").
**Depends on**: Nothing (first phase of milestone)
**Requirements**: ROUTE-01 (route stub envelope); spike outputs de-risk DIA-04, DIA-05, MUS-04 (conditional reqs whose ship/defer hinges on Phase 10 thresholds)
**Success Criteria** (what must be TRUE):
  1. Developer can POST to `/api/production/audio-analysis` and receive a `{"code":200,"data":{...}}` envelope even with ML models unloaded (stub mode) — proving producer client has an integration target before route ML lands (mount path `/api/production/audio-analysis` — NO `/v1/`, verified against kais-aigc-platform/src/router.ts sibling shot-analysis mount)
  2. Spike report documents Chinese SER macro-F1 on 1 episode vocals stem (cross-domain RAVDESS→中文动画 gap), enabling an evidence-based DIA-04 ship (≥50%) / defer (<40%) / ship-nullable (40-50%) decision
  3. Spike report documents polyphonic instrument recognition mAP on 1 episode `drums+bass+other` mix (esp. erhu/pipa/guzheng/dizi folk instruments), enabling the MUS-04 ship/defer decision and the MERT-vs-PANNs head-to-head pick
  4. Spike report documents WhisperX word-level alignment drift on ≥N Chinese segments (PyPI hard-requires CUDA 12.8), enabling the DIA-05 ship-experimental / defer decision AND the CUDA 12.8 upgrade vs stay-on-12.4 (drop WhisperX) decision
  5. PROJECT.md Key Decisions logs the 4 locked outcomes (models_used strings per modality; CUDA path; DIA-04/MUS-04/DIA-05 ship-or-defer per thresholds)
**Plans**:
- [x] 10-01-PLAN.md — Wave 0 foundation: spike/audio/common.py + tests/ smoke harness + aggregate_report.py skeleton
- [x] 10-02-PLAN.md — ROUTE-01 cross-repo stub (kais-aigc-platform feat/audio-analysis-route): envelope mirrors shot-analysis
- [x] 10-03-PLAN.md — SER spike (SenseVoice on ep01 vocals, DIA-04 de-risk) + methodology checkpoint
- [x] 10-04-PLAN.md — MIR head-to-head spike (MERT-v1-95M + PANNs Cnn14 on drums+bass+other, MUS-04 de-risk) + methodology checkpoint
- [x] 10-05-PLAN.md — WhisperX drift spike (isolated venv CPU, DIA-05 + CUDA-path de-risk)
- [x] 10-06-PLAN.md — Aggregate spike report + lock 4 outcomes into PROJECT.md + threshold-decision checkpoint

### Phase 11: Contract v1.2
**Goal**: Lock the v1.2 contract — 3 new schemas + additive asset.schema extension + `SCHEMA_VERSION = "1.2"` single-source + 12-file fixture + bidirectional cross-version proof + SPEC + fidelity_disclaimer — BEFORE any producer code writes against it (mirror v1.1 Phase 5 contract-first).
**Depends on**: Phase 10 (spike results inform field shapes: emotion as `type:string` not enum until calibrated, nullable+confidence pattern for low-confidence fields, instruments as `list[{label,confidence}]`)
**Requirements**: CONTRACT-01, CONTRACT-02, CONTRACT-03, CONTRACT-04, CONTRACT-05
**Success Criteria** (what must be TRUE):
  1. `audio_semantic.schema.json`, `speakers.schema.json`, `speaker-edits.schema.json` (all draft 2020-12, `additionalProperties:false`) validate; `asset.schema.json` extended with optional `data.audio_semantic` + `data.speakers` (not in `required[]`)
  2. `SCHEMA_VERSION = "1.2"` locked single-source in export_asset.py; v1.0/v1.1 fixtures remain byte-identical when audio_semantic.json + speakers.json absent (graceful-degrade CONTRACT-05 proof)
  3. v1.2 12-file fixture set validates 12/12 green under new V12_ORDER; v1.1 fixture still 10/10 green under extended schemas (additive-only proof)
  4. verify_contract.py bidirectional cross-version self-test GREEN: forward (v1.1 fixture × v1.2 schema = 0 errors) + backward (v1.2 fixture × recovered-v1.1 schema = only additionalProperties errors) + fixture-consistency (`speakers.char_id ⊆ characters.id` where present)
  5. SPEC.md §4 Changelog `1.2` entry + §5 audio_semantic/speakers shapes + `fidelity_disclaimer` documented (AF-01 "perfect restoration" explicitly out-of-scope)
**Plans**:
- [x] 11-01-PLAN.md — 3 new schemas (audio_semantic + speakers + speaker-edits) + asset.schema additive + SCHEMA_VERSION="1.2" bump + conditional producer emission
- [x] 11-02-PLAN.md — 12-file v1.2 fixture + validate.py 3-tier gate (V12_ORDER) + verify_contract.py bidirectional v1.0↔v1.1↔v1.2 proof + speakers⊆characters consistency
- [x] 11-03-PLAN.md — SPEC.md §4 Changelog 1.2 + §5.8/§5.9 shapes + fidelity_disclaimer + README.md v1.2 footer

### Phase 12: Producer Route Client (`call_audio_analysis.py`)
**Goal**: Producer-side thin httpx client hits the audio-analysis route per-shot (mirror `call_shot_analysis.py` pattern) + per-shot 4-tuple cache + poisoned-cache invalidation (mirror `call_reid.py`) + read-merge-write `[audio]` warnings sidecar + graceful-degrade to schema-valid empty state.
**Depends on**: Phase 11 (schema is the client's pre-write validation target)
**Requirements**: ROUTE-02, ROUTE-03, PIPE-02
**Success Criteria** (what must be TRUE):
  1. `call_audio_analysis.py` POSTs per-shot `{video, shots, shot_id_range, stems_dir, models, language}` to the documented route contract and normalizes the 3-modality response into `audio_semantic.json` (route contract documented per ROUTE-03)
  2. Per-shot cache (4-tuple key: `video_content_hash`/`route_name`/`route_version`/implicit `shot_id`) hits on re-run; poisoned cache (schema-validate fail) auto-invalidates and re-fetches (mirror `call_reid.py:418-427`)
  3. Graceful-degrade: route unreachable / preflight fail / `--offline` → `audio_semantic.json` not written (byte-identical to v1.1 asset) AND `[audio]` warning appended to sidecar WITHOUT clobbering existing `[semantic]`/`[reid]` tags (read-merge-write per `call_reid.py:443-449`)
  4. Stub-only round-trip (Phase 10 stub, models not loaded) confirms envelope parsing + cache write + warnings merge work BEFORE route ML is live
**Plans**:
- [x] 12-01-PLAN.md — the producer client `analysis/call_audio_analysis.py` (httpx POST + envelope normalize + schema-validate gate + per-shot 4-tuple cache + poisoned-cache invalidation + graceful-degrade + [audio] warnings read-merge-write + CLI)
- [x] 12-02-PLAN.md — SC#4 stub-only round-trip proof (local stub server + frozen fixtures + 5-scenario smoke harness + best-effort live cross-repo stub cross-check)

### Phase 13: SPEAKER-01 Linkage HITL
**Goal**: Close the v1.1 SPEAKER-01 deferral via a NEW `^spk_[0-9]{3}$` acoustic ID space (NOT reusing `^char_[0-9]{3}$` — avoids identity-signal conflation) + HITL review HTML + confirmed-only apply gate (mirror v1.1 Phase 7 `apply_edits.py`).
**Depends on**: Phase 12 (producer client produces raw `spk_NNN` IDs from route) + v1.1 character registry (provides `char_NNN` mapping target)
**Requirements**: SPEAKER-01, SPEAKER-02, SPEAKER-03, DIA-02, DIA-03
**Success Criteria** (what must be TRUE):
  1. `html/gen_speaker_review.py` renders HITL HTML with speaker cards sorted by shot_count desc + per-speaker character dropdown filtered to `characters.json#review_state=="confirmed"` + export-edits button → `speaker-edits.json`
  2. `registry/link_speakers.py` confirmed-only hard gate at build-entry (mirror `apply_edits.py`): only `review_state=="confirmed"` mappings land in `speakers.json`; idempotent re-apply produces byte-identical output (fixed apply order + deterministic _next_speaker_id)
  3. `speakers.json` validates against speakers.schema.json; `char_id` nullable (旁白/群杂 supported); non-null `char_id` MUST resolve to a confirmed `characters.json#id`
  4. Producer registry integrity assert extended additively from v1.1 `_producer_registry_integrity` (gated on file existence — no-op on v1.0/v1.1/route-down assets): catches speakers→characters dangling refs at producer time (Pitfall 17 second-line defense)
  5. End-to-end HITL round-trip proven on fixture: `audio_semantic.json` + `characters.json` → review HTML → `speaker-edits.json` → `speakers.json` (confirmed-only); DIA-02 diarization + DIA-03 speaker↔character HITL both exercised
**Plans**: 3 plans
- [x] 13-01-PLAN.md — registry/link_speakers.py confirmed-only apply gate (mirror apply_edits.py) + producer registry integrity additive extension (SPEAKER-03)
- [x] 13-02-PLAN.md — html/gen_speaker_review.py HITL review HTML (speaker cards sorted by shot_count + character dropdown filtered to confirmed + Export-edits + XSS hardening)
- [x] 13-03-PLAN.md — End-to-end HITL round-trip proof on v1.2 fixtures (SC#5) + idempotency + confirmed-only gate + XSS regression + producer integrity acceptance
**UI hint**: yes

### Phase 14: Pipeline Integration
**Goal**: Wire `step_audio_semantic` into run_pipeline.py as slot 7 of 9 (between `step_reid[6]` and `step_timeline[8]`) with all CLI flags, `--force` cache extension, mtime-cache extension, and a 5-scenario smoke regression harness — mirror v1.1 Phase 6/7 pipeline wiring.
**Depends on**: Phase 12 (client) + Phase 13 (link_speakers, invoked between step_audio_semantic and step_timeline as a non-blocking standalone CLI)
**Requirements**: PIPE-01, PIPE-03
**Success Criteria** (what must be TRUE):
  1. `step_audio_semantic` runs as slot 7 of 9 (after `step_reid`, before `step_timeline`); all 17 `[N/8]` banner instances renumbered to `[N/9]` (grep audit confirms zero stragglers — Pitfall: phase-counter drift)
  2. CLI flags `--skip-audio-semantic` / `--audio-url` / `--audio-timeout` / `--skip-speaker-link` / `--offline` work as documented; `--force` clears `audio_semantic.json` + `speakers.json` + `route_cache/audio_analysis/` (explicit list, NOT glob — project convention)
  3. `step_timeline` regenerates when `audio_semantic.json` or `speakers.json` mtime changes (inputs list extended — Pitfall 9 prevention, mirror Phase 8 prompts_json addition)
  4. `scripts/verify_phase_audio_smoke.py` 5-scenario regression GREEN: route-up / route-down / cache-hit-offline / conditional-field-defer (nullable+confidence) / stub-only (mirror Phase 6/7 3-scenario + Phase 8 6-scenario harness pattern)
  5. End-to-end `python run_pipeline.py --video <ep>` produces `asset.json` with `schema_version: "1.2"` and conditionally emits `data.audio_semantic` + `data.speakers`
**Plans**: TBD

### Phase 15: Layered Reproduction Prompts
**Goal**: Promote the `audio/gen_audio_prompts.py` spike (quick task 260725-afz) from sidecar experiment to pipeline producer of model-agnostic NL reproduction prompts in-place at `audio_semantic.json#shots[].reproduction.{tts, music_gen, foley}` + `--offline` recompose from cached modalities + CONDITIONAL field gating per Phase 10 spike thresholds.
**Depends on**: Phase 14 (pipeline slot + 3-modality data flow exist)
**Requirements**: PROMPT-01, PROMPT-02, PROMPT-03, DIA-01, DIA-04, DIA-05, MUS-01, MUS-02, MUS-03, MUS-04, MUS-05, MUS-06, SFX-01, SFX-02, SFX-03
**Success Criteria** (what must be TRUE):
  1. Per-shot `reproduction.{tts, music_gen, foley}` strings composed from upstream modalities (dialogue/music/sfx) — model-agnostic NL (locked decision #7 — no NC weights embedded); deterministic recompose (mirror v1.1 Pattern 2 — fixed key ordering, idempotent re-apply)
  2. Every reproduction field carries `nullable + confidence` + SPEC documents `fidelity_disclaimer` (TTS ~70% / music-gen ~60-75% / foley ~80% — AF-01 mitigation); HTML/SPEC/README never claim "perfectly reconstruct"/"exact restoration"
  3. Table-stakes modality enrichment flows through to reproduction prompts: DIA-01 segment dialogue, MUS-01 BGM presence segmentation, MUS-02 tempo BPM, MUS-03 discrete mood, SFX-01 foley description (with SenseVoice 8 audio-event tags)
  4. Differentiator modality enrichment populates nullable+confidence fields when models produce signal: MUS-05 key, MUS-06 VA (arousal ship / valence experimental), SFX-02 AudioSet taxonomy + timestamps, SFX-03 foley complex event sequences
  5. CONDITIONAL-gated items (DIA-04 emotion / DIA-05 word-level / MUS-04 instruments) ship-or-defer per Phase 10 spike thresholds; deferred items emitted as nullable with `confidence=null` (or omitted per schema) — the roadmap's conditional path is explicit in speakers.json warnings sidecar
  6. `--offline` recompose from cached `audio_semantic.json` (no route hit) produces byte-identical reproduction layer — proven by deterministic re-run diff
**Plans**: TBD

### Phase 16: HTML Gallery
**Goal**: shot-timeline `timeline.html` surfaces v1.2 audio semantics end-user-visible — per-shot dialogue/music/sfx chips + speaker→character chip + reproduction panel with "estimated" labels + XSS hardening (mirror v1.1 Phase 8 PRESENT-01/02/03).
**Depends on**: Phase 15 (reproduction data ready) + Phase 14 (`--audio-semantic` / `--speakers` CLI flags exist on gen_timeline_html wiring)
**Requirements**: PRESENT-01
**Success Criteria** (what must be TRUE):
  1. `gen_timeline_html.py --audio-semantic <path> --speakers <path>` renders per-shot dialogue chip (speaker label + emotion + text excerpt), music chip (tempo/key/instruments), sfx chip (description excerpt) — non-present modalities gracefully omitted
  2. When `speakers.json` resolves `spk_NNN → char_NNN`, a character chip links to the v1.1 character gallery (mirror Phase 8 PRESENT-02 reference chip); unresolved speakers (旁白/群杂) render the speaker label alone
  3. Reproduction panel displays the 3 TTS/music-gen/foley strings with a visible "estimated" label on every field (AF-01 fidelity-ceiling mitigation — reproduction ≠ restoration)
  4. XSS `_esc()` defense (Python + JS + JSON-in-script `.replace`) applied to EVERY route-derived string interpolated into HTML (mirror Phase 7 CR-04 fix 336d04f + Phase 8 carry-over — layered-prompt HTML is a new attack surface); XSS test cases (raw `<script>`, `"onerror="`, base64 payloads) pass
**Plans**: TBD
**UI hint**: yes

### Phase 17: Canvas Consumer (deferrable via graceful-degrade)
**Goal**: `@kais/infinite-canvas` consumer (cross-repo `kais-aigc-platform` `feat/canvas-asset-collection`) recognizes `schema_version:"1.2"` and emits per-shot dialogue/music/sfx `type:"asset"` child nodes via the §7 `buildPhaseTree` post-process workaround proven in v1.1 Phase 9 — NO custom renderer, NO Zod contract bump.
**Depends on**: Phase 11 (contract locked — consumer needs schema_version literal) + Phase 16 (HTML side shipped — cross-repo work comes last per v1.1 sequencing lesson)
**Requirements**: CONSUMER-01
**Success Criteria** (what must be TRUE):
  1. `import-from-dir.ts` appends `"1.2"` to `SHOT_TIMELINE_KNOWN_VERSIONS`; v1.0/v1.1 asset directories still import with zero regression (forward-compat proof)
  2. §7 post-process emits 1 dialogue + 1 music + 1 sfx `type:"asset"` child per shot with non-null modality (gated on `KNOWN_VERSIONS.has("1.2")`); older consumers silently skip with a graceful-degrade warning per SPEC §4
  3. `AssetNode.tsx` `typeIcons` cosmetic extension: `dialogue:"💬"` / `music:"🎵"` / `sfx:"🔊"` (mirror v1.1 character `🧑` / prop `🔧`)
  4. `verify-canvas-shot-timeline.ts` assertion counts extended for v1.2 audio nodes (mirror v1.1 27→29 bump); GREEN on a v1.2 fixture
  5. `scripts/verify_contract.py` 3-mode harness GREEN for v1.2 fixture (producer + consumer shells; e2e backend mode deferred per v1.1 precedent)
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
v1.2 phases execute in numeric order: 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. ShotTimelineAsset Specification | v1.0 | 2/2 | Complete | 2026-07-20 |
| 2. shot-timeline Exporter (Producer) | v1.0 | 2/2 | Complete | 2026-07-20 |
| 3. Canvas Consumer | v1.0 | 1/1 | Complete | 2026-07-21 |
| 4. Cross-Repo Contract Verification | v1.0 | 2/2 | Complete | 2026-07-21 |
| 5. Contract v1.1 | v1.1 | 4/4 | Complete | 2026-07-24 |
| 6. Cinematography Auto-Fill (`step_semantic`) | v1.1 | 3/3 | Complete | 2026-07-24 |
| 7. Cross-Shot Re-ID Registry + HITL Review (`step_reid`) | v1.1 | 4/4 | Complete | 2026-07-25 |
| 8. Prompt Reference System + shot-timeline HTML Gallery | v1.1 | 3/3 | Complete | 2026-07-25 |
| 9. Canvas Consumer Integration (cross-repo) | v1.1 | 2/2 | Complete | 2026-07-25 |
| 10. Risk-Validation Spike + Route Stub | v1.2 | 6/6 | Complete    | 2026-07-25 |
| 11. Contract v1.2 | v1.2 | 3/3 | Complete    | 2026-07-25 |
| 12. Producer Route Client | v1.2 | 2/2 | Complete    | 2026-07-25 |
| 13. SPEAKER-01 Linkage HITL | v1.2 | 3/3 | Complete    | 2026-07-25 |
| 14. Pipeline Integration | v1.2 | 2/2 | Complete    | 2026-07-26 |
| 15. Layered Reproduction Prompts | v1.2 | 2/2 | Complete    | 2026-07-26 |
| 16. HTML Gallery | v1.2 | 1/1 | Complete    | 2026-07-26 |
| 17. Canvas Consumer | v1.2 | 1/1 | Complete    | 2026-07-26 |
