#!/bin/sh
# NAS 侧探活脚本：在国内网络上探测节点可达性。
#
# 用法：
#   sh probe_domestic.sh [仓库目录]
#
# 环境变量：
#   INTERVAL_JITTER=1   每次运行前随机等待 0~15 分钟，打散周期性（默认开启）
#   NO_PUSH=1           只把结果留在本地，不推送到 GitHub（首次试跑建议这么用）
#   LIST_URL=<url>      节点列表来源，默认走 jsDelivr CDN（国内速度快）
#   PROBE_TIMEOUT=5     单次探测超时秒数，默认 5（国内链路抖动大）
#
# 依赖：git、python3（PyYAML）、curl。不需要 Docker、GitHub Actions、任何 API。
#
# 流量：441 个节点做一轮 TCP + TLS 探测约 900 KB（TLS 的证书链占 94%）。
#       加上下载节点列表约 1.4 MB/轮，6 小时一轮即 5.8 MB/天。
#
# 做的事：
#   1. 取最新节点列表（默认 jsDelivr，失败回退 git output 分支）
#   2. 对每个节点做 TCP 连接探测 + TLS 握手（走本机直连，不走任何代理）
#   3. 结果写到 probe_domestic.csv 和带时间戳的副本
#   4. 有推送凭据时提交回 probe-domestic 分支（失败不影响本地结果）

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# 默认工作目录：脚本的上级目录（仓库根）。传参可覆盖。
REPO="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$REPO" || { echo "目录不存在：$REPO"; exit 1; }

BRANCH_PROBE="probe-domestic"
LIST_URL="${LIST_URL:-https://cdn.jsdelivr.net/gh/learnLi/free-nodes@output/list.meta.full.yml}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}"
WORKERS="${WORKERS:-64}"
JITTER_MAX=$((15 * 60))

# probe.py 的位置：先找工作目录下的（仓库根），再找脚本同级，最后从 CDN 取
if [ -n "${PROBE_PY:-}" ]; then
  :
elif [ -f "$REPO/probe.py" ]; then
  PROBE_PY="$REPO/probe.py"
elif [ -f "$SCRIPT_DIR/probe.py" ]; then
  PROBE_PY="$SCRIPT_DIR/probe.py"
else
  PROBE_PY="$REPO/probe.py"
fi

# ---- 0. 环境预检 ----
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "找不到 $PYTHON。请安装 Python 3，或用 PYTHON=/path/to/python3 指定。"
  exit 1
fi
if ! "$PYTHON" -c "import yaml" >/dev/null 2>&1; then
  echo "缺少 PyYAML。装一下："
  echo "  $PYTHON -m pip install PyYAML"
  echo "  (群晖/威联也可以用包中心装 Python 3 + PyYAML，或用 Docker)"
  exit 1
fi

# ---- 确保 probe.py 在手 ----
# 这样 NAS 上只需要放这一个脚本，不用 clone 整个仓库
if [ ! -f "$PROBE_PY" ]; then
  echo "本地没有 probe.py，从 CDN 取一份"
  for u in \
    "https://cdn.jsdelivr.net/gh/learnLi/free-nodes@master/probe.py" \
    "https://raw.githubusercontent.com/learnLi/free-nodes/master/probe.py" ; do
    curl -sL --max-time 60 "$u" -o "$PROBE_PY" && [ -s "$PROBE_PY" ] && break
  done
  if [ ! -s "$PROBE_PY" ]; then
    echo "取不到 probe.py，退出"
    exit 1
  fi
  echo "  已获取 $PROBE_PY"
fi

# ---- 随机抖动：打散「固定周期自动外连」的特征 ----
if [ "${INTERVAL_JITTER:-1}" = "1" ] && [ "$JITTER_MAX" -gt 0 ]; then
  W=$(( $(od -An -N2 -tu2 /dev/urandom 2>/dev/null || echo $RANDOM) % JITTER_MAX ))
  echo "[$(date '+%F %T')] 随机等待 ${W}s（打散周期性）"
  sleep "$W"
