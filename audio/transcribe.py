#!/usr/bin/env python3
"""Whisper 语音转录（支持 faster-whisper 或 openai-whisper）

流程：
  1. 用 ffmpeg 从视频中抽取 16kHz 单声道 wav（Whisper 要求）
  2. 自动选择后端：先尝试 faster-whisper，再回退到 openai-whisper
  3. 输出时间戳级 segments JSON

输出 JSON 结构：
{
  "backend": "faster-whisper",
  "model": "large-v3",
  "language": "zh",
  "duration": 308.33,
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "..."},
    ...
  ],
  "text": "（全文拼接，方便检索）"
}

每个 segment 也会按分镜归属后处理（可选，由 pipeline 拼接时使用）。
每个 segment 也会按分镜归属后处理（可选，由 pipeline 拼接时使用）。
"""
import argparse
import json
import os
import subprocess
import sys

import torch
import tempfile
from pathlib import Path


def extract_audio_wav(input_path: str, output_wav: str = None) -> str:
    """用 ffmpeg 抽取 16kHz 单声道 wav（Whisper 标准输入）。"""
    if output_wav is None:
        output_wav = tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, prefix="whisper_in_").name
    cmd = ["ffmpeg", "-y", "-i", input_path,
           "-vn", "-ac", "1", "-ar", "16000",
           "-loglevel", "error", output_wav]
    print(f"[ffmpeg] extracting 16kHz mono wav → {output_wav}")
    subprocess.run(cmd, check=True)
    return output_wav


def probe_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "a:0",
             "-show_entries", "stream=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True)
        if r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet",
             "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def transcribe_faster_whisper(wav: str, model: str, language: str,
                              device: str = "cuda", compute_type: str = None):
    """使用 faster-whisper（CTranslate2 后端，速度快、显存占用低）。"""
    from faster_whisper import WhisperModel
    if compute_type is None:
        compute_type = "float16" if device.startswith("cuda") else "int8"
    print(f"[faster-whisper] model={model} device={device} compute={compute_type}")
    m = WhisperModel(model, device=device, compute_type=compute_type)
    segments, info = m.transcribe(wav, language=language, vad_filter=True)
    seg_list = []
    full_text_parts = []
    for s in segments:
        text = s.text.strip()
        seg_list.append({"start": round(s.start, 2), "end": round(s.end, 2),
                         "text": text})
        full_text_parts.append(text)
    return {
        "backend": "faster-whisper",
        "model": model,
        "language": info.language if hasattr(info, "language") else language,
        "segments": seg_list,
        "text": " ".join(full_text_parts),
    }


def _other_gpu(device: str) -> str | None:
    """返回另一张卡的 device id（仅当当前是 cuda:N）。"""
    import re
    m = re.fullmatch(r"cuda:(\d+)", device)
    if not m:
        return None
    import torch
    n = torch.cuda.device_count()
    cur = int(m.group(1))
    for i in range(n):
        if i == cur:
            continue
        free, _total = torch.cuda.mem_get_info(i)
        if free > 2 * 1024**3:  # 至少 2GB 空闲才考虑
            return f"cuda:{i}"
    return None


def transcribe_openai_whisper(wav: str, model: str, language: str,
                              device: str = "cuda"):
    """使用 openai-whisper 官方实现。

    OOM 回退链:cuda:N → 另一张卡 → cpu
    """
    import whisper
    chain = [device]
    if device.startswith("cuda"):
        other = _other_gpu(device)
        if other and other != device:
            chain.append(other)
        chain.append("cpu")
    last_err = None
    for dev in chain:
        print(f"[openai-whisper] model={model} trying device={dev}")
        try:
            m = whisper.load_model(model, device=dev)
            result = m.transcribe(wav, language=language, verbose=False)
            seg_list = [{"start": round(s["start"], 2), "end": round(s["end"], 2),
                         "text": s["text"].strip()} for s in result["segments"]]
            return {
                "backend": "openai-whisper",
                "model": model,
                "language": language,
                "segments": seg_list,
                "text": result.get("text", "").strip(),
            }
        except torch.cuda.OutOfMemoryError as e:
            last_err = e
            print(f"[openai-whisper] OOM on {dev}, trying next fallback...")
            import gc
            gc.collect()
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            continue
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                last_err = e
                print(f"[openai-whisper] OOM on {dev}, trying next fallback...")
                import gc
                gc.collect()
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                continue
            raise
    if last_err:
        raise last_err


