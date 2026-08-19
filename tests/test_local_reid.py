"""local_reid 纯函数测试 —— 不触网（GLM 检测段不在覆盖内）。

覆盖：
  * frame_to_shot：frames_5fps 文件名 → (shot_id, 帧号) 边界归属。
  * conform_draft：富聚类 → schema 合规 draft + GLM 元数据 sidecar；
    tier 三档切分；draft 过 Draft202012Validator(registry.schema.json)。
"""
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "local_reid", REPO_ROOT / "analysis" / "local_reid.py")
lr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lr)

SHOTS = [
    {"id": 1, "start_sec": 0.0, "end_sec": 10.0, "duration": 10.0},
    {"id": 2, "start_sec": 10.0, "end_sec": 25.5, "duration": 15.5},
    {"id": 3, "start_sec": 25.5, "end_sec": 30.0, "duration": 4.5},
]


def test_frame_to_shot_boundaries():
    assert lr.frame_to_shot("f000000.jpg", SHOTS) == (1, 0)      # t=0 → 首镜
    assert lr.frame_to_shot("f000049.jpg", SHOTS) == (1, 49)     # t=9.8 仍在镜1
    assert lr.frame_to_shot("f000050.jpg", SHOTS) == (2, 50)     # t=10.0 边界归镜2
    assert lr.frame_to_shot("f000127.jpg", SHOTS) == (2, 127)    # t=25.4
    assert lr.frame_to_shot("f000999.jpg", SHOTS) == (3, 999)    # 越界兜底末镜


def rich_clusters():
    return [{
        "cluster_id": "char_001", "name": "角色1", "species": "拟人化生物",
        "appearance": "蓝色皮肤，尖耳朵", "review_state": "proposed",
        "mean_cosine": 0.87, "member_count": 2,
        "representative_image": "characters/char_001.png",
        "crops_dir": "characters/char_001/",
        "members": [{"frame": "f000010.jpg", "bbox": [0, 0, 100, 100], "cos_sim": 0.9},
                    {"frame": "f000060.jpg", "bbox": [10, 10, 90, 90], "cos_sim": 0.84}],
    }, {
        "cluster_id": "char_002", "name": "角色2", "species": "人类",
        "appearance": "绿衣", "review_state": "proposed",
        "mean_cosine": 0.70, "member_count": 1,
        "representative_image": "characters/char_002.png",
        "crops_dir": "characters/char_002/",
        "members": [{"frame": "f000100.jpg", "bbox": [0, 0, 50, 50], "cos_sim": 1.0}],
    }]


def test_conform_draft_schema_valid_and_tier():
    draft, meta = lr.conform_draft(rich_clusters(), SHOTS, 0.35)
    schema = json.loads(
        (REPO_ROOT / "spec" / "schemas" / "registry.schema.json").read_text("utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(draft))
    assert not errors, errors[:2]

    c1, c2 = draft["clusters"]
    assert c1["tier"] == "auto_distinct"        # 0.87 ≥ 0.85
    assert c2["tier"] == "review"               # 0.70 中带
    assert [m["shot_id"] for m in c1["members"]] == [1, 2]   # f10→镜1, f60→t12→镜2
    assert all(m["mask_quality"] == "unknown" for m in c1["members"])

    # sidecar 保住 GLM rich 字段
    assert meta["clusters"][0]["appearance"] == "蓝色皮肤，尖耳朵"
    assert meta["clusters"][0]["members"][0]["frame"] == "f000010.jpg"


def test_conform_draft_tier_auto_merge_low_cos():
    clusters = rich_clusters()
    clusters[0]["mean_cosine"] = 0.55
    draft, _ = lr.conform_draft(clusters, SHOTS, 0.35)
    assert draft["clusters"][0]["tier"] == "auto_merge"       # < 0.65
