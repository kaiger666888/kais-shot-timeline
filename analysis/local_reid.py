#!/usr/bin/env python3
"""本地角色 re-id + crop 提取（无需远程路由，替代 DEFERRED call_reid.py）

两阶段：
  Stage 1: GLM-4.6V vision 从帧中检测角色 bbox → crop
  Stage 2: CLIP embedding 聚类 → 角色 identity 分组 → 每角色选最佳 crop

输出：
  characters/char_001.png ... char_NNN.png   (角色最佳 crop)
  registry.draft.json                          (聚类结果 —— spec/schemas/registry.schema.json
                                               合规，写前 Draft202012Validator 自校验)
  registry.reid_meta.json                      (GLM name/species/appearance 元数据 sidecar ——
                                               契约 draft 是 additionalProperties:false，
                                               rich 字段分流到此，审阅/策展侧不丢信息)
  registry_review.html                         (HITL 审阅)

用法：
  python analysis/local_reid.py \\
      --frames-dir /path/to/frames_5fps \\
      --work-dir output/<video-stem>/ \\
      --output output/<video-stem>/registry.draft.json \\
      --shots output/<video-stem>/shots.json
"""
import argparse
import base64
import json
import os
import sys
import time
import hashlib
from pathlib import Path
from io import BytesIO

import numpy as np
from PIL import Image
from sklearn.cluster import AgglomerativeClustering


# ─── GLM-4.6V vision bbox detection ─────────────────────────────────────────

def _load_api_key() -> str:
    """从 hermes config 读取 zhipu api key"""
    import yaml
    config_path = os.path.expanduser('~/.hermes/config.yaml')
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return cfg.get('providers', {}).get('zhipu-anthropic', {}).get('api_key', '')


def detect_characters_frame(img_path: str, api_key: str, max_retries: int = 2) -> list[dict]:
    """用 GLM-4.6V 检测帧中的角色 bbox

    Returns:
        [{name, bbox: [x1,y1,x2,y2], species, appearance}, ...]
        bbox 坐标为 0-1000 归一化
    """
    import urllib.request

    with open(img_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    prompt = (
        "这是3D动画的一帧截图。找到图中所有角色（拟人化生物/角色），"
        "为每个角色输出JSON：\n"
        '[{"name":"简短名","bbox":[x1,y1,x2,y2],"species":"物种","appearance":"外观"}]\n'
        "坐标0-1000归一化。只输出JSON数组，不要其他文字。"
    )

    payload = {
        # DEPRECATED 2026-08-27: glm-4.6v 生产端点已回归故障（thinking 吃满 max_tokens→零文本；
        # 加大额度后幻觉认错角色）。bbox 检测路线由 DINOv2 embedding + apply_edits 人审取代，
        # 本函数保留仅供离线复现，新管线勿调。
        "model": "glm-4.6v",
        "max_tokens": 800,
        "temperature": 0.1,
        "messages": [
            {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                {"type": "text", "text": prompt}
            ]}
        ]
    }

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                'https://open.bigmodel.cn/api/anthropic/v1/messages',
                data=json.dumps(payload).encode(),
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01'
                }
            )
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())
            text = result.get('content', [{}])[0].get('text', '')
            # 解析 JSON
            text = text.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print(f"  [WARN] detect failed for {os.path.basename(img_path)}: {e}")
    return []


# ─── Color histogram embedding for clustering (no external model download) ──

def get_embedding(img: Image.Image) -> np.ndarray:
    """HSV + RGB 联合颜色直方图 embedding (512-dim)

    替代 CLIP embedding：对动画角色特别有效（角色主色调是核心辨识特征）。
    无需下载任何外部模型，纯本地 OpenCV 计算。
    """
    import cv2
    arr = np.array(img.convert('RGB'))
    # HSV 直方图 (H: 50 bins, S: 25 bins = 125 dim) — 捕捉主色调
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h_hist = cv2.calcHist([hsv], [0, 1], None, [50, 25], [0, 180, 0, 256]).flatten()
    # RGB 直方图 (每通道 64 bins = 192 dim) — 捕捉亮度分布
    r_hist = cv2.calcHist([arr], [0], None, [64], [0, 256]).flatten()
    g_hist = cv2.calcHist([arr], [1], None, [64], [0, 256]).flatten()
    b_hist = cv2.calcHist([arr], [2], None, [64], [0, 256]).flatten()
    # 拼接 + L2 normalize
    emb = np.concatenate([h_hist, r_hist, g_hist, b_hist])
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


# ─── Main pipeline ───────────────────────────────────────────────────────────

