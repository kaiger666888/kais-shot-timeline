# Phase 16: HTML Gallery - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — frontend phase extending the existing gen_timeline_html.py (the established timeline.html UI); shape forced by v1.1 Phase 8 PRESENT patterns + Phase 11 schema + Phase 10 thresholds. All recommendations accepted per user momentum preference. UI-SPEC skipped — gen_timeline_html.py IS the design contract (the existing timeline.html pattern); this phase extends it additively.

<domain>
## Phase Boundary

Extend `html/gen_timeline_html.py` (the 1294-line timeline.html generator) to surface v1.2 audio semantics end-user-visible: per-shot dialogue/music/sfx chips + speaker→character chip + reproduction panel with "estimated" labels + XSS hardening. New CLI flags `--audio-semantic <path>` + `--speakers <path>` (graceful-omit when absent).

This phase produces the HTML rendering ONLY — NO new ML, NO new data (Phase 15 produced reproduction; Phase 12/13 produced audio_semantic + speakers). It renders existing data.

</domain>

<decisions>
## Implementation Decisions

### Per-shot chips (mirror v1.1 Phase 8 PRESENT-01/02/03 patterns)

- **Dialogue chip**: speaker label + emotion (nullable+confidence per DIA-04 ship-nullable) + text excerpt. Emotion rendered as a small badge; null emotion → no badge (not "unknown").
- **Music chip**: tempo BPM (MUS-02) + mood (MUS-03 discrete) + key (MUS-05 differentiator, nullable) + VA arousal (MUS-06 ship)/valence (experimental). **MUS-04 instruments OMITTED** — do NOT render an instruments sub-element (MUS-04 deferred v1.3; the SC#1 "tempo/key/instruments" wording predates the Phase 10 spike — instruments overruled). Music chip shows tempo/mood/key/VA only; BGM-absent shots (MUS-01) omit the music chip.
- **SFX chip**: foley description (SFX-01) + SenseVoice 8-event tags. Empty events → omit.
- Non-present modalities gracefully omitted (don't render empty chips).

### Speaker→character chip (mirror Phase 8 PRESENT-02 reference chip)

- When speakers.json resolves `spk_NNN → char_NNN`, render a character chip that links to the v1.1 character gallery (mirror PRESENT-02 reference-chip pattern).
- Unresolved speakers (旁白/群杂, char_id=null) render the speaker label alone (no character chip).
- spk_NNN disjoint from char_NNN (Phase 11 lock) — render both IDs clearly.

### Reproduction panel (AF-01 fidelity-ceiling mitigation)

- Display the 3 reproduction strings (TTS/music-gen/foley) with a VISIBLE **"estimated"** label on EVERY field (reproduction ≠ restoration — AF-01). Mirror the SPEC §10 fidelity_disclaimer framing.
- Null reproduction fields (route didn't populate) → omit gracefully (not "N/A").

### XSS hardening (CRITICAL — new attack surface)

- `_esc()` (Python) + JS text-only DOM APIs + JSON-in-script `.replace("</", "<\\/")` applied to EVERY route-derived string interpolated into HTML (mirror Phase 7 CR-04 fix 336d04f + Phase 8 carry-over).
- The layered-prompt / reproduction / speaker content is NEW attack surface (route-derived NL strings). XSS test cases MUST pass: raw `<script>`, `"onerror="`, base64 payloads, `</script>` breakout — all neutralized.
- No `innerHTML` with route-derived content; use textContent / createTextNode.

### CLI flags (mirror gen_timeline_html.py argparse)

- `--audio-semantic <path>` + `--speakers <path>` (graceful-omit when absent — byte-identical to v1.1 timeline when both absent). Wire into run_pipeline.py step_timeline (Phase 14 mtime-cache already extended for these).

### Claude's Discretion

- Exact chip layout/CSS (mirror the existing GitHub-dark chip patterns in gen_timeline_html.py).
- Whether reproduction panel is collapsible (default collapsed to avoid clutter).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`html/gen_timeline_html.py`** (1294 lines) — THE file to extend. Already renders audio_analysis (92 matches for dialogue/audio/speaker/stem). Phase 16 adds audio_semantic + speakers + reproduction rendering.
- **v1.1 Phase 8 PRESENT patterns** — the chip + reference-chip + XSS-hardening precedents (the canonical patterns to mirror).
- **`spec/fixtures/v1.2/audio_semantic.json` + `speakers.json`** — the rendered data (Phase 11/15).
- **`html/gen_registry_review.py` + `gen_speaker_review.py`** (Phase 13) — the recent XSS _esc() patterns to reuse.

### Established Patterns
- **GitHub-dark palette** (#0d1117/#161b22/#30363d/#58a6ff/#3fb950/#d29922/#f85149) — reuse for chips.
- **XSS _esc() + JSON-in-script replace** — mirror Phase 7 CR-04 + Phase 8.
- **Graceful-omit** absent modalities (don't render empty).

### Integration Points
- run_pipeline.py step_timeline (Phase 14) invokes gen_timeline_html.py with the new flags.
- Phase 17 canvas consumer renders the same data on the infinite-canvas side.

</code_context>

<specifics>
## Specific Ideas

- **MUS-04 instruments OMITTED in the music chip** — the SC#1 wording "tempo/key/instruments" is stale (predates Phase 10). Render tempo/mood/key/VA only. This is the key Phase-10-informed deviation for Phase 16.
- **AF-01 "estimated" label on EVERY reproduction field** — non-negotiable. Reproduction is a calibrated estimate, not restoration.
- **XSS is the critical security gate** — the reproduction/speaker content is route-derived NL (new attack surface). Test cases MUST pass.

</specifics>

<deferred>
## Deferred Ideas

- **DIA-06 face-voice auto speaker→character** — v1.3 (v1.2 always HITL).
- **Live route ML populating all modalities** — Phase 16 renders whatever exists; full richness when route ML is live.

</deferred>
