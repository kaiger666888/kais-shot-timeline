# Stack Research — v1.2 音频语义深化 (Audio Semantic Deepening)

**Domain:** Route-based three-modality audio semantic analysis (dialogue + music + sfx) + layered reproduction prompts (TTS / music-gen / foley), layered on top of the validated v1.0 Demucs+Whisper baseline and the v1.1 route-based cinematography pattern. Producer-side thin httpx client + heavy-ML route host.
**Researched:** 2026-07-25
**Confidence:** **HIGH** for production-ready picks (WhisperX, pyannote.audio 3.1, SenseVoice, librosa, CosyVoice, GPT-SoVITS — all verified against official repos / HuggingFace model cards); **MEDIUM** for MIR (MERT vs PANNs is a Phase 1 risk-validation call, not a paper claim — no head-to-head benchmark on Chinese pop exists); **MEDIUM** for music-gen/sfx targets (most open-weights models are NC-licensed — commercial path needs separate roadmap decision).

> Scope: ONLY stack additions/changes for **v1.2 NEW capabilities**. The validated v1.0 baseline (PySceneDetect / Demucs htdemucs / faster-whisper / ffmpeg / jsonschema) and v1.1 route-based cinematography pattern are OUT OF SCOPE — already shipped.

---

## TL;DR — The Split That Governs Everything

v1.2 inherits v1.1's `call_shot_analysis.py` shape: **heavy ML lives in `kais-aigc-platform/audio-analysis` route; `shot-timeline` stays a thin httpx client with ZERO new ML deps.**

| Side | Adds | Forbids |
|------|------|---------|
| **`kais-aigc-platform/audio-analysis` route (cross-repo)** | WhisperX, pyannote.audio 3.1, SenseVoice (funasr), MERT-v1-95M, librosa, optional PANNs | — (already a ComfyUI-bearing route host) |
| **`shot-timeline` (this repo)** | `analysis/call_audio_analysis.py` (near-clone of call_shot_analysis.py); `httpx` (already a v1.1 dep); stdlib only | ANY new ML dep — no torch / whisper / WhisperX / pyannote / funasr / MERT / SER / TTS / music-gen / sfx-gen imports |

**Single hardest constraint → CUDA 12.8 conflict (Phase 0/1 BLOCKER).** WhisperX's current PyPI release hard-requires CUDA toolkit 12.8 (official README "Setup step 0"). This project's runtime is `torch 2.6.0+cu124` (CUDA 12.4, see CLAUDE.md). The route host MUST upgrade to CUDA 12.8 before Phase 1 risk-validation can run. SenseVoice, pyannote 3.1, MERT, and librosa all work on 12.4 — WhisperX alone forces the upgrade. This is a route-host concern, not something this repo resolves.

**SINGLE MOST IMPORTANT PICK → SenseVoice over RAVDESS.** Native Mandarin+Cantonese SER (Alibaba, 8.9k★, MIT code). The milestone flags "中文 SER 跨域" as the highest risk — SenseVoice is the mitigation: trained on Chinese speech, not English studio performances. Also emits audio-event tags (BGM / applause / laughter / cry / cough) in the same pass, covering part of sfx modality for free.

---

## Recommended Stack

