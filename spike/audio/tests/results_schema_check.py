#!/usr/bin/env python3
"""逐个 model 校验 spike/audio/results/*.json 的形状（per Plan 10-01 Task 2）。

Wave 0 baseline：results/ 为空时 exit 0（无结果不算错）。
当 results/ 有内容时，每个文件按文件名前缀分派到对应 schema 校验函数；
任一文件不符合 → exit 1。

文件命名约定（来自 common.py:write_result）：
    ser_sensevoice_<fixture>.json   — SenseVoice SER spike
    mir_mert_<fixture>.json         — MERT-v1-95M MIR spike
    mir_panns_<fixture>.json        — PANNs Cnn14 MIR spike
    whisperx_align_<fixture>.json   — WhisperX word-align drift spike
    diarize_<fixture>.json          — optional pyannote diarization spike

每个 model 的 schema 来自 Plan 10-01 Task 2 §results_schema_check.py 列表。
mir_mert_* / mir_panns_* 用**完全相同**的 per-sample entry shape
（per Plan 10-04 Task 2 "uniform slice"）—— 只在顶层 ``checkpoint`` 字段值不同。
"""
import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def _err(msg: str) -> None:
    print(f"[smoke:schema] FAIL {msg}", file=sys.stderr)


def _check_common(d: dict, fname: str, required_top: list) -> bool:
    """通用顶层字段检查。"""
    ok = True
    for k, expected_type in required_top:
        if k not in d:
            _err(f"{fname}: missing top-level field {k!r}")
            ok = False
            continue
        v = d[k]
        # 简单类型断言：str/int/float/list/dict
        if expected_type is int and (not isinstance(v, int) or isinstance(v, bool)):
            _err(f"{fname}: field {k!r} must be int, got {type(v).__name__}")
            ok = False
        elif expected_type is str and not isinstance(v, str):
            _err(f"{fname}: field {k!r} must be str, got {type(v).__name__}")
            ok = False
        elif expected_type is float and not isinstance(v, (int, float)):
            _err(f"{fname}: field {k!r} must be number, got {type(v).__name__}")
            ok = False
        elif expected_type is list and not isinstance(v, list):
            _err(f"{fname}: field {k!r} must be list, got {type(v).__name__}")
            ok = False
        elif expected_type is dict and not isinstance(v, dict):
            _err(f"{fname}: field {k!r} must be dict, got {type(v).__name__}")
            ok = False
    return ok


def _check_ser_sensevoice(d: dict, fname: str) -> bool:
    """ser_sensevoice_*.json: model/fixture/sample_size>=1/per_sample/methodology/caveat."""
    ok = _check_common(d, fname, [
        ("model", str), ("fixture", str), ("sample_size", int),
        ("per_sample", list), ("methodology", str), ("caveat", str),
    ])
    if ok and d["sample_size"] < 1:
        _err(f"{fname}: sample_size must be >=1, got {d['sample_size']}")
        ok = False
    if ok and not d["caveat"].strip():
        _err(f"{fname}: caveat must be non-empty (AF-02/AF-03 anti-fabrication)")
        ok = False
    if ok:
        for i, entry in enumerate(d["per_sample"]):
            for req in ("shot_id", "start_sec", "end_sec", "predicted_emotion"):
                if req not in entry:
                    _err(f"{fname}: per_sample[{i}] missing {req!r}")
                    ok = False
                    break
    return ok


def _check_mir(d: dict, fname: str) -> bool:
    """mir_mert_*.json + mir_panns_*.json — UNIFORM per_sample entry shape."""
    ok = _check_common(d, fname, [
        ("model", str), ("fixture", str), ("sample_size", int),
        ("per_sample", list), ("checkpoint", str), ("methodology", str),
        ("caveat", str),
    ])
    if ok and d["sample_size"] < 1:
        _err(f"{fname}: sample_size must be >=1, got {d['sample_size']}")
        ok = False
    if ok:
        for i, entry in enumerate(d["per_sample"]):
            if not isinstance(entry, dict):
                _err(f"{fname}: per_sample[{i}] must be dict")
                ok = False
                continue
            if "shot_id" not in entry or not isinstance(entry.get("shot_id"), int):
                _err(f"{fname}: per_sample[{i}].shot_id must be int")
                ok = False
            if "predicted_instruments" not in entry or not isinstance(
                entry.get("predicted_instruments"), list
            ):
                _err(f"{fname}: per_sample[{i}].predicted_instruments must be list")
                ok = False
            if "metric_per_sample" not in entry or not isinstance(
                entry.get("metric_per_sample"), (int, float)
            ):
                _err(f"{fname}: per_sample[{i}].metric_per_sample must be number")
                ok = False
    return ok


def _check_whisperx_align(d: dict, fname: str) -> bool:
    """whisperx_align_*.json: sample_size>=30, drift_stats{pct_under_200_ms,mean_drift_ms}."""
    ok = _check_common(d, fname, [
        ("model", str), ("fixture", str), ("sample_size", int),
        ("per_sample", list), ("drift_stats", dict), ("methodology", str),
        ("caveat", str),
    ])
    if ok and d["sample_size"] < 30:
        _err(f"{fname}: sample_size must be >=30 (stratified n=30 invariant), got {d['sample_size']}")
        ok = False
    if ok:
        ds = d["drift_stats"]
        for k in ("pct_under_200_ms", "mean_drift_ms"):
            if k not in ds or not isinstance(ds[k], (int, float)):
                _err(f"{fname}: drift_stats.{k} must be number")
                ok = False
    return ok


def _check_diarize(d: dict, fname: str) -> bool:
    """diarize_*.json (optional): DER float + per_sample list."""
    return _check_common(d, fname, [
        ("model", str), ("fixture", str), ("DER", float),
        ("per_sample", list), ("methodology", str), ("caveat", str),
    ])


DISPATCH = {
    "ser_sensevoice_": _check_ser_sensevoice,
    "mir_mert_": _check_mir,
    "mir_panns_": _check_mir,
    "whisperx_align_": _check_whisperx_align,
    "diarize_": _check_diarize,
}


def main() -> int:
    if not RESULTS_DIR.exists():
        print(f"[smoke:schema] {RESULTS_DIR} does not exist — Wave 0 baseline, exit 0")
        return 0
    files = sorted(RESULTS_DIR.glob("*.json"))
    if not files:
        print(f"[smoke:schema] {RESULTS_DIR} empty — Wave 0 baseline, exit 0")
        return 0

    failures = 0
    for fp in files:
        fname = fp.name
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001  spike 容错
            _err(f"{fname}: cannot parse JSON ({e})")
            failures += 1
            continue
        checker = next(
            (fn for prefix, fn in DISPATCH.items() if fname.startswith(prefix)),
            None,
        )
        if checker is None:
            _err(f"{fname}: unknown result-file prefix (expected one of "
                 f"{sorted(DISPATCH.keys())})")
            failures += 1
            continue
        if not checker(d, fname):
            failures += 1
            continue
        print(f"[smoke:schema] {fname}: OK")

    if failures:
        print(f"[smoke:schema] {failures} file(s) failed schema check")
        return 1
    print(f"[smoke:schema] all {len(files)} result file(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
