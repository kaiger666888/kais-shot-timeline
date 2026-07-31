#!/usr/bin/env python3
"""v2 turnaround 生成：从原片全帧提取高质量角色参考 → GLM-4.6V 分析 → dreamina img2image

v1 (gen_turnaround.py) 的问题：
  - 用 registry 的 representative_image（小 crop 392×542）做唯一参考
  - GLM 分析低分辨率 crop → 描述错误（所有角色都"蓝色皮肤"）
  - 只传 1 张参考图给 dreamina

v2 改进（8123 页面验证的最佳实践）：
  - 从 registry.draft.json members 选 cos_sim 最高的 N 帧
  - 从原片 5fps 帧目录提取**全帧**（1920×1080），不裁切
  - GLM-4.6V 看**全帧**（非小 crop）→ 准确分析角色外观
  - dreamina img2image 传入多张全帧作为参考 → 生成高质量 turnaround

用法：
  python3 analysis/gen_turnaround_v2.py \
      --draft output/<video>/registry.draft.json \
      --work-dir output/<video>/ \
      --frames-dir output/<video>/frames_5fps/ \
      [--top-n 4] \
      [--dreamina /home/kai/.local/bin/dreamina] \
      [--skip-existing]

输出：
  output/<video>/turnarounds_v2/
    ├── char_001_turnaround.png
    ├── char_002_turnaround.png
    ├── ...
    └── manifest.json
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image


def select_best_frames(cluster: dict, frames_dir: str, top_n: int = 4) -> list[str]:
    """从 cluster members 中选 cos_sim 最高的 N 张全帧"""
    members = sorted(cluster.get("members", []),
                     key=lambda m: m.get("cos_sim", 0), reverse=True)
    selected = []
    seen_frames = set()
    for m in members[:top_n * 3]:  # 多取一些，去重
        frame_name = m.get("frame", "")
        if frame_name in seen_frames:
            continue
        frame_path = os.path.join(frames_dir, frame_name)
        if os.path.exists(frame_path):
            selected.append(frame_path)
            seen_frames.add(frame_name)
        if len(selected) >= top_n:
            break
    return selected


def downscale_frame(frame_path: str, max_w: int = 1280) -> str:
    """如果帧太大，缩小到 max_w 宽度（dreamina 上传限制）"""
    img = Image.open(frame_path)
    if img.width <= max_w:
        return frame_path
    ratio = max_w / img.width
    img = img.resize((max_w, int(img.height * ratio)), Image.Resampling.LANCZOS)
    # 保存到临时文件
    tmp_path = frame_path.replace(".jpg", f"_ds{max_w}.jpg")
    img.save(tmp_path, quality=90)
    return tmp_path


def analyze_character_crops(crops: list, api_key: str) -> dict | None:
    """用 GLM-4.6V 从 bbox 裁出的角色 crop 分析外观（避免背景干扰）"""
    import urllib.request
    import io

    images_b64 = []
    for crop in crops[:3]:
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=90)
        images_b64.append(base64.b64encode(buf.getvalue()).decode())

    prompt = """请详细分析这些3D动画帧中的角色外观。这是从画面中裁出的角色特写，请聚焦角色本身。

输出JSON：
{
  "species": "物种（如毛毛虫/独角仙/螳螂/蜈蚣等，拟人化的也要写出原形）",
  "body_color": "主色调（要准确！橙黄/翠绿/蓝灰/棕褐等）",
  "body_shape": "体型描述",
  "head": "头部特征（角/触角/发型/帽子等）",
  "eyes": "眼睛描述",
  "distinguishing_features": ["特征1", "特征2", "特征3"],
  "clothing": "服装描述",
  "style": "动画风格",
  "turnaround_prompt": "英文prompt，描述这个角色的多角度turnaround sheet。格式：Create a professional character reference sheet. Same person in ALL four views. 然后是详细的角色描述。最后是 Arrange into four columns... FRONT VIEW... THREE-QUARTER VIEW... SIDE PROFILE... BACK VIEW..."
}
只输出JSON。"""

    content = []
    for img_b64 in images_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}
        })
    content.append({"type": "text", "text": prompt})

    payload = {
        "model": "glm-4.6v",
        "max_tokens": 800,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": content}]
    }

    for attempt in range(3):
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
            resp = urllib.request.urlopen(req, timeout=60)
            result = json.loads(resp.read())
            text = result.get('content', [{}])[0].get('text', '')
            text = text.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            return json.loads(text)
        except Exception as e:
            if attempt < 2:
                print(f"    [retry {attempt+1}] {e}")
                time.sleep(3)
            else:
                print(f"    [WARN] analyze failed: {e}")
                return {}
    return {}


def analyze_character_frames(frame_paths: list[str], api_key: str) -> dict | None:
    """用 GLM-4.6V 从多张全帧分析角色外观，生成 turnaround prompt"""
    import urllib.request

    images_b64 = []
    for path in frame_paths[:3]:  # 最多传 3 张
        with open(path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode()
        images_b64.append(img_b64)

    prompt = """请详细分析这些3D动画帧中的主要角色外观（帧中可能包含多个角色，请聚焦出现次数最多/最突出的那个角色）。

