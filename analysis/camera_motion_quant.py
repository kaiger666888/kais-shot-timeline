# -*- coding: utf-8 -*-
"""GPR-L2 光流运镜/动作量化探针 —— 把「运镜比喻」翻译成数值证据.

方法(方法论与上游实现见 analysis/vendor_sea_raft/README.md 与 docs/gpr_flow_report.md):
  1. ffmpeg 抽窗内帧(可降采样宽度), 自适应 stride 取 20-40 个帧对;
  2. 帧对光流: SEA-RAFT-small(GPU, 默认) 或 OpenCV Farneback(CPU 降级);
  3. 全局单应(仿射)分量 = 相机运动: 平移(pan/tilt) + 散度(zoom/push) + 旋转,
     稳健拟合(MAD 剔野值)把运动主体从全局模型里剥掉;
  4. 残差局部运动 = 角色动作能量曲线(时间轴, 中位数/p90 px/帧);
  5. 静止判定: 低光流像素占比(可定标阈值) + 相机通道全零检验.

输出 JSON schema (camera_motion_quant/1):
  source{video,start,end,fps,n_frames,window_dur,flow_width,flow_height}
  impl{name,model,device,iters}
  pairs[{t0_sec,t1_sec,frame_i,frame_j,stride,
         camera{tx_px_per_frame,ty_px_per_frame,zoom_scale_per_frame,
                rot_deg_per_frame,inlier_ratio,foe_offset_pct},
         residual{median_px_per_frame,p90_px_per_frame,p99_px_per_frame},
         global_flow_mag_px_per_frame,static_ratio}]
  camera{label,dominant,pan{direction,deg_per_s,pct_frame_per_s},
         tilt{...},zoom{direction,pct_per_s,scale_per_frame},
         rot_deg_per_s,foe_offset_pct_frame,confidence}
  residual_curve[{t_norm,t_sec,energy_median_px_per_frame,
                  energy_p90_px_per_frame,static_ratio}]
  static{static_ratio_mean,static_ratio_min,
         action_peak{t_norm,t_sec,energy_p90_px_per_frame},verdict}
  thresholds{...}

用法:
  CUDA_VISIBLE_DEVICES=2 .venv_flow/bin/python analysis/camera_motion_quant.py \\
      --video <mp4> --start 182.9003 --end 185.6 --label r071 \\
      --out analysis/flow_probe/r071_flow.json
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent          # analysis/
REPO = HERE.parent                              # 仓根, 供 vendor 包导入
sys.path.insert(0, str(REPO))

# ---- 判定阈值(初版经验值, 定标讨论见 docs/gpr_flow_report.md §5) ----
TH_STATIC_PCT_FRAME = 0.5    # %画面/s: pan/tilt 低于此认为静止
TH_STATIC_ZOOM_PCT = 1.0     # %/s: 缩放率低于此认为静止
TH_STATIC_ROT_DEG = 0.5      # °/s
TH_SECONDARY_RATIO = 0.5     # 次通道 ≥ 主通道×0.5 时并入标签
TH_PUSH_TRANS_RATIO = 0.35   # zoom-in 且平移 ≥ zoom×0.35 → 判 push(推近)而非纯 zoom
TH_FLOW_SAT_PCT = 25.0       # 帧对 |光流|p90 超画面宽 25% → 疑似量程饱和, stride 减半重测


def probe_fps(video: str) -> tuple:
    """ffprobe 取流帧率与时长(GT 切片恒定 30fps, 通用路径仍探流)."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-show_entries",
         "format=duration", "-of", "json", video],
        capture_output=True, text=True, timeout=30)
    info = json.loads(r.stdout)
    num, den = info["streams"][0]["r_frame_rate"].split("/")
    return float(num) / float(den), float(info.get("format", {}).get("duration") or 0.0)


