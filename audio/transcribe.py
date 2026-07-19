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
"""
import argparse
import json
import os
import subprocess
import sys
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


def transcribe_openai_whisper(wav: str, model: str, language: str,
                              device: str = "cuda"):
    """使用 openai-whisper 官方实现。"""
    import whisper
    print(f"[openai-whisper] model={model} device={device}")
    m = whisper.load_model(model, device=device)
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


def transcribe(wav: str, model: str, language: str, device: str,
               backend: str = "auto"):
    """按 backend 选择实现；auto 时先 faster-whisper 再 openai-whisper。"""
    if backend in ("auto", "faster-whisper"):
        try:
            return transcribe_faster_whisper(wav, model, language, device=device)
        except ImportError:
            if backend == "faster-whisper":
                raise
            print("[whisper] faster-whisper not available, falling back to openai-whisper")
        except Exception as e:
            if backend == "faster-whisper":
                raise
            print(f"[whisper] faster-whisper failed ({e}), trying openai-whisper")
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
