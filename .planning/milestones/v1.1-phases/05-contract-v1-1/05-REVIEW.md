---
phase: 05-contract-v1-1
reviewed: 2026-07-24T00:00:00Z
depth: deep
files_reviewed: 3
files_reviewed_list:
  - scripts/verify_contract.py
  - scripts/export_asset.py
  - spec/validate.py
findings:
  blocker: 0
  warning: 4
  info: 4
  total: 8
status: findings
---

# Phase 5: Code Review Report

**Reviewed:** 2026-07-24
**Depth:** deep (cross-file: schemas + fixtures diffed against v1.0 tag to verify strip logic)
**Files Reviewed:** 3
**Status:** findings

## Summary

Phase 5 extends the regression harness (`verify_contract.py`) from 6-shape producer
validation to a 9-shape v1.1 world, adds two contract-level cross-checks
(`_cross_version_check`, `_fixture_consistency_check`), a v1-schema-recovery helper
(`_recover_v1_schema`), bumps the producer `SCHEMA_VERSION` constant to `"1.1"`, and
wires a `validate_v11()` pass into `spec/validate.py`.

**Empirically verified GREEN (per task brief, re-confirmed during review):**
- `EIGHT_SHAPES` rename leaves `run_self_test`'s fail-loud path intact — self-test
  iterates `manifest_copy.get("data", {}).items()` and calls `validate_asset_json`
  (asset-shape only); neither path references the renamed constant. Fail-loud still
  fires on `schema_version='v1'` injection.
- `_recover_v1_schema` programmatic-strip fallback is **structurally correct** for the
  current additive keys. Diffing `git show v1.0:spec/schemas/{asset,prompts}.schema.json`
  against HEAD confirms the ONLY v1.0→v1.1 structural deltas are exactly the 4 keys
  the strip removes (`data.{characters,props}`, `media.{characters,props}`) for asset
  and the 2 keys for prompts (`items.properties.{character_refs,prop_refs}`). No
  `required[]` changes, no `$defs` changes. The strip produces an equivalent of v1.0.
- `validate_eight_shapes` correctly skips `registry.draft.json` when absent (v1.0
  producer) and validates it when present, with `JSONDecodeError` handled.
- `validate.py` `validate_v11()` handles `FileNotFoundError` + `JSONDecodeError` per
  existing pattern and is correctly wired into the exit-code gate.

**Concerns found** are all in the new contract-level check helpers and center on
**false-negative coverage gaps** (the harness can silently pass on broken/missing
fixtures) and **inconsistent error handling** (raw tracebacks escape the structured
`(bool, str)` return contract). No bugs in the producer emit path or self-test path.

---

## Warnings

### WR-01: `_fixture_consistency_check` silently reports "0 dangling" when v1.1 fixture set is missing

**File:** `scripts/verify_contract.py:397-454`
**Issue:** The `_load() or []` pattern returns an empty list when a fixture file is
absent. If the entire `spec/fixtures/v1.1/` directory is missing (or every file
except `shots.json` is removed), every iteration loop is empty, `registry` is `None`,
no failures are appended, and the function returns:
`(True, "v1.1 fixture set cross-file IDs consistent (0 dangling)")`.

This is a **direct false-negative hole** in the regression net — the exact scenario
the check is meant to catch (broken/missing shipped fixtures) is the one scenario
that silently passes. Verified empirically:

```python
v11 = Path('/tmp/does-not-exist-v11')
chars = _load('characters.json') or []   # []
props = _load('props.json') or []        # []
shots = _load('shots.json') or []        # []
# all loops empty → returns (True, "...consistent (0 dangling)")
```

`spec/validate.py::validate_v11()` does catch this (it explicitly prints
`[FAIL-v11] <shape>: fixture missing`), but `verify_contract.py` is documented as a
standalone cross-repo regression harness that must NOT subprocess to `spec/validate.py`
(see the docstring at line 191-192) — so defense-in-depth does not apply here.

**Fix:** Add an upfront existence guard at the top of `_fixture_consistency_check`:

