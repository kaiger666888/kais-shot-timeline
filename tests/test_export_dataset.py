"""export_dataset 测试 —— 独立 dataset 目录导出（RT-05 + DATASET-02，
22-02 Task 2，零网络零 GPU，tmp_path 合成 work_dir）。

覆盖（九断言组，mirror test_judge.py tmp fixture 风格）：
  * 目录/文件名布局：dataset/<video-stem>/shot_NNN/{first_frame.jpg,
    last_frame.jpg,prompt.json} + manifest.json + accepted.txt/rejected.txt；
    --dataset-root 缺省 → work_dir.parent/"dataset"。
  * prompt.json 自含字段集：timing + prompt_text + 六 facet + refs（缺席空
    列表）+ scores 整块 + attribution 冗余直取 + regen 四字段（无 path——
    消费端独立性）。
  * manifest 分桶：accepted/rejected 计数 + rejected_buckets（faithful_below_tau/
    diverged/underspecified，从冻结 verdict+scores 直接统计）+ tau_sim/引擎版本
    /shots 索引。
  * 两 txt 行格式：accepted.txt 每行 shot_NNN；rejected.txt 每行
    `shot_NNN sim={:.4f} {attribution} {reason 前 80 字符}`。
  * 直拷路径命中：route_cache/h3_regen/frames/ 假帧字节 == dataset 帧字节
    （copy2 直拷非 symlink）。
  * 回落路径：cache 帧缺席 → h3s.extract_endpoint_frames 被调（monkeypatch
    记录）后改名落 dataset。
  * 消费端独立性：dataset 内全部 JSON 全文无 "asset.json"/"roundtrip/" 引用；
    帧为拷贝非 symlink。
  * 缺席 sidecar graceful：roundtrip.json 不在 → warning + 退出 0。
  * 幂等重建 prune：不在当前 accepted 集的陈旧 shot_NNN 目录被清（显式清单
    删自身目录）；dataset-root 下其它 video-stem 目录不碰。
"""
import importlib.util
import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "roundtrip_export_dataset", REPO_ROOT / "analysis" / "roundtrip" / "export_dataset.py")
em = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(em)

VCH = "a" * 16


# ── fixture ─────────────────────────────────────────────────────────────────

def _shot(sid, decision, sim, attribution, reason):
    return {
        "shot_id": sid,
        "regen": {
            "path": f"roundtrip/shot_{sid:03d}_regen.mp4",
            "video_content_hash": VCH,
            "engine_name": "comfyui-fl2va",
            "engine_version": "fl2va-int8/euler+simple/15/1344x768",
            "prompt_version": f"pv{sid}",
            "duration_sec": 5.0,
            "width": 1344,
            "height": 768,
        },
        "scores": {
            "midframe_sim": {"score": sim, "model": "siglip-so400m-patch14-384"},
            "judge": {"attribution": attribution, "confidence": 0.9,
                      "reason": reason},
        },
        "verdict": {"decision": decision, "source": "auto",
                    "decided_at": "2026-08-20T00:00:00"},
    }


LONG_REASON = "R" * 100


