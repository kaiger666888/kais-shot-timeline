#!/bin/bash
# GSRT 迭代轮自动接力: 等 ComfyUI 队列排空 → 提交 prompt_v2 迭代轮 (3镜)
# 2026-08-29 night shift — Kai 指令: 迭代推导小江湖EP01抽样分镜prompt直到与黄金集基本一致
set -u
LOG=/data/workspace/kais-shot-timeline/gsrt/renderback/iter_v3.log
echo "[$(date +%H:%M:%S)] watcher start — waiting for ComfyUI queue drain" >> "$LOG"

# 最多等 100 分钟 (压测批预计 <1h 收尾); 每 60s 探一次
DEADLINE=$(( $(date +%s) + 6000 ))
while [ $(date +%s) -lt $DEADLINE ]; do
  Q=$(curl -s -m 8 http://127.0.0.1:8188/queue 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(len(d.get('queue_running',[]))+len(d.get('queue_pending',[])))
except Exception:
    print(999)
" 2>/dev/null)
  if [ "$Q" = "0" ]; then
    # 双确认: 15s 后再查一次, 防两job间空档误判
    sleep 15
    Q2=$(curl -s -m 8 http://127.0.0.1:8188/queue 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(len(d.get('queue_running',[]))+len(d.get('queue_pending',[])))
except Exception:
    print(999)
" 2>/dev/null)
    if [ "$Q2" = "0" ]; then
      echo "[$(date +%H:%M:%S)] queue drained — submitting iter v3" >> "$LOG"
      python3 /data/workspace/kais-shot-timeline/gsrt/renderback/submit_iter.py v3 >> "$LOG" 2>&1
      echo "[$(date +%H:%M:%S)] iter v3 round complete" >> "$LOG"
      exit 0
    fi
  fi
  sleep 60
done
echo "[$(date +%H:%M:%S)] DEADLINE hit — GPU still busy, NOT submitting" >> "$LOG"
exit 1
