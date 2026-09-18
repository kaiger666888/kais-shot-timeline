# -*- coding: utf-8 -*-
"""SEA-RAFT 最小 vendor 包(上游: https://github.com/princeton-vl/SEA-RAFT, BSD-3)

只引入推理必需模块: layer/extractor/update/corr/raft/utils。与上游 diff 见
README.md——除「sys.path 平铺导入改相对导入」「移除 huggingface_hub Mixin
基类」外逐行一致。权重不随仓入库(weights/ 已 gitignore), load_sea_raft()
首次调用时经 HF_ENDPOINT(默认 hf-mirror.com 直连镜像)自动下载。

用法:
    from analysis.vendor_sea_raft import load_sea_raft
    model = load_sea_raft()                      # -> eval 模式 RAFT, 默认 cuda
    model = load_sea_raft(device='cpu')
    flow = model(img1, img2, iters=4, test_mode=True)['flow'][-1]
"""
import os
import urllib.request
from types import SimpleNamespace

import torch
from safetensors.torch import load_file

from .raft import RAFT
from .utils import InputPadder, coords_grid

# MemorySlices/Tartan-C-T-TSKH432x960-S 的官方训练配置(config/eval/sintel-S.json)
# 与权重对应, 勿改; iters 可在 forward 调用时覆盖
SEA_RAFT_SMALL_ARGS = SimpleNamespace(
    use_var=True, var_min=0, var_max=10,
    pretrain="resnet18", initial_dim=64, block_dims=[64, 128, 256],
    radius=4, dim=128, num_blocks=2, iters=4,
)

HF_REPO = "MemorySlices/Tartan-C-T-TSKH432x960-S"

_WEIGHTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights")


def load_sea_raft(weights: str = "", device: str = "cuda", iters: int = 4) -> RAFT:
    """加载 SEA-RAFT-small; weights 缺省用包内缓存, 不存在则从镜像自动下载.

    Args:
        weights: safetensors 文件路径; 空串 = <pkg>/weights/<repo>.safetensors
        device: 'cuda' / 'cpu' (GPU 红线下由 CUDA_VISIBLE_DEVICES 控制具体卡)
        iters: 推理迭代数(官方 S 配置 4)
    """
    if not weights:
        os.makedirs(_WEIGHTS_DIR, exist_ok=True)
        weights = os.path.join(_WEIGHTS_DIR, HF_REPO.split("/")[-1] + ".safetensors")
    if not os.path.exists(weights):
        endpoint = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
        url = f"{endpoint}/{HF_REPO}/resolve/main/model.safetensors"
        print(f"[vendor_sea_raft] 权重缺失, 下载 {url}")
        tmp = weights + ".part"
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, weights)

    cfg = dict(vars(SEA_RAFT_SMALL_ARGS), iters=iters)
    args = SimpleNamespace(**cfg)
    model = RAFT(args)
    state = dict(load_file(weights))
    # 上游 main 分支 layer.py 把 downsample 的 BN 同时注册为 bn3 与 downsample.1(同一模块
    # 双路径), 放出的权重只存了 bn3.* 一份——此处按双注册语义补别名, 非结构改动
    for k in [k for k in state if ".bn3." in k]:
        state[k.replace(".bn3.", ".downsample.1.")] = state[k]
    model.load_state_dict(state, strict=True)
    model = model.to(device)
    model.eval()
    return model


__all__ = ["RAFT", "load_sea_raft", "InputPadder", "coords_grid", "SEA_RAFT_SMALL_ARGS", "HF_REPO"]
