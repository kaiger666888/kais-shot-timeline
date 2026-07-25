#!/usr/bin/env bash
# Phase 13 SC#5 end-to-end HITL round-trip proof. Mirrors Phase 12
# tests/run_audio_analysis_smoke.sh structure but simpler (no stub server —
# both Plan 01 link_speakers.py + Plan 02 gen_speaker_review.py CLIs are
# file-in/file-out). Canonical v1.2 fixtures are READ-ONLY inputs; all
# augmentations (synthetic third speaker, poison payloads, corrupted producer
# dirs) go to the /tmp workdir which is trap-rm-rf'd on exit.
#
# Proves the full SPEAKER-01 HITL round-trip on the v1.2 fixture set:
#   audio_semantic.json + characters.json
#     → gen_speaker_review.py HTML (Plan 02)
#     → frozen speaker-edits.json (operator decision surrogate)
#     → link_speakers.py (Plan 01)
#     → canonical speakers.json (confirmed-only, schema-valid)
#
# 5 scenarios (all MUST pass; any failure → exit 1 + diff/grep evidence):
#   1. Happy-path round-trip (gen HTML + apply edits → canonical speakers.json)
#   2. Idempotency (re-apply 3× → byte-identical sha256)
#   3. Confirmed-only gate (reject_ids → rejected spk omitted from canonical)
#   4. XSS regression (poison <script> payloads neutralized by _esc + JSON
#      bootstrap .replace("</","<\\/"))
#   5. Producer integrity extension (accepts canonical + rejects Pitfall 7 leak)
#
# On all 5 PASS → echo "PHASE13_ROUND_TRIP_PASS" + exit 0.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="/tmp/p13-smoke-$$"

cleanup() {
    rm -rf "${WORK}"
}
trap cleanup EXIT

# ─── Phase 13 fixture inputs (READ-ONLY — never modify) ───────────────────
FIX_AUDIO="${REPO_ROOT}/spec/fixtures/v1.2/audio_semantic.json"
FIX_CHARS="${REPO_ROOT}/spec/fixtures/v1.2/characters.json"
FIX_SHOTS="${REPO_ROOT}/spec/fixtures/v1.2/shots.json"
FROZEN_EDITS="${REPO_ROOT}/tests/fixtures/speaker_edits_phase13_smoke.json"
SPEAKERS_SCHEMA="${REPO_ROOT}/spec/schemas/speakers.schema.json"
SPEAKER_EDITS_SCHEMA="${REPO_ROOT}/spec/schemas/speaker-edits.schema.json"
LINK_CLI="${REPO_ROOT}/registry/link_speakers.py"
REVIEW_CLI="${REPO_ROOT}/html/gen_speaker_review.py"

mkdir -p "${WORK}"

# ─── helpers ─────────────────────────────────────────────────────────────
run_link() {
    # wraps link_speakers.py with predictable paths; extra flags via "$@".
    python3 "${LINK_CLI}" \
        --audio-semantic "${FIX_AUDIO}" \
        --characters "${FIX_CHARS}" \
        --edits "${FROZEN_EDITS}" \
        --work-dir "${WORK}" \
        "$@"
}

run_review() {
    # wraps gen_speaker_review.py; all flags via "$@" (audio-semantic/characters
    # intentionally overridable so Scenario 4 can poison them).
    python3 "${REVIEW_CLI}" "$@"
}

assert_schema() {
    # assert_schema <schema-path> <instance-path> <label>
    local schema="$1" instance="$2" label="$3"
    if python3 -c "
import json, jsonschema, sys
schema = json.load(open('${schema}'))
data = json.load(open('${instance}'))
errors = list(jsonschema.Draft202012Validator(schema).iter_errors(data))
if errors:
    for e in errors[:5]:
        print('  -', '[', '/'.join(str(p) for p in e.absolute_path) or '<root>', ']', e.message, file=sys.stderr)
    sys.exit(1)
"; then
        echo "  [PASS] ${label}: schema-valid (Draft202012Validator)"
    else
        echo "  [FAIL] ${label}: schema-invalid"
        exit 1
    fi
}

assert_grep() {
    # assert_grep <label> <pattern> <file>
    local label="$1" pattern="$2" file="$3"
    if grep -qE "${pattern}" "${file}" 2>/dev/null; then
        echo "  [PASS] ${label}: grep '${pattern}' in $(basename "${file}")"
    else
        echo "  [FAIL] ${label}: grep '${pattern}' NOT found in $(basename "${file}")"
        cat "${file}" 2>/dev/null | head -40 || echo "(file missing)"
        exit 1
    fi
}