def extract_frames(video: str, start: float, end: float, width: int, outdir: Path) -> list:
    """ffmpeg 精确抽窗内全部帧(先快进到窗前 1s, 再 select 滤镜逐帧精确, 免转码)."""
    seek = max(0.0, start - 1.0)
    rel_s, rel_e = start - seek, end - seek
    vf = f"select='between(t,{rel_s:.6f},{rel_e:.6f})',scale={width}:-2"
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", f"{seek:.6f}", "-i", video,
           "-vf", vf, "-vsync", "0", "-q:v", "2", str(outdir / "f%04d.jpg")]
    subprocess.run(cmd, check=True, timeout=300)
    return sorted(outdir.glob("f*.jpg"))


def pick_stride(n_frames: int, target_pairs: int) -> int:
    """窗长自适应 stride: 帧对数贴近 target_pairs 且尽量 ≥20(极短窗退化为全相邻对)."""
    stride = max(1, math.ceil((n_frames - 1) / max(1, target_pairs)))
    while stride > 1 and (n_frames - 1) // stride < 20:
        stride -= 1
    return stride


# ---------- 光流实现 ----------

class SeaRaftFlow:
    """SEA-RAFT-small (vendor), 输入 uint8 BGR 帧, 返回 (H,W,2) float32 光流."""

    def __init__(self, device: str, iters: int):
        import torch
        from analysis.vendor_sea_raft import load_sea_raft
        self.torch = torch
        self.iters = iters
        self.device = device if (device == "cpu" or torch.cuda.is_available()) else "cpu"
        self.model = load_sea_raft(device=self.device, iters=iters)

    def __call__(self, frame_bgr: np.ndarray, next_bgr: np.ndarray) -> np.ndarray:
        torch = self.torch
        imgs = []
        for f in (frame_bgr, next_bgr):
            t = torch.from_numpy(np.ascontiguousarray(f[:, :, ::-1]))  # BGR→RGB
            imgs.append(t.permute(2, 0, 1)[None].to(self.device).float())
        with torch.no_grad():
            out = self.model(*imgs, iters=self.iters, test_mode=True)
        return out["flow"][-1][0].permute(1, 2, 0).cpu().numpy()


class FarnebackFlow:
    """OpenCV Farneback 稠密光流(CPU 降级实现, 接口与 SEA-RAFT 对齐)."""

    def __init__(self):
        import cv2
        self.cv2 = cv2

    def __call__(self, frame_bgr: np.ndarray, next_bgr: np.ndarray) -> np.ndarray:
        g1 = self.cv2.cvtColor(frame_bgr, self.cv2.COLOR_BGR2GRAY)
        g2 = self.cv2.cvtColor(next_bgr, self.cv2.COLOR_BGR2GRAY)
        return self.cv2.calcOpticalFlowFarneback(
            g1, g2, None, 0.5, 3, 15, 3, 5, 1.2, 0)


def make_flow_fn(args):
    """auto: vendor 可导入且 CUDA 可用 → sea-raft; 否则 farneback(降级, 报告写明)."""
    if args.impl in ("auto", "sea-raft"):
        try:
            import torch  # noqa: F401
            fn = SeaRaftFlow(args.device, args.iters)
            return fn, {"name": "sea-raft",
                        "model": "MemorySlices/Tartan-C-T-TSKH432x960-S",
                        "device": fn.device, "iters": args.iters}
        except Exception as e:  # noqa: BLE001 探针允许显式降级, 原因打印留痕
            if args.impl == "sea-raft":
                raise
            print(f"[flow] sea-raft 不可用({type(e).__name__}: {e}), 降级 farneback")
    fn = FarnebackFlow()
    return fn, {"name": "farneback", "model": "cv2.calcOpticalFlowFarneback",
                "device": "cpu", "iters": 0}


# ---------- 全局/残差分解 ----------

def _lstsq_affine(x, y, u, v, keep):
    """最小二乘仿射: 解 [x y 1]·[[a1,a2,tx],[a3,a4,ty]] = (u, v)."""
    D = np.stack([x[keep], y[keep], np.ones(keep.sum())], axis=1)
    sol, *_ = np.linalg.lstsq(D, np.stack([u[keep], v[keep]], axis=1), rcond=None)
    return (*sol[:, 0], *sol[:, 1])  # a1,a2,tx,a3,a4,ty