```python
expected = ("characters.json", "props.json", "shots.json",
            "prompts.json", "registry.draft.json")
missing = [n for n in expected if not (v11 / n).is_file()]
if missing:
    return (
        False,
        f"v1.1 fixture set incomplete; missing: {missing} "
        f"(expected at {v11})",
    )
```

### WR-02: `_fixture_consistency_check` does not validate `looks[].appearance_shots[]` / `states[].appearance_shots[]`

**File:** `scripts/verify_contract.py:425-432`
**Issue:** The docstring at line 386 states the invariant
"`characters/props.appearance_shots[] ⊆ shots[].id`", and the implementation only
iterates the **top-level** `appearance_shots` of each character/prop. But
`characters.schema.json` (`$defs.look`) and `props.schema.json` (`$defs.state`) both
define a **nested** `appearance_shots[]` inside `looks[]` / `states[]`, and the
shipped v1.1 fixtures exercise them (e.g., `char_001.looks[1].appearance_shots=[2]`,
`prop_001.states[0].appearance_shots=[2]`).

The schema comment for the nested field says it is "the basis for Phase 8 prompt-ref
attachment" — a dangling ref here would cause real Phase 8 bugs that this check is
specifically designed to prevent. The check currently cannot catch them.

**Fix:** Extend the iteration to cover nested arrays:

```python
for c in chars:
    for sid in c.get("appearance_shots", []):
        if sid not in shot_ids:
            failures.append(f"character {c.get('id')} appearance_shots unknown shot {sid}")
    for look in c.get("looks", []):
        for sid in look.get("appearance_shots", []):
            if sid not in shot_ids:
                failures.append(
                    f"character {c.get('id')} look {look.get('label')!r} "
                    f"appearance_shots unknown shot {sid}"
                )
# analogous loop for props.states[]
```

### WR-03: `_cross_version_check` file reads are not wrapped — missing fixture escapes as raw traceback

**File:** `scripts/verify_contract.py:342-343, 360`
**Issue:** Both the forward and backward iterations read fixtures without `try/except`:

```python
schema = json.loads((SCHEMAS_DIR / f"{shape}.schema.json").read_text(encoding="utf-8"))
instance = json.loads((minimal_dir / f"{shape}.json").read_text(encoding="utf-8"))
...
instance = json.loads((v11_dir / f"{shape}.json").read_text(encoding="utf-8"))
```

If any of these files is missing (e.g., someone renames `v1.1/asset.json` →
`v1.1/manifest.json` during a refactor, or the v1.1 dir is removed in a future
rollback), `FileNotFoundError` propagates out of `_cross_version_check`, escapes
`run_producer_check`'s structured `return (False, reason)` contract, and surfaces
as a raw Python traceback — bypassing the `[producer] FAIL: <reason>` summary line
that downstream CI wrappers parse.

This is inconsistent with the surrounding pattern: `validate_eight_shapes`
(lines 238-263) wraps each fixture load in `try/except FileNotFoundError` +
`try/except JSONDecodeError`, and `_recover_v1_schema` (lines 295-305) wraps its
`git show` and file reads.

**Fix:** Either wrap each load in `try/except (FileNotFoundError, json.JSONDecodeError)`
appending to `failures` (matching `validate_eight_shapes`), or add a single
existence pre-check at the top of `_cross_version_check`:

```python
required = (
    [(minimal_dir, n) for n in (f"{s}.json" for s in SIX_SHAPES)]
    + [(v11_dir, "asset.json"), (v11_dir, "prompts.json")]
)
missing = [str(p / n) for p, n in required if not (p / n).is_file()]
if missing:
    return (False, "cross-version fixtures missing: " + ", ".join(missing))
```

### WR-04: `_fixture_consistency_check` crashes (AttributeError/TypeError) if a fixture is valid JSON but not a list

