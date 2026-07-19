# kais-shot-timeline

视频分镜检测 + 音轨分离 + 交互式时间轴可视化。

## 功能

1. **分镜检测**：PySceneDetect 双检测器融合（AdaptiveDetector 粗切 + ContentDetector 补切长镜头）+ V3b 自适应参数 + Pass3/Pass4 后处理
2. **音轨分离**：Demucs (htdemucs) 分离人声/BGM/环境音
3. **语音转录**：Whisper 时间戳级转录
4. **交互式 HTML**：双面板同步滚动（左：分镜首尾帧+对白，右：竖向音轨波形），点击音轨任意位置播放对应分轨

## 目录结构

```
detectors/          分镜检测脚本
├── psd_shot_preview_v1.py    PySceneDetect 基础版
├── psd_shot_preview_v2.py    双检测器组合 + 后处理
└── detect_v3b.py             V3b 融合检测 + Pass3/Pass4

html/               HTML 生成脚本
├── gen_shots_preview.py      分镜预览 HTML（首尾帧缩略图）
└── gen_timeline_html.py      时间轴双面板 HTML（含音轨波形 + stem 播放）

examples/           示例数据
output/             生成产物（.gitignore）
```

## 使用流程

```bash
# 1. 分镜检测（AV1 视频需先转码 H264）
python detectors/psd_shot_preview_v2.py input.mp4
python detectors/detect_v3b.py input.mp4

# 2. 音轨分离
python -m demucs --two-stems vocals input.mp4  # 或 htdemucs 4-stem

# 3. 语音转录
whisper input.mp4 --model large-v3 --language zh

# 4. 生成时间轴 HTML
python html/gen_timeline_html.py shots.json --stems-dir ./stems/ --whisper transcript.json
```

## 技术要点

- AV1 视频：`ffmpeg -c:v libdav1d` 软解，PySceneDetect 需先转 H264
- Canvas 65535px 高度限制：波形拆分段 canvas
- 音轨播放：用 `<audio>` 元素（不用 Web Audio API，后者在移动端/Telegram 不可靠）
- 自适应模式：左面板自然流 + 右面板非线性映射，DOM 高度回写同步

## 依赖

- Python 3.10+
- ffmpeg (with libdav1d for AV1)
- [PySceneDetect](https://github.com/Breakthrough/PySceneDetect)
- [Demucs](https://github.com/facebookresearch/demucs)
- [whisper](https://github.com/openai/whisper) or [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- PIL/Pillow, numpy

## License

MIT