def fit_global_model(x, y, u, v, w, h):
    """稳健全局(相机)模型估计 —— 面向「大主体运动污染」场景的三段式:

    1. 平移假设 T0=(median u, median v): 分量中位数抗 49% 外点;
    2. 平移一致像素(误差<2.5%画面宽)上拟合完整仿射(这些像素大概率属背景/主平面),
       MAD 再剔一轮野值;
    3. 平移模型 vs 仿射模型按内点数(阈值 2.5%画面宽)竞争: 仿射解释不了更多像素
       就退回纯平移(zoom=1, rot=0) —— 防止把主体运动拟合荒谬的旋转/缩放.
    主体占满画面、两者支撑都不足 20% 时标 degenerate(该对不进相机聚合).

    Returns (params6orNone, model_kind, inlier_ratio, support_ratio)
    """
    thr = max(0.025 * w, 1.0)
    tx0, ty0 = float(np.median(u)), float(np.median(v))
    m_trans = np.hypot(u - tx0, v - ty0) < thr
    support_t = float(m_trans.mean())
    if support_t < 0.20:
        return None, "degenerate", 0.0, support_t
    # 平移一致像素上拟仿射, 再 MAD 剔野值两轮(仿射可把平移外点捞回内点集)
    keep = m_trans.copy()
    params = _lstsq_affine(x, y, u, v, keep)
    for _ in range(2):
        a1, a2, tx, a3, a4, ty = params
        mag = np.hypot(u - (a1 * x + a2 * y + tx), v - (a3 * x + a4 * y + ty))
        med = np.median(mag[keep])
        mad = np.median(np.abs(mag[keep] - med))
        keep = mag <= max(med + 3.0 * 1.4826 * mad, med + 1e-3)
        params = _lstsq_affine(x, y, u, v, keep)
    a1, a2, tx, a3, a4, ty = params
    m_aff = np.hypot(u - (a1 * x + a2 * y + tx), v - (a3 * x + a4 * y + ty)) < thr
    # 合理性闸: 真实相机帧对级尺度变化/滚转不会超此量级; 越界说明 LSQ 把
    # 视差/主体运动塞进了剪切项 → 回退纯平移模型(退化说明见 docstring)
    s_pair = 1.0 + (a1 + a4) / 2.0
    rot_pair = math.degrees(0.5 * math.atan2(a3 - a2, (a1 + a4) + 2.0))
    plausible = 0.75 <= s_pair <= 1.25 and abs(rot_pair) <= 10.0
    if m_aff.mean() < 0.20 or not plausible or m_aff.sum() <= m_trans.sum():
        return (0.0, 0.0, tx0, 0.0, 0.0, ty0), "translation", support_t, support_t
    return params, "affine", float(m_aff.mean()), float(m_aff.mean())