def frame_to_shot(frame_fname: str, shots_meta: list[dict]) -> tuple[int, int]:
    """frames_5fps 文件名 → (shot_id, frame 序号)。

    帧文件名 f%06d.jpg 按 5 fps 采样（repo 惯例 frames_5fps/），秒 = N / 5；
    落在哪个 shot 的 [start_sec, end_sec) 就归属哪镜；越界（尾帧恰好等于
    duration）兜底最后一镜。
    """
    n = int(frame_fname.lstrip('f').split('.')[0])
    t = n / 5.0
    for s in shots_meta:
        if s["start_sec"] <= t < s["end_sec"]:
            return s["id"], n
    return shots_meta[-1]["id"], n


def conform_draft(rich_clusters: list[dict], shots_meta: list[dict],
                  tau: float) -> tuple[dict, dict]:
    """内部富聚类结果 → (schema 合规 draft, GLM 元数据 sidecar)。

    registry.draft.json 必须严格符合 spec/schemas/registry.schema.json
    （root/cluster 均 additionalProperties:false），GLM 的 name/species/
    appearance 等 rich 字段分流到 registry.reid_meta.json sidecar —— 契约
    侧零污染，审阅/策展侧信息不丢。

    tier 三档（对齐 gen_registry_review.py 的 mid-band 优先审约定）：
      mean_cos ≥ 0.85 → auto_distinct（紧簇，独立角色信号强）
      0.65 ≤ cos < 0.85 → review（中带，优先人审）
      cos < 0.65 → auto_merge（簇内松散，可能该并入其他簇）
    """
    clusters_out, meta_clusters = [], []
    for c in rich_clusters:
        members = [{"shot_id": sid, "frame_pos": n, "mask_quality": "unknown"}
                   for m in c["members"]
                   for sid, n in [frame_to_shot(m["frame"], shots_meta)]]
        cos = float(c.get("mean_cosine", 0.85))
        tier = ("auto_distinct" if cos >= 0.85
                else "review" if cos >= 0.65 else "auto_merge")
        clusters_out.append({
            "cluster_id": c["cluster_id"], "review_state": "proposed",
            "tier": tier, "mean_cosine": round(cos, 4), "members": members})
        meta_clusters.append({k: c[k] for k in (
            "cluster_id", "name", "species", "appearance",
            "member_count", "representative_image", "crops_dir", "members")})
    draft = {"generated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             "model": "glm-4.6v+colorhist-local", "tau": float(tau),
             "clusters": clusters_out}
    meta = {"generated_at": draft["generated_at"],
            "method": "local_reid_glm46v_hist", "clusters": meta_clusters}
    return draft, meta


