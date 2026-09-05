#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s064 smoke 修正渲染: 视频轴时长 + ensure_minimum_context=False.
根因(2026-09-03 Kai 质询实证): T8 AudioWindow 的 ensure_minimum_context 会把
<124f(5.17s) 的渲染撑到 5.17s 再居中 trim → 输出不含首尾锚点帧 → 尾帧失锁
(MAD 69-71 vs 锁定镜 2.5-13)。修法: scene_duration=对齐帧数/24, 禁撑窗。
"""
import json, subprocess, time, sys, os

RB = "/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01"
BASE = "http://127.0.0.1:8188"
OUTDIR = "ep01_batch_lx9_fix"

E = dict(lora="minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors",
         steps=9, sampler="euler", shift_video=6.0, seed=990202)

def n(cid, ct, **inp):
    return {"class_type": ct, "inputs": inp, "_meta": {"title": ct}}

def build_wf(m, dur):
    wf = {}
    wf["1"] = n(1, "LoadAudio", audio=m["audio"].replace(RB, "gsrt_batch"))
    wf["2"] = n(2, "MiniMaxH3AudioWindowT8", audio=["1", 0],
                scene_start_seconds=0.0, scene_duration_seconds=dur,
                warmup_seconds=0.0, cooldown_seconds=0.0, ensure_minimum_context=False)  # ← 关键
    wf["3"] = n(3, "VAELoader", vae_name="minimax_h3_video_vae_fp16.safetensors")
    wf["4"] = n(4, "VAELoader", vae_name="minimax_h3_audio_vae_fp32.safetensors")
    wf["5"] = n(5, "CLIPLoader", clip_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", type="minimax", device="default")
    wf["6"] = n(6, "UNETLoader", unet_name="minimax_h3_fl2va_int8_convrot.safetensors", weight_dtype="default")
    wf["17"] = n(17, "LoraLoaderModelOnly", model=["6", 0], lora_name=E["lora"], strength_model=1.0)
    wf["7"] = n(7, "MiniMaxH3SigmaShift", model=["17", 0], shift_video=E["shift_video"], shift_audio=3.0)
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
    wf["9"] = n(9, "RandomNoise", noise_seed=E["seed"])
    wf["10"] = n(10, "BasicGuider", model=["7", 0], conditioning=["8", 0])
    wf["11"] = n(11, "KSamplerSelect", sampler_name=E["sampler"])
    wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=E["steps"], denoise=1.0)
    wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                 sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])
    wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0], video_vae=["3", 0], audio_vae=["4", 0])
    wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                 duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)
    wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                 frame_rate=24, loop_count=0,
                 filename_prefix=f"{OUTDIR}/s{m['sid']:03d}_fix_seed{E['seed']}",
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                 save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True)
    return {"prompt": wf, "client_id": "ep01_s064_fix"}

def main():
    sid = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    mf = {m["sid"]: m for m in json.load(open(f"{RB}/batch_manifest.json"))}
    m = mf[sid]
    # 干净条件帧 + 视频轴音频（源头直抽, 0902 精确切法）
    m["cond_first"] = f"{RB}/cond/s064_first_clean.jpg"
    m["cond_last"] = f"{RB}/cond/s064_last_clean.jpg"
    m["audio"] = f"{RB}/audio/s064_vwin.wav"
    frames = m["grid_frames"]
    aligned = ((frames + 3) // 4) * 4
    dur = round(aligned / 24.0, 4)
    print(f"s{sid:03d}: video-axis dur={dur}s ({aligned}f, grid {frames}f), min-context OFF", flush=True)
    os.makedirs(f"{RB}/{OUTDIR}", exist_ok=True)
    r = subprocess.run(["curl", "-s", "-X", "POST", f"{BASE}/prompt",
                        "-H", "Content-Type: application/json",
                        "-d", json.dumps(build_wf(m, dur))], capture_output=True, text=True)
    pid = json.loads(r.stdout)["prompt_id"]
    print("submitted:", pid, flush=True)
    t0 = time.time()
    while True:
        time.sleep(10)
        h = subprocess.run(["curl", "-s", f"{BASE}/history/{pid}"], capture_output=True, text=True).stdout
        hd = json.loads(h)
        if pid in hd:
            st = hd[pid].get("status", {})
            if st.get("status_str") == "error":
                print("ERROR:", json.dumps(st.get("details", ""))[:400]); sys.exit(1)
            outs = hd[pid].get("outputs", {})
            for node, o in outs.items():
                for g in o.get("gifs", []):
                    print(f"DONE {g['filepath']} ({time.time()-t0:.0f}s)", flush=True)
                    sys.exit(0)
            print("completed but no gifs??", json.dumps(outs)[:300]); sys.exit(1)

if __name__ == "__main__":
    main()