输出JSON：
{
  "species": "物种（如毛毛虫/独角仙/螳螂/蜈蚣等，拟人化的也要写出原形）",
  "body_color": "主色调（要准确！橙黄/翠绿/蓝灰等）",
  "body_shape": "体型描述",
  "head": "头部特征（角/触角/发型/帽子等）",
  "eyes": "眼睛描述",
  "distinguishing_features": ["特征1", "特征2", "特征3"],
  "clothing": "服装描述",
  "style": "动画风格",
  "turnaround_prompt": "英文prompt，描述这个角色的多角度turnaround sheet。格式：Create a professional character reference sheet. Same person in ALL four views. 然后是详细的角色描述。最后是 Arrange into four columns... FRONT VIEW... THREE-QUARTER VIEW... SIDE PROFILE... BACK VIEW..."
}
只输出JSON。"""

    content = []
    for img_b64 in images_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}
        })
    content.append({"type": "text", "text": prompt})

    payload = {
        "model": "glm-4.6v",
        "max_tokens": 800,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": content}]
    }

    for attempt in range(3):
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
            resp = urllib.request.urlopen(req, timeout=60)
            result = json.loads(resp.read())
            text = result.get('content', [{}])[0].get('text', '')
            text = text.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            return json.loads(text)
        except Exception as e:
            if attempt < 2:
                print(f"    [retry {attempt+1}] {e}")
                time.sleep(3)
            else:
                print(f"    [WARN] analyze failed: {e}")
                return {}
    return {}


def gen_turnaround_dreamina(ref_images: list[str], prompt: str, output_path: str,
                             dreamina_bin: str = '/home/kai/.local/bin/dreamina') -> str | None:
    """用 dreamina img2image 从多张参考帧生成 turnaround"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 传入最多 4 张参考图
    images_str = ",".join(ref_images[:4])

    cmd = [
        dreamina_bin, 'image2image',
        '--images', images_str,
        '--prompt', prompt,
        '--ratio', '16:9',
        '--resolution_type', '2k',
        '--poll', '10',
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr

        import re
        m = re.search(r'"submit_id":\s*"([^"]+)"', output)
        if not m:
            print(f"    [WARN] no submit_id in dreamina output")
            return None
        submit_id = m.group(1)

        # 轮询
        for attempt in range(60):  # 最多等 300s
            time.sleep(5)
            qcmd = [dreamina_bin, 'query_result', f'--submit_id={submit_id}']
            qresult = subprocess.run(qcmd, capture_output=True, text=True, timeout=30)
            try:
                data = json.loads(qresult.stdout)
            except json.JSONDecodeError:
                continue

            status = data.get("gen_status", "")
            if status == "success":
                # 兼容多种返回格式
                images = data.get("result_json", {}).get("images", [])
                if not images:
                    images = data.get("images", [])
                if images:
                    url = ""
                    if isinstance(images[0], dict):
                        url = images[0].get("image_url", "") or images[0].get("url", "")
                    elif isinstance(images[0], str):
                        url = images[0]
                    if url:
                        dcmd = ['curl', '-sL', '-o', output_path, url]
                        subprocess.run(dcmd, timeout=60)
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                            return output_path
                break
            elif status == "failed":
                print(f"    [WARN] dreamina generation failed")
                break
        print(f"    [WARN] dreamina polling timeout (300s)")
    except subprocess.TimeoutExpired:
        print(f"    [WARN] dreamina submit timeout")
    except Exception as e:
        print(f"    [WARN] dreamina error: {e}")

    return None


def _load_api_key() -> str:
    import yaml
    config_path = os.path.expanduser('~/.hermes/config.yaml')
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return cfg.get('providers', {}).get('zhipu-anthropic', {}).get('api_key', '')


def run(draft_path: str, work_dir: str, frames_dir: str,
        top_n: int, dreamina_bin: str, skip_existing: bool):
    """主函数：registry.draft.json → 选帧 → GLM 分析 → dreamina img2image turnaround"""
    with open(draft_path) as f:
        draft = json.load(f)

    clusters = draft.get('clusters', [])
    if not clusters:
        print("[v2] No clusters in draft!")
        return

    api_key = _load_api_key()
    turnaround_dir = os.path.join(work_dir, 'turnarounds_v2')
    os.makedirs(turnaround_dir, exist_ok=True)

    results = []

    for cluster in clusters:
        char_id = cluster['cluster_id']
        name = cluster.get('name', char_id)
        member_count = len(cluster.get('members', []))

        # 跳过只有 1 个 member 的角色（参考帧太少）
        if member_count < 2:
            print(f"\n[{char_id}] {name} — SKIP (only {member_count} member)")
            continue

        output_path = os.path.join(turnaround_dir, f'{char_id}_turnaround.png')
        if skip_existing and os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
            print(f"\n[{char_id}] {name} — SKIP (already exists)")
            results.append({'char_id': char_id, 'name': name, 'turnaround': output_path, 'skipped': True})
            continue

        print(f"\n[{char_id}] {name} ({cluster.get('species', '?')}) — {member_count} members")

        # Step 1: 选最佳全帧
        print(f"  Selecting best {top_n} frames by cos_sim...")
        best_frames = select_best_frames(cluster, frames_dir, top_n)
        if not best_frames:
            print(f"  [SKIP] No frames found in {frames_dir}")
            continue

        # 缩小太大的帧（dreamina 参考用）
        ref_images = [downscale_frame(f) for f in best_frames]
        for f in ref_images:
            print(f"    {os.path.basename(f)}")

        # Step 1b: 用 bbox 裁角色 crop 供 GLM 分析（避免背景干扰）
        crops_for_analysis = []
        members_sorted = sorted(cluster.get("members", []),
                                key=lambda m: m.get("cos_sim", 0), reverse=True)
        for m in members_sorted[:top_n]:
            frame_name = m.get("frame", "")
            frame_path = os.path.join(frames_dir, frame_name)
            bbox = m.get("bbox", [])
            if os.path.exists(frame_path) and len(bbox) == 4:
                img = Image.open(frame_path)
                # bbox 扩展 20% 给 GLM 更多上下文
                x1, y1, x2, y2 = bbox
                w, h = x2 - x1, y2 - y1
                x1 = max(0, int(x1 - w * 0.2))
                y1 = max(0, int(y1 - h * 0.2))
                x2 = min(img.width, int(x2 + w * 0.2))
                y2 = min(img.height, int(y2 + h * 0.2))
                crop = img.crop((x1, y1, x2, y2))
                crops_for_analysis.append(crop)

        # Step 2: GLM-4.6V 分析 bbox crop（只看角色，不看背景）
        print(f"  Analyzing character from bbox crops ({len(crops_for_analysis)} crops)...")
        analysis = analyze_character_crops(crops_for_analysis, api_key)
        if analysis:
            print(f"    Species: {analysis.get('species', '?')}")
            print(f"    Color: {analysis.get('body_color', '?')}")
            print(f"    Features: {analysis.get('distinguishing_features', [])}")
        else:
            print(f"    [WARN] Analysis failed, using generic prompt")

        # Step 3: dreamina img2image 生成 turnaround
        turnaround_prompt = analysis.get('turnaround_prompt', '') if analysis else ''
        if not turnaround_prompt:
            turnaround_prompt = (
                f"Create a professional character reference sheet. "
                f"Same character in ALL four views. "
                f"3D animation style character: {analysis.get('body_color', '')} "
                f"{analysis.get('species', '')} with {analysis.get('head', '')}. "
                f"Arrange into four columns on a plain light gray background: "
                f"Column 1: FRONT VIEW. Column 2: THREE-QUARTER VIEW. "
                f"Column 3: SIDE PROFILE. Column 4: BACK VIEW. "
                f"Even spacing. Pixar-level 3D animation style. No text. No labels."
            )

        print(f"  Generating turnaround via dreamina img2image...")
        result_path = gen_turnaround_dreamina(
            ref_images, turnaround_prompt, output_path, dreamina_bin
        )

        if result_path:
            print(f"  ✅ Saved: {result_path}")
            results.append({
                'char_id': char_id,
                'name': name,
                'species': analysis.get('species', cluster.get('species', '')),
                'body_color': analysis.get('body_color', ''),
                'ref_frames': [os.path.basename(f) for f in ref_images],
                'analysis': analysis,
                'turnaround': result_path,
            })
        else:
            print(f"  ❌ Generation failed")
            results.append({
                'char_id': char_id,
                'name': name,
                'failed': True,
            })

    # 写 manifest
    manifest_path = os.path.join(turnaround_dir, 'manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump({
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'method': 'gen_turnaround_v2_glm46v_fulframes_dreamina',
            'improvement_over_v1': '使用原片全帧(1920x1080)而非小crop做GLM分析和dreamina参考',
            'total': len(results),
            'entries': results,
        }, f, ensure_ascii=False, indent=2)

    success = sum(1 for r in results if r.get('turnaround'))
    print(f"\n[v2] Done: {success}/{len(clusters)} characters")
    print(f"[v2] Manifest: {manifest_path}")
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='v2 turnaround: 从原片全帧 + GLM-4.6V + dreamina img2image')
    parser.add_argument('--draft', required=True, help='registry.draft.json path')
    parser.add_argument('--work-dir', required=True, help='Asset root directory')
    parser.add_argument('--frames-dir', required=True,
                        help='5fps frames directory (e.g. output/<video>/frames_5fps/)')
    parser.add_argument('--top-n', type=int, default=4,
                        help='每角色选多少张最佳参考帧 (default: 4)')
    parser.add_argument('--dreamina', default='/home/kai/.local/bin/dreamina',
                        help='Dreamina CLI path')
    parser.add_argument('--skip-existing', action='store_true',
                        help='跳过已生成的 turnaround')
    args = parser.parse_args()

    run(args.draft, args.work_dir, args.frames_dir,
        args.top_n, args.dreamina, args.skip_existing)
