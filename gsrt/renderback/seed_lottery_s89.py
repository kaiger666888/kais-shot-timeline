#!/usr/bin/env python3
"""GSRT-A2V shot89 seed 彩票批量：v4 锁定配方逐字克隆，唯一变量 = seed。
纪律依据: h3-ab-testing-methodology (同配方同台) + renderback-prompt-iteration (唯一变量=prompt/seed)。
v4 配方源: submit_a2v_s89_v4.py (T8 Audio Lock + FL2VA 首尾帧 + LightX2V 768p, steps=4, audio_denoise=0.0)
用法: python3 seed_lottery_s89.py [submit|poll|collect]
"""
import json, subprocess, sys, time, os, glob

BASE = "http://127.0.0.1:8188"
WD = "/data/workspace/kais-shot-timeline/gsrt/renderback"
OUT_DIR_GUESS = ["/data/workspace/comfyui-output/output", "/data/workspace/comfyui-output"]
SEEDS = [7, 100, 1234, 2026, 3141, 5926, 5358, 9793]
STATE = f"{WD}/lottery_state.json"

def n(cid, ct, **inp):
    return {"class_type": ct, "inputs": inp}

def build_wf(seed):
    wf = {}
    wf["1"] = n(1, "LoadAudio", audio="gsrt/s89_vocals.wav")
    wf["2"] = n(2, "MiniMaxH3AudioWindowT8", audio=["1", 0],
                scene_start_seconds=0.0, scene_duration_seconds=4.1,
                warmup_seconds=0.0, cooldown_seconds=0.0, ensure_minimum_context=True)
    wf["3"] = n(3, "VAELoader", vae_name="minimax_h3_video_vae_fp16.safetensors")
    wf["4"] = n(4, "VAELoader", vae_name="minimax_h3_audio_vae_fp32.safetensors")
    wf["5"] = n(5, "CLIPLoader", clip_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                type="minimax", device="default")
    wf["6"] = n(6, "UNETLoader", unet_name="minimax_h3_fl2va_int8_convrot.safetensors", weight_dtype="default")
    wf["17"] = n(17, "LoraLoaderBypassModelOnly", model=["6", 0],
                 lora_name="minimax_h3_turbo_4step_original_comfyui.safetensors",
                 strength_model=1.0, strength_clip=0.0)
    wf["7"] = n(7, "MiniMaxH3SigmaShift", model=["17", 0], shift_video=12.0, shift_audio=3.0)
    wf["18"] = n(18, "LoadImage", image="gsrt/s89_first_1344.jpg")
    wf["19"] = n(19, "LoadImage", image="gsrt/s89_last_1344.jpg")
    wf["8"] = n(8, "MiniMaxH3AudioConditioningT8",
                clip=["5", 0], video_vae=["3", 0], audio_vae=["4", 0],
                length=["2", 1], drive_audio=["2", 0],
                first_frame=["18", 0], last_frame=["19", 0],
                prompt="3D animation, Pixar-level rendering, cinematic shallow depth of field. Primeval forest, moss-covered fallen logs, towering trees. A green mantis warrior holds the drawn bamboo katana vertically at his front, blade tip pointing down, and holds this exact pose still. Beat 1 (first 45% of the shot): mantis stands upright, gripping the katana with both bandaged hands, blade tip down, eyes on the katana, almost motionless. Beat 2 (from 45% onward): mantis bows deeply forward from the waist, upper body folding until the back is arched high and the head hangs very low beside the vertical katana, eyes closed, the bow deepening continuously until the end of the shot; the katana never rises, never lifts, stays tip-down. An orange fuzzy caterpillar child in the far background covers its eyes with both paws, counting numbers aloud, fully diegetic sound, no other speech, no scored music, strictly diegetic in-world sound, unscored scene. Medium shot, eye level, locked camera, static tripod.",
                width=1344, height=768, task_type="FL2VA",
                audio_mode="lock_source", audio_denoise_strength=0.0,
                add_source_as_reference=False, prompt_primary_audio_ordinal=1,
                strict_prompt_tags=True, ref_image_size="match",
                reference_video_policy="official_2_to_15s")
    wf["9"] = n(9, "RandomNoise", noise_seed=seed)
    wf["10"] = n(10, "BasicGuider", model=["7", 0], conditioning=["8", 0])
    wf["11"] = n(11, "KSamplerSelect", sampler_name="res_multistep")
    wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=4, denoise=1.0)
    wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                 sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])
    wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0], video_vae=["3", 0], audio_vae=["4", 0])
    wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                 duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)
    wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                 frame_rate=24, loop_count=0,
                 filename_prefix=f"gsrt_a2v_s89_lot{seed}",
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                 save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True)
    return wf

def submit():
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    st.setdefault("submitted", {})
    results = []
    for seed in SEEDS:
        if str(seed) in st["submitted"]:
            results.append((seed, st["submitted"][str(seed)], "already"))
            continue
        payload = {"prompt": build_wf(seed), "client_id": "gsrt_a2v_lottery"}
        r = subprocess.run(["curl", "-s", "-m", "15", "-X", "POST", f"{BASE}/prompt",
                            "-H", "Content-Type: application/json",
                            "-d", json.dumps(payload)], capture_output=True, text=True)
        try:
            pid = json.loads(r.stdout)["prompt_id"]
            st["submitted"][str(seed)] = pid
            results.append((seed, pid, "queued"))
        except Exception:
            results.append((seed, r.stdout[:120] or r.stderr[:120], "FAIL"))
    json.dump(st, open(STATE, "w"), indent=1)
    for seed, pid, tag in results:
        print(f"seed={seed} {tag} pid={pid}")

def find_outputs():
    pats = []
    for d in OUT_DIR_GUESS:
        pats += glob.glob(f"{d}/gsrt_a2v_s89_lot*")
    return sorted(pats)

def poll():
    st = json.load(open(STATE))
    r = subprocess.run(["curl", "-s", "-m", "8", f"{BASE}/queue"], capture_output=True, text=True)
    q = json.loads(r.stdout)
    print("running:", len(q.get("queue_running", [])), "pending:", len(q.get("queue_pending", [])))
    outs = find_outputs()
    done = {}
    for f in outs:
        base = os.path.basename(f)
        if base.endswith(".mp4") and "-audio" not in base:
            seed = base.replace("gsrt_a2v_s89_lot", "").split("_")[0]
            done[seed] = f
    for seed in SEEDS:
        pid = st["submitted"].get(str(seed), "?")
        f = done.get(str(seed))
        print(f"seed={seed} pid={str(pid)[:8]} file={os.path.basename(f) if f else 'PENDING'}")

def collect():
    """把完成的渲染收编到 renders_a2v (容器 /root/ComfyUI/output 无宿主挂载, 走 docker cp)"""
    r = subprocess.run(["docker", "exec", "comfyui-primary", "ls", "/root/ComfyUI/output"],
                       capture_output=True, text=True)
    files = [f for f in r.stdout.split() if f.startswith("gsrt_a2v_s89_lot") and f.endswith(".mp4") and "-audio" not in f]
    for base in sorted(files):
        dst = f"{WD}/renders_a2v/{base}"
        if not os.path.exists(dst):
            subprocess.run(["docker", "cp", f"comfyui-primary:/root/ComfyUI/output/{base}", dst], check=True)
            print("collected:", base)
    if not files:
        print("(no lottery outputs yet)")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "submit"
    {"submit": submit, "poll": poll, "collect": collect}[cmd]()
