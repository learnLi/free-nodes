#!/bin/sh
# 容器入口：探测指定列表里的节点，输出 CSV。
#
# 刻意把「取列表 / 推 GitHub」放在宿主机（docker/run.sh），容器只做探测：
#   宿主机负责 git（拉代码、取 Stage 1 产物、提交推送）
#   容器负责探测（需要 Python 环境与网络）
# 这样 probe.py 改了只要宿主机 git pull 一下，不用重建镜像。
#
# 输入：
#   LIST      列表文件路径（宿主机挂载进来的），默认 /in/list.meta.us.yml
#   LIST_URL  若给了则优先从该 URL 下载列表（覆盖 LIST）
#   OUT_DIR   输出目录，默认 /out
set -e

LIST="${LIST:-/in/list.meta.us.yml}"
OUT_DIR="${OUT_DIR:-/out}"
LIST_URL="${LIST_URL:-}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}"
WORKERS="${WORKERS:-64}"

mkdir -p "$OUT_DIR"

if [ -n "$LIST_URL" ]; then
  echo "[$(date '+%F %T')] 从 URL 获取列表：$LIST_URL"
  python3 - "$LIST_URL" "$LIST" <<'PY'
import os
import sys
import urllib.request

url, dst = sys.argv[1], sys.argv[2]
proxy = (os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
         or os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy'))
if proxy:
    urllib.request.install_opener(urllib.request.ProxyHandler(
        {'http': proxy, 'https': proxy}))
req = urllib.request.Request(url, headers={'User-Agent': 'free-nodes-probe'})
with urllib.request.urlopen(req, timeout=120) as r:
    data = r.read()
if len(data) < 10000:
    print('列表异常（%d 字节）' % len(data))
    sys.exit(1)
open(dst, 'wb').write(data)
print('  %d 字节' % len(data))
PY
fi

if [ ! -s "$LIST" ]; then
  echo "拿不到列表：$LIST"
  exit 1
fi
echo "[$(date '+%F %T')] 开始探测（timeout=${PROBE_TIMEOUT}s workers=${WORKERS}）"

python3 /app/probe.py \
  --input "$LIST" \
  --output "$OUT_DIR/probe_domestic.csv" \
  --timeout "$PROBE_TIMEOUT" \
  --workers "$WORKERS" \
  --ref 223.5.5.5:443 \
  --ref 114.114.114.114:443 \
  --ref 1.1.1.1:443 \
  --ref 8.8.8.8:443

STAMP=$(date -u '+%Y%m%d_%H%M')
cp "$OUT_DIR/probe_domestic.csv" "$OUT_DIR/probe_domestic_${STAMP}.csv"
# probe.py 把摘要写在工作目录，搬到输出目录
for f in probe_summary.json probe_summary.md; do
  [ -f "/app/$f" ] && cp "/app/$f" "$OUT_DIR/"
done
echo "[$(date '+%F %T')] 完成：$OUT_DIR/probe_domestic.csv"
