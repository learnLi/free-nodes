#!/bin/sh
# NAS 宿主机侧的定时任务入口（Docker 版）：
#   git 拉代码 -> 取 Stage 1 产物 -> 容器内探测 -> 提交推送
#
# 分工：
#   宿主机  git（拉代码、取 output 分支的 Stage 1 产物、提交推送）
#   容器    探测（需要 Python 环境与网络）
# 仓库的 probe.py 直接挂载进容器，代码更新不需要重建镜像。
#
# 用法：
#   sh docker/run.sh [仓库目录] [工作目录]
set -e

REPO="${1:-/root/free-nodes/repo}"
WORK="${2:-/root/free-nodes}"
IMAGE="${IMAGE:-free-nodes-probe:latest}"
BRANCH="probe-domestic"

cd "$REPO" || { echo "仓库目录不存在：$REPO"; exit 1; }

# 随机抖动：打散「固定周期自动外连」的特征。
# 住宅 IP 每 6 小时固定向几百个境外 IP 发连接，形态很规整。
JITTER_MAX=$((15 * 60))
if [ "${INTERVAL_JITTER:-1}" = "1" ] && [ "$JITTER_MAX" -gt 0 ]; then
  W=$(( $(od -An -N2 -tu2 /dev/urandom 2>/dev/null || echo $RANDOM) % JITTER_MAX ))
  echo "[$(date '+%F %T')] 随机等待 ${W}s（打散周期性）"
  sleep "$W"
fi

# ---- 1. 拉最新代码（probe.py 会随仓库更新，容器是挂载的，不用重建）----
git config user.name 'NAS probe' 2>/dev/null || true
git config user.email 'probe@nas.local' 2>/dev/null || true
git config core.sshCommand "ssh -i /root/.ssh/nas_probe -o UserKnownHostsFile=/root/.ssh/github_known_hosts -o StrictHostKeyChecking=yes" 2>/dev/null || true
git fetch --depth=1 origin main || true
git checkout -B main origin/main 2>/dev/null || true
git reset --hard origin/main 2>/dev/null || true

# ---- 2. 取 Stage 1 产物（output 分支里最新的带时间戳副本）----
git fetch --depth=1 origin \
  "+refs/heads/output:refs/remotes/origin/output" 2>/dev/null || true
LIST_NAME=$(git ls-tree --name-only origin/output 2>/dev/null \
  | grep -oE 'list\.meta\.us_[0-9]{8}_[0-9]{4}\.yml' | sort | tail -1 || true)
if [ -z "$LIST_NAME" ]; then
  echo "output 分支里没有 Stage 1 产物（list.meta.us_<ts>.yml），跳过本次探测"
  exit 1
fi
mkdir -p "$WORK/in" "$WORK/out"
git show "origin/output:$LIST_NAME" > "$WORK/in/list.meta.us.yml" || exit 1
STAMP=$(echo "$LIST_NAME" | sed -E 's/^list\.meta\.us_([0-9]{8}_[0-9]{4})\.yml$/\1/')
echo "[$(date '+%F %T')] 探测 Stage 1 产物 $LIST_NAME（批次 $STAMP）"

# ---- 3. 容器内探测 ----
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "镜像 $IMAGE 不存在，构建中..."
  docker build -t "$IMAGE" -f docker/Dockerfile . || exit 1
fi
docker run --rm \
  -v "$REPO:/app:ro" \
  -v "$WORK/in:/in:ro" \
  -v "$WORK/out:/out" \
  -w /out \
  -e LIST=/in/list.meta.us.yml \
  -e OUT_DIR=/out \
  -e PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}" \
  -e WORKERS="${WORKERS:-64}" \
  -e TZ=Asia/Shanghai \
  "$IMAGE" || exit 1

# ---- 4. 提交推送 ----
if [ ! -f "$WORK/out/probe_domestic.csv" ]; then
  echo "没有生成 probe_domestic.csv"
  exit 1
fi
# 结果按**列表的批次**命名，和美国侧的 probe_<ts>.csv 严格对应
cp "$WORK/out/probe_domestic.csv" "./probe_domestic_${STAMP}.csv"
cp "$WORK/out/probe_domestic.csv" ./probe_domestic.csv

if [ "${NO_PUSH:-0}" = "1" ]; then
  echo "[$(date '+%F %T')] NO_PUSH=1，跳过推送。结果在 $WORK/out/"
  exit 0
fi

git checkout -B "$BRANCH" 2>/dev/null || true
# 必须基于远端分支继续，否则推送会被判非快进：
# 直接 checkout -B 会从当前 HEAD（main）开分支，丢掉远端分支上的提交历史。
git fetch --depth=1 origin \
  "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" 2>/dev/null || true
if git rev-parse --verify "origin/$BRANCH" >/dev/null 2>&1; then
  git checkout -B "$BRANCH" "origin/$BRANCH"
  echo "  基于远端分支继续"
else
  git checkout -B "$BRANCH"
  echo "  远端分支不存在，新建"
fi
git add -f probe_domestic*.csv 2>/dev/null || true
if git diff --cached --quiet; then
  echo "  无变化"
else
  git -c user.name="NAS probe" -c user.email="probe@nas.local" \
    commit -m "probe: $(date '+%F %T') 国内可达性探测" || true
  if git push origin HEAD:refs/heads/"$BRANCH"; then
    echo "  已推送 $BRANCH"
  else
    echo "  推送失败（不影响本地结果）"
    exit 1
  fi
fi
echo "[$(date '+%F %T')] 完成"