**File:** `scripts/verify_contract.py:397-407, 413, 425, 429`
**Issue:** The `_load() or []` fallback only substitutes for `None` (file absent).
If a fixture file exists and parses as valid JSON but is **not an array** — e.g.,
`characters.json` contains `{"foo": 1}` (object), `"string"`, or `42` — the loaded
value flows directly into `for c in chars: c.get(...)` with no type guard.

Verified empirically:
```
chars = {'foo': 1}   # non-empty dict is truthy, so `or []` is skipped
for c in chars:      # iterates dict KEYS (strings)
  c.get('id')        # → AttributeError: 'str' object has no attribute 'get'
```

For `shots = 42` (JSON number), `for s in shots` raises `TypeError: 'int' object
is not iterable`. Either case escapes `run_producer_check`'s structured contract
as a raw traceback, exactly like WR-03.

The schemas for these files all mandate `"type": "array"` at the root, so a
non-array fixture is necessarily schema-invalid — but as established in WR-01,
`verify_contract.py` does not run schema validation on the v1.1 fixtures
(only `spec/validate.py` does, which is deliberately not subprocess-invoked).

**Fix:** Add a list-type assertion immediately after loading:

```python
def _load_list(name):
    v = _load(name)
    if v is None:
        return None
    if not isinstance(v, list):
        return ["__TYPE_ERROR__", type(v).__name__, v]
    return v

chars = _load_list("characters.json")
if chars is None:
    return (False, f"v1.1 fixture missing: characters.json")
if chars and isinstance(chars[0], str) and chars[0] == "__TYPE_ERROR__":
    return (False, f"characters.json must be a JSON array, got {chars[1]}")
```

(Or more simply: assert `isinstance(chars, list)` and append a failure on mismatch
rather than crashing.)

---

## Info

### IN-01: `export_asset.py` docstring stale after SCHEMA_VERSION bump to "1.1"

