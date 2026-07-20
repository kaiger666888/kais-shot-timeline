# kais-shot-timeline

视频分镜检测 + 音轨分离 + 语音转录 + 交互式时间轴可视化。

## 功能

1. **分镜检测** — 多版本 PySceneDetect 检测器，V3b 为推荐融合版
   - V1：`AdaptiveDetector` 基础版（动画友好）
   - V2：双检测器（`AdaptiveDetector` 粗切 + 长镜头内 `ContentDetector` 二次扫描）+ 后处理
   - V3b：4 趟融合（`AdaptiveDetector` + `HistCorr` + 长镜头逐帧扫描 + 溶解转场检测）
2. **音轨分离** — Demucs `htdemucs` 4-stem（vocals / drums / bass / other）+ 分镜级能量分析
3. **语音转录** — Whisper（`faster-whisper` 优先，回退 `openai-whisper`）
4. **交互式 HTML**
   - 分镜卡片网格（V1/V2/V3 风格）
   - 音频分析卡片网格（4-stem 能量条 + 对白文本）
   - 时间轴双面板（左：分镜首尾帧 + 对白；右：竖向音轨波形，点击即播对应 stem）
5. **分镜 prompt 反推** — 由首尾帧反推视频生成 prompt（主体/动作/镜头/场景/光影/风格 结构化 + 连贯 prompt 文本），产出 prompts.json + 卡片审阅 HTML（一键复制）

## 目录结构

```
kais-shot-timeline/
├── run_pipeline.py             # 端到端 pipeline 入口
│
├── detectors/                  # 分镜检测
│   ├── psd_shot_preview_v1.py  # PySceneDetect 基础版
│   ├── psd_shot_preview_v2.py  # 双检测器 + 后处理
│   └── detect_v3b.py           # V3b 4 趟融合检测（推荐）
│
├── audio/                      # 音频处理
│   ├── separate_stems.py       # Demucs 4-stem 分离 + 分镜能量分析
│   └── transcribe.py           # Whisper 转录（faster-whisper / openai-whisper）
│
├── html/                       # HTML 生成
│   ├── gen_shots_preview.py    # 分镜卡片网格 HTML
│   ├── gen_audio_html.py       # 音频分析卡片 HTML（4-stem 能量条）
│   ├── gen_timeline_html.py    # 时间轴双面板 HTML（含 stem 播放）
│   └── gen_prompts_html.py     # 分镜 prompt 审阅 HTML（一键复制）
│
├── prompts/                    # 分镜 prompt 反推
│   ├── extract_frames.py       # frames.json → 每镜首尾帧 jpg
│   └── merge_prompts.py        # prompt_parts/*.json → prompts.json（补时间元数据）
│
├── examples/                   # 示例数据
│   ├── ep01_shots.json
│   └── xiaojianghu_ep01_shots_v2.json
│
└── output/                     # 生成产物（.gitignore）
```

## 快速开始

### 一键端到端

```bash
python run_pipeline.py --video input.mp4
# 或：跳过某些步骤
python run_pipeline.py --video input.mp4 \
    --skip-detect --skip-separate --skip-transcribe

# 指定 GPU / 模型（默认 cuda:1 = RTX 3090）
python run_pipeline.py --video input.mp4 \
    --device cuda:1 \
    --demucs-model htdemucs \
    --whisper-model large-v3 --whisper-language zh
```

输出布局（缓存在 `output/<video-stem>/`）：

```
output/<video-stem>/
├── h264.mp4               # 仅当输入是 AV1 时存在
├── shots.json             # V3b 分镜结果
├── frames.json            # 首尾帧 base64 缓存
├── frames_5fps/           # V3b Pass2 用的 5fps 抽帧
├── stems/htdemucs/<stem>/ # Demucs 分轨（vocals/drums/bass/other.wav）
├── audio_analysis.json    # per-shot stem 能量分析
├── transcript.json        # Whisper 转录
└── timeline.html          # 最终时间轴 HTML
```

### 分步执行