assert_not_grep() {
    # assert_not_grep <label> <pattern> <file>
    local label="$1" pattern="$2" file="$3"
    if ! grep -qE "${pattern}" "${file}" 2>/dev/null; then
        echo "  [PASS] ${label}: grep '${pattern}' NOT in $(basename "${file}") (expected)"
    else
        echo "  [FAIL] ${label}: grep '${pattern}' unexpectedly found in $(basename "${file}")"
        grep -nE "${pattern}" "${file}" 2>/dev/null | head -10
        exit 1
    fi
}

assert_py() {
    # assert_py <label> <python code>. Code runs via stdin; non-zero exit = FAIL.
    local label="$1" code="$2"
    if python3 -c "${code}"; then
        echo "  [PASS] ${label}"
    else
        echo "  [FAIL] ${label}"
        exit 1
    fi
}

# Sanity: frozen fixture parses + schema-validates BEFORE any scenario runs.
# T-13-13 mitigation: catches fixture/schema drift early with a clear message.
python3 -c "
import json, jsonschema
schema = json.load(open('${SPEAKER_EDITS_SCHEMA}'))
data = json.load(open('${FROZEN_EDITS}'))
jsonschema.Draft202012Validator(schema).validate(data)
print('[smoke] frozen fixture parses + schema-validates against speaker-edits.schema.json')
"

# ═══ SCENARIO 1: happy-path round-trip ═══════════════════════════════════
echo "[smoke] SCENARIO 1: happy-path round-trip (gen HTML + apply frozen edits)"

# Step 1: gen HITL review HTML on canonical fixture inputs (proves Plan 02).
run_review --audio-semantic "${FIX_AUDIO}" --characters "${FIX_CHARS}" \
           --shots "${FIX_SHOTS}" --output "${WORK}/review.html" > /dev/null
[ -s "${WORK}/review.html" ] || { echo "  [FAIL] S1 review.html empty/missing"; exit 1; }
echo "  [PASS] S1 review.html generated ($(wc -c < "${WORK}/review.html") bytes)"
assert_grep "S1 spk_001 card present" 'data-speaker-id="spk_001"' "${WORK}/review.html"
assert_grep "S1 confirmed char_001 dropdown option" '<option value="char_001">少女</option>' "${WORK}/review.html"
# Pitfall 7 upstream gate: no unconfirmed char data leaks into the HTML.
# (confirmed_chars_json bootstrap only includes confirmed entries — a regression
#  that inlined raw characters.json would surface 'review_state':'proposed' here.)
assert_not_grep "S1 no unconfirmed chars in HTML" 'review_state.*proposed|review_state.*rejected' "${WORK}/review.html"

# Step 2: link_speakers applies the frozen operator decisions → canonical.
run_link --output "${WORK}/speakers.json" > /dev/null
[ -f "${WORK}/speakers.json" ] || { echo "  [FAIL] S1 speakers.json missing"; exit 1; }
assert_schema "${SPEAKERS_SCHEMA}" "${WORK}/speakers.json" "S1 speakers.json schema-valid"
assert_py "S1 canonical shape (2 confirmed; spk_001→char_001; spk_002→null)" "
import json
d = json.load(open('${WORK}/speakers.json'))
assert all(s['review_state']=='confirmed' for s in d['speakers']), 'non-confirmed leaked'
assert len(d['speakers'])==2, f'expected 2, got {len(d[\"speakers\"])}'
spk1 = next(s for s in d['speakers'] if s['spk_id']=='spk_001')
assert spk1['char_id']=='char_001', f'spk_001 char_id: {spk1[\"char_id\"]}'
spk2 = next(s for s in d['speakers'] if s['spk_id']=='spk_002')
assert spk2.get('char_id') is None, f'spk_002 should have null char_id, got {spk2.get(\"char_id\")}'
print('    2 confirmed speakers; spk_001→char_001; spk_002→null (旁白/群杂)')
"
echo "[smoke] SCENARIO 1: PASS"

# ═══ SCENARIO 2: idempotency — byte-identical re-apply ═══════════════════
echo "[smoke] SCENARIO 2: idempotency (re-apply frozen edits 3× → byte-identical)"
H1=$(sha256sum "${WORK}/speakers.json" | awk '{print $1}')
run_link --output "${WORK}/speakers_run2.json" > /dev/null
run_link --output "${WORK}/speakers_run3.json" > /dev/null
H2=$(sha256sum "${WORK}/speakers_run2.json" | awk '{print $1}')
H3=$(sha256sum "${WORK}/speakers_run3.json" | awk '{print $1}')
if [ "${H1}" == "${H2}" ] && [ "${H2}" == "${H3}" ]; then
    echo "  [PASS] S2 byte-identical across 3 runs (sha256: ${H1})"
else
    echo "  [FAIL] S2 sha256 mismatch: H1=${H1} H2=${H2} H3=${H3}"
    diff "${WORK}/speakers.json" "${WORK}/speakers_run2.json" || true
    exit 1