def analyze_pair(flow: np.ndarray, stride: float) -> dict:
    """单帧对分解: 全局模型(相机) + 残差(动作能量).

    平移/旋转按 dt 线性每帧化; 缩放按等速假设开 stride 次方每帧化.
    """
    h, w = flow.shape[:2]
    grid = 4
    fu, fv = flow[..., 0], flow[..., 1]
    xs, ys = np.meshgrid(np.arange(0, w, grid), np.arange(0, h, grid))
    params, kind, inlier, support = fit_global_model(
        xs.ravel().astype(np.float64), ys.ravel().astype(np.float64),
        fu[::grid, ::grid].ravel().astype(np.float64),
        fv[::grid, ::grid].ravel().astype(np.float64), w, h)
    if params is None:
        # degenerate: 主体占满画面, 该对只出残差统计, 相机记 None
        gmag = np.hypot(fu, fv)
        return {
            "camera": None, "model_kind": kind,
            "residual": {"median_px_per_frame": float(np.median(gmag) / stride),
                         "p90_px_per_frame": float(np.percentile(gmag, 90) / stride),
                         "p99_px_per_frame": float(np.percentile(gmag, 99) / stride)},
            "global_flow_mag_px_per_frame": float(np.median(gmag) / stride),
            "flow_p90_px_pair": float(np.percentile(gmag, 90)),
        }
    a1, a2, tx, a3, a4, ty = params
    px, py = np.meshgrid(np.arange(w), np.arange(h))
    rmag = np.hypot(fu - (a1 * px + a2 * py + tx), fv - (a3 * px + a4 * py + ty))
    gmag = np.hypot(fu, fv)
    # 拟合得到的 (a1..a4) 是光流场雅可比 A = M − I(M=底层单应/仿射):
    # 尺度 s = 1 + trace(A)/2 (纯平移 A=0 → s=1); 旋转取 M 的相似分量
    s_pair = 1.0 + (a1 + a4) / 2.0
    return {
        "camera": {
            "tx_px_per_frame": float(tx / stride),
            "ty_px_per_frame": float(ty / stride),
            "zoom_scale_per_frame": float(s_pair ** (1.0 / stride)),
            "rot_deg_per_frame": float(math.degrees(
                0.5 * math.atan2(a3 - a2, (a1 + a4) + 2.0)) / stride),
            "inlier_ratio": inlier,
        },
        "model_kind": kind,
        "support_ratio": support,
        "affine_raw": {"a1": a1, "a2": a2, "tx": tx, "a3": a3, "a4": a4, "ty": ty},
        "residual": {
            "median_px_per_frame": float(np.median(rmag) / stride),
            "p90_px_per_frame": float(np.percentile(rmag, 90) / stride),
            "p99_px_per_frame": float(np.percentile(rmag, 99) / stride),
        },
        "global_flow_mag_px_per_frame": float(np.median(gmag) / stride),
        "flow_p90_px_pair": float(np.percentile(gmag, 90)),  # 帧对级, 量程饱和检验用
    }


def foe_offset_pct(a1, a2, tx, a3, a4, ty, w, h):
    """焦点扩散(FOE)偏离画面中心比例(以半画面宽为单位).

    (a1..a4)已是光流雅可比 A=M−I, FOE 解 A·p + t = 0.
    纯光变 zoom 的 FOE≈镜头光轴中心; 推轨/摇+推组合 FOE 常明显偏心或出画.
    """
    A = np.array([[a1, a2], [a3, a4]])
    t = np.array([tx, ty])
    if abs(np.linalg.det(A)) < 1e-6:
        return None
    foe = -np.linalg.solve(A, t)
    return float(np.hypot(*(foe - np.array([w / 2, h / 2]))) / (w / 2))