def run_reid(frames_dir: str, work_dir: str, output_path: str,
             shots_meta: list[dict],
             max_frames: int = 40, tau: float = 0.35):
    """主流程：帧 → 检测 → crop → 聚类 → 最佳 crop → registry.draft.json

    Args:
        frames_dir: frames_5fps 目录路径
        work_dir: 资产根目录
        output_path: registry.draft.json 输出路径
        max_frames: 最多处理的帧数（均匀采样）
        tau: 聚类距离阈值 (cosine distance)
    """
    api_key = _load_api_key()
    if not api_key:
        print("[ERROR] No API key found in ~/.hermes/config.yaml")
        return []

    # 采样帧
    all_frames = sorted([f for f in os.listdir(frames_dir) if f.endswith('.jpg')])
    if len(all_frames) > max_frames:
        indices = np.linspace(0, len(all_frames) - 1, max_frames, dtype=int)
        sampled = [all_frames[i] for i in indices]
    else:
        sampled = all_frames

    print(f"[reid] Sampling {len(sampled)} frames from {len(all_frames)} total")

    # Stage 1: 逐帧检测角色
    all_crops = []  # [{frame, name, bbox, species, appearance, img_path, embedding}]
    for i, fname in enumerate(sampled):
        fpath = os.path.join(frames_dir, fname)
        print(f"  [{i+1}/{len(sampled)}] {fname}...", end=' ', flush=True)

        detections = detect_characters_frame(fpath, api_key)
        if not detections:
            print("no characters")
            continue

        # 读取原图
        orig = Image.open(fpath)
        W, H = orig.size

        for det in detections:
            bbox = det.get('bbox', [0, 0, 0, 0])
            if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue

            # 归一化坐标 → 像素坐标
            x1 = max(0, int(bbox[0] / 1000 * W))
            y1 = max(0, int(bbox[1] / 1000 * H))
            x2 = min(W, int(bbox[2] / 1000 * W))
            y2 = min(H, int(bbox[3] / 1000 * H))

            # 跳过太小的 crop
            if (x2 - x1) < 30 or (y2 - y1) < 30:
                continue

            crop = orig.crop((x1, y1, x2, y2))
            crop_resized = crop.resize((224, 224), Image.LANCZOS)

            try:
                emb = get_embedding(crop_resized)
            except Exception as e:
                print(f"[WARN] embedding failed: {e}")
                continue

            all_crops.append({
                'frame': fname,
                'name': det.get('name', 'unknown'),
                'species': det.get('species', ''),
                'appearance': det.get('appearance', ''),
                'bbox': [x1, y1, x2, y2],
                'orig_path': fpath,
                'embedding': emb.tolist(),
            })

        print(f"{len(detections)} chars")

    if not all_crops:
        print("[reid] No characters detected!")
        return []

    print(f"\n[reid] Total crops: {len(all_crops)}")

    # Stage 2: CLIP embedding 聚类
    embeddings = np.array([c['embedding'] for c in all_crops])

    # Agglomerative clustering with cosine distance
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric='cosine',
        linkage='average',
        distance_threshold=tau
    )
    labels = clustering.fit_predict(embeddings)

    n_clusters = len(set(labels))
    print(f"[reid] Clusters: {n_clusters}")

    # 按 cluster 分组，选最佳 crop (最大面积)
    clusters = []
    chars_dir = os.path.join(work_dir, 'characters')
    os.makedirs(chars_dir, exist_ok=True)

    for cid in range(n_clusters):
        members = [all_crops[i] for i in range(len(all_crops)) if labels[i] == cid]
        # 计算平均 cosine similarity（到中心）
        cluster_emb = np.mean([np.array(m['embedding']) for m in members], axis=0)
        cluster_emb_norm = cluster_emb / (np.linalg.norm(cluster_emb) + 1e-8)
        cos_sims = [float(np.dot(cluster_emb_norm, np.array(m['embedding']))) for m in members]
        mean_cos = float(np.mean(cos_sims))

        # 选面积最大的 crop 作为代表
        best = max(members, key=lambda m: (m['bbox'][2] - m['bbox'][0]) * (m['bbox'][3] - m['bbox'][1]))

        # 从原图 crop 并保存
        orig = Image.open(best['orig_path'])
        crop_img = orig.crop(tuple(best['bbox']))
        char_id = f"char_{cid+1:03d}"
        crop_path = os.path.join(chars_dir, f"{char_id}.png")
        crop_img.save(crop_path)

        # 收集所有 member crops（用于 turnaround 生成）
        member_crops_dir = os.path.join(chars_dir, char_id)
        os.makedirs(member_crops_dir, exist_ok=True)
        for j, m in enumerate(members):
            orig_m = Image.open(m['orig_path'])
            crop_m = orig_m.crop(tuple(m['bbox']))
            crop_m.save(os.path.join(member_crops_dir, f"frame_{j:03d}.png"))

        clusters.append({
            'cluster_id': char_id,
            'name': best['name'],
            'species': best['species'],
            'appearance': best['appearance'],
            'review_state': 'proposed',
            'mean_cosine': round(mean_cos, 4),
            'member_count': len(members),
            'representative_image': f"characters/{char_id}.png",
            'crops_dir': f"characters/{char_id}/",
            'members': [{
                'frame': m['frame'],
                'bbox': m['bbox'],
                'cos_sim': round(cos_sims[i], 4),
            } for i, m in enumerate(members)]
        })
        print(f"  {char_id}: {best['name']} ({best['species']}) | {len(members)} members | mean_cos={mean_cos:.3f}")

    # 写 registry.draft.json（schema 合规）+ registry.reid_meta.json（GLM 元数据 sidecar）
    draft, meta = conform_draft(clusters, shots_meta, tau)
    meta["total_crops"] = len(all_crops)
    meta["total_clusters"] = n_clusters
    # 写前 fails-loud 自校验（repo 惯例，mirror call_shot_analysis PROMPTS_SCHEMA）
    from jsonschema import Draft202012Validator
    schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'spec', 'schemas', 'registry.schema.json')
    with open(schema_path, encoding='utf-8') as f:
        schema = json.load(f)
    errors = list(Draft202012Validator(schema).iter_errors(draft))
    if errors:
        sys.exit(f"[reid] registry.draft.json schema validation failed "
                 f"({len(errors)} errors): {errors[0].message}")
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    meta_path = os.path.join(os.path.dirname(os.path.abspath(output_path)),
                             'registry.reid_meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"\n[reid] Written: {output_path} (schema-validated, {len(clusters)} clusters)")
    print(f"[reid] GLM meta sidecar: {meta_path}")
    print(f"[reid] Character crops: {chars_dir}/")

    return clusters


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Local character re-id + crop extraction')
    parser.add_argument('--frames-dir', required=True, help='frames_5fps directory')
    parser.add_argument('--work-dir', required=True, help='Asset root directory')
    parser.add_argument('--output', required=True, help='registry.draft.json output path')
    parser.add_argument('--shots', required=True,
                        help='shots.json path (frame→shot_id 映射，schema members 必填)')
    parser.add_argument('--max-frames', type=int, default=40, help='Max frames to sample')
    parser.add_argument('--tau', type=float, default=0.35, help='Clustering distance threshold')
    args = parser.parse_args()

    with open(args.shots, encoding='utf-8') as f:
        shots_meta = json.load(f)
    run_reid(args.frames_dir, args.work_dir, args.output, shots_meta,
             args.max_frames, args.tau)