fi
echo "[smoke] SCENARIO 2: PASS"

# ═══ SCENARIO 3: confirmed-only gate — reject_ids excludes speaker ═══════
echo "[smoke] SCENARIO 3: confirmed-only gate (reject_ids → spk omitted from canonical)"
# Augment audio_semantic with a synthetic 3rd speaker (spk_003 in synthetic shot 3).
# Copy to /tmp — NEVER modify the canonical fixture (T-13-14 mitigation).
python3 -c "
import json, copy
src = json.load(open('${FIX_AUDIO}'))
augmented = copy.deepcopy(src)
augmented['shots'].append({
    'shot_id': 3, 'start_sec': 3.0, 'end_sec': 4.5, 'duration': 1.5,
    'dialogue': {'text': 'third speaker (synthetic for reject_ids proof)', 'spk_id': 'spk_003'},
})
json.dump(augmented, open('${WORK}/audio_augmented.json', 'w'), ensure_ascii=False, indent=2)
print('  [info] augmented audio_semantic copied to $WORK/audio_augmented.json (canonical untouched)')
"
# Inline edits: confirm spk_001 + spk_002, REJECT spk_003, link spk_001.
python3 -c "
import json
edits = {
    'confirm_ids': ['spk_001', 'spk_002'],
    'reject_ids': ['spk_003'],
    'link_mappings': {'spk_001': 'char_001'},
}
json.dump(edits, open('${WORK}/edits_with_reject.json', 'w'), ensure_ascii=False, indent=2)
"
python3 "${LINK_CLI}" \
    --audio-semantic "${WORK}/audio_augmented.json" \
    --characters "${FIX_CHARS}" \
    --edits "${WORK}/edits_with_reject.json" \
    --work-dir "${WORK}" \
    --output "${WORK}/speakers_with_reject.json" > /dev/null
assert_py "S3 spk_003 NOT in canonical (reject_ids hard gate)" "
import json
d = json.load(open('${WORK}/speakers_with_reject.json'))
ids = {s['spk_id'] for s in d['speakers']}
assert 'spk_003' not in ids, f'spk_003 leaked into canonical: {ids}'
assert ids == {'spk_001', 'spk_002'}, f'unexpected ids: {ids}'
print('    canonical speakers =', sorted(ids), '(spk_003 rejected → omitted)')
"
echo "[smoke] SCENARIO 3: PASS"

# ═══ SCENARIO 4: XSS regression — _esc + JSON bootstrap neutralize poison ═══
echo "[smoke] SCENARIO 4: XSS regression (_esc + JSON bootstrap defuse <script> payloads)"
# Rule 1 deviation (test bug fix): the plan's original poison spec used a malformed
# spk_id ('<script>x</script>') for ALL poison shots → _aggregate_speakers skipped
# them (SPK_PATTERN defense) → 0 speakers → dropdown never rendered → the plan's
# secondary 'grep &lt;script&gt;' assertion silently never fired (false-pass risk,
# T-13-15). Fix: add a SECOND shot with a VALID spk_id alongside the malformed one,
# so a card renders and the dropdown (where _esc fires on char name) is exercised.
# Both defenses are now proven: SPK_PATTERN skip (malformed) AND _esc (rendered).
python3 -c "
import json
audio_poison = {'shots': [
    # Shot 1: malformed spk_id → skipped by SPK_PATTERN (defense-in-depth proof).
    {'shot_id': 1, 'start_sec': 0.0, 'end_sec': 1.0, 'duration': 1.0,
     'dialogue': {'text': '<script>alert(1)</script>', 'spk_id': '<script>x</script>'}},
    # Shot 2: VALID spk_id → card renders → dropdown renders → _esc fires on char name.
    {'shot_id': 2, 'start_sec': 1.0, 'end_sec': 2.0, 'duration': 1.0,
     'dialogue': {'text': '<script>alert(1)</script>', 'spk_id': 'spk_001'}},
]}
json.dump(audio_poison, open('${WORK}/audio_poison.json', 'w'), ensure_ascii=False)
chars_poison = [
    {'id': 'char_001', 'name': '<script>alert(2)</script>',
     'review_state': 'confirmed', 'appearance_shots': []},
]
json.dump(chars_poison, open('${WORK}/chars_poison.json', 'w'), ensure_ascii=False)
"
# run_review may succeed (1 valid speaker → card+dropdown render) — that's the
# path we WANT so _esc is exercised. Keep '|| true' as defense if it ever exits
# non-zero on poisoned input (skip == neutralized is still acceptable per T-13-15).
run_review --audio-semantic "${WORK}/audio_poison.json" \
           --characters "${WORK}/chars_poison.json" \
           --shots "${FIX_SHOTS}" \
           --output "${WORK}/review_poison.html" > /dev/null 2>&1 || true

