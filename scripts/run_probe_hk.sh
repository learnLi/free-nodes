#!/bin/sh
# 香港侧的探活任务（在香港 VPS 上跑）。
#
# 香港 VPS **没有 GitHub 写权限**，所以这里只负责「探测」，
# 把结果放到共享目录，由 NAS 那边取走并推送到 probe-hk 分支。
#
# 为什么不让 VPS 自己推：GitHub 的 deploy key 只能在仓库设置里手工添加，
# 自动化流程拿不到那个权限。改用「NAS 代推」——两边都是定时任务，
# 不新增任何对外端口，也不共享私钥。
#
# 结果文件名带**批次号**（与 Stage 1 产物、与美国侧的 probe_<ts>.csv 同源），
# 交叉比对就是按这个批次号配对的。
set -e

REPO="${REPO:-/root/free-nodes/repo}"
OUT="${OUT:-/var/lib/free-nodes-probe}"

cd "$REPO"

# ---- 1. 更新代码（probe.py 随仓库更新，容器是挂载的，不用重建镜像）----
git fetch --depth=1 origin main || true
git checkout -B main origin/main 2>/dev/null || true
git reset --hard origin/main 2>/dev/null || true

# ---- 2. 确定本轮批次：output 分支里最新的 Stage 1 产物 ----
git fetch --depth=1 origin \
  "+refs/heads/output:refs/remotes/origin/output" 2>/dev/null || true
LIST_NAME=$(git ls-tree --name-only origin/output 2>/dev/null \
  | grep -oE 'list\.meta\.us_[0-9]{8}_[0-9]{4}\.yml' | sort | tail -1 || true)
if [ -z "$LIST_NAME" ]; then
  echo "output 分支里没有 Stage 1 产物（list.meta.us_<ts>.yml），跳过本次探测"
  exit 1
fi
STAMP=$(echo "$LIST_NAME" | sed -E 's/^list\.meta\.us_([0-9]{8}_[0-9]{4})\.yml$/\1/')
echo "[$(date '+%F %T')] 探测 Stage 1 产物 $LIST_NAME（批次 $STAMP）"

# ---- 3. 探测。NO_PUSH=1：只探测不推送，推送交给 NAS ----
mkdir -p "$OUT"
NO_PUSH=1 BRANCH=probe-hk PREFIX=probe_hk \
  INTERVAL_JITTER="${INTERVAL_JITTER:-1}" PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}" \
  WORKERS="${WORKERS:-64}" \
  sh docker/run.sh "$REPO" /root/free-nodes

# ---- 4. 结果改名后放进共享目录，等 NAS 来取 ----
SRC=/root/free-nodes/out/probe_domestic.csv
if [ ! -f "$SRC" ]; then
  echo "没有生成探测结果：$SRC"
  exit 1
fi
cp "$SRC" "$OUT/probe_hk_${STAMP}.csv"
cp "$SRC" "$OUT/probe_hk.csv"
chmod 644 "$OUT"/probe_hk*.csv
echo "[$(date '+%F %T')] 结果已放到 $OUT（批次 $STAMP），等待 NAS 取走推送"
