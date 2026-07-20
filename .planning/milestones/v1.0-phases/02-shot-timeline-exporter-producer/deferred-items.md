# Phase 02 Deferred Items

Out-of-scope discoveries logged during plan execution. These are pre-existing issues
unrelated to the current plan's changes — surfaced for future plans / housekeeping.

## [Logged 2026-07-20 — plan 02-02] spec/validate.py smoke fails on output/《小江湖》第03话…/

**Source:** Pre-existing test-fixture cleanup carried over from 02-01-SUMMARY "Test-Fixture
Cleanup Note". Not caused by 02-02 changes (02-02 only touched `scripts/serve.py` and added
`scripts/check_range.py`; neither touches any data JSON or spec/validate.py).

**Symptom:**
```
$ python3 spec/validate.py --strict-smoke
[smoke-FAIL] transcript: producer file missing at output/《小江湖》第03话…/transcript.json
[smoke-FAIL] frames: producer file missing at output/《小江湖》第03话…/frames.json
[validate] minimal failures=0, smoke failures=2 (strict-smoke=on)
[validate] FAIL
```

**Root cause:** A `--skip-detect --force` cascade during 02-01 Task 2 testing deleted
`transcript.json` and `frames.json` under ep03's work_dir. A background pipeline regen was
started to rebuild the cache but was interrupted (no `run_pipeline.py` process active as of
2026-07-20 22:00 UTC; `asset.json` is a 0-byte stub from a half-finished export). The
pre-existing `--force + --skip-detect` abort is documented in 02-01-SUMMARY as out-of-scope
for the exporter plan.

**Why not auto-fixed:** Plan 02-02's scope is `scripts/serve.py` FD-leak fix +
`scripts/check_range.py` Range-206 verifier. Re-running Whisper transcription for ep03
takes ~10min on GPU and is unrelated to either deliverable. The stable test target ep01
(all 5 data JSONs intact and schema-valid) was used for both task verifications instead.

**Suggested fix (future /gsd-quick):**
```bash
# Re-run ep03 with full pipeline (cached detection/separation; re-transcribe only)
python3 run_pipeline.py --video "/data/home/kai/下载/bilibili_xiaojianghu/《小江湖》第03话：白头发的少女（画面只是工具，情绪才是目的.mp4"
# Then verify
python3 spec/validate.py --strict-smoke  # expect 0 failures
```

**Affected requirement IDs:** None (EXPORT-01/02/03 verification evidence comes from ep01,
which is green for all 5 data shapes + asset.json schema).
