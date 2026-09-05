#!/usr/bin/env python3
"""EP01 smoke3 修正臂: KAP 定案引擎 lightx2v-8-768p 9步 重渲 s064/s089/s092.
同 seed / 同 prompt / 同条件帧 / 同音窗, 唯一变量 = 采样引擎:
  turbo(旧臂, 已渲) → lightx2v-8-768p (blind3 定案 preview 档)
差异点 per KAP config.ts:
  - LoRA: minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16
  - steps: 9 (8+1终步sigma=0), scheduler simple, sampler euler
  - shift_video 6.0 (768p 官方值; turbo 臂用 12.0)
  - LoRA loader: LoraLoaderModelOnly (lightx2v 家族用 ModelOnly, 非 Bypass)
其余 (T8 AudioLock + FL2VA + AudioWindow + OutputTrim) 与 turbo 臂完全同构.
"""
import json, subprocess, time, sys, os, argparse

RB = "/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01"
OUTDIR = f"{RB}/renders_lightx2v9"
BASE = "http://127.0.0.1:8188"
STATE = f"{OUTDIR}/batch_state_lightx2v9.json"
LORA = "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors"

def n(cid, ct, **inp):
    return {"class_type": ct, "inputs": inp, "_meta": {"title": ct}}

def build_wf(m, seed):
    L = m["grid_frames"]
    a0, a1 = m["audio_win"]
    wf = {}
    wf["1"] = n(1, "LoadAudio", audio=m["audio"].replace(RB, "gsrt_batch"))
    wf["2"] = n(2, "MiniMaxH3AudioWindowT8", audio=["1", 0],
                scene_start_seconds=0.0, scene_duration_seconds=round(a1-a0, 2),
                warmup_seconds=0.0, cooldown_seconds=0.0, ensure_minimum_context=True)
    wf["3"] = n(3, "VAELoader", vae_name="minimax_h3_video_vae_fp16.safetensors")
    wf["4"] = n(4, "VAELoader", vae_name="minimax_h3_audio_vae_fp32.safetensors")
    wf["5"] = n(5, "CLIPLoader", clip_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", type="minimax", device="default")
    wf["6"] = n(6, "UNETLoader", unet_name="minimax_h3_fl2va_int8_convrot.safetensors", weight_dtype="default")
    # 差异点1: LoRA 换 lightx2v-8-768p v1.0 正式版; loader 用 ModelOnly (KAP lightx2v 链路规格)
    wf["17"] = n(17, "LoraLoaderModelOnly", model=["6", 0],
                 lora_name=LORA, strength_model=1.0)
    # 差异点2: shift_video 6.0 (768p 官方) — turbo 臂是 12.0
    wf["7"] = n(7, "MiniMaxH3SigmaShift", model=["17", 0], shift_video=6.0, shift_audio=3.0)
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
    # 差异点3: sampler euler (官方 training_euler); turbo 臂是 res_multistep
    wf["11"] = n(11, "KSamplerSelect", sampler_name="euler")
    # 差异点4: steps 9 (8+1); turbo 臂是 4
    wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=9, denoise=1.0)
    wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                 sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])
    wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0],
                 video_vae=["3", 0], audio_vae=["4", 0])
    wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                 duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)
    wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                 frame_rate=24, loop_count=0,
                 filename_prefix=f"ep01_batch_lx9/s{m['sid']:03d}_seed{seed}",
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                 save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True)
    return {"prompt": {k: v for k, v in wf.items()}, "client_id": "ep01_batch_lx9"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sids", default="64,89,92")
    ap.add_argument("--seed", type=int, default=990202)
    args = ap.parse_args()
    sids = [int(x) for x in args.sids.split(",")]
    os.makedirs(OUTDIR, exist_ok=True)
    manifest = {int(m["sid"]): m for m in json.load(open(f"{RB}/batch_manifest.json"))}
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    # output dir 映射: 容器 /root/ComfyUI/output -> 宿主机
    import glob
    host_out = glob.glob("/data/models/comfyui/output") + glob.glob("/data/comfyui/output")
    for sid in sids:
        if state.get(str(sid), {}).get("done"):
            print(f"[s{sid:03d}] skip (done)", flush=True); continue
        m = manifest[sid]
        wf = build_wf(m, args.seed)
        r = subprocess.run(["curl", "-s", "-X", "POST", f"{BASE}/prompt",
                            "-H", "Content-Type: application/json",
                            "-d", json.dumps(wf)], capture_output=True, text=True, timeout=60)
        try:
            pid = json.loads(r.stdout)["prompt_id"]
        except Exception:
            print(f"[s{sid:03d}] SUBMIT FAIL: {r.stdout[:300]}", flush=True)
            sys.exit(1)
        print(f"[s{sid:03d}] submitted {pid}", flush=True)
        t0 = time.time()
        while True:
            time.sleep(15)
            h = subprocess.run(["curl", "-s", f"{BASE}/history/{pid}"],
                               capture_output=True, text=True, timeout=30).stdout
            hd = json.loads(h)
            if pid in hd:
                e = hd[pid].get("status", {})
                if e.get("status_str") == "error":
                    print(f"[s{sid:03d}] RENDER ERROR: {json.dumps(e.get('details',''))[:400]}", flush=True)
                    sys.exit(1)
                outs = hd[pid].get("outputs", {})
                vids = []
                for nid, o in outs.items():
                    for g in o.get("gifs", []):
                        vids.append(g["filename"])
                if vids:
                    state[str(sid)] = {"done": True, "status": "success", "files": vids,
                                       "seed": args.seed, "prompt_id": pid,
                                       "engine": "lightx2v-8-768p-9step",
                                       "finished": time.strftime("%m-%d %H:%M")}
                    json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
                    print(f"[s{sid:03d}] DONE {vids} ({(time.time()-t0)/60:.1f}min)", flush=True)
                    break
            if time.time() - t0 > 1500:
                print(f"[s{sid:03d}] TIMEOUT 25min", flush=True); sys.exit(1)

if __name__ == "__main__":
    main()
