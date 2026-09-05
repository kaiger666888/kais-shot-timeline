#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s064 修正臂 seed 彩票: 干净条件帧+视频轴+禁撑窗, 3 seeds 择尾帧锁定最优."""
import json, subprocess, time, sys, os
import numpy as np
from PIL import Image

RB = "/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01"
BASE = "http://127.0.0.1:8188"
OUTDIR = "ep01_batch_lx9_fix"
SEEDS = [20260903, 424242, 777]

def n(cid, ct, **inp):
    return {"class_type": ct, "inputs": inp, "_meta": {"title": ct}}

def build_wf(m, dur, seed):
    wf = {}
    wf["1"] = n(1, "LoadAudio", audio=m["audio"].replace(RB, "gsrt_batch"))
    wf["2"] = n(2, "MiniMaxH3AudioWindowT8", audio=["1", 0],
                scene_start_seconds=0.0, scene_duration_seconds=dur,
                warmup_seconds=0.0, cooldown_seconds=0.0, ensure_minimum_context=False)
    wf["3"] = n(3, "VAELoader", vae_name="minimax_h3_video_vae_fp16.safetensors")
    wf["4"] = n(4, "VAELoader", vae_name="minimax_h3_audio_vae_fp32.safetensors")
    wf["5"] = n(5, "CLIPLoader", clip_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", type="minimax", device="default")
    wf["6"] = n(6, "UNETLoader", unet_name="minimax_h3_fl2va_int8_convrot.safetensors", weight_dtype="default")
    wf["17"] = n(17, "LoraLoaderModelOnly", model=["6", 0], lora_name="minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors", strength_model=1.0)
    wf["7"] = n(7, "MiniMaxH3SigmaShift", model=["17", 0], shift_video=6.0, shift_audio=3.0)
    wf["18"] = n(18, "LoadImage", image=m["cond_first"].replace(RB, "gsrt_batch"))
    wf["19"] = n(19, "LoadImage", image=m["cond_last"].replace(RB, "gsrt_batch"))
    wf["8"] = n(8, "MiniMaxH3AudioConditioningT8",
                clip=["5", 0], video_vae=["3", 0], audio_vae=["4", 0],
                length=["2", 1], drive_audio=["2", 0],
                first_frame=["18", 0], last_frame=["19", 0],
                prompt=m["h3_prompt"], width=1344, height=768,
                task_type="FL2VA", audio_mode="lock_source",
                audio_denoise_strength=0.0, add_source_as_reference=False,
                prompt_primary_audio_ordinal=1, strict_prompt_tags=True,
                ref_image_size="match", reference_video_policy="official_2_to_15s")
    wf["9"] = n(9, "RandomNoise", noise_seed=seed)
    wf["10"] = n(10, "BasicGuider", model=["7", 0], conditioning=["8", 0])
    wf["11"] = n(11, "KSamplerSelect", sampler_name="euler")
    wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=9, denoise=1.0)
    wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                 sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])
    wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0], video_vae=["3", 0], audio_vae=["4", 0])
    wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                 duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)
    wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                 frame_rate=24, loop_count=0,
                 filename_prefix=f"{OUTDIR}/s064_lot{seed}",
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                 save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True)
    return {"prompt": wf, "client_id": f"ep01_s064_lot_{seed}"}

def gray(p, size=(480,274)):
    return np.asarray(Image.open(p).convert("L").resize(size, Image.LANCZOS), dtype=np.float32)

def mad(a, b): return float(np.abs(a - b).mean())

def render_one(m, dur, seed):
    r = subprocess.run(["curl", "-s", "-X", "POST", f"{BASE}/prompt",
                        "-H", "Content-Type: application/json",
                        "-d", json.dumps(build_wf(m, dur, seed))], capture_output=True, text=True)
    pid = json.loads(r.stdout)["prompt_id"]
    print(f"seed {seed} submitted {pid}", flush=True)
    while True:
        time.sleep(10)
        h = subprocess.run(["curl", "-s", f"{BASE}/history/{pid}"], capture_output=True, text=True).stdout
        hd = json.loads(h)
        if pid in hd:
            st = hd[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"seed {seed} ERROR", json.dumps(st.get("details",""))[:200], flush=True)
                return None
            for node, o in hd[pid].get("outputs", {}).items():
                for g in o.get("gifs", []):
                    return g["fullpath"]

def main():
    mf = {m["sid"]: m for m in json.load(open(f"{RB}/batch_manifest.json"))}
    m = mf[64]
    m["cond_first"] = f"{RB}/cond/s064_first_clean.jpg"
    m["cond_last"] = f"{RB}/cond/s064_last_clean.jpg"
    m["audio"] = f"{RB}/audio/s064_vwin.wav"
    aligned = ((m["grid_frames"] + 3) // 4) * 4
    dur = round(aligned / 24.0, 4)
    cl = gray(f"{RB}/cond/s064_last_clean.jpg")
    cf = gray(f"{RB}/cond/s064_first_clean.jpg")
    results = []
    for seed in SEEDS:
        fp = render_one(m, dur, seed)
        if not fp:
            continue
        # 拷出到宿主可读位置
        local = f"/tmp/lot_{seed}.mp4"
        subprocess.run(["docker", "cp", f"comfyui-primary:{fp}", local], check=True)
        f0 = "/tmp/lot_f.jpg"; l0 = "/tmp/lot_l.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", local, "-vframes", "1", "-q:v", "3", f0], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.05", "-i", local, "-vframes", "1", "-q:v", "3", l0], check=True)
        ml, mf_ = mad(gray(l0), cl), mad(gray(f0), cf)
        results.append({"seed": seed, "path": local, "mad_last": round(ml,2), "mad_first": round(mf_,2)})
        print(f"seed {seed}: MAD last={ml:.2f} first={mf_:.2f}", flush=True)
    results.sort(key=lambda r: r["mad_last"])
    json.dump(results, open("/tmp/s064_lottery_results.json", "w"), indent=1)
    print("BEST:", results[0] if results else None, flush=True)

if __name__ == "__main__":
    main()
