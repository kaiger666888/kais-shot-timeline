"""ShotTimelineAsset 规范校验器。

用途:
  python3 spec/validate.py               # 校验 spec/fixtures/minimal/ 下的最小样例 + 对 output/ 下真实生产产物做 smoke 校验
  python3 spec/validate.py --strict-smoke # 同上,但 smoke 失败也会让退出码非零(用于 CI 严格模式)

行为:
  - 对 6 个 schema(shots / audio_analysis / transcript / frames / prompts / asset)
    各跑一次 Draft202012Validator 校验,每条打印 [valid] 或 [FAIL]。
  - minimal 样例必须 6 条全部 [valid] 才算通过(决定退出码)。
  - smoke 阶段:自动在仓库根的 output/ 下查找第一个含 shots.json 的子目录,
    对其中 5 个数据 JSON 做宽容校验,打印 [smoke-valid] / [smoke-FAIL]。
    smoke 失败默认不影响退出码(生产端可能有 schema 之外的额外字段,
    这是 Phase 2 导出器需要清理的有用反馈);加 --strict-smoke 后才计入退出码。

依赖:仅标准库 + jsonschema(系统已装 4.26.0)。无 pip install 步骤。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from jsonschema import Draft202012Validator


# === 路径常量 ============================================================
SPEC_DIR = Path(__file__).parent.resolve()
SCHEMAS_DIR = SPEC_DIR / "schemas"
FIXTURE_DIR = SPEC_DIR / "fixtures" / "minimal"
REPO_ROOT = SPEC_DIR.parent

# 6 个 schema 与对应 fixture 文件名(同名约定)
SHAPE_TO_FIXTURE = {
    "shots": "shots.json",
    "audio_analysis": "audio_analysis.json",
    "transcript": "transcript.json",
    "frames": "frames.json",
    "prompts": "prompts.json",
    "asset": "asset.json",
}

# minimal 校验的固定顺序(asset 先,5 个数据形状随后)
MINIMAL_ORDER = ["asset", "shots", "audio_analysis", "transcript", "frames", "prompts"]

# smoke 阶段只校验 5 个数据形状(asset.json 由 Phase 2 导出器生成,真实生产目录里没有)
SMOKE_SHAPES = ["shots", "audio_analysis", "transcript", "frames", "prompts"]

# v1.1 fixture set (Phase 5 additive + Phase 7 additive) —— 10 shapes. minimal 仍 gate 退出码
# (CONTRACT-09);v1.1 失败也计入退出码(v1.1 fixture 必须 schema-valid)。registry fixture 文件名
# 是 registry.draft.json (pipeline-internal canonical 名);registry-edits fixture 文件名是
# registry.edits.json (HITL review round-trip canonical 名 —— Plan 07-01 新增)。
V11_FIXTURE_DIR = SPEC_DIR / "fixtures" / "v1.1"
V11_FIXTURE_MAP = {
    "asset": "asset.json",
    "shots": "shots.json",
    "audio_analysis": "audio_analysis.json",
    "transcript": "transcript.json",
    "frames": "frames.json",
    "prompts": "prompts.json",
    "characters": "characters.json",
    "props": "props.json",
    "registry": "registry.draft.json",
    "registry-edits": "registry.edits.json",
}
V11_ORDER = [
    "asset", "shots", "audio_analysis", "transcript", "frames", "prompts",
    "characters", "props", "registry", "registry-edits",
]

# v1.2 fixture set (Phase 11 additive) —— 12 shapes. minimal + v1.1 + v1.2 三阶 gate。
# 复用 v1.1 的 10 个 substrate 文件名（asset/shots/audio_analysis/transcript/frames/
# prompts/characters/props/registry/registry-edits）+ 新增 audio_semantic/speakers。
# speaker-edits 推迟到 Phase 13（HITL 流程落地才有 fixture）。
V12_FIXTURE_DIR = SPEC_DIR / "fixtures" / "v1.2"
V12_FIXTURE_MAP = {
    # 10 v1.1 entries verbatim (v1.2 fixture reuses the same substrate filenames):
    "asset": "asset.json",
    "shots": "shots.json",
    "audio_analysis": "audio_analysis.json",
    "transcript": "transcript.json",
    "frames": "frames.json",
    "prompts": "prompts.json",
    "characters": "characters.json",
    "props": "props.json",
    "registry": "registry.draft.json",
    "registry-edits": "registry.edits.json",
    # 2 NEW v1.2 shapes:
    "audio_semantic": "audio_semantic.json",
    "speakers": "speakers.json",
}
V12_ORDER = [
    "asset", "shots", "audio_analysis", "transcript", "frames", "prompts",
    "characters", "props", "registry", "registry-edits",
    "audio_semantic", "speakers",
]


def load_validator(shape: str) -> Draft202012Validator:
    """根据形状名加载对应的 Draft202012Validator。"""
    schema_path = SCHEMAS_DIR / f"{shape}.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    return Draft202012Validator(schema)


def _format_errors(errors: list) -> str:
    """把 jsonschema 错误列表格式化为简短多行字符串。"""
    lines = []
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        lines.append(f"    at {loc}: {err.message}")
    return "\n".join(lines)


def validate_minimal() -> int:
    """对 spec/fixtures/minimal/ 下的 6 个 JSON 跑 schema 校验,返回失败数。"""
    failures = 0
    for shape in MINIMAL_ORDER:
        fixture_path = FIXTURE_DIR / SHAPE_TO_FIXTURE[shape]
        try:
            with open(fixture_path, encoding="utf-8") as f:
                instance = json.load(f)
        except FileNotFoundError:
            print(f"[FAIL] {shape}: fixture missing at {fixture_path}")
            failures += 1
            continue
        except json.JSONDecodeError as e:
            print(f"[FAIL] {shape}: invalid JSON in fixture: {e}")
            failures += 1
            continue

        validator = load_validator(shape)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
        if errors:
            print(f"[FAIL] {shape}: {len(errors)} error(s)")
            print(_format_errors(errors))
            failures += 1
        else:
            print(f"[valid] {shape}")
    return failures


def validate_v11() -> int:
    """对 spec/fixtures/v1.1/ 下的 10 个 v1.1 fixture 跑 schema 校验,返回失败数。

    v1.1 fixture set(Phase 5 + Phase 7)= minimal 的 6 形状(复用 substrate)
    + characters/props/registry 三个 Phase 5 新形状 + registry-edits 一个 Phase 7
    新形状(HITL review round-trip canonical 名)。registry fixture 文件名是
    registry.draft.json(pipeline-internal canonical 名)。复用 load_validator
    + _format_errors,不复制。
    """
    failures = 0
    for shape in V11_ORDER:
        fixture_path = V11_FIXTURE_DIR / V11_FIXTURE_MAP[shape]
        try:
            with open(fixture_path, encoding="utf-8") as f:
                instance = json.load(f)
        except FileNotFoundError:
            print(f"[FAIL-v11] {shape}: fixture missing at {fixture_path}")
            failures += 1
            continue
        except json.JSONDecodeError as e:
            print(f"[FAIL-v11] {shape}: invalid JSON in fixture: {e}")
            failures += 1
            continue

        validator = load_validator(shape)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
        if errors:
            print(f"[FAIL-v11] {shape}: {len(errors)} error(s)")
            print(_format_errors(errors))
            failures += 1
        else:
            print(f"[valid-v11] {shape}")
    return failures


def validate_v12() -> int:
    """对 spec/fixtures/v1.2/ 下的 12 个 v1.2 fixture 跑 schema 校验,返回失败数。

    v1.2 fixture set(Phase 11)= v1.1 的 10 形状(byte-copied substrate)
    + audio_semantic/speakers 两个 Phase 11 新形状。asset.json 在 v1.2 中
    被编辑过(schema_version=1.2 + data.audio_semantic + data.speakers);
    其余 9 个 v1.1 substrate 文件 byte-identical。registry fixture 文件名
    仍是 registry.draft.json(pipeline canonical 名);registry-edits 仍是
    registry.edits.json。复用 load_validator + _format_errors,不复制。
    """
    failures = 0
    for shape in V12_ORDER:
        fixture_path = V12_FIXTURE_DIR / V12_FIXTURE_MAP[shape]
        try:
            with open(fixture_path, encoding="utf-8") as f:
                instance = json.load(f)
        except FileNotFoundError:
            print(f"[FAIL-v12] {shape}: fixture missing at {fixture_path}")
            failures += 1
            continue
        except json.JSONDecodeError as e:
            print(f"[FAIL-v12] {shape}: invalid JSON in fixture: {e}")
            failures += 1
            continue

        validator = load_validator(shape)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
        if errors:
            print(f"[FAIL-v12] {shape}: {len(errors)} error(s)")
            print(_format_errors(errors))
            failures += 1
        else:
            print(f"[valid-v12] {shape}")
    return failures


def discover_producer_fixture() -> Optional[Path]:
    """扫描 REPO_ROOT/output/,返回第一个含 shots.json 的子目录;没有则返回 None。"""
    output_root = REPO_ROOT / "output"
    if not output_root.is_dir():
        return None
    for child in sorted(output_root.iterdir()):
        if child.is_dir() and (child / "shots.json").is_file():
            return child
    return None


def validate_smoke(producer_dir: Path) -> int:
    """对真实生产产物跑 5 个数据形状的 schema 校验,返回失败数。

    失败默认不影响退出码(除非 --strict-smoke)。生产端可能 emit
    schema 之外的额外字段,strict schema 会拒绝——这正是 Phase 2
    导出器需要清理的有用反馈。
    """
    failures = 0
    for shape in SMOKE_SHAPES:
        producer_path = producer_dir / f"{shape}.json"
        if not producer_path.is_file():
            print(f"[smoke-FAIL] {shape}: producer file missing at {producer_path}")
            failures += 1
            continue
        try:
            with open(producer_path, encoding="utf-8") as f:
                instance = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[smoke-FAIL] {shape}: invalid JSON: {e}")
            failures += 1
            continue

        validator = load_validator(shape)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
        if errors:
            print(f"[smoke-FAIL] {shape}: {len(errors)} error(s) (informational; producer pre-canonical)")
            print(_format_errors(errors))
            failures += 1
        else:
            print(f"[smoke-valid] {shape}")
    return failures


def main() -> None:
    """CLI 入口。"""
    ap = argparse.ArgumentParser(
        description="ShotTimelineAsset 规范校验器(对 minimal fixture + 真实生产产物做 schema 校验)"
    )
    ap.add_argument(
        "--strict-smoke",
        action="store_true",
        help="smoke 失败也计入退出码(默认 smoke 仅打印,不影响退出码)",
    )
    args = ap.parse_args()

    print(f"[validate] minimal fixture = {FIXTURE_DIR}")
    minimal_failures = validate_minimal()

    print(f"[validate] v1.1 fixture = {V11_FIXTURE_DIR}")
    v11_failures = validate_v11()

    print(f"[validate] v1.2 fixture = {V12_FIXTURE_DIR}")
    v12_failures = validate_v12()

    producer_dir = discover_producer_fixture()
    smoke_failures = 0
    if producer_dir is None:
        print("[validate] no producer fixture found under output/ — skipping smoke pass")
    else:
        print(f"[validate] producer fixture (smoke) = {producer_dir}")
        smoke_failures = validate_smoke(producer_dir)

    # 决定退出码:minimal 仍 gate(CONTRACT-09 回归),v1.1 + v1.2 失败也计入
    # (Plan 01 schemas 必须接受 Plan 03 fixtures —— 否则 contract 本身破裂;
    # Phase 11 v1.2 fixture 必须由 Plan 11-01 schemas 接受 —— 否则 v1.2 contract 破裂)。
    total_strict_failures = minimal_failures + v11_failures + v12_failures
    if args.strict_smoke:
        total_strict_failures += smoke_failures

    print()
    print(
        f"[validate] minimal failures={minimal_failures}, "
        f"v1.1 failures={v11_failures}, "
        f"v1.2 failures={v12_failures}, "
        f"smoke failures={smoke_failures} "
        f"(strict-smoke={'on' if args.strict_smoke else 'off'})"
    )
    if total_strict_failures == 0:
        print("[validate] OK")
        sys.exit(0)
    else:
        print("[validate] FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