def make_work_dir(tmp_path, with_sidecar=True):
    """tmp 合成 work_dir：2 accepted（1/2）+ 2 rejected（5 faithful / 7 diverged）
    + 假帧 cache + prompts.json（六 facet 齐、无 refs——缺席空列表路径）。"""
    wd = tmp_path / "wd"
    wd.mkdir()
    if with_sidecar:
        payload = {"schema_version": em.h3s._load_schema_version(),
                   "shots": [_shot(1, "accepted", 0.97, "prompt_faithful", "ok1"),
                             _shot(2, "accepted", 0.98, "prompt_faithful", "ok2"),
                             _shot(5, "rejected", 0.9011, "prompt_faithful",
                                   LONG_REASON),
                             _shot(7, "rejected", 0.95, "model_diverged",
                                   "diverged reason")]}
        (wd / "roundtrip.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    frames = wd / "route_cache" / "h3_regen" / "frames"
    frames.mkdir(parents=True)
    for sid in (1, 2):
        (frames / f"kst_{VCH}_shot{sid:03d}_ff.jpg").write_bytes(
            f"FF-FAKE-{sid}".encode())
        (frames / f"kst_{VCH}_shot{sid:03d}_lf.jpg").write_bytes(
            f"LF-FAKE-{sid}".encode())
    prompts = []
    for sid in (1, 2, 5, 7):
        prompts.append({
            "shot_id": sid, "start_sec": sid * 10.0, "end_sec": sid * 10.0 + 3.0,
            "duration": 3.0,
            "subject": f"主体{sid}", "action": f"动作{sid}", "camera": "特写",
            "scene": "森林", "lighting": "暖光", "style": "3D 动画",
            "prompt_text": f"prompt text {sid}",
        })
    (wd / "prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    return wd


def run(wd, root):
    return em.main(["--work-dir", str(wd), "--dataset-root", str(root)])


# ── 1. 目录/文件名布局 ───────────────────────────────────────────────────────

def test_directory_layout(tmp_path):
    wd = make_work_dir(tmp_path)
    root = tmp_path / "ds"
    assert run(wd, root) == 0
    stem_dir = root / wd.name
    assert stem_dir.is_dir()
    for sid in (1, 2):
        d = stem_dir / f"shot_{sid:03d}"
        assert (d / "first_frame.jpg").is_file()
        assert (d / "last_frame.jpg").is_file()
        assert (d / "prompt.json").is_file()
    assert (stem_dir / "manifest.json").is_file()
    assert (stem_dir / "accepted.txt").is_file()
    assert (stem_dir / "rejected.txt").is_file()
    # rejected 镜不建目录（accepted 子集导出）
    assert not (stem_dir / "shot_005").exists()


def test_default_dataset_root_is_sibling_of_work_dir(tmp_path):
    wd = make_work_dir(tmp_path)
    assert em.main(["--work-dir", str(wd)]) == 0
    stem_dir = tmp_path / "dataset" / wd.name
    assert (stem_dir / "manifest.json").is_file()


# ── 2. prompt.json 自含字段集 ────────────────────────────────────────────────

def test_prompt_json_fields(tmp_path):
    wd = make_work_dir(tmp_path)
    root = tmp_path / "ds"
    run(wd, root)
    pj = json.loads((root / wd.name / "shot_001" / "prompt.json").read_text(
        encoding="utf-8"))
    for k in ("shot_id", "start_sec", "end_sec", "duration", "prompt_text",
              "subject", "action", "camera", "scene", "lighting", "style",
              "character_refs", "prop_refs", "scores", "attribution", "regen"):
        assert k in pj, k
    assert pj["prompt_text"] == "prompt text 1"
    assert pj["character_refs"] == [] and pj["prop_refs"] == []
    assert pj["attribution"] == "prompt_faithful"
    assert pj["scores"]["midframe_sim"]["score"] == 0.97
    for k in ("engine_name", "engine_version", "prompt_version",
              "video_content_hash"):
        assert k in pj["regen"], k
    assert "path" not in pj["regen"], "消费端独立性：regen.path 不进 dataset"


# ── 3. manifest 分桶 ─────────────────────────────────────────────────────────

def test_manifest_buckets(tmp_path):
    wd = make_work_dir(tmp_path)
    root = tmp_path / "ds"
    run(wd, root)
    m = json.loads((root / wd.name / "manifest.json").read_text(encoding="utf-8"))
    assert m["video_stem"] == wd.name
    assert m["tau_sim"] == 0.9670
    assert m["generated"]
    assert m["accepted_count"] == 2 and m["rejected_count"] == 2
    assert m["rejected_buckets"] == {"faithful_below_tau": 1, "diverged": 1,
                                     "underspecified": 0}
    assert m["engine_versions"] == ["fl2va-int8/euler+simple/15/1344x768"]
    assert m["shots"] == {"1": "shot_001", "2": "shot_002"}


# ── 4. 两 txt 行格式 ─────────────────────────────────────────────────────────

def test_txt_line_formats(tmp_path, capsys):
    wd = make_work_dir(tmp_path)
    root = tmp_path / "ds"
    run(wd, root)
    stem = root / wd.name
    acc = (stem / "accepted.txt").read_text(encoding="utf-8").strip().splitlines()
    assert acc == ["shot_001", "shot_002"]
    rej = (stem / "rejected.txt").read_text(encoding="utf-8").strip().splitlines()
    assert rej[0] == f"shot_005 sim=0.9011 prompt_faithful {LONG_REASON[:80]}"
    assert rej[1] == "shot_007 sim=0.9500 model_diverged diverged reason"
    # 前 80 字符截断（可 grep 可审计）
    assert "R" * 80 in rej[0] and "R" * 81 not in rej[0]


# ── 5. 直拷路径命中（假帧字节相等，非 symlink）──────────────────────────────

def test_direct_copy_from_frame_cache(tmp_path):
    wd = make_work_dir(tmp_path)
    root = tmp_path / "ds"
    run(wd, root)
    d = root / wd.name / "shot_001"
    src_ff = wd / "route_cache" / "h3_regen" / "frames" / f"kst_{VCH}_shot001_ff.jpg"
    assert (d / "first_frame.jpg").read_bytes() == src_ff.read_bytes()
    assert not (d / "first_frame.jpg").is_symlink()


# ── 6. 回落路径（cache 缺席 → extract_endpoint_frames）──────────────────────

def test_fallback_extraction_when_cache_miss(tmp_path, monkeypatch):
    wd = make_work_dir(tmp_path)
    # 删掉 shot 2 的 cache 帧制造 miss；放一个假源视频（resolve 只查存在性）
    for f in ("ff", "lf"):
        (wd / "route_cache" / "h3_regen" / "frames"
         / f"kst_{VCH}_shot002_{f}.jpg").unlink()
    (wd / "h264.mp4").write_bytes(b"fake-video")
    calls = []

    def fake_extract(src_video, shot, vch, frames_dir):
        calls.append((src_video, dict(shot), vch))
        ff = os.path.join(frames_dir, f"kst_{vch}_shot{shot['id']:03d}_ff.jpg")
        lf = os.path.join(frames_dir, f"kst_{vch}_shot{shot['id']:03d}_lf.jpg")
        with open(ff, "wb") as fh:
            fh.write(b"EXTRACT-FF")
        with open(lf, "wb") as fh:
            fh.write(b"EXTRACT-LF")
        return ff, lf

    monkeypatch.setattr(em.h3s, "extract_endpoint_frames", fake_extract)
    root = tmp_path / "ds"
    assert run(wd, root) == 0
    assert len(calls) == 1
    assert calls[0][1]["id"] == 2 and calls[0][2] == VCH
    d = root / wd.name / "shot_002"
    assert (d / "first_frame.jpg").read_bytes() == b"EXTRACT-FF"
    assert (d / "last_frame.jpg").read_bytes() == b"EXTRACT-LF"
    # 回落产物回填 cache（下轮直拷）
    assert (wd / "route_cache" / "h3_regen" / "frames"
            / f"kst_{VCH}_shot002_ff.jpg").exists()


# ── 7. 消费端独立性（零 asset.json / roundtrip/ 引用）──────────────────────

def test_consumer_independence(tmp_path):
    wd = make_work_dir(tmp_path)
    root = tmp_path / "ds"
    run(wd, root)
    for p in root.rglob("*.json"):
        text = p.read_text(encoding="utf-8")
        assert "asset.json" not in text, p
        assert "roundtrip/" not in text, p
    for p in root.rglob("*.jpg"):
        assert not p.is_symlink(), p


# ── 8. 缺席 sidecar graceful ─────────────────────────────────────────────────

def test_missing_sidecar_graceful(tmp_path, capsys):
    wd = make_work_dir(tmp_path, with_sidecar=False)
    rc = run(wd, tmp_path / "ds")
    assert rc == 0
    out = capsys.readouterr().out
    assert "[roundtrip-dataset]" in out and ("warning" in out or "跳过" in out)


# ── 9. 幂等重建 prune ────────────────────────────────────────────────────────

def test_stale_shot_dir_pruned_sibling_stem_untouched(tmp_path):
    wd = make_work_dir(tmp_path)
    root = tmp_path / "ds"
    run(wd, root)
    stem = root / wd.name
    stale = stem / "shot_009"
    stale.mkdir()
    (stale / "prompt.json").write_text("{}", encoding="utf-8")
    sibling = root / "另一支视频"
    sibling.mkdir(parents=True)
    (sibling / "manifest.json").write_text("{}", encoding="utf-8")
    assert run(wd, root) == 0
    assert not stale.exists(), "陈旧 shot 目录必须被清（显式清单删自身目录）"
    assert (sibling / "manifest.json").exists(), "兄弟 video-stem 目录绝不碰"
    # 当前 accepted 目录仍在
    assert (stem / "shot_001" / "prompt.json").is_file()


# ── 10. WR-01 回归锚：部分失败时索引只列实际导出的镜 ───────────────────────

def test_partial_failure_index_consistency(tmp_path, capsys):
    """WR-01（22-REVIEW）：accepted 镜降级跳过（prompts.json 缺条目）时，
    accepted.txt / manifest["shots"] 只列实际导出成功的镜——accepted_count ==
    len(shots) == accepted.txt 行数；skipped 镜单列 manifest.exported_skipped，
    绝不进索引（旧实现索引全 accepted 集，消费端迭代会撞缺席目录）。"""
    wd = make_work_dir(tmp_path)
    # 删掉 shot 2 的 prompts 条目 → 该镜本轮降级跳过（无目录可导出）
    prompts = json.loads((wd / "prompts.json").read_text(encoding="utf-8"))
    prompts = [p for p in prompts if p["shot_id"] != 2]
    (wd / "prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    root = tmp_path / "ds"
    assert run(wd, root) == 0
    stem = root / wd.name
    # 索引三一致：accepted_count == len(shots) == accepted.txt 行数 == 1
    acc = (stem / "accepted.txt").read_text(encoding="utf-8").strip().splitlines()
    m = json.loads((stem / "manifest.json").read_text(encoding="utf-8"))
    assert acc == ["shot_001"]
    assert m["shots"] == {"1": "shot_001"}
    assert m["accepted_count"] == 1
    assert m["accepted_count"] == len(m["shots"]) == len(acc)
    # skipped 镜单列 exported_skipped（可审计），不进任何索引
    assert m["exported_skipped"] == [2]
    assert "2" not in m["shots"] and "shot_002" not in acc
    # 被跳过镜无目录残留（本轮自建的半成品已清）
    assert not (stem / "shot_002").exists()
    # shot 1 导出完好不受牵连
    assert (stem / "shot_001" / "prompt.json").is_file()
    out = capsys.readouterr().out
    assert "shot 2" in out and "prompts.json 缺该镜条目" in out


def test_partial_failure_frame_degrade_index_consistency(tmp_path):
    """WR-01 帧降级路径：accepted 镜帧两级来源全失败（cache 缺席 + 无源视频）
    → 跳过镜不进 accepted.txt / shots 索引（第二类降级路径同口径）。"""
    wd = make_work_dir(tmp_path)
    # 删 shot 2 的 cache 帧 + 不放假源视频 → _ensure_endpoint_frames 降级返回 None
    for f in ("ff", "lf"):
        (wd / "route_cache" / "h3_regen" / "frames"
         / f"kst_{VCH}_shot002_{f}.jpg").unlink()
    root = tmp_path / "ds"
    assert run(wd, root) == 0
    stem = root / wd.name
    acc = (stem / "accepted.txt").read_text(encoding="utf-8").strip().splitlines()
    m = json.loads((stem / "manifest.json").read_text(encoding="utf-8"))
    assert acc == ["shot_001"]
    assert m["shots"] == {"1": "shot_001"} and m["accepted_count"] == 1
    assert m["exported_skipped"] == [2]


# ── 11. WR-02 回归锚：降级重跑不删上轮已成功导出的目录 ─────────────────────

def test_degraded_rerun_preserves_prior_good_dirs(tmp_path, capsys):
    """WR-02（22-REVIEW）：首轮成功导出后，第二轮因帧来源降级（cache 帧被清
    + 无源视频）重跑——上轮 shot 目录的 first/last_frame.jpg + prompt.json
    **必须保留**（旧实现 rmtree 毁掉上轮完好派生数据）；仅本轮自建的半成品
    目录才清。保留目录不进本轮索引（WR-01 口径）。"""
    wd = make_work_dir(tmp_path)
    root = tmp_path / "ds"
    assert run(wd, root) == 0          # 首轮：1/2 两镜全部导出成功
    stem = root / wd.name
    ff_before = (stem / "shot_002" / "first_frame.jpg").read_bytes()
    pj_before = (stem / "shot_002" / "prompt.json").read_bytes()

    # 第二轮降级：清 shot 2 帧缓存 + 无源视频 → _ensure_endpoint_frames None
    for f in ("ff", "lf"):
        (wd / "route_cache" / "h3_regen" / "frames"
         / f"kst_{VCH}_shot002_{f}.jpg").unlink()
    assert run(wd, root) == 0

    # 上轮完好导出保留（WR-02 核心）：帧 + prompt.json 字节不变
    d2 = stem / "shot_002"
    assert d2.is_dir(), "降级重跑不得删上轮已成功导出的 shot 目录"
    assert (d2 / "first_frame.jpg").read_bytes() == ff_before
    assert (d2 / "last_frame.jpg").is_file()
    assert (d2 / "prompt.json").read_bytes() == pj_before
    # 但本轮该镜不进索引（帧未重算，索引只列本轮导出成功集）
    m = json.loads((stem / "manifest.json").read_text(encoding="utf-8"))
    acc = (stem / "accepted.txt").read_text(encoding="utf-8").strip().splitlines()
    assert m["exported_skipped"] == [2] and "2" not in m["shots"]
    assert "shot_002" not in acc
    # 未降级的 shot 1 本轮照常重导出成功
    assert m["shots"] == {"1": "shot_001"} and m["accepted_count"] == 1
    # 保留决策可审计（warning 打印）
    out = capsys.readouterr().out
    assert "shot 2" in out and "保留不删" in out


def test_degraded_first_run_cleans_own_half_built_dir(tmp_path):
    """WR-02 对照面：目录是**本轮自建**（无上轮遗存）且降级 → 半成品目录仍清
    （不残留空目录冒充导出成功）。"""
    wd = make_work_dir(tmp_path)
    for f in ("ff", "lf"):
        (wd / "route_cache" / "h3_regen" / "frames"
         / f"kst_{VCH}_shot002_{f}.jpg").unlink()
    root = tmp_path / "ds"
    assert run(wd, root) == 0
    assert not (root / wd.name / "shot_002").exists(), \
        "本轮自建半成品目录必须清（无上轮遗存可保留）"
