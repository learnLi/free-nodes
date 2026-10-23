#!/bin/sh
# NAS 宿主机侧的定时任务：跑容器 + 把结果推回 GitHub。
#
# 群晖：任务计划 -> 用户定义的脚本 -> 计划任务（每 6 小时）
# 威联：任务调度器 -> 创建任务 -> 类型选「Shell 脚本」
#
# 用法：
#   sh docker/run.sh [仓库目录] [输出目录]
#
# 依赖：docker、git。宿主机上需要有仓库的 SSH 部署密钥才能推送。

set -e

REPO="${1:-/volume1/free-nodes}"
OUT_DIR="${2:-/volume1/free-nodes}"
IMAGE="${IMAGE:-free-nodes-probe:latest}"
BRANCH="probe-domestic"

cd "$REPO" || { echo "仓库目录不存在：$REPO"; exit 1; }

# ---- 1. 探测（容器内完成）----
echo "[$(date '+%F %T')] 运行探测容器"
if ! command -v docker >/dev/null 2>&1; then
  echo "找不到 docker"
  exit 1
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "镜像 $IMAGE 不存在，先构建："
  echo "  docker build -t $IMAGE -f docker/Dockerfile ."
  exit 1
fi

docker run --rm \
  -v "$OUT_DIR:/out" \
  -e LIST_URL="${LIST_URL:-https://cdn.jsdelivr.net/gh/learnLi/free-nodes@output/list.meta.full.yml}" \
  -e PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}" \
  -e WORKERS="${WORKERS:-64}" \
  "$IMAGE"

if [ ! -f "$OUT_DIR/probe_domestic.csv" ]; then
  echo "没有生成 probe_domestic.csv"
  exit 1
fi
echo "[$(date '+%F %T')] 探测完成"

# ---- 2. 推送（宿主机负责，容器里没有 git）----
if [ "${NO_PUSH:-0}" = "1" ]; then
  echo "[$(date '+%F %T')] NO_PUSH=1，跳过推送。结果：$OUT_DIR/probe_domestic.csv"
  exit 0
fi

echo "[$(date '+%F %T')] 提交并推送"
cp "$OUT_DIR/probe_domestic.csv" ./probe_domestic.csv
cp "$OUT_DIR"/probe_domestic_*.csv ./ 2>/dev/null || true

git checkout -B "$BRANCH" 2>/dev/null || true
git add -f probe_domestic*.csv
if git diff --cached --quiet; then
  echo "  无变化"
else
  git -c user.name="NAS probe" -c user.email="probe@nas.local" \
    commit -m "probe: $(date '+%F %T') 国内可达性探测"
  if git push origin "$BRANCH"; then
    echo "  已推送 $BRANCH"
  else
    echo "  推送失败（不影响本地结果）。可能没配 SSH 部署密钥。"
    exit 1
  fi
fi
echo "[$(date '+%F %T')] 完成"
