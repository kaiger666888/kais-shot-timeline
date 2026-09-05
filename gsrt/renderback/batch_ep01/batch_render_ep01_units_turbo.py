#!/usr/bin/env python3
"""EP01 unit-v2 × turbo 4-step 臂: 与 units_v2 (lx9) 唯一变量=引擎.
目的: 分离"静态化"根因——cond换新(跨切→单元) vs 引擎换挡(turbo→lx9).
同 seed 990202 / 同 prompt / 同单元cond / 同音窗.
"""
import json, subprocess, time, sys, os, argparse

RB = "/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01"
OUTDIR = f"{RB}/renders_units_turbo"
BASE = "http://127.0.0.1:8188"
MANIFEST = f"{RB}/batch_manifest_units.json"
LORA = "minimax_h3_turbo_4step_original_comfyui.safetensors"

def n(cid, ct, **inp):
    return {"class_type": ct, "inputs": inp, "_meta": {"title": ct}}

def build_wf(m, seed):
    a0, a1 = m["audio_win"]
    dur = round(a1 - a0, 2)
    wf = {}
    wf["1"] = n(1, "LoadAudio", audio=m["audio"].replace(RB, "gsrt_batch"))
    wf["2"] = n(2, "MiniMaxH3AudioWindowT8", audio=["1", 0],
                scene_start_seconds=0.0, scene_duration_seconds=dur,
                warmup_seconds=0.0, cooldown_seconds=0.0, ensure_minimum_context=True)
    wf["3"] = n(3, "VAELoader", vae_name="minimax_h3_video_vae_fp16.safetensors")
    wf["4"] = n(4, "VAELoader", vae_name="minimax_h3_audio_vae_fp32.safetensors")
    wf["5"] = n(5, "CLIPLoader", clip_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", type="minimax", device="default")
    wf["6"] = n(6, "UNETLoader", unet_name="minimax_h3_fl2va_int8_convrot.safetensors", weight_dtype="default")
    # 引擎差异点1: turbo LoRA + Bypass loader (S89 v4 中奖配方原样)
    wf["17"] = n(17, "LoraLoaderBypassModelOnly", model=["6", 0],
                 lora_name=LORA, strength_model=1.0, strength_clip=0.0)
    # 差异点2: shift_video 12.0
    wf["7"] = n(7, "MiniMaxH3SigmaShift", model=["17", 0], shift_video=12.0, shift_audio=3.0)
    wf["18"] = n(18, "LoadImage", image=m["cond_first"].replace(RB, "gsrt_batch"))
    wf["19"] = n(19, "LoadImage", image=m["cond_last"].replace(RB, "gsrt_batch"))
    wf["8"] = n(8, "MiniMaxH3AudioConditioningT8",
                clip=["5", 0], video_vae=["3", 0], audio_vae=["4", 0],
                length=["2", 1],
                drive_audio=["2", 0],
                first_frame=["18", 0], last_frame=["19", 0],
                prompt=m["h3_prompt"] + (" " + m["dialogue_line"] if m.get("dialogue_line") else ""),
                width=1344, height=768,
                task_type="FL2VA",
                audio_mode="lock_source",
                audio_denoise_strength=0.0,
                add_source_as_reference=False,
                prompt_primary_audio_ordinal=1,
                strict_prompt_tags=True,
                ref_image_size="match",
                reference_video_policy="official_2_to_15s")
    wf["9"] = n(9, "RandomNoise", noise_seed=seed)
    wf["10"] = n(10, "BasicGuider", model=["7", 0], conditioning=["8", 0])
    # 差异点3/4: res_multistep + 4步
    wf["11"] = n(11, "KSamplerSelect", sampler_name="res_multistep")
    wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=4, denoise=1.0)
    wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                 sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])
    wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0],
                 video_vae=["3", 0], audio_vae=["4", 0])
    wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                 duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)
    wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                 frame_rate=24, loop_count=0,
                 filename_prefix=f"ep01_units_turbo/s{m['sid']:03d}_seed{seed}",
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                 save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True)
    return {"prompt": wf, "client_id": "ep01_units_turbo"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sids", default="64,89,92")
    ap.add_argument("--seed", type=int, default=990202)
    args = ap.parse_args()
    man = json.load(open(MANIFEST))
    shots = {it["sid"]: it for it in man["shots"]}
    for sid in [int(x) for x in args.sids.split(",")]:
        m = shots[sid]
        wf = build_wf(m, args.seed)
        r = subprocess.run(["curl", "-s", "-X", "POST", f"{BASE}/prompt",
                            "-H", "Content-Type: application/json",
                            "-d", json.dumps(wf)], capture_output=True, text=True)
        try:
            pid = json.loads(r.stdout)["prompt_id"]
        except Exception:
            print(f"s{sid} submit FAIL: {r.stdout[:300]}"); sys.exit(1)
        print(f"s{sid} turbo submitted pid={pid}", flush=True)
        t0 = time.time()
        while True:
            time.sleep(20)
            h = json.loads(subprocess.run(["curl","-s",f"{BASE}/history/{pid}"],capture_output=True,text=True).stdout or "{}")
            if pid in h:
                print(f"s{sid} turbo DONE in {round(time.time()-t0)}s status={h[pid]['status'].get('status_str')}", flush=True)
                break
            if time.time() - t0 > 1500:
                print(f"s{sid} TIMEOUT", flush=True); sys.exit(2)

if __name__ == "__main__":
    main()
