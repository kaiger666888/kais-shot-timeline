# Phase 15: Layered Reproduction Prompts - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — promotes an existing spike (gen_audio_prompts.py) into the pipeline; shape forced by Phase 10 thresholds + Phase 14 slot + Phase 11 reproduction schema. All recommendations accepted per user momentum preference.

<domain>
## Phase Boundary

Promote `audio/gen_audio_prompts.py` (quick task 260725-afz spike) from sidecar experiment to pipeline producer of model-agnostic NL reproduction prompts in-place at `audio_semantic.json#shots[].reproduction.{tts, music_gen, foley}`. Includes `--offline` recompose from cached audio_semantic.json (no route hit) + CONDITIONAL field gating per Phase 10 spike thresholds.

This phase produces the reproduction layer ONLY — NO new ML, NO new schema (Phase 11 already defined reproduction.{tts,music_gen,foley} with confidence+fidelity_disclaimer). It composes the 3-modality data (from Phase 12 route via step_audio_semantic) into per-shot reproduction prompts.

</domain>

<decisions>
## Implementation Decisions

### Promote the spike → pipeline producer

- `audio/gen_audio_prompts.py` (398-line spike) becomes the pipeline producer. Composes per-shot `reproduction.{tts, music_gen, foley}` strings from upstream modalities (dialogue/music/sfx) — model-agnostic NL (locked decision #7: NO NC-licensed weights embedded, just NL text).
- Invoked from `step_audio_semantic` (Phase 14 slot 7/9) AFTER the route response is normalized into audio_semantic.json. Reads the 3-modality data, writes reproduction.{tts,music_gen,foley} in-place.
- Deterministic recompose (mirror v1.1 Pattern 2 — fixed key ordering, idempotent re-apply; same input → byte-identical output).

### nullable + confidence + fidelity_disclaimer (AF-01 mitigation)

- EVERY reproduction field carries `nullable + confidence` + the SPEC `fidelity_disclaimer` (TTS ~70% / music-gen ~60-75% / foley ~80% per the Phase 11 SPEC §10 lock). HTML/SPEC/README NEVER claim "perfectly reconstruct"/"exact restoration" (AF-01 grep gate, mirror Phase 11).

### CONDITIONAL field gating per Phase 10 thresholds

- **DIA-04 emotion** (ship-nullable+confidence): populate emotion nullable + emotion_confidence.
- **DIA-05 word-level** (ship-experimental): populate words[] gated behind word_level_experimental flag.
- **MUS-04 instruments** (DEFER v1.3): emit nullable with confidence=null OR omit per schema — instruments absent. The roadmap's conditional path is explicit in the [audio] warnings sidecar.
- Table-stakes modalities (DIA-01 segment dialogue, MUS-01 BGM presence, MUS-02 tempo BPM, MUS-03 discrete mood, SFX-01 foley desc with SenseVoice 8-event tags) always flow through.
- Differentiator modalities (MUS-05 key, MUS-06 VA arousal ship/valence experimental, SFX-02 AudioSet taxonomy+timestamps, SFX-03 foley complex events) populate nullable+confidence WHEN the models produce signal; null otherwise.

### --offline recompose

- `--offline` recompose from cached `audio_semantic.json` (no route hit) produces byte-identical reproduction layer — proven by deterministic re-run diff. This lets the operator iterate on prompt composition without re-hitting the route.

### Claude's Discretion

- Exact NL prompt templates for tts/music_gen/foley (the spike has drafts; refine per the modality inputs).
- Whether reproduction composition is a function in call_audio_analysis.py or a separate step in gen_audio_prompts.py invoked from step_audio_semantic.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`audio/gen_audio_prompts.py`** (398 lines, spike) — THE artifact to promote. Has draft NL templates for tts/music_gen/foley.
- **`.planning/quick/260725-afz-*`** — the spike's plan + summary (the design rationale).
- **`analysis/call_audio_analysis.py`** (Phase 12) — normalizes route response into audio_semantic.json; Phase 15 composes reproduction from that.
- **`run_pipeline.py:step_audio_semantic`** (Phase 14) — the pipeline slot; Phase 15 hooks reproduction composition into it.
- **`spec/schemas/audio_semantic.schema.json`** (Phase 11) — the `reproduction.{tts,music_gen,foley}` shape with confidence+fidelity_disclaimer (already defined).
- **Phase 10 spike results** — the threshold basis (DIA-04/MUS-04/DIA-05 ship-or-defer).

### Established Patterns
- **Model-agnostic NL** (locked decision #7): reproduction = NL text, no weight embedding.
- **Deterministic recompose** (v1.1 Pattern 2): fixed key order, idempotent.
- **CONDITIONAL gating**: ship-or-defer per spike thresholds, deferred → nullable+confidence=null.

### Integration Points
- Phase 16 HTML gallery renders the reproduction panel with "estimated" labels.
- Phase 14 step_audio_semantic is where reproduction composition hooks in.

</code_context>

<specifics>
## Specific Ideas

- The AF-01 grep gate ("perfectly reconstruct"/"exact restoration"/"完美复刻"/"精确复原" = 0 matches) is non-negotiable — reproduction is a calibrated estimate, not perfect restoration. Mirror Phase 11's fidelity_disclaimer.
- Deterministic recompose (--offline byte-identical) is the correctness proof — same audio_semantic input → same reproduction output, always.
- MUS-04 instruments are OMITTED (confidence=null or absent) — the spike showed no instrument signal. Don't synthesize.

</specifics>

<deferred>
## Deferred Ideas

- **Live route ML populating all modalities** — Phase 15 composes from whatever the route returns; full modality richness when route ML is live (post-merge).
- **MUS-04 instruments in reproduction** — v1.3, pending real MIR classifier.

</deferred>