**File:** `scripts/export_asset.py:12-13, 139`
**Issue:** The module docstring at lines 12-13 still says `schema_version="1"`,
and the `build_asset_dict` docstring at line 139 says
`schema_version: 字面量 "1"（spec/fixtures/minimal/asset.json 一致）`.
After Phase 5 the constant emits `"1.1"`, while `spec/fixtures/minimal/asset.json`
(correctly) remains `"1"` (it's the v1.0 minimal fixture). The claim of consistency
between producer emit and the minimal fixture is now doubly wrong.

Future maintainers reading the docstring will be misled about both the emitted
value and the relationship to the minimal fixture.

**Fix:**
- Line 12-13: change `schema_version="1"` → `schema_version="1.1"`.
- Line 139: change to `schema_version: SCHEMA_VERSION 常量（当前 "1.1"；
  spec/fixtures/minimal/asset.json 仍为 "1" —— minimal 是 v1.0 baseline fixture，
  producer emit 已 bump 到 v1.1，两者刻意不同）`.

### IN-02: `verify_contract.py::run_self_test` docstring stale re: injected value

**File:** `scripts/verify_contract.py:598`
**Issue:** The docstring says `把 schema_version 从 '1' 改为 'v1'`. Since the
producer now emits `"1.1"`, the self-test actually overwrites `"1.1"` → `"v1"`.
The behavior is correct (the injected value `"v1"` still violates the pattern
`^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$` and is rejected), but the docstring no longer
matches the runtime value.

**Fix:** Change line 598 to `把 schema_version 从 '1.1' 改为 'v1'`.

### IN-03: `_recover_v1_schema` programmatic strip is brittle to future schema growth (masked by `git show v1.0` primary)

**File:** `scripts/verify_contract.py:298-316`
**Issue:** The fallback strip explicitly enumerates v1.1 additive keys for `asset`
and `prompts` only. If a later phase adds another additive key to one of these
schemas (e.g., `data.properties.scenes` in Phase 6), the strip will silently
produce an "impure" v1 schema that still contains the new key. The backward
cross-version check would then validate the v1.1 fixture against this impure
schema and (correctly) not flag the new key as additionalProperties — giving a
false sense of "no drift" when in fact the recovered schema is not v1.

This is currently masked because the primary path (`git show v1.0:...`) succeeds
on this repo (v1.0 tag exists) and the fallback never runs. But on a shallow
clone, in CI without the tag, or after a future `git tag -d v1.0`, the fallback
silently degrades.

**Fix (one of):**
- Add a comment making the maintenance contract explicit: "If you add additive
  keys to asset/prompts schemas in a future phase, extend the strip here."
- Or: assert the strip produced the same result as `git show v1.0` when both
  paths are available, so drift between the two paths is caught at test time.

### IN-04: `_fixture_consistency_check` registry cluster membership ignores `review_state` — would flag legitimately rejected clusters

**File:** `scripts/verify_contract.py:434-442`
**Issue:** The check `elif cid not in (char_ids | prop_ids)` requires every
registry `cluster_id` to appear in `characters.json` or `props.json`. But per
`registry.schema.json`'s `$comment`, `review_state` may be `"rejected"` — and
rejected clusters intentionally do NOT flow to the canonical registries
(`characters.schema.json` explicitly says rejected = soft-deleted to preserve
referential integrity; the ID is kept in registry but not in characters.json).

The shipped v1.1 fixture happens to model the all-confirmed happy path (every
registry cluster has a matching characters/props entry), so this passes today.
But if a future fixture models the rejection path (legitimate per schema), the
check produces a false positive.

**Fix:** Gate the membership check on `review_state != "rejected"`:

```python
for cl in registry.get("clusters", []):
    cid = cl.get("cluster_id")
    if not (isinstance(cid, str) and re.match(r"^(char|prop)_[0-9]{3}$", cid)):
        failures.append(f"registry cluster_id malformed: {cid!r}")
        continue
    if cl.get("review_state") == "rejected":
        continue  # rejected clusters intentionally absent from canonical registries
    if cid not in (char_ids | prop_ids):
        failures.append(f"registry cluster_id {cid} not in characters+props IDs")
```

---

## Notes on items explicitly cleared by the review

- **`run_self_test` fail-loud path is intact.** The `EIGHT_SHAPES`/`SIX_SHAPES`
  rename has no call-site in `run_self_test`; it iterates `manifest_copy["data"]`
  directly and validates via `validate_asset_json` (asset-shape only). Injecting
  `schema_version="v1"` still triggers pattern rejection. Confirmed both by reading
  and by the user's empirical `PHASE4_SELF_TEST=1` green run.
- **`validate_eight_shapes` registry branch.** Correctly degrades when
  `registry.draft.json` is absent (v1.0 producer) and validates when present,
  with `JSONDecodeError` caught and reported as a failure rather than crashing.
- **`_recover_v1_schema` strip correctness.** Verified by `diff <(git show
  v1.0:spec/schemas/...) spec/schemas/...` — the strip removes exactly the
  additive keys and nothing else. No `required[]` or `$defs` deltas exist between
  v1.0 and v1.1 for `asset`/`prompts`.
- **`export_asset.py` `SCHEMA_VERSION` constant.** Correctly placed as a module
  singleton, referenced via `SCHEMA_VERSION` in `build_asset_dict`, and the
  emitted `"1.1"` satisfies `asset.schema.json`'s
  `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$` pattern. The pre-write `validate_asset_json`
  call catches any future value that drifts out of pattern.
- **`spec/validate.py::validate_v11()`.** Mirrors `validate_minimal()` structure
  exactly (FileNotFoundError + JSONDecodeError handling, sorted iter_errors,
  exit-code gating). Clean.

## REVIEW COMPLETE

**Status: findings** — 0 BLOCKER, 4 WARNING, 4 INFO.

No blockers; the producer emit path, self-test fail-loud path, and schema
correctness are all sound. The 4 WARNINGs are real false-negative / robustness
gaps in the newly-added contract-level check helpers (`_fixture_consistency_check`
and `_cross_version_check`) that should be addressed before this harness is relied
on as the cross-repo regression net. The 4 INFOs are docstring drift + brittleness
caveats.
