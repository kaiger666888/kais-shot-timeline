#!/usr/bin/env python3
"""EP01 物理单元全量批渲 (units_full pass_A): 80 整镜单元, 试点配方原样放大.
配方铁律(试点验证): 端点cond=窗start/end帧direct拉伸; 音频=单元wav全窗 -t精确截断;
                   engine=FL2VA int8-convrot + lightx2v-8 768p 9步 + seed 990202 恒定;
                   1344x768; audio_mode=lock_source; sigma shift 6/3.
断点续跑: 渲染成功(状态文件)即跳过; 状态JSONL逐单元落盘.
"""
import json, subprocess, time, sys, os, argparse

RB = "/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01"
OUTDIR = "ep01_units_full"
BASE = "http://127.0.0.1:8188"
MANIFEST = f"{RB}/batch_manifest_units_full.json"
STATE = f"{RB}/units_full_state.jsonl"
LORA = "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors"

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
    wf["17"] = n(17, "LoraLoaderModelOnly", model=["6", 0],
                 lora_name=LORA, strength_model=1.0)
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
    wf["11"] = n(11, "KSamplerSelect", sampler_name="euler")
    wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=9, denoise=1.0)
    wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                 sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])
    wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0],
                 video_vae=["3", 0], audio_vae=["4", 0])
    wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                 duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)
    wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                 frame_rate=24, loop_count=0,
                 filename_prefix=f"{OUTDIR}/{m['uid']}_seed{seed}",
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                 save_metadata=True, trim_to_audio=False, pingpong=False, save_output=True)
    return {"prompt": wf, "client_id": "ep01_units_full"}

def log_state(rec):
    with open(STATE, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def done_uids():
    if not os.path.exists(STATE):
        return set()
    out = set()
    for line in open(STATE):
        try:
            r = json.loads(line)
            if r.get("status") == "success":
                out.add(r["uid"])
        except Exception:
            pass
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=990202)
    ap.add_argument("--limit", type=int, default=0, help="最多渲 N 个单元(0=全部)")
    ap.add_argument("--only", default="", help="逗号分隔 uid 列表(调试用)")
    args = ap.parse_args()

    man = json.load(open(MANIFEST))
    shots = [s for s in man["shots"] if s.get("ready")]
    if args.only:
        want = set(args.only.split(","))
        shots = [s for s in shots if s["uid"] in want]
    done = done_uids()
    todo = [s for s in shots if s["uid"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"总就绪 {len(shots)} | 已完成 {len(done)} | 待渲 {len(todo)}", flush=True)

    t_batch = time.time()
    ok = fail = 0
    for i, m in enumerate(todo, 1):
        t0 = time.time()
        wf = build_wf(m, args.seed)
        r = subprocess.run(["curl", "-s", "-X", "POST", f"{BASE}/prompt",
                            "-H", "Content-Type: application/json",
                            "-d", json.dumps(wf)], capture_output=True, text=True)
        try:
            pid = json.loads(r.stdout)["prompt_id"]
        except Exception:
            print(f"[{i}/{len(todo)}] {m['uid']} SUBMIT FAIL: {r.stdout[:200]}", flush=True)
            log_state({"uid": m["uid"], "status": "submit_fail", "ts": time.time()})
            fail += 1
            continue
        print(f"[{i}/{len(todo)}] {m['uid']} (dur={m['render_dur']}s) pid={pid}", flush=True)
        status = "timeout"
        while True:
            time.sleep(20)
            h = json.loads(subprocess.run(["curl", "-s", f"{BASE}/history/{pid}"],
                                          capture_output=True, text=True).stdout or "{}")
            if pid in h:
                st = h[pid].get("status", {})
                status = st.get("status_str", "unknown")
                break
            if time.time() - t0 > 2400:
                break
        rec = {"uid": m["uid"], "pid": pid, "status": status,
               "sec": round(time.time() - t0), "ts": time.time()}
        if status == "success":
            # 产物回拷宿主机
            rc = subprocess.run(f"docker cp comfyui-primary:/root/ComfyUI/output/{OUTDIR}/. {RB}/{OUTDIR}/ 2>/dev/null",
                                shell=True, capture_output=True)
            rec["copied"] = (rc.returncode == 0)
        log_state(rec)
        if status == "success":
            ok += 1
            print(f"    DONE {rec['sec']}s ✓ ({round((time.time()-t_batch)/60,1)}min 批计)", flush=True)
        else:
            fail += 1
            print(f"    FAIL status={status}", flush=True)
            # 连续3失败熔断
            if fail >= 3 and ok == 0:
                print("连续3失败且零成功 → 熔断停止", flush=True)
                sys.exit(2)
    print(f"\n批渲完成: ok={ok} fail={fail} 总耗时 {round((time.time()-t_batch)/3600,2)}h", flush=True)

if __name__ == "__main__":
    main()
