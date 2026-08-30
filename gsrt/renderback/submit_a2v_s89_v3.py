#!/usr/bin/env python3
"""GSRT-A2V shot89: T8 Audio Lock (lock_source) 原片数数台词驱动 + FL2VA 首尾帧
拓扑基座 = T8 官方 audio_lock_api.json，变更：
  1. 首尾帧接 ConditioningT8 first_frame/last_frame + add_source_as_reference=False
     (skill h3-t8-audio-lock-tts-driven: False+有帧=i2va/fl2va 路径, 不触发 hybrid shape mismatch)
  2. audio_denoise_strength=0.0 (完全锁定音频, 输出即原片数数声)
  3. task_type=FL2VA 显式
  4. LightX2V 8-step v1.0 768p (blind3 同台盲测全胜的 P11b 生产档)
"""
import json, subprocess, time, sys

BASE = "http://127.0.0.1:8188"
SEED = 42
LENGTH = 90  # 17n+5 grid, 3.75s (音频 4.1s, OutputTrim 裁齐)

def n(cid, ct, **inp):
    return str(cid), {"class_type": ct, "inputs": inp}

wf = {}
# 音频链
wf["1"] = n(1, "LoadAudio", audio="gsrt/s89_vocals.wav")[1]
wf["2"] = n(2, "MiniMaxH3AudioWindowT8", audio=["1", 0],
               scene_start_seconds=0.0, scene_duration_seconds=4.1,
               warmup_seconds=0.0, cooldown_seconds=0.0,
               ensure_minimum_context=True)[1]
# 模型
wf["3"] = n(3, "VAELoader", vae_name="minimax_h3_video_vae_fp16.safetensors")[1]
wf["4"] = n(4, "VAELoader", vae_name="minimax_h3_audio_vae_fp32.safetensors")[1]
wf["5"] = n(5, "CLIPLoader", clip_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
               type="minimax", device="default")[1]
wf["6"] = n(6, "UNETLoader",
               unet_name="minimax_h3_fl2va_int8_convrot.safetensors", weight_dtype="default")[1]
wf["17"] = n(17, "LoraLoaderBypassModelOnly",
             model=["6", 0],
             lora_name="minimax_h3_turbo_4step_original_comfyui.safetensors",
             strength_model=1.0, strength_clip=0.0)[1]
wf["7"] = n(7, "MiniMaxH3SigmaShift", model=["17", 0], shift_video=12.0, shift_audio=3.0)[1]
# LightX2V 8-step (生产档) — bypass 到 SigmaShift 输出
wf["18"] = n(18, "LoadImage", image="gsrt/s89_first_1344.jpg")[1]
wf["19"] = n(19, "LoadImage", image="gsrt/s89_last_1344.jpg")[1]
# Conditioning — lock_source + FL2VA + 首尾帧
wf["8"] = n(8, "MiniMaxH3AudioConditioningT8",
               clip=["5", 0], video_vae=["3", 0], audio_vae=["4", 0],
               length=["2", 1],
               drive_audio=["2", 0],
               first_frame=["18", 0],
               last_frame=["19", 0],
               prompt="3D animation, Pixar-level rendering, cinematic shallow depth of field. Primeval forest, moss-covered fallen logs, towering trees. A green mantis warrior holds the drawn bamboo katana vertically at his front, blade tip pointing down, and holds this exact pose still. Beat 1 (first half of the shot): mantis stands upright, gripping the katana with both bandaged hands, blade tip down, eyes on the katana, almost motionless. Beat 2 (second half): mantis bows deeply forward from the waist, head lowering beside the vertical katana, eyes closed, holding the reverent bow till the end; the katana never rises, never lifts, stays tip-down. An orange fuzzy caterpillar child in the far background covers its eyes with both paws, counting numbers aloud, fully diegetic sound, no other speech, no scored music, strictly diegetic in-world sound, unscored scene. Medium shot, eye level, locked camera, static tripod.",
               width=1344, height=768,
               task_type="FL2VA",
               audio_mode="lock_source",
               audio_denoise_strength=0.0,
               add_source_as_reference=False,
               prompt_primary_audio_ordinal=1,
               strict_prompt_tags=True,
               ref_image_size="match",
               reference_video_policy="official_2_to_15s")[1]
# 采样 (9步 ≈ blind3 定案 lightx2v-8 profile 的 9 步)
wf["9"] = n(9, "RandomNoise", noise_seed=SEED)[1]
wf["10"] = n(10, "BasicGuider", model=["7", 0], conditioning=["8", 0])[1]
wf["11"] = n(11, "KSamplerSelect", sampler_name="res_multistep")[1]
wf["12"] = n(12, "BasicScheduler", model=["7", 0], scheduler="simple", steps=4, denoise=1.0)[1]
wf["13"] = n(13, "SamplerCustomAdvanced", noise=["9", 0], guider=["10", 0],
                sampler=["11", 0], sigmas=["12", 0], latent_image=["8", 1])[1]
# 解码 + 裁剪 + 输出
wf["14"] = n(14, "MiniMaxH3AVDecodeT8", av_latent=["13", 0],
                video_vae=["3", 0], audio_vae=["4", 0])[1]
wf["15"] = n(15, "MiniMaxH3OutputTrimT8", start_seconds=["2", 2],
                duration_seconds=["2", 3], frames=["14", 0], audio=["8", 2], fps=24.0)[1]
wf["16"] = n(16, "VHS_VideoCombine", images=["15", 0], audio=["15", 1],
                frame_rate=24, loop_count=0,
                filename_prefix="gsrt_a2v_s89_v3",
                format="video/h264-mp4", pix_fmt="yuv420p", crf=19,
                save_metadata=True, trim_to_audio=False,
                pingpong=False, save_output=True)[1]


payload = {"prompt": {k: v for k, v in wf.items()}, "client_id": "gsrt_a2v"}
r = subprocess.run(["curl", "-s", "-m", "15", "-X", "POST", f"{BASE}/prompt",
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps(payload)], capture_output=True, text=True)
print("submit:", r.stdout[:300] or r.stderr[:300])
try:
    pid = json.loads(r.stdout)["prompt_id"]
    print("PROMPT_ID:", pid)
    open("/tmp/gsrt_a2v_s89.pid", "w").write(pid)
except Exception as e:
    print("PARSE FAIL:", e)
    sys.exit(1)