```bash
# 1. 分镜检测（AV1 视频会自动转码 H264）
python detectors/detect_v3b.py --video input.mp4 --output shots.json

# 2a. Demucs 音轨分离 + 分镜能量分析
python audio/separate_stems.py \
    --input input.mp4 --shots shots.json \
    --output-dir ./stems/ --output audio_analysis.json

# 2b. （或仅两轨分离）
python audio/separate_stems.py \
    --input input.mp4 --shots shots.json \
    --two-stems vocals --output-dir ./stems/

# 3. Whisper 转录
python audio/transcribe.py \
    --input input.mp4 \
    --model large-v3 --language zh \
    --backend faster-whisper \
    --output transcript.json

# 4a. 时间轴双面板 HTML
python html/gen_timeline_html.py \
    --shots shots.json \
    --audio-json audio_analysis.json \
    --transcript transcript.json \
    --stems-dir ./stems/htdemucs/<video-stem>/ \
    --video input.mp4 \
    --output timeline.html

# 4b. 音频分析卡片 HTML（4-stem 能量条）
python html/gen_audio_html.py \
    --video input.mp4 \
    --audio-json audio_analysis.json \
    --stems-dir ./stems/htdemucs/<video-stem>/ \
    --output audio.html

# 4c. 简单分镜卡片网格
python html/gen_shots_preview.py \
    --video input.mp4 --shots shots.json \
    --output shots.html
```

### 分镜 prompt 反推

反推由 AI agent 看图完成（不依赖外部 VLM API），脚本负责素材准备与产物合并：

```bash
# 1. 解出每镜首尾帧 jpg（供 agent 看图）
python prompts/extract_frames.py \
    --frames output/<stem>/frames.json \
    --output-dir output/<stem>/shot_frames/

# 2. AI agent 分批读 shot_frames/，按统一 schema 写 output/<stem>/prompt_parts/part_*.json
#    （字段：subject/action/camera/scene/lighting/style/prompt_text）

# 3. 合并分片 + 补时间元数据
python prompts/merge_prompts.py \
    --parts-dir output/<stem>/prompt_parts/ \
    --shots output/<stem>/shots.json \
    --output output/<stem>/prompts.json

# 4. 生成审阅 HTML（首尾帧 + 台词 + 结构化字段 + prompt 一键复制）
python html/gen_prompts_html.py \
    --prompts output/<stem>/prompts.json \
    --frames output/<stem>/frames.json \
    --transcript output/<stem>/transcript.json \
    --output output/<stem>/prompts.html
```

## 时间轴 HTML 特性

`html/gen_timeline_html.py` 是从最终 855 行版本反向同步而来，保留全部前端特性：

- **双模式切换** — 线性 vs 自适应（按钮 `📐 线性模式`）
  - 线性：时间 → 像素严格成正比（`PX_PER_SEC_LINEAR = 396`）
  - 自适应：每镜至少 280px，所有缩略图自然流；DOM 测高后回写右面板
- **分段 canvas 波形** — 浏览器 canvas 高度上限 ~65535px，单段最长 60000px
- **`<audio>` stem 播放** — 点击音轨任意位置播放对应 stem，与 `<video>` 互斥
- **XHR blob 预加载** — `preload='auto'` 只是 hint，用 XHR 强制下载并创建 object URL
- **音轨视觉分隔** — `border-left/right` + `hover`/`playing` 高亮
- **`ontimeupdate` 跟踪** — playhead 自动跟随，超出可视区域时滚动
- **body flex 布局** — 不用 JS 计算高度，header 自适应内容
- **缩略图 flex:1 + aspect-ratio:16/9** — 自适应任意面板宽度
- **双面板滚动同步** — 线性模式 1:1，自适应模式按比例

### Stem 文件命名约定

`gen_timeline_html.py` 生成的 HTML 引用 `<basename>_vocals.wav` /
`<basename>_drums.wav` / `<basename>_other.wav`。`<basename>` 由
`--stem-basename` 参数（或视频文件名）决定。把它们放到与 HTML 同目录即可。

## 技术要点

- **AV1 视频** — `ffmpeg -c:v libdav1d` 软解，PySceneDetect 需先转 H264（pipeline 自动）
- **Canvas 65535px 高度限制** — 波形拆分为多段 canvas
- **音轨播放** — 用 `<audio>` 元素（不用 Web Audio API，后者在移动端/Telegram 不可靠）
- **自适应模式** — 左面板自然流 + 右面板非线性映射，DOM 高度回写同步
- **`faster-whisper` vs `openai-whisper`** — `transcribe.py --backend auto` 优先前者（CTranslate2，速度快、显存低）

## 依赖

- Python 3.10+
- ffmpeg (with libdav1d for AV1)
- [PySceneDetect](https://github.com/Breakthrough/PySceneDetect)
- [Demucs](https://github.com/facebookresearch/demucs)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (推荐) 或 [openai-whisper](https://github.com/openai/whisper)
- PIL/Pillow, numpy, opencv-python

```bash
pip install scenedetect demucs faster-whisper pillow numpy opencv-python
# 或只装 openai-whisper
pip install openai-whisper
```

## License

MIT