fi

# ---- 1. 取节点列表 ----
LIST="list.meta.full.yml"
echo "[$(date '+%F %T')] 获取节点列表"
if [ "$LIST_URL" = "git" ]; then
  git fetch --depth=1 origin output || true
  git checkout -B output origin/output 2>/dev/null || true
else
  curl -sL --max-time 120 "$LIST_URL" -o "$LIST" || true
  if [ ! -s "$LIST" ]; then
    echo "  CDN 获取失败，回退到 git output 分支"
    git fetch --depth=1 origin output || true
    git checkout -B output origin/output 2>/dev/null || true
  fi
fi
if [ ! -s "$LIST" ]; then
  echo "拿不到 $LIST，退出"
  exit 1
fi
echo "  节点列表 $(wc -c < "$LIST") 字节"

# ---- 2. 探测 ----
echo "[$(date '+%F %T')] 开始探测（timeout=${PROBE_TIMEOUT}s workers=${WORKERS}）"
if ! "$PYTHON" "$PROBE_PY" \
  --input "$LIST" \
  --output probe_domestic.csv \
  --timeout "$PROBE_TIMEOUT" \
  --workers "$WORKERS" \
  --ref 223.5.5.5:443 \
  --ref 114.114.114.114:443 \
  --ref 1.1.1.1:443 \
  --ref 8.8.8.8:443 ; then
  echo "  探测过程报错（结果文件若已生成则继续）"
fi

STAMP=$(date '+%Y%m%d_%H%M')
if [ -f probe_domestic.csv ]; then
  cp probe_domestic.csv "probe_domestic_${STAMP}.csv"
  echo "[$(date '+%F %T')] 结果："
  echo "    $REPO/probe_domestic.csv"
  echo "    $REPO/probe_domestic_${STAMP}.csv"
  echo "    $(wc -l < probe_domestic.csv) 行"
else
  echo "没有生成 probe_domestic.csv，探测可能失败了"
  exit 1
fi

# ---- 3. 推送（可选）----
if [ "${NO_PUSH:-0}" = "1" ]; then
  echo "[$(date '+%F %T')] NO_PUSH=1，跳过推送。结果在本地："
  echo "  $REPO/probe_domestic_${STAMP}.csv"
  exit 0
fi

echo "[$(date '+%F %T')] 尝试推送"
# 先把远端分支拉下来作为基线。少了这一步，git checkout -B 会从当前 HEAD
# （通常是 main）开分支，推送时会被判为非快进而被拒绝。
# 用显式 refspec，确保 remote-tracking ref 一定建出来。
git fetch --depth=1 origin \
  "+refs/heads/$BRANCH_PROBE:refs/remotes/origin/$BRANCH_PROBE" 2>/dev/null || true
if git rev-parse --verify "origin/$BRANCH_PROBE" >/dev/null 2>&1; then
  git checkout -B "$BRANCH_PROBE" "origin/$BRANCH_PROBE"
  echo "  基于远端分支继续"
else
  git checkout -B "$BRANCH_PROBE"
  echo "  远端分支不存在，新建"
fi
# 必须用 -f：仓库的 .gitignore 里忽略了 probe_domestic*.csv
#（避免误提交到 main），而这里就是要把它提交到数据分支
git add -f probe_domestic*.csv 2>/dev/null || true
if git diff --cached --quiet; then
  echo "  无变化"
else
  git -c user.name="NAS probe" -c user.email="probe@nas.local" \
    commit -m "probe: $(date '+%F %T') 国内可达性探测" || true
  if git push origin "$BRANCH_PROBE" 2>&1; then
    echo "  已推送 $BRANCH_PROBE"
  else
    echo "  推送失败（不影响本地结果）。可能是没配 SSH 部署密钥。"
    echo "  手动回传即可：$REPO/probe_domestic_${STAMP}.csv"
  fi
fi
echo "[$(date '+%F %T')] 完成"
