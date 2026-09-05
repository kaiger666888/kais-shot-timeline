#!/usr/bin/env python3
"""EP01 lx9 全量批量渲染 (引擎参数化版, 2026-09-03).

根治: 引擎写死导致漂移于 KAP 平台定案 → --engine {turbo,lx9} 双臂可选。
特判镜:
  s070 (19.73s/481f 超训练域 362f) → 用 long_video in-node loop 分段, 或跳过留人工
  s093 (黑底字卡镜) → 跳过 H3 (幻觉区), 留 PIL 合成
默认放量臂 = lx9 (KMC 08-31 blind3 定案, KAP config.ts H3_EXPOSED 白名单)。
用法:
  python3 batch_render_ep01_v2.py --engine lx9 --all --seed 990202
  python3 batch_render_ep01_v2.py --engine lx9 --sids 1,2,3 --seed 990202
"""
import json, subprocess, time, sys, os, argparse

RB = "/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01"
BASE = "http://127.0.0.1:8188"

ENGINES = {
    "turbo": {
        "dir": "renders",
        "lora": "minimax_h3_turbo_4step_original_comfyui.safetensors",
        "lora_loader": "LoraLoaderBypassModelOnly",
        "steps": 4, "sampler": "res_multistep", "shift_video": 12.0,
    },
    "lx9": {
        "dir": "renders_lightx2v9",
        "lora": "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors",
        "lora_loader": "LoraLoaderModelOnly",
        "steps": 9, "sampler": "euler", "shift_video": 6.0,
    },
}
SKIP_SIDS = {70: "超训练域(481f>362f) 需 long-video 分段路线", 93: "黑底字卡镜 H3 幻觉区 → PIL 合成"}
MAX_TRAIN_FRAMES = 362

def n(cid, ct, **inp):
    return {"class_type": ct, "inputs": inp, "_meta": {"title": ct}}

def build_wf(m, seed, E):
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
    wf["17"] = n(17, E["lora_loader"], model=["6", 0], lora_name=E["lora"], strength_model=1.0)
    wf["7"] = n(7, "MiniMaxH3SigmaShift", model=["17", 0], shift_video=E["shift_video"], shift_audio=3.0)
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
    wf["11"] = n(11, "KSamplerSelect", sampler_name=E["sampler"])
    wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=E["steps"], denoise=1.0)
    wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                 sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])
    wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0], video_vae=["3", 0], audio_vae=["4", 0])
    wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                 duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)
    outdir = E["outdir"]
    wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                 frame_rate=24, loop_count=0,
                 filename_prefix=f"{outdir}/s{m['sid']:03d}_seed{seed}",
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                 save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True)
    return {"prompt": {k: v for k, v in wf.items()}, "client_id": f"ep01_batch_{outdir}"}

def load_json(p):
    return json.load(open(p)) if os.path.exists(p) else {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=list(ENGINES), default="lx9")
    ap.add_argument("--sids"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=990202)
    ap.add_argument("--include-special", action="store_true", help="不跳过特判镜(慎用)")
    args = ap.parse_args()
    E = ENGINES[args.engine]
    E["outdir"] = "ep01_batch" if args.engine == "turbo" else "ep01_batch_lx9"
    OUTDIR = f"{RB}/{E['dir']}"
    STATE = f"{OUTDIR}/batch_state_{args.engine}.json"
    os.makedirs(OUTDIR, exist_ok=True)
    manifest = {int(m["sid"]): m for m in json.load(open(f"{RB}/batch_manifest.json"))}
    state = load_json(STATE)
    if args.all:
        targets = sorted(manifest)
    else:
        targets = sorted(int(x) for x in args.sids.split(","))
    skipped = []
    for sid in list(targets):
        if sid in SKIP_SIDS and not args.include_special:
            skipped.append(sid)
            targets.remove(sid)
    if skipped:
        print(f"[SKIP] {[(s, SKIP_SIDS[s]) for s in skipped]}", flush=True)
    print(f"=== EP01 batch v2 engine={args.engine} lora={E['lora'][:40]} steps={E['steps']} "
          f"sampler={E['sampler']} shift={E['shift_video']} | {len(targets)} shots seed={args.seed} ===", flush=True)
    ok = 0
    for i, sid in enumerate(targets):
        m = manifest[sid]
        if m["grid_frames"] > MAX_TRAIN_FRAMES and not args.include_special:
            print(f"[{i+1}/{len(targets)}] SKIP s{sid:03d}: {m['grid_frames']}f 超训练域", flush=True)
            continue
        if state.get(str(sid), {}).get("done"):
            print(f"[{i+1}/{len(targets)}] s{sid:03d} skip (done)", flush=True); ok += 1
            continue
        wf = build_wf(m, args.seed, E)
        r = subprocess.run(["curl", "-s", "-X", "POST", f"{BASE}/prompt",
                            "-H", "Content-Type: application/json",
                            "-d", json.dumps(wf)], capture_output=True, text=True, timeout=60)
        try:
            pid = json.loads(r.stdout)["prompt_id"]
        except Exception:
            print(f"[{i+1}] s{sid:03d} SUBMIT FAIL: {r.stdout[:260]}", flush=True)
            state[str(sid)] = {"done": False, "error": r.stdout[:260]}
            json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
            continue
        t0 = time.time()
        result = None
        while True:
            time.sleep(15)
            try:
                h = subprocess.run(["curl", "-s", f"{BASE}/history/{pid}"],
                                   capture_output=True, text=True, timeout=30).stdout
                hd = json.loads(h)
            except Exception:
                hd = {}
            if pid in hd:
                e = hd[pid].get("status", {})
                if e.get("status_str") == "error":
                    print(f"[{i+1}] s{sid:03d} RENDER ERROR: {json.dumps(e.get('details',''))[:300]}", flush=True)
                    state[str(sid)] = {"done": False, "error": str(e.get("details"))[:300]}
                    json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
                    break
                vids = [g["filename"] for o in hd[pid].get("outputs", {}).values()
                        for g in o.get("gifs", [])]
                if vids:
                    mins = (time.time()-t0)/60
                    state[str(sid)] = {"done": True, "status": "success", "files": vids,
                                       "seed": args.seed, "prompt_id": pid, "engine": args.engine,
                                       "finished": time.strftime("%m-%d %H:%M")}
                    json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
                    print(f"[{i+1}] s{sid:03d} DONE {vids[0]} ({mins:.1f}min)", flush=True)
                    ok += 1
                    break
            if time.time() - t0 > 2700:
                print(f"[{i+1}] s{sid:03d} TIMEOUT 45min", flush=True)
                state[str(sid)] = {"done": False, "error": "timeout"}
                json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
                break
    print(f"=== BATCH DONE: {ok}/{len(targets)} (engine={args.engine}) ===", flush=True)

if __name__ == "__main__":
    main()