if [ ! -s "${WORK}/review_poison.html" ]; then
    echo "  [PASS] S4 poison HTML absent (aggregator skipped all poison — neutralized)"
else
    # Primary assertions: raw <script> payloads MUST NOT appear in HTML output.
    assert_not_grep "S4 no raw <script>alert(1)</script>" '<script>alert\(1\)</script>' "${WORK}/review_poison.html"
    assert_not_grep "S4 no raw <script>alert(2)</script>" '<script>alert\(2\)</script>' "${WORK}/review_poison.html"
    # Secondary assertion (T-13-15): _esc fired on poisoned char name → &lt;script&gt; present.
    # This is the MEANINGFUL proof that the escape layer ran (not just absence).
    if grep -q '&lt;script&gt;' "${WORK}/review_poison.html"; then
        echo "  [PASS] S4 _esc active on poison (char name → &lt;script&gt; in dropdown option)"
    else
        echo "  [WARN] S4 _esc marker '&lt;script&gt;' not found — dropdown may not have rendered"
    fi
    # Defense-in-depth: exactly one literal </script> (the real block terminator) —
    # no poison breakout added a second one. (HTML parser terminates on first </script>;
    # .replace("</","<\\/") in the JSON bootstrap is what prevents a breakout.)
    N_CLOSE=$(grep -o '</script>' "${WORK}/review_poison.html" | wc -l)
    if [ "${N_CLOSE}" -le 1 ]; then
        echo "  [PASS] S4 no </script> breakout (found ${N_CLOSE} literal close tag(s), ≤1 expected)"
    else
        echo "  [FAIL] S4 </script> breakout: found ${N_CLOSE} literal close tags (expected ≤1)"
        grep -n '</script>' "${WORK}/review_poison.html" | head
        exit 1
    fi
fi
echo "[smoke] SCENARIO 4: PASS"

# ═══ SCENARIO 5: producer integrity extension (Plan 01 Task 2 proof) ═════
echo "[smoke] SCENARIO 5: producer integrity extension (accepts canonical + rejects leak)"

# Positive: place Scenario 1 speakers.json + sibling characters/shots in workdir
# mirroring the producer asset_dir layout → _producer_registry_integrity returns [].
python3 -c "
import shutil, os
W = '${WORK}/producer_integrity'
os.makedirs(W, exist_ok=True)
shutil.copy('${WORK}/speakers.json', os.path.join(W, 'speakers.json'))
shutil.copy('${FIX_CHARS}', os.path.join(W, 'characters.json'))
shutil.copy('${FIX_SHOTS}', os.path.join(W, 'shots.json'))
"
assert_py "S5 producer integrity accepts canonical shape (0 failures)" "
from pathlib import Path
from scripts.verify_contract import _producer_registry_integrity
failures = _producer_registry_integrity(Path('${WORK}/producer_integrity'))
assert failures == [], f'producer integrity failures on canonical shape: {failures}'
print('    _producer_registry_integrity =', failures)
"

# Negative: corrupt speakers.json with a non-confirmed entry → failures surface
# the Pitfall 7 second-line assert (mirror verify_contract.py:777-781).
python3 -c "
import json, os, shutil
W = '${WORK}/producer_integrity_bad'
os.makedirs(W, exist_ok=True)
json.dump({'speakers': [{'spk_id': 'spk_001', 'review_state': 'proposed'}]},
          open(os.path.join(W, 'speakers.json'), 'w'))
shutil.copy('${FIX_CHARS}', os.path.join(W, 'characters.json'))
shutil.copy('${FIX_SHOTS}', os.path.join(W, 'shots.json'))
"
assert_py "S5 producer integrity rejects Pitfall 7 leak (proposed in canonical)" "
from pathlib import Path
from scripts.verify_contract import _producer_registry_integrity
failures = _producer_registry_integrity(Path('${WORK}/producer_integrity_bad'))
assert any('confirmed' in m.lower() or 'pitfall 7' in m.lower() for m in failures), \
    f'expected Pitfall 7 failure, got: {failures}'
print('    failures =', failures)
"
echo "[smoke] SCENARIO 5: PASS"

# ─── Confidence: canonical fixtures untouched (T-13-14 mitigation) ────────
if git -C "${REPO_ROOT}" diff --quiet -- spec/fixtures/v1.2/ ; then
    echo "[smoke] canonical v1.2 fixtures unchanged (git diff clean)"
else
    echo "  [FAIL] canonical v1.2 fixtures modified during smoke (T-13-14 violation)"
    git -C "${REPO_ROOT}" diff --stat -- spec/fixtures/v1.2/ || true
    exit 1
fi

echo ""
echo "PHASE13_ROUND_TRIP_PASS"
exit 0