def classify_camera(med: dict, w: int, h: int, fps: float, hfov: float) -> dict:
    """相机通道汇总+分类(输入为跨帧对中位数). 方向约定: 场景右移 ⇔ 相机左摇."""
    tx, ty = med["tx_px_per_frame"], med["ty_px_per_frame"]
    zoom_pf, rot_ds = med["zoom_scale_per_frame"], med["rot_deg_per_s"]
    pan_pct = abs(tx) / w * fps * 100.0            # %画面宽/s
    tilt_pct = abs(ty) / h * fps * 100.0
    pan_deg = abs(tx) / w * hfov * fps             # °/s(按 --hfov 假设换算)
    tilt_deg = abs(ty) / h * (hfov * h / w) * fps
    zoom_pct = abs(zoom_pf - 1.0) * fps * 100.0    # %/s
    pan_dir = "pan-left" if tx > 0 else "pan-right"
    tilt_dir = "tilt-up" if ty > 0 else "tilt-down"  # 图像系 y 向下: 场景下移 ⇔ 相机上摇
    zoom_dir = "zoom-in" if zoom_pf > 1.0 else "zoom-out"

    chans = {"pan": pan_pct, "tilt": tilt_pct, "zoom": zoom_pct,
             "rot": abs(rot_ds) / hfov * 100.0}
    static = (pan_pct < TH_STATIC_PCT_FRAME and tilt_pct < TH_STATIC_PCT_FRAME
              and zoom_pct < TH_STATIC_ZOOM_PCT and abs(rot_ds) < TH_STATIC_ROT_DEG)
    if static:
        label, dominant = "static", "static"
    else:
        dominant = max(chans, key=chans.get)
        label = {"pan": pan_dir, "tilt": tilt_dir, "zoom": zoom_dir}[dominant]
        if dominant == "zoom" and zoom_dir == "zoom-in" and \
                max(pan_pct, tilt_pct) >= zoom_pct * TH_PUSH_TRANS_RATIO:
            label = "push-in"   # 散度+显著平移 = 前推轨迹(定标说明见报告 §4)
        sub_names = {"pan": pan_dir, "tilt": tilt_dir, "zoom": zoom_dir, "rot": "roll"}
        for name, pct in sorted(chans.items(), key=lambda kv: -kv[1]):
            floor = TH_STATIC_ZOOM_PCT if name == "zoom" else TH_STATIC_PCT_FRAME
            if name != dominant and pct >= chans[dominant] * TH_SECONDARY_RATIO \
                    and pct > floor:
                label += "+" + sub_names[name]
        # 速度档位前缀: 甩镜量级(pan ≥ 40%画面宽/s) / 快速竖摇(tilt ≥ 40%画面高/s)
        if dominant == "pan" and pan_pct >= 40.0:
            label = "whip-" + label
        elif dominant == "tilt" and tilt_pct >= 40.0:
            label = "fast-" + label
    return {
        "label": label, "dominant": dominant,
        "pan": {"direction": pan_dir, "deg_per_s": round(pan_deg, 2),
                "pct_frame_per_s": round(pan_pct, 2)},
        "tilt": {"direction": tilt_dir, "deg_per_s": round(tilt_deg, 2),
                 "pct_frame_per_s": round(tilt_pct, 2)},
        "zoom": {"direction": zoom_dir, "pct_per_s": round(zoom_pct, 2),
                 "scale_per_frame": round(zoom_pf, 5)},
        "rot_deg_per_s": round(rot_ds, 2),
        "foe_offset_pct_frame": med.get("foe_offset"),
        "confidence": round(med["inlier_ratio"], 3),
    }