def transcribe(wav: str, model: str, language: str, device: str,
               backend: str = "auto"):
    """按 backend 选择实现；auto 时先 faster-whisper 再 openai-whisper。

    OOM 回退链（仅 faster-whisper）：
        cuda:N (float16) → 另一张空闲 cuda (float16) → cuda (int8) → cpu (int8)
    """
    if backend in ("auto", "faster-whisper"):
        # 回退链构建
        chain = [device]
        if device.startswith("cuda"):
            other = _other_gpu(device)
            if other and other != device:
                chain.append(other)
            chain.append(device)   # 同卡换 int8
            chain.append("cpu")
        seen = set()
        last_err = None
        for dev in chain:
            key = (dev, "int8" if (dev == device and chain.index(dev) > 0) or dev == "cpu" else "float16")
            if key in seen:
                continue
            seen.add(key)
            try:
                compute = key[1]
                print(f"[whisper] trying faster-whisper on {dev} ({compute})")
                return transcribe_faster_whisper(wav, model, language,
                                                 device=dev, compute_type=compute)
            except ImportError:
                if backend == "faster-whisper":
                    raise
                print("[whisper] faster-whisper not available, falling back to openai-whisper")
                last_err = ImportError()
                break
            except Exception as e:
                # 区分 OOM vs 其他错误
                is_oom = "OutOfMemoryError" in type(e).__name__ or "out of memory" in str(e).lower()
                if is_oom:
                    last_err = e
                    print(f"[whisper] OOM on {dev} ({key[1]}), trying next fallback...")
                    import gc
                    gc.collect()
                    try:
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                    continue
                # 非OOM错误(如模型下载失败):auto模式回退到openai-whisper
                last_err = e
                if backend == "faster-whisper":
                    raise
                print(f"[whisper] faster-whisper failed ({e}), trying openai-whisper")
                break
        # 非OOM错误或所有OOM回退都失败 → 回退到 openai-whisper
    return transcribe_openai_whisper(wav, model, language, device=device)


def main():
    ap = argparse.ArgumentParser(description="Whisper 时间戳级语音转录")
    ap.add_argument("--input", required=True, help="输入视频/音频文件")
    ap.add_argument("--output", default=None, help="输出 JSON 路径")
    ap.add_argument("--model", default="large-v3",
                    help="Whisper 模型名（large-v3 / medium / small ...）")
    ap.add_argument("--language", default="zh", help="语言代码（默认 zh）")
    ap.add_argument("--device", default="cuda",
                    help="cuda / cpu（faster-whisper 还可 cuda:0）")
    ap.add_argument("--backend", default="auto",
                    choices=["auto", "faster-whisper", "openai-whisper"])
    ap.add_argument("--wav-out", default=None,
                    help="保留抽取的 16kHz wav 到该路径（可选，调试用）")
    args = ap.parse_args()

    out_path = args.output or os.path.join(
        os.path.dirname(args.input) or ".",
        f"{Path(args.input).stem}_transcript.json")

    if args.wav_out:
        wav = extract_audio_wav(args.input, args.wav_out)
    else:
        wav = extract_audio_wav(args.input)

    try:
        result = transcribe(wav, args.model, args.language,
                            args.device, args.backend)
    finally:
        if args.wav_out is None and os.path.exists(wav):
            os.unlink(wav)

    result["duration"] = probe_duration(args.input)
    result["source"] = os.path.basename(args.input)

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[whisper] wrote {len(result['segments'])} segments → {out_path}")


if __name__ == "__main__":
    main()
