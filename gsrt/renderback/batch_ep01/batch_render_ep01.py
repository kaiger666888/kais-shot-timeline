#!/usr/bin/env python3
"""EP01 全镜批量首尾帧渲染队列 (FL2VA + T8 audio_lock) — H3 :8188
从 batch_manifest.json 逐镜构建工作流并串行渲染（GPU 独占单队列）。
用法: python3 batch_render_ep01.py --sids 89,92 --seed 990202
     python3 batch_render_ep01.py --all --seed 990202
"""
import json, subprocess, time, sys, os, argparse

RB = "/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01"
BASE = "http://127.0.0.1:8188"
STATE = f"{RB}/batch_state.json"

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
    wf["17"] = n(17, "LoraLoaderBypassModelOnly", model=["6", 0],
                 lora_name="minimax_h3_turbo_4step_original_comfyui.safetensors",
                 strength_model=1.0, strength_clip=0.0)
    wf["7"] = n(7, "MiniMaxH3SigmaShift", model=["17", 0], shift_video=12.0, shift_audio=3.0)
    wf["18"] = n(18, "LoadImage", image=m["cond_first"].replace(RB, "gsrt_batch"))
    wf["19"] = n(19, "LoadImage", image=m["cond_last"].replace(RB, "gsrt_batch"))
    wf["8"] = n(8, "MiniMaxH3AudioConditioningT8",
                clip=["5", 0], video_vae=["3", 0], audio_vae=["4", 0],
                length=["2", 1],  # v4 中奖配方: AudioWindow 自动网格对齐长度 (17n+5>=窗), OutputTrim 裁齐
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
    wf["11"] = n(11, "KSamplerSelect", sampler_name="res_multistep")
    wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=4, denoise=1.0)  # v4 中奖配方
    wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                 sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])
    wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0],
                 video_vae=["3", 0], audio_vae=["4", 0])
    wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                 duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)
    wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                 frame_rate=24, loop_count=0,
                 filename_prefix=f"ep01_batch/s{m['sid']:03d}_seed{seed}",
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                 save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True)
    return {"prompt": {k: v for k, v in wf.items()}, "client_id": "ep01_batch"}

def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {}

def save_state(st):
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)

def render_one(m, seed):
    st = load_state()
    key = str(m["sid"])
    if st.get(key, {}).get("done") and st[key].get("seed") == seed:
        print(f"[skip] s{m['sid']:03d} already done (seed={seed})")
        return True
    payload = build_wf(m, seed)
    r = subprocess.run(["curl", "-s", "-m", "15", "-X", "POST", f"{BASE}/prompt",
                        "-H", "Content-Type: application/json",
                        "-d", json.dumps(payload)], capture_output=True, text=True)
    try:
        pid = json.loads(r.stdout)["prompt_id"]
    except Exception as e:
        print(f"[ERR ] s{m['sid']:03d} submit fail: {r.stdout[:200]}")
        st[key] = {"done": False, "error": f"submit: {r.stdout[:150]}", "seed": seed}
        save_state(st)
        return False
    # 轮询完成
    for i in range(80):  # 40min 上限
        time.sleep(30)
        h = subprocess.run(["curl", "-s", "-m", "10", f"{BASE}/history/{pid}"],
                           capture_output=True, text=True).stdout
        try:
            hj = json.loads(h)
        except Exception:
            continue
        if hj:
            e = list(hj.values())[0]
            status = e.get("status", {}).get("status_str", "?")
            outs = []
            for nid, o in e.get("outputs", {}).items():
                for g in o.get("gifs", []):
                    outs.append(g.get("filename"))
            st = load_state()
            st[key] = {"done": status == "success", "status": status,
                       "files": outs, "seed": seed, "prompt_id": pid,
                       "finished": time.strftime("%m-%d %H:%M")}
            save_state(st)
            if status == "success":
                print(f"[OK  ] s{m['sid']:03d} {outs}")
                return True
            else:
                print(f"[FAIL] s{m['sid']:03d} status={status}")
                return False
    st = load_state()
    st[key] = {"done": False, "error": "timeout 40min", "seed": seed}
    save_state(st)
    return False

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sids", help="comma list, e.g. 89,92")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=990202)
    args = ap.parse_args()
    mf = json.load(open(f"{RB}/batch_manifest.json"))
    mf.sort(key=lambda m: m["sid"])
    if args.all:
        targets = mf
    else:
        want = set(int(x) for x in args.sids.split(","))
        targets = [m for m in mf if m["sid"] in want]
    print(f"=== EP01 batch render: {len(targets)} shots, seed={args.seed} ===")
    ok = 0
    for i, m in enumerate(targets):
        print(f"[{i+1}/{len(targets)}] s{m['sid']:03d} ({m['dur']}s -> {m['grid_frames']}f)")
        if render_one(m, args.seed):
            ok += 1
    print(f"=== BATCH DONE: {ok}/{len(targets)} ===")