### Core Technologies — ROUTE HOST (`kais-aigc-platform/audio-analysis`)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **WhisperX** | PyPI latest (v3.x line; CUDA 12.8 hard-req) | Word-level timestamps + speaker diarization (replaces segment-only `faster-whisper` for dialogue modality) | The canonical "Whisper + word alignment + diarization" pipeline (8.9k★, INTERSPEECH 2023 paper, 70× realtime with large-v2). Uses **faster-whisper as backend** (same as this project's `audio/transcribe.py`) — ASR quality is identical, only adds: (a) wav2vec2 forced alignment for sub-100ms word timestamps; (b) per-word speaker assignment via pyannote. **Preserves investment in `large-v3`.** Speaker diarization now uses `pyannote/speaker-diarization-community-1` (CC-BY-4.0, NOT gated 3.1) — RESOLVES the licensing concern raised in the milestone context. |
| **pyannote.audio** | 3.1 (`pip install pyannote.audio`) | Standalone speaker diarization (fallback if WhisperX's bundled community-1 underperforms on Chinese animation dialogue with overlap) | De-facto diarization standard. 3.1 removed the `onnxruntime` dep that plagued 3.0 — segmentation + embedding now pure PyTorch, easier deployment. ~11–19% DER on least-forgiving benchmarks. MIT code; weights gated for 3.1 / CC-BY-4.0 for community-1. |
| **SenseVoice** (FunAudioLLM) | SenseVoiceSmall via `funasr>=1.3.26` | Chinese-native SER + audio event detection (BGM / applause / laughter / cry / cough / sneeze / breath) | **The killer pick for the Chinese-SER cross-domain risk.** Native Mandarin + Cantonese training (NOT RAVDESS English performances). Reports SOTA on Chinese+English SER benchmarks WITHOUT target-domain finetuning. 7 emotion labels (HAPPY/SAD/ANGRY/NEUTRAL/FEARFUL/DISGUSTED/SURPRISED) + 8 audio event tags — covers BOTH dialogue-emotion AND part of sfx detection in ONE model. Non-autoregressive → 5–15× faster than Whisper-Small/Large. MIT code; weights under FunASR model card terms. Released Jul 2024, actively maintained. llama.cpp GGUF runtime since 2026/06 (q8 ~254MB, CPU/edge deployable). 8.9k★. |
| **MERT-v1-95M** (m-a-p) | `m-a-p/MERT-v1-95M` via `transformers` | Music instrument recognition + tempo + key (foundation model for music MIR) | SOTA on 14 MIR tasks (ICLR 2024, 384+ citations). HuBERT-style SSL on music audio; finetune heads for instrument/tempo/key. 95M chosen over 330M for route VRAM discipline (~380MB fp16 vs ~660MB; both fit, but 95M leaves headroom for WhisperX + pyannote + SenseVoice on one GPU). **Phase 1 risk-validation MUST confirm tempo/key/instrument accuracy on Chinese pop/animation BGM — paper claims ≠ erhu/pipa/guzheng reality.** |
| **PANNs / HTS-AT** (complement to MERT) | Pre-trained CNN14 / HTS-AT (HuggingFace `qiuqiangkong/audioset_tagging_cnn` lineage) | Polyphonic audio event detection + instrument recognition (sfx taxonomy) | More battle-tested for **polyphonic** sfx/instrument classification than MERT (trained on AudioSet 527 classes). Better coverage of "door creak / footsteps / glass break" foley than SenseVoice's 8 narrow event tags. Use as MERT's COMPLEMENT for sfx + polyphonic instrument, NOT replacement. |
| **librosa** | 0.11.x stable | Tempo (beat_track) + key estimation (chroma) + onset detection — DSP-classic baselines | Industry-standard Python audio DSP. `beat_track` is the canonical BPM estimator; key detection via chroma. **Production-honest baseline** if MERT tempo head underperforms. Lightweight (CPU-only, no GPU contention). Already transitively present via Demucs/numpy ecosystem. |
| **CosyVoice 2 / Fun-CosyVoice 3.0** (FunAudioLLM) | Fun-CosyVoice 3.0 line (Apache 2.0) | **Target** of TTS reproduction prompts (dialogue modality) | Apache 2.0 — **commercial-use OK** (unlike F5-TTS). Same FunAudioLLM family as SenseVoice — natural pairing for "transcribe with SenseVoice → reproduce with CosyVoice". Multilingual zero-shot voice cloning (perfect for SPEAKER-01: clone each speaker_id's timbre from the v1.1 character registry's audio sample). |
| **GPT-SoVITS v4** (RVC-Boss) | v4 (MIT license) | Alternate TTS reproduction prompt target (esp. for 1-minute voice cloning from registry samples) | MIT — commercial OK. v4 fixes v3's metallic artifacts, native 48k output, supports Korean + Cantonese + Chinese + English. Designed for **few-shot cloning from <1 min of reference audio** — exactly the v1.1 character registry's representative_image → voice use case. |
| **Stable Audio Open 1.0** (Stability AI) | open-weights (Stability Community License — **non-commercial**) | Target of music-gen + foley reproduction prompts | Only open-weights model purpose-built for **short foley** (footsteps, door creaks, environmental) per Stability's research paper. Generates ≤47s clips. **License blocker:** non-commercial only — prompts must be model-agnostic OR route must declare a commercial-vs-research mode flag. |
| **AudioLDM2** (cvssp) | audioldm2 / audioldm2-large / audioldm2-music (CC-BY-NC-SA-4.0 — **non-commercial**) | Alternate target for sfx + music prompts | Latent text-to-audio diffusion, 48kHz, supports SFX / speech / music. **CC-BY-NC-SA-4.0 — non-commercial only.** Same licensing story as Stable Audio Open. |

### Supporting Libraries — ROUTE HOST

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `funasr` | ≥1.3.26 | SenseVoice runtime (also exposes FSMN-VAD + CAM++ + ct-punc for composed diarization without HF token) | SenseVoice emotion + AED; optional FSMN-VAD/CAM++ diarization that doesn't need HF token (unlike pyannote 3.1) |
| `transformers` | ≥4.40 (5.x preferred) | MERT-v1 inference (AutoModel + AutoFeatureExtractor) | Music MIR — instrument/tempo/key classification heads |
| `torch` + `torchaudio` | 2.6+ with **CUDA 12.8** backend (WhisperX req) | Backend for WhisperX, pyannote 3.1, MERT, SenseVoice | ALL heavy ML — shared GPU |
| `faster-whisper` | 1.2.1 (same as project) | WhisperX backend (WhisperX WRAPS this, does NOT replace it) | Already the project's primary ASR — preserved through WhisperX |
| `wav2vec2` Chinese align model | `jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn` | WhisperX's Chinese word-alignment (DEFAULT_ALIGN_MODELS_HF["zh"]) | Loaded automatically by WhisperX when `language="zh"`; Phase 1 verify it lands Chinese animation dialogue well |
| `pyannote.audio` | 3.1 | Standalone diarization Pipeline API | If choosing standalone 3.1 over WhisperX's community-1 default |
| `librosa` | 0.11.x | Tempo (beat_track), key (chroma), onset detection | Baseline MIR + MERT cross-check |
| `numpy` | 2.2.6 (same as project) | Array math | Already present |
| `httpx` | 0.28.1+ | (Already on route host) Route-to-driver HTTP if needed | Mirror existing `shot-analysis` route pattern |

### Development Tools — ROUTE HOST

| Tool | Purpose | Notes |
|------|---------|-------|
| HuggingFace access token (read) | Required for: WhisperX diarization (community-1 ToU), pyannote 3.1 if used, MERT-v1 weights | Route-side env var, never crosses into shot-timeline |
| **CUDA 12.8 toolkit** | WhisperX hard-requirement | **Phase 0/1 blocker** — current runtime is CUDA 12.4 (`torch 2.6.0+cu124`); route host needs upgrade |
| Docker (optional) | SenseVoice ships a Dockerfile + docker-compose | Eases route-side deploy if the route host containerizes |

### CLIENT SIDE — `shot-timeline` (this repo, v1.2 additions)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **`httpx`** | already a v1.1 transitive dep (since `analysis/call_shot_analysis.py`) | Sync HTTP client to call `POST /api/v1/production/audio-analysis` | **The only "dependency"** on this side — and it's already there. v1.2 inherits v1.1's pattern verbatim. |
| **stdlib only** (`json`, `argparse`, `hashlib`, `pathlib`, `re`, `os`, `sys`) | Python 3.10+ | Compose request body, parse response, write `audio_semantic.json` + `route_cache/audio_analysis/shot_XXX.json` + `warnings.json` sidecar, content-hash cache key | Match `call_shot_analysis.py` exactly. No new runtime deps. |
| **`jsonschema.Draft202012Validator`** | already dep (`spec/validate.py`) | Validate `audio_semantic.json` against new schema before write | Project convention: fails-loud before writing downstream-corrupted JSON |

---

## Installation

### Route host (`kais-aigc-platform/audio-analysis` route — NOT this repo)

```bash
# Phase 0 — CUDA 12.8 upgrade (WhisperX hard-req; current project runtime is 12.4)
#   Follow NVIDIA CUDA Toolkit 12.8 install guide for Linux.
#   Without this, WhisperX cannot load large-v3 on GPU.

# Phase 1 risk-validation install
pip install whisperx                       # PyPI latest; pulls faster-whisper, pyannote.audio 3.1, etc.
pip install "funasr>=1.3.26"               # SenseVoice + FunASR runtime
pip install "transformers>=4.40"           # MERT-v1
pip install "librosa>=0.11"                # baseline MIR (tempo / key / onset)
pip install "torch>=2.6" "torchaudio>=2.6" # CUDA 12.8 wheels

# HuggingFace auth (one-time per host)
huggingface-cli login    # paste read token
# In browser, accept ToU for:
#   - pyannote/segmentation-3.0
#   - pyannote/speaker-diarization-3.1   (only if used; WhisperX defaults to community-1)
#   - m-a-p/MERT-v1-95M
```

### This repo (`shot-timeline`) — v1.2 adds NOTHING

```bash
# NO pip install commands. v1.2 client code reuses:
#   - httpx        (already used by analysis/call_shot_analysis.py since v1.1)
#   - stdlib       (json, argparse, hashlib, pathlib, re, os, sys)
#   - jsonschema   (already used by spec/validate.py)
```

The new file `analysis/call_audio_analysis.py` will be a near-clone of `analysis/call_shot_analysis.py` (445 lines) with: route path swapped (`/api/v1/production/audio-analysis`), request body schema changed, response → `audio_semantic.json` mapping, `ROUTE_VERSION` constant bumped.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not (or When to Use Alternative) |
|----------|-------------|-------------|--------------------------------------|
| Word-level ASR | **WhisperX** | Keep faster-whisper + add standalone wav2vec2 forced alignment | WhisperX bundles exactly this — saves glue code, gets diarization for free. Standalone alignment only if WhisperX's CUDA 12.8 req is immovable AND route host can't upgrade (would block Phase 1). |
| Diarization weights | **WhisperX's default `speaker-diarization-community-1` (CC-BY-4.0)** | pyannote 3.1 gated weights | Community-1 sidesteps the HF ToU + commercial-license ambiguity that 3.1 carries. Switch to 3.1 only if Phase 1 shows community-1 DER is too high on Chinese animation dialogue (multiple speakers + overlapping speech). |
| Chinese SER | **SenseVoice (funasr)** | RAVDESS-trained English SER; EmoBox; C2SER-LLM; HuBERT+finetune | RAVDESS English performances → Chinese animation is exactly the cross-domain risk the milestone flags. SenseVoice is native-Mandarin-trained + production-deployed (Alibaba) + emits AED tags in same pass. C2SER-LLM and HuBERT-finetune are research-grade (more setup, less battle-tested). |
| Music MIR | **MERT-v1-95M + librosa baseline** | MERT-v1-330M; PANNs/HTS-AT alone; "MuQ" | 330M is overkill for route VRAM budget alongside WhisperX+pyannote+SenseVoice. PANNs better for polyphonic sfx but weaker on music semantics — keep as **complement** for sfx. "MuQ" did NOT surface as a real published model in 2025 searches (possibly name confusion; treat as not-available until proven otherwise). |
| Reproduction: TTS | **CosyVoice 2 / Fun-CosyVoice 3.0 (Apache 2.0)** | F5-TTS; GPT-SoVITS v4 (MIT) | CosyVoice is same family as SenseVoice → natural pair, commercial-safe. F5-TTS is higher quality but **CC-BY-NC-4.0 models block commercial use** — only choose if v1.2 is research-only. GPT-SoVITS is the right pick if 1-minute-few-shot cloning from registry samples matters more than zero-shot naturalness. |
| Reproduction: music-gen | **Stable Audio Open (with license flag)** | Stable Audio 2.5/3.0 paid; Suno/Udio closed | No open-weights commercial-use model exists in this space as of mid-2026. Phase 1 MUST surface this to the user: either (a) declare v1.2 research-only and use Stable Audio Open + AudioLDM2; (b) target Stable Audio paid API; (c) emit model-agnostic NL prompts and let downstream user pick. **Roadmap decision, not tech decision.** |
| Reproduction: sfx/foley | **Stable Audio Open (purpose-built for foley)** | AudioLDM2 | Stability's paper explicitly positions Stable Audio Open for foley (door creaks, footsteps). AudioLDM2 is more general (SFX + music + speech). Both non-commercial. |
| Spike retirement | **Retire `audio/gen_audio_prompts.py` to `--offline` fallback** | Keep as primary sidecar | Per locked v1.2 decision #6: spike's NL prompt is superseded by layered TTS/music-gen/foley prompts. Keep code path as offline fallback so cache-only runs still produce *something*. |

---

## What NOT to Use (the boundary, made explicit)

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **ANY new ML dep in `shot-timeline` repo** (torch, transformers, whisperx, pyannote, funasr, MERT, librosa, SenseVoice, TTS, music-gen, sfx-gen) | Violates locked v1.2 decision #1 ("shot-timeline stays thin httpx client with ZERO new ML deps"). Would duplicate route-side models, break 松耦合 contract, bloat producer with multi-GB downloads, force GPU ownership onto the producer. | `analysis/call_audio_analysis.py` (httpx + stdlib only) |
| **RAVDESS-trained English SER models** | Known cross-domain risk: English studio performances ≠ Chinese animation dialogue. Multiple papers report >20% accuracy drop cross-domain. | SenseVoice (native Mandarin + Cantonese training) |
| **pyannote 3.1 gated weights as default** | License ambiguity for commercial use; HF ToU gating adds friction for re-deployment | WhisperX's `speaker-diarization-community-1` (CC-BY-4.0, no gating) — fall back to 3.1 only if DER on Chinese dialogue is unacceptable |
| **WhisperX without CUDA 12.8 upgrade** | WhisperX hard-requires CUDA 12.8 (README "Setup step 0") | Resolve CUDA upgrade FIRST in Phase 0/1; do NOT attempt CPU fallback (Whisper-large on CPU is hours-per-episode — already documented in CLAUDE.md) |
| **MERT-v1-330M as the default** | 330M adds ~280MB VRAM for marginal accuracy gain over 95M; route host needs VRAM headroom for WhisperX + pyannote + SenseVoice | MERT-v1-95M; only upgrade to 330M if Phase 1 shows 95M underperforms on Chinese pop instruments (erhu, pipa, etc.) |
| **F5-TTS pretrained models for commercial use** | CC-BY-NC-4.0 (Emilia dataset) — outputs cannot be used commercially | CosyVoice 2 (Apache 2.0) or GPT-SoVITS v4 (MIT) |
| **`pyannote/speaker-diarization-3.0`** | Has problematic `onnxruntime` dep that 3.1 removed | pyannote.audio 3.1 + speaker-diarization-3.1 weights (or WhisperX's community-1) |
| **Replacing `faster-whisper` entirely with WhisperX as a separate ASR** | WhisperX USES faster-whisper as backend — no replacement needed, just wrapping | Keep `audio/transcribe.py` AS-IS; route layer adds WhisperX above same backend |
| **Demucs re-run for music MIR** | Demucs stems already produced by v1.0 baseline — re-running wastes ~3min/episode of GPU | Route consumes the existing `stems/htdemucs/<stem>/*.wav` from Demucs output; MERT/librosa/PANNs/SenseVoice read stems directly |
| **AudioLDM2 / Stable Audio Open as a commercial product** (without flagging) | Both are non-commercial-licensed | Phase 1 must escalate to roadmap decision: research-only vs commercial path |
| **`pydantic`** | Project has zero pydantic usage; jsonschema Draft 2020-12 is the contract surface; adding pydantic would split validation | jsonschema Draft202012Validator (already used) |
| **A new canvas node type or contract bump for audio semantic data** | Consumer's `canvasAssetSchema.ts` already accepts arbitrary `assetType` string; v1.2 audio_semantic.json is a new optional sidecar under existing `data.*` pattern | Reuse existing `asset` node; bump only `SHOT_TIMELINE_KNOWN_VERSIONS` Set + `schema_version` 1.1→1.2 (pure minor) |

---

## Stack Patterns by Variant

### Pattern A — "Full pipeline, route up" (default)
```
shot-timeline          kais-aigc-platform/audio-analysis route
─────────────          ────────────────────────────────────
step_audio_semantic →  POST /api/v1/production/audio-analysis
  (httpx)               ├─ WhisperX (words + diarization, reads vocals.wav)
                        ├─ SenseVoice (emotion + AED, reads vocals.wav)
                        ├─ MERT-v1-95M (instruments + tempo + key, reads drums/bass/other.wav)
                        ├─ librosa (tempo/key cross-check)
                        ├─ PANNs (polyphonic sfx taxonomy, reads other.wav)
                        └─ → audio_semantic.json (per shot:
                            dialogue{words,speaker_id,emotion} +
                            music{instruments,tempo_bpm,key,va,occurrences} +
                            sfx{description[]} +
                            reproduction_prompts{tts,music_gen,foley})
```
**When:** Route host healthy, CUDA 12.8 installed, all model licenses accepted.

### Pattern B — "Offline / cache-only" (mirror v1.1's `--offline`)
```
shot-timeline (--offline flag)
───────────────────────────────
step_audio_semantic →  reads route_cache/audio_analysis/shot_*.json only
  (no network)         on cache miss → graceful-degrade to schema-valid
                       empty audio_semantic.json + warning sidecar
                       (existing audio_analysis.json from v1.0 still
                        produced — audio_semantic.json is OPTIONAL)
```
**When:** Operator running offline, route host down, or re-running after cache populated. Exact mirror of `call_shot_analysis.py:--offline`.

### Pattern C — "Spike fallback" (locked decision #6)
```
shot-timeline (--offline + cache-miss on all shots)
───────────────────────────────────────────────────
step_audio_semantic delegates to audio/gen_audio_prompts.py
  → produces sidecar NL prompt from Demucs energies + transcript
    (NOT the layered TTS/music-gen/foley; single NL string)
```
**When:** v1.2 spike retirement: `gen_audio_prompts.py` demoted to offline fallback per locked decision. NEVER the primary path.

### Pattern D — "Partial modality" (route returns partial)
```
shot-timeline handles route response with modality-level nulls:
  - dialogue present, music null, sfx null → write partial audio_semantic
  - all three null → graceful-degrade (Pattern B)
  - warnings sidecar records which modalities failed
```
**When:** One model in the route crashes (e.g., MERT OOM) but others succeed. Route-side must support partial response; client treats missing keys as null. Mirror CR-02 defensive isinstance guards from `call_shot_analysis.py`.

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `whisperx` (PyPI latest) | **CUDA 12.8** (hard req), torch ≥2.6, faster-whisper 1.x | **Current project CUDA 12.4 is NOT compatible — route host upgrade required.** WhisperX's bundled pyannote is community-1 (CC-BY-4.0). |
| `whisperx` Chinese alignment | `jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn` (DEFAULT_ALIGN_MODELS_HF["zh"]) | Auto-downloaded first run; verify it lands Chinese animation dialogue cleanly in Phase 1. |
| `funasr>=1.3.26` (SenseVoice) | Python 3.10+, torch ≥1.13 (works with 2.6+cu124 too — SenseVoice does NOT require CUDA 12.8) | SenseVoice can run on the current 12.4 runtime — only WhisperX forces the upgrade. |
| `pyannote.audio` 3.1 | torch ≥1.11, torchaudio ≥0.11, Python ≥3.9 | Pure PyTorch (no onnxruntime); works with both CUDA 12.4 and 12.8 |
| MERT-v1 | transformers ≥4.40, torch compatible | Works on current runtime; CUDA 12.4 fine |
| `pyannote/speaker-diarization-3.1` weights | pyannote.audio ≥3.1 + HF token + ToU acceptance | Gated; alternative is community-1 (no gating) |
| `pyannote/speaker-diarization-community-1` weights | pyannote.audio ≥3.1, CC-BY-4.0 | WhisperX default as of current release; no gating but still requires HF token (read) |
| CosyVoice 2 / Fun-CosyVoice 3.0 | Same FunAudioLLM/funasr ecosystem as SenseVoice | Apache 2.0 — commercial-safe target for TTS prompts |
| Stable Audio Open 1.0 | diffusers ≥0.21 | Non-commercial — see license caveat |
| AudioLDM2 | diffusers ≥0.21 | Non-commercial — see license caveat |
| F5-TTS (code) | MIT | F5-TTS pretrained models are CC-BY-NC-4.0 — non-commercial only |
| `httpx` (this repo) | 0.28.1+ already installed | No change for v1.2 |

---

## Integration With Existing v1.0/v1.1 Pipeline (Critical for Phase 1)

| Existing artifact | v1.2 consumer (route-side) | Notes |
|-------------------|---------------------------|-------|
| `stems/htdemucs/<stem>/{vocals,drums,bass,other}.wav` | WhisperX + SenseVoice (read `vocals.wav` for clean ASR / emotion — less BGM interference); MERT + PANNs + librosa (read `drums.wav` + `bass.wav` + `other.wav` for music MIR; `other.wav` for sfx) | **Demucs NOT re-run.** Route reuses existing 4-stem output. Saves ~3min/episode GPU. |
| `shots.json` (V3b time grid) | Route chunks all per-shot analysis by `{start_sec, end_sec}` — same pattern as `call_shot_analysis.py:shot_id_range=[N,N]` | Per-shot isolation preserved; cache key includes `video_content_hash + route_name + route_version`. |
| `transcript.json` (Whisper segments) | **NOT replaced.** v1.0 `audio/transcribe.py` stays untouched (still the producer of `transcript.json`); route overlays word-level + speakers + emotion into the NEW `audio_semantic.json` sidecar. | v1.0 transcript.json schema UNCHANGED; `audio_semantic.json` is the optional sidecar with richer per-shot data. Backward compatibility preserved. |
| `prompts.json` (v1.1 cinematography prompts) | v1.2 reproduction prompts (TTS / music-gen / foley) live in NEW `audio_semantic.json` sidecar — `prompts.json` is NOT modified (it stays the visual-cinematography prompt). | Mirrors v1.1's decision to keep `audio_prompts.json` as a sidecar. |
| `characters.json` (v1.1 registry) | SPEAKER-01: speaker attribution links `speaker_id → character_id` via the registry | Route returns speaker_id labels; client-side (or HITL step) maps speaker_id to character_id. v1.1's `registry/apply_edits.py` confirmed-only gate pattern applies. |
| `route_cache/` pattern | New subdir `route_cache/audio_analysis/shot_XXX.json` + existing `route_cache/warnings.json` sidecar merge | Mirrors `call_shot_analysis.py` cache layout exactly (4-tuple key: video_content_hash + route_name + route_version). |
| `asset.json` manifest | Add optional `data.audio_semantic` (v1.2 minor bump 1.1→1.2) | Pure-additive per SPEC §4 — old consumers graceful-degrade. |
| `scripts/serve.py` (Range-aware HTTP) | Unchanged — serves `audio_semantic.json` as static JSON (no Range needed for JSON); stems/video Range still needed as before | Zero new server infrastructure. |

---

## Schema Bump Nuance — Confirm v1.1 Pattern

v1.2 schema bump `1.1 → 1.2` follows the EXACT pattern v1.1 established (and PROJECT.md Key Decisions locks):

- **Pure-additive only**: new optional `data.audio_semantic` field in `asset.json`; new optional `audio_semantic.schema.json` file; NO rename, NO semantic shift, NO new required field.
- **Producer-locked literal**: `scripts/export_asset.py:SCHEMA_VERSION = "1.2"` (single-source constant, NOT schema `const` — so v1/v1.1 minimal fixtures still validate).
- **Cross-version self-test**: `scripts/verify_contract.py:_cross_version_check` extended to cover v1.2; v1/v1.1/v1.2 bidirectional proof (forward 0 errors; backward only additional properties errors → 0 non-additive errors).
- **`schema_version` pattern unchanged**: `^(0|[1-9]\d*)(\.(0|[1-9]\d*))?$` — no regex change.

No new contract mechanism; mirrors v1.1 Phase 5 exactly.

---

## Sources

### Authoritative (HIGH confidence)

- **WhisperX GitHub** — [github.com/m-bain/whisperx](https://github.com/m-bain/whisperx): confirmed faster-whisper backend, wav2vec2 alignment, speaker-diarization-community-1 (CC-BY-4.0) default, **CUDA 12.8 hard-req**, <8GB VRAM for large-v2 beam_size=5. INTERSPEECH 2023 paper (Bain et al.). **Confidence: HIGH.**
- **pyannote/speaker-diarization-3.1 HF model card** — [huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1): confirmed pyannote.audio 3.1+, pure-PyTorch (3.0 onnxruntime removed), 16kHz mono, `num_speakers` / `min_speakers` / `max_speakers` hints, MIT-licensed code, gated weights. **Confidence: HIGH.**
- **FunAudioLLM/SenseVoice GitHub** — [github.com/FunAudioLLM/SenseVoice](https://github.com/FunAudioLLM/SenseVoice): confirmed SenseVoiceSmall supports Mandarin/Cantonese/English/Japanese/Korean ASR + LID + SER (7 emotions) + AED (8 events incl. BGM), non-autoregressive (5–15× faster than Whisper), MIT code, funasr≥1.3.26, llama.cpp/GGUF runtime since 2026/06 (q8 ~254MB), composed FSMN-VAD+CAM++ diarization pipeline, 8.9k★. SER benchmark table shows SenseVoice-Large is SOTA across Chinese+English test sets without target-domain finetuning. **Confidence: HIGH.**
- **MERT-v1-330M HF model card + arXiv 2306.00107** — [huggingface.co/m-a-p/MERT-v1-330M](https://huggingface.co/m-a-p/MERT-v1-330M), [arxiv.org/abs/2306.00107](https://arxiv.org/abs/2306.00107): confirmed 95M/330M variants, ICLR 2024 (384+ citations), SOTA on 14 MIR tasks, ~660MB fp16 weights (330M) / ~380MB (95M). **Confidence: HIGH for existence/perf claims; MEDIUM for production-readiness on Chinese pop/animation BGM (must verify Phase 1).**
- **CosyVoice GitHub** — [github.com/FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice): confirmed Apache 2.0 license, Fun-CosyVoice 3.0 line, multilingual zero-shot cloning. **Confidence: HIGH.**
- **F5-TTS GitHub + Discussion #997** — confirmed MIT code + CC-BY-NC-4.0 pretrained models (Emilia dataset). **Confidence: HIGH.**
- **GPT-SoVITS GitHub** — [github.com/RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS): confirmed MIT, v4 released 2025, 48k native output. **Confidence: HIGH.**
- **Stable Audio Open model card + LICENSE.md** — [huggingface.co/stabilityai/stable-audio-open-1.0](https://huggingface.co/stabilityai/stable-audio-open-1.0): confirmed Stability Community License = non-commercial; ≤47s clips; designed for foley. **Confidence: HIGH.**
- **AudioLDM2 HF model card** — [huggingface.co/cvssp/audioldm2](https://huggingface.co/cvssp/audioldm2): confirmed CC-BY-NC-SA-4.0 — non-commercial. **Confidence: HIGH.**
- **librosa docs** — [librosa.org/doc/main](https://librosa.org/doc/main/generated/librosa.beat.beat_track.html): confirmed `beat_track` + chroma key detection as canonical DSP baseline. **Confidence: HIGH.**

### Secondary (MEDIUM confidence)

- **WhisperX Issue #810 + alignment.py source** — confirms Chinese default align model is `jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn` (XLSR-53 finetune). Phase 1 must validate on animation dialogue.
- **SenseVoice SER benchmark figure (image in README)** — claims SOTA without target-domain finetuning, but the benchmark is on standard test sets (not animation); cross-domain still a risk for v1.2 use case.
- **arXiv 2603.04809 "Word-Boundary-Aware ASR and WhisperX-Anchored Pyannote Diarization"** — flags temporal drift when pairing WhisperX ASR with standalone pyannote pipelines using different VADs. **Actionable:** prefer WhisperX's bundled community-1 diarization over a standalone pyannote pipeline, to keep VAD consistent.

### Not found / LOW confidence

- **MuQ**: did NOT surface in 2025 searches as a real published model — possibly name confusion with another model. **Treat as not-available until proven otherwise.** If the user knows MuQ by another spelling, research can re-run.
- **Polyphonic instrument recognition on Chinese pop specifically**: no head-to-head benchmark MERT vs PANNs on erhu/pipa/guzheng etc. Phase 1 risk-validation must produce this.

---

## Gaps / Open Questions for Phase-Specific Research

1. **CUDA 12.8 upgrade path for the route host.** WhisperX cannot run without it. Phase 0/1 unblocks this BEFORE any model risk-validation. Not technically a "research gap" but a prerequisite gate.
2. **MERT vs PANNs vs librosa on Chinese pop/animation BGM.** No head-to-head benchmark exists. Phase 1 risk-validation on 1 episode MUST measure tempo accuracy, key accuracy, and instrument classification precision on representative Chinese soundtrack samples — paper MERT benchmarks are Western music.
3. **SenseVoice cross-domain on Chinese animation dialogue.** Native Mandarin training is promising but benchmark is on test sets, not animation. Phase 1 must spot-check 1 episode for emotion accuracy.
4. **WhisperX `community-1` diarization DER on Chinese animation.** Multiple speakers + overlapping speech + BGM interference are the failure mode. Phase 1 measures DER vs standalone pyannote 3.1; if community-1 < 3.1 by >5pp DER, switch to 3.1.
5. **Music-gen / sfx commercial roadmap decision.** Open-weights are all non-commercial. Phase 1 must escalate: research-only mode (use Stable Audio Open + AudioLDM2) vs commercial mode (Stable Audio paid API or model-agnostic prompts). This is a PLANNING decision, not a tech decision.
6. **Speaker_id ↔ character_id linkage mechanism.** Route returns numeric speaker labels (SPEAKER_00, SPEAKER_01...); v1.1 character registry uses `char_NNN` IDs. Need a HITL mapping step (mirror v1.1 `registry/apply_edits.py` confirmed-only gate) or route-side heuristic (CAM++ voice embedding similarity to registry audio samples). Scope of SPEAKER-01 requirement.

---

*Stack research for: v1.2 音频语义深化 (route-based three-modality audio semantic analysis + layered reproduction prompts)*
*Researched: 2026-07-25*
