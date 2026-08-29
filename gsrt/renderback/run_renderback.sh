#!/bin/bash
# GSRT render-back 外层循环: 单镜40min轮询超时(退出码3)则续跑, 直到全部完成
cd /data/workspace/kais-shot-timeline/gsrt/renderback
for i in $(seq 1 24); do
  echo "=== ROUND $i $(date '+%H:%M:%S') ==="
  python3 submit_renderback.py
  rc=$?
  if [ $rc -eq 0 ]; then echo "ALL_ROUNDS_DONE rc=0"; exit 0; fi
  if [ $rc -eq 2 ]; then echo "SUBMIT_FAILED_HARD rc=2"; exit 2; fi
  sleep 30
done
echo "MAX_ROUNDS_EXHAUSTED"
exit 1
