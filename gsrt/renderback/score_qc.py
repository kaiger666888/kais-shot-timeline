#!/usr/bin/env python3
"""GSRT 量化判分器 v1 — 全片 SSIM + VGG16-fc7 语义相似度曲线 + 低谷检测
用法: python3 score_qc.py TARGET.mp4 RENDER.mp4 [--json OUT.json]
门槛 (2026-08-30 Kai 拍板收紧): SSIM mean>=0.55 / 语义 mean>=0.75 / 无连续 3 帧低于门槛-0.1 的低谷段
判分口径: 双方 fps 均匀抽 24 帧配对 (256x144 SSIM / 224 center-crop VGG)
"""
import sys, json, os, subprocess, tempfile
import numpy as np
from PIL import Image

SSIM_GATE = 0.55
SEM_GATE = 0.75
DIP_SPAN = 3
DIP_MARGIN = 0.10

def sample_frames(video, n=24, size=256):
    d = tempfile.mkdtemp(prefix=f"qc_{os.path.basename(video)[:12]}_")
    subprocess.run(['ffmpeg','-y','-v','error','-i',video,'-vf',
                    f"fps={n}/3.9,scale={size}:{int(size*9/16)}" if False else f"fps=24/3.9,scale={size}:-2",
                    f"{d}/f_%02d.jpg"], check=True)
    return sorted(os.path.join(d,f) for f in os.listdir(d) if f.endswith('.jpg'))

def ssim_curve(tf, rf):
    from skimage.metrics import structural_similarity as ssim
    out = []
    for t, r in zip(tf, rf):
        a = np.asarray(Image.open(t).convert('L'), dtype=np.float32)/255
        b = np.asarray(Image.open(r).convert('L'), dtype=np.float32)/255
        h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
        out.append(float(ssim(a[:h,:w], b[:h,:w], data_range=1.0)))
    return out

def _vgg():
    import torch
    from torchvision import models
    w = os.path.expanduser('~/.cache/torch/hub/checkpoints/vgg16-397923af.pth')
    m = models.vgg16(weights=None)
    m.load_state_dict(torch.load(w, map_location='cpu'))
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    m = m.to(dev).eval()
    head = torch.nn.Sequential(*list(m.classifier.children())[:-1]).to(dev)
    return m, head, dev

def sem_curve(tf, rf):
    import torch
    from torchvision import transforms
    m, head, dev = _vgg()
    tfm = transforms.Compose([transforms.Resize(224), transforms.CenterCrop(224),
                              transforms.ToTensor(),
                              transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])])
    @torch.no_grad()
    def emb(p):
        x = tfm(Image.open(p).convert('RGB')).unsqueeze(0).to(dev)
        return torch.nn.functional.normalize(head(m.features(x).flatten(1)), dim=-1).cpu()[0]
    return [float((emb(t)*emb(r)).sum()) for t, r in zip(tf, rf)]

def dips(curve, gate):
    low = [v < gate - DIP_MARGIN for v in curve]
    runs, i = [], 0
    while i < len(low):
        if low[i]:
            j = i
            while j < len(low) and low[j]: j += 1
            if j - i >= DIP_SPAN: runs.append((i, j-1))
            i = j
        else: i += 1
    return runs

def main():
    target, render = sys.argv[1], sys.argv[2]
    out_json = sys.argv[sys.argv.index('--json')+1] if '--json' in sys.argv else None
    t24 = sample_frames(target); r24 = sample_frames(render)
    n = min(len(t24), len(r24)); t24, r24 = t24[:n], r24[:n]
    ss = ssim_curve(t24, r24)
    se = sem_curve(t24, r24)
    ss_runs, se_runs = dips(ss, SSIM_GATE), dips(se, SEM_GATE)
    verdict = {
        'n_pairs': n,
        'ssim': {'mean': round(float(np.mean(ss)),4), 'min': round(min(ss),4),
                 'gate': SSIM_GATE, 'pass': bool(np.mean(ss) >= SSIM_GATE), 'curve': [round(v,3) for v in ss],
                 'dips': ss_runs},
        'semantic': {'mean': round(float(np.mean(se)),4), 'min': round(min(se),4),
                     'gate': SEM_GATE, 'pass': bool(np.mean(se) >= SEM_GATE), 'curve': [round(v,3) for v in se],
                     'dips': se_runs},
        'overall_pass': bool(np.mean(ss) >= SSIM_GATE and np.mean(se) >= SEM_GATE and not ss_runs and not se_runs),
    }
    print(json.dumps(verdict, ensure_ascii=False, indent=1))
    if out_json:
        json.dump(verdict, open(out_json,'w'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
