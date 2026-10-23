#!/bin/sh
# 容器入口：取节点列表 -> 探测 -> 写结果到 /out
#
# 刻意不包含 git：推送由宿主机负责，容器只需要产出数据。
set -e

LIST_URL="${LIST_URL:-https://cdn.jsdelivr.net/gh/learnLi/free-nodes@output/list.meta.full.yml}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}"
WORKERS="${WORKERS:-64}"
OUT_DIR="${OUT_DIR:-/out}"
LIST="/tmp/list.meta.full.yml"

mkdir -p "$OUT_DIR"

echo "[$(date '+%F %T')] 获取节点列表"
python3 - "$LIST_URL" "$LIST" <<'PY'
import os
import sys
import urllib.request

url, dst = sys.argv[1], sys.argv[2]
proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') \
    or os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
if proxy:
    urllib.request.install_opener(urllib.request.ProxyHandler(
        {'http': proxy, 'https': proxy}))
req = urllib.request.Request(url, headers={'User-Agent': 'free-nodes-probe'})
with urllib.request.urlopen(req, timeout=120) as r:
    data = r.read()
if len(data) < 10000:
    print('节点列表异常（%d 字节）' % len(data))
    sys.exit(1)
open(dst, 'wb').write(data)
print('  %d 字节' % len(data))
PY

echo "[$(date '+%F %T')] 开始探测（timeout=${PROBE_TIMEOUT}s workers=${WORKERS}）"
set -- --input "$LIST" \
       --output "$OUT_DIR/probe_domestic.csv" \
       --timeout "$PROBE_TIMEOUT" \
       --workers "$WORKERS" \
       --ref 223.5.5.5:443 \
       --ref 114.114.114.114:443 \
       --ref 1.1.1.1:443 \
       --ref 8.8.8.8:443
# LIMIT>0 时只探测前 N 个节点（调试用）
if [ -n "${LIMIT:-}" ] && [ "$LIMIT" -gt 0 ] 2>/dev/null; then
  set -- "$@" --limit "$LIMIT"
  echo "  LIMIT=${LIMIT}，只探测前 ${LIMIT} 个节点"
fi
python3 /app/probe.py "$@"

STAMP=$(date '+%Y%m%d_%H%M')
cp "$OUT_DIR/probe_domestic.csv" "$OUT_DIR/probe_domestic_${STAMP}.csv"
# probe.py 把摘要写在工作目录（容器内 /app），这里一并搬到输出目录
for f in probe_summary.json probe_summary.md; do
  [ -f "/app/$f" ] && cp "/app/$f" "$OUT_DIR/"
done
echo "[$(date '+%F %T')] 完成：$OUT_DIR/probe_domestic.csv"