def aggregate(pairs: list, w: int, h: int, fps: float, hfov: float, static_px: float):
    """跨帧对聚合: 时间轴门控剔瞬时污染对 → 可靠对中位数 → 分类 + 曲线 + 静止判定.

    门控依据: 相机运动跨帧持续一致; 主体爆发(如直扑镜头)只在个别帧对上表现为
    相机参数瞬时离群(巨大假旋转/缩放). 对 k×MAD 之外的相机参数对, 该对不进
    相机聚合, 残差/静止统计仍保留(动作证据不受门控影响).
    """
    cam_pairs = [p for p in pairs if p["camera"] is not None]

    def gate(vals, k=3.5):
        vals = np.asarray(vals, dtype=np.float64)
        med = np.median(vals)
        mad = np.median(np.abs(vals - med)) * 1.4826
        return np.abs(vals - med) <= k * mad + 1e-6

    reliable = cam_pairs
    if cam_pairs:
        gates = np.ones(len(cam_pairs), dtype=bool)
        for key, transform in (("tx_px_per_frame", None), ("ty_px_per_frame", None),
                               ("zoom_scale_per_frame", lambda s: s - 1.0),
                               ("rot_deg_per_frame", None)):
            vals = [p["camera"][key] for p in cam_pairs]
            if transform:
                vals = [transform(v) for v in vals]
            gates &= gate(vals)
        reliable = [p for p, g in zip(cam_pairs, gates) if g]

    if reliable:
        def med(key, src=None):
            return float(np.median([(p["camera"] if src is None else p)[key]
                                    for p in (src or reliable)]))

        foe_vals = [p["foe_offset_pct"] for p in reliable
                    if p.get("foe_offset_pct") is not None]
        camera = classify_camera(
            {"tx_px_per_frame": med("tx_px_per_frame"),
             "ty_px_per_frame": med("ty_px_per_frame"),
             "zoom_scale_per_frame": med("zoom_scale_per_frame"),
             "rot_deg_per_s": med("rot_deg_per_frame") * fps,
             "inlier_ratio": med("inlier_ratio"),
             "foe_offset": float(np.median(foe_vals)) if foe_vals else None},
            w, h, fps, hfov)
        camera["n_pairs_reliable"] = len(reliable)
        camera["n_pairs_with_fit"] = len(cam_pairs)
        # 相位剖面: 窗口三分位各自的相机方向中位数 —— 运镜随时间的变化
        # (beat 证据: 对峙段 vs 爆发段往往方向/速度不同)
        phases = []
        for k in range(3):
            third = [p for p in reliable if k / 3 <= p["t_norm"] < (k + 1) / 3] or \
                    [p for p in reliable if abs(p["t_norm"] - (k + 0.5) / 3) < 0.2]
            if not third:
                continue
            txm = float(np.median([p["camera"]["tx_px_per_frame"] for p in third]))
            tym = float(np.median([p["camera"]["ty_px_per_frame"] for p in third]))
            sm = float(np.median([p["camera"]["zoom_scale_per_frame"] for p in third]))
            desc = []
            if abs(txm) / w * fps * 100 >= TH_STATIC_PCT_FRAME:
                desc.append("pan-left" if txm > 0 else "pan-right")
            if abs(tym) / h * fps * 100 >= TH_STATIC_PCT_FRAME:
                desc.append("tilt-up" if tym > 0 else "tilt-down")
            if abs(sm - 1) * fps * 100 >= TH_STATIC_ZOOM_PCT:
                desc.append("zoom-in" if sm > 1 else "zoom-out")
            phases.append({
                "t_range": [round(k / 3, 2), round((k + 1) / 3, 2)],
                "pan_pct_frame_per_s": round(abs(txm) / w * fps * 100, 1),
                "tilt_pct_frame_per_s": round(abs(tym) / h * fps * 100, 1),
                "zoom_pct_per_s": round(abs(sm - 1) * fps * 100, 1),
                "motion": "+".join(desc) if desc else "static",
            })
        camera["phases"] = phases
    else:
        camera = {"label": "unresolvable-subject-dominated", "dominant": "unknown",
                  "n_pairs_reliable": 0, "n_pairs_with_fit": len(cam_pairs),
                  "note": "无一对通过时间轴门控, 相机分量无法与主体运动分离"}

    curve = [{"t_norm": round(p["t_norm"], 4), "t_sec": round(p["t0_sec"], 3),
              "energy_median_px_per_frame": round(p["residual"]["median_px_per_frame"], 3),
              "energy_p90_px_per_frame": round(p["residual"]["p90_px_per_frame"], 3),
              "static_ratio": round(p["static_ratio"], 4)} for p in pairs]
    peak = max(pairs, key=lambda p: p["residual"]["p90_px_per_frame"])
    sratios = [p["static_ratio"] for p in pairs]
    res_hi = float(np.median([p["residual"]["p90_px_per_frame"] for p in pairs])) \
        >= 2.0 * static_px
    if camera["dominant"] == "unknown":
        verdict = "主体主导(相机分量不可分离), 见残差曲线"
    elif camera["dominant"] == "static" and not res_hi:
        verdict = "全静止(相机与主体均无显著运动)"
    elif camera["dominant"] == "static":
        verdict = "相机静止+主体运动(fixed-camera action)"
    elif not res_hi:
        verdict = "纯运镜(相机运动, 无显著主体动作)"
    else:
        verdict = "运镜+主体运动(mixed camera & subject motion)"
    return {
        "camera": camera,
        "residual_curve": curve,
        "static": {
            "static_ratio_mean": round(float(np.mean(sratios)), 4),
            "static_ratio_min": round(float(np.min(sratios)), 4),
            "action_peak": {"t_norm": round(peak["t_norm"], 4),
                            "t_sec": round(peak["t0_sec"], 3),
                            "energy_p90_px_per_frame":
                                round(peak["residual"]["p90_px_per_frame"], 3)},
            "verdict": verdict,
        },
        "thresholds": {
            "static_px_per_frame": static_px,
            "static_pct_frame_per_s": TH_STATIC_PCT_FRAME,
            "static_zoom_pct_per_s": TH_STATIC_ZOOM_PCT,
            "static_rot_deg_per_s": TH_STATIC_ROT_DEG,
            "secondary_ratio": TH_SECONDARY_RATIO,
            "push_trans_ratio": TH_PUSH_TRANS_RATIO,
            "note": "初版经验值, 定标建议见 docs/gpr_flow_report.md §5",
        },
    }


