---
phase: 11-contract-v1-2
status: fixed
depth: quick
reviewer: gsd-code-reviewer (inline) + orchestrator capture
reviewed_at: 2026-07-25
---

# Phase 11 Code Review (quick depth)

**Status:** fixed — 0 blockers, 1 warning (WR-01, fixed).
**Files reviewed (9):** the 3 new schemas + asset.schema + export_asset.py + verify_contract.py + validate.py + 2 new fixtures.

## Summary

Phase 11 v1.2 contract artifacts are sound. Pitfall-11 additive-only invariant verified byte-identical (asset.schema `data.required` = 5 keys unchanged; git diff confirms only 2 additive properties). All 3 new schemas valid draft 2020-12 + `additionalProperties:false`. All v1.2 fixtures validate.

**Adversarial verification performed (beyond reading):**
- `Draft202012Validator.check_schema` on all 4 schemas — well-formed.
- Forward + backward cross-version checks pass (v1.1×v1.2 = 0 errors; v1.2×recovered-v1.1 = only additionalProperties, correctly filtered).
- Simulated shared-field drift (tightened pattern, injected required field) — BOTH caught. Bidirectional proof is sound.
- Phase-10 deviations: instruments omitted, emotion nullable-string, word_level_experimental flag, spk_NNN disjoint from char_NNN.
- No AF-01 over-claiming in fixtures (TTS confidence 0.7 + fidelity_disclaimer).
- Conditional emission correct (file-exists→emit, absent→omit, byte-identical to v1.0/v1.1).
- No supply-chain risk (jsonschema 4.26.0 already installed).

## WR-01 — Asymmetric source-of-truth in speakers consistency check (FIXED)

**File:** `scripts/verify_contract.py` (speakers.json consistency block).
**Issue:** the `turn.shot_id ⊆ shots.json#id` check loaded shots from the **v1.1** fixture dir while the sibling `char_id ⊆ characters.json#id` check correctly used **v1.2**. Asymmetric sources. Passed today because v1.2/shots.json is a byte-copy of v1.1, but would false-pass/fail if v1.2/shots.json ever diverges.
**Fix (applied):** added `shots_v12_ids` build mirroring `chars_v12_ids` (load from v1.2 fixture dir, fall back to v1.1 shot_ids if v1.2 absent). Symmetric source-of-truth. `verify_contract.py` exit 0 after fix.

## Notes (design choices, not findings)

- `sfx.events` / `dialogue.events` "subset" constraint is prose-only (free-string for forward-compat) — intentional.
- `word_level_experimental` "iff" invariant is prose-only (schema can't express cross-element invariant) — Phase 12 producer responsibility.
- `audio_semantic.dialogue.spk_id ⊆ speakers.speakers[].spk_id` not enforced — producer builds audio_semantic from speakers by construction (Phase 15).
- `speaker-edits.schema.json` has no fixture — intentional Phase 13 deferral (HITL round-trip).

**Verdict:** APPROVED. WR-01 fixed. No blockers.
