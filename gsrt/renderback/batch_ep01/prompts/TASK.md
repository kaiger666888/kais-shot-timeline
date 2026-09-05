# EP01 批量 prompt 迭代任务（pack_{PACK}）

你在处理《小江湖》EP01 批量视频重生成工程的 prompt 翻译批次 {PACK}。输入：`/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01/prompts/input_pack{PACK}.json`（~24 个镜头条目）。

## 背景

我们要用本地 MiniMax H3（FL2VA 首尾帧模式 + T8 audio_lock 台词驱动）重生成 EP01 全部 93 镜。原片条件帧已切好，需要把每镜的中文创作要素翻译成 H3 英语 prompt。已验证的最佳实践来自 S89 单镜闭环（数数台词镜，量化双门 PASS + 盲测最优）。

## 对每镜输出一个 JSON 条目

```json
{
  "sid": 89,
  "h3_prompt": "英文 prompt（见下方规则）",
  "dialogue_line": "数数台词的英文提示词化改写（见规则4）",
  "notes": "可选：特殊处理说明，20字内"
}
```

## H3 prompt 规则（S89 实证沉淀，严格遵守）

1. **结构**：`3D animation, Pixar-level rendering, cinematic shallow depth of field.` 开头 → 场景一句（森林/苔藓倒木/巨树等，从 scene 翻译）→ 角色与主体动作一句（用 roster 英文角色名，从 subject+action 翻译）→ 镜头语言一句（从 camera 翻译：slow pull-back / static medium shot / tracking shot 等）→ 光照短语（从 lighting 翻译：soft natural light, misty forest, cool green tones）。
2. **节拍分段**：时长 >2s 且 action 含明显先后动作的镜，用 `Beat 1 (first XX% of the shot): ... Beat 2 (from XX% onward): ...` 结构拆分（百分比按动作语义分配）。≤2s 或单一持续动作的镜不拆。
3. **首尾帧锚意识**：条件首尾帧已锁构图与角色位置，prompt 不要重复描述构图细节，重点写**中间过程动作**（first/last 之间发生什么）。
4. **台词轴**：dialogue_zh 非空时，在 prompt 末尾追加一句英文说明台词驱动。数数类台词写 `Character counts numbers aloud continuously, mouth movements synced to counting rhythm`；普通对白写 `Character speaks aloud, natural lip-sync`；画外音（dialogue_note 含"画外"）写 `Off-screen narration, characters do not speak`。dialogue_line 字段 = 该英文句。
5. **物理与禁令**：动作描述用物理可达的表述（S89 教训：百分比时相指令引擎会忽略，但节拍语义有效）；禁用 "no text, no watermark"；不要写镜头切换（单镜内只一个连续镜头）。
6. **角色一致性**：一律用 roster 提供的英文描述短语，不要自创外貌描写。
7. **输出语言**：h3_prompt 全英文。notes 可中文。

## 输出

把全部条目写入 `/data/workspace/kais-shot-timeline/gsrt/renderback/batch_ep01/prompts/output_pack{PACK}.json`（JSON 数组，顺序与输入一致）。完成后打印统计：处理条数、含节拍拆分条数、含台词轴条数。
