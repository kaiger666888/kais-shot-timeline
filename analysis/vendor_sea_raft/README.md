# vendor_sea_raft — SEA-RAFT 最小推理引入

- **上游**: https://github.com/princeton-vl/SEA-RAFT （ECCV2024 Oral, BSD-3-Clause, 见本目录 `LICENSE`）
- **引入方式**: 2026-09-18 经 codeload tarball 取 `main` 分支（commit 彼时 HEAD）, 只拷推理必需的 6 个文件:
  `core/{layer,extractor,update,corr,raft}.py` + `core/utils/utils.py`（裁剪后存为 `utils.py`）
- **权重**: `MemorySlices/Tartan-C-T-TSKH432x960-S`（HuggingFace, 官方 README "Custom Usage" 路线）
  —— SEA-RAFT-small, Tartan→Chairs→Things3D→Sintel→KITTI→HD1K 全程训练, 通用性最好的 S 档。
  不入库（`weights/` 已 gitignore）, `load_sea_raft()` 首次调用经 `HF_ENDPOINT`（默认 hf-mirror.com）自动下载。

## 与上游的 diff（全部改动, 逐文件）

| 文件 | 改动 |
|---|---|
| `layer.py` | 无（逐行一致） |
| `extractor.py` | `from layer import …` → `from .layer import …` |
| `update.py` | `from layer import …` → `from .layer import …` |
| `corr.py` | `from utils.utils import …` → `from .utils import …` |
| `raft.py` | 5 处平铺导入改相对导入; 移除 `huggingface_hub.PyTorchModelHubMixin` 基类（HF repo 无 config.json 且免装 huggingface_hub）, 类体逻辑逐行一致 |
| `utils.py` | 去掉 `scipy` 依赖与 `forward_interpolate`; 去掉 datasets 专用几何函数 `transform/from_homog/reproject/induced_flow/check_cycle_consistency`; 保留 `load_ckpt/resize_data/InputPadder/bilinear_sampler/coords_grid/upflow8`（保留部分逐行一致） |
| `__init__.py` | 新增: `load_sea_raft()` 本地 safetensors 加载器（strict=True）+ 自动下载; 训练配置常量 `SEA_RAFT_SMALL_ARGS` 抄自 `config/eval/sintel-S.json` |

加载器含一处键别名: 上游 main 分支 `layer.py` 将 downsample 支路的 BN 同时注册为
`bn3` 与 `downsample.1`（同一模块双路径), 而 HF 放出的权重只保存了 `bn3.*` 一份;
加载时把 `X.bn3.*` 复制出 `X.downsample.1.*`——按双注册语义补齐, 非结构改动,
strict=True 全量加载通过即为凭据。

模型结构与前向逻辑零改动——上游权重 strict 加载通过即为凭据。