def main():
    ap = argparse.ArgumentParser(description="光流运镜/动作量化探针(GPR-L2)")
    ap.add_argument("--video", required=True, help="输入视频(GT 切片或整片)")
    ap.add_argument("--start", type=float, default=None, help="窗口起点(秒), 缺省=0")
    ap.add_argument("--end", type=float, default=None, help="窗口终点(秒), 缺省=片尾")
    ap.add_argument("--out", required=True, help="输出 JSON 路径")
    ap.add_argument("--label", default="", help="镜标签(仅写入元数据, 如 s064/r071)")
    ap.add_argument("--impl", choices=["auto", "sea-raft", "farneback"], default="auto",
                    help="光流实现: auto=优先 SEA-RAFT(GPU), 失败降级 Farneback")
    ap.add_argument("--device", default="cuda", help="sea-raft 设备(cuda/cpu)")
    ap.add_argument("--flow-width", type=int, default=480, help="光流计算宽度(等比缩放)")
    ap.add_argument("--target-pairs", type=int, default=32, help="目标帧对数(20-40 自适应)")
    ap.add_argument("--iters", type=int, default=4, help="SEA-RAFT 迭代数(官方 S 配置=4)")
    ap.add_argument("--hfov", type=float, default=55.0,
                    help="假设水平视场角(°), 仅用于 deg/s 换算; 主指标是 %画面/s")
    ap.add_argument("--static-px", type=float, default=0.6,
                    help="静止阈值: |光流| 低于该 px/帧 的像素判静止")
    ap.add_argument("--keep-frames", action="store_true", help="保留抽帧目录(调试)")
    args = ap.parse_args()

    import cv2  # 帧读取, 两种光流实现均需

    t_wall = time.time()
    fps, dur = probe_fps(args.video)
    start = 0.0 if args.start is None else args.start
    end = dur if args.end is None else args.end
    if end <= start:
        sys.exit(f"[error] 窗口非法: start={start} >= end={end}")

    tmpdir = Path(tempfile.mkdtemp(prefix="flowprobe_"))
    try:
        frames = extract_frames(args.video, start, end, args.flow_width, tmpdir)
        if len(frames) < 2:
            sys.exit(f"[error] 窗口内仅 {len(frames)} 帧, 无法计算")
        H, W = cv2.imread(str(frames[0])).shape[:2]
        stride = pick_stride(len(frames), args.target_pairs)
        print(f"[frames] {len(frames)} 帧 @ {fps:.3f}fps, 流分辨率 {W}x{H}, stride={stride}")

        flow_fn, impl_meta = make_flow_fn(args)
        if impl_meta["name"] == "sea-raft":
            print(f"[flow] SEA-RAFT-small on {impl_meta['device']} "
                  f"(具体卡由 CUDA_VISIBLE_DEVICES 控制, 工单红线=GPU2)")
        else:
            print("[flow] Farneback (CPU, 降级实现)")

        def run_pairs(stride):
            pairs = []
            t0 = time.time()
            idx = list(range(0, len(frames) - stride, stride))
            sat = 0
            for n, i in enumerate(idx):
                f1 = cv2.imread(str(frames[i]))
                f2 = cv2.imread(str(frames[i + stride]))
                flow = flow_fn(f1, f2)
                r = analyze_pair(flow, stride)
                r["frame_i"], r["frame_j"] = i, i + stride
                r["t0_sec"] = round(start + i / fps, 3)
                r["t1_sec"] = round(start + (i + stride) / fps, 3)
                r["t_norm"] = (i + stride / 2) / max(1, len(frames) - 1)
                r["stride"] = stride
                # 静止掩码: 全场 |光流| < 阈值(帧对级阈值 = 每帧阈值×stride)
                r["static_ratio"] = float(
                    np.mean(np.hypot(flow[..., 0], flow[..., 1])
                            < args.static_px * stride))
                if "affine_raw" in r:
                    r["foe_offset_pct"] = foe_offset_pct(
                        *[r["affine_raw"][k]
                          for k in ("a1", "a2", "tx", "a3", "a4", "ty")], W, H)
                else:
                    r["foe_offset_pct"] = None
                pairs.append(r)
                sat += r["flow_p90_px_pair"] > TH_FLOW_SAT_PCT / 100.0 * W
                if (n + 1) % 10 == 0:
                    print(f"  {n + 1}/{len(idx)} 对")
            print(f"[flow] {len(idx)} 对完成, {time.time() - t0:.1f}s, 疑似饱和 {sat} 对")
            return pairs, sat / max(1, len(idx))

        pairs, sat_ratio = run_pairs(stride)
        if sat_ratio > 0.3 and stride > 1:
            # 快速运动镜: 帧对位移超可信量程 → stride 减半重测(帧对数让位于量程)
            new_stride = max(1, stride // 2)
            print(f"[flow] 光流疑似饱和({sat_ratio:.0%}), stride {stride}->{new_stride} 重测")
            pairs, _ = run_pairs(new_stride)

        result = {
            "schema": "camera_motion_quant/1",
            "label": args.label,
            "source": {"video": args.video, "start": start, "end": end,
                       "fps": fps, "n_frames": len(frames),
                       "window_dur": round(end - start, 3),
                       "flow_width": W, "flow_height": H},
            "impl": impl_meta,
            "pairs": [{k: v for k, v in p.items() if k != "affine_raw"}
                      for p in pairs],
            "affine_raw": [p["affine_raw"] for p in pairs if "affine_raw" in p],
            "elapsed_s": round(time.time() - t_wall, 1),
        }
        result.update(aggregate(pairs, W, H, fps, args.hfov, args.static_px))

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[out] {out}")

        cam, st = result["camera"], result["static"]
        if "pan" in cam:
            print(f"[summary] {args.label or Path(args.video).stem}: "
                  f"相机={cam['label']} | {cam['pan']['direction']} "
                  f"{cam['pan']['deg_per_s']}°/s ({cam['pan']['pct_frame_per_s']}%画面/s) | "
                  f"{cam['tilt']['direction']} {cam['tilt']['deg_per_s']}°/s | "
                  f"{cam['zoom']['direction']} {cam['zoom']['pct_per_s']}%/s | "
                  f"rot {cam['rot_deg_per_s']}°/s | 拟合内点率 {cam['confidence']}")
        else:
            print(f"[summary] {args.label or Path(args.video).stem}: "
                  f"相机={cam['label']} ({cam.get('note', '')})")
        print(f"[summary] 残差峰值 p90={st['action_peak']['energy_p90_px_per_frame']}px/帧 "
              f"@ {st['action_peak']['t_norm']:.0%} 时位 | 静止占比 "
              f"mean={st['static_ratio_mean']:.0%} min={st['static_ratio_min']:.0%} "
              f"| {st['verdict']}")
    finally:
        if not args.keep_frames:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
