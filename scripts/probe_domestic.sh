#!/bin/sh
# NAS 侧探活脚本：在国内网络上探测节点可达性。
#
# 用法：
#   sh probe_domestic.sh [仓库目录]
#
# 依赖：git、python3（仅用标准库 + PyYAML）、仓库可读写
# 不依赖：Docker、GitHub Actions、任何 API
#
# 做的事：
#   1. 从 output 分支拉取最新的节点列表（由 GitHub Actions 发布）
#   2. 对每个节点做一次 TCP 连接探测 + TLS 握手（走本机直连，不走任何代理）
#   3. 结果写到 probe_domestic.csv，提交回 probe-domestic 分支
#
# 注意：探测走的是「中国住宅宽带直连境外节点」这条路径，
#       与目标用户不用代理时的实际路径一致，所以结果可以直接参考。
#       若本机有全局代理/透明代理路由，探测会受其影响，
#       此时结果反映的是「经代理后能否连」，而非直连。

set -e

REPO="${1:-/volume1/free-nodes}"
cd "$REPO" || { echo "仓库目录不存在：$REPO"; exit 1; }

BRANCH_PROBE="probe-domestic"

# 节点列表来源。国内访问 raw.githubusercontent.com 很不稳，默认走 jsDelivr CDN
# （国内速度好）；也可以用 LIST_URL 覆盖，或设 LIST_URL=git 改从 output 分支取。
LIST_URL="${LIST_URL:-https://cdn.jsdelivr.net/gh/learnLi/free-nodes@output/list.meta.full.yml}"
LIST="list.meta.full.yml"

echo "[$(date '+%F %T')] 获取节点列表"
if [ "$LIST_URL" = "git" ]; then
  git fetch --depth=1 origin output || true
  git checkout -B output origin/output 2>/dev/null || true
else
  curl -sL --max-time 120 "$LIST_URL" -o "$LIST" || true
  if [ ! -s "$LIST" ]; then
    echo "CDN 获取失败，回退到 git output 分支"
    git fetch --depth=1 origin output || true
    git checkout -B output origin/output 2>/dev/null || true
  fi
fi

if [ ! -s "$LIST" ]; then
  echo "拿不到 $LIST，退出"
  exit 1
fi
echo "节点列表：$LIST（$(grep -c 'name:' "$LIST" 2>/dev/null || echo '?') 项）"

echo "[$(date '+%F %T')] 开始探测"
# --timeout 5：国内链路抖动大，比美国那边放宽一点
# --workers 64：家用带宽和 NAS 的并发能力都够用
python3 ./probe.py \
  --input "$LIST" \
  --output probe_domestic.csv \
  --timeout 5 \
  --workers 64 \
  --ref 223.5.5.5:443 \
  --ref 114.114.114.114:443 \
  --ref 1.1.1.1:443 \
  --ref 8.8.8.8:443

echo "[$(date '+%F %T')] 提交结果"
git checkout -B "$BRANCH_PROBE" || true
cp probe_domestic.csv "probe_domestic_$(date '+%Y%m%d').csv" 2>/dev/null || true
git add -A probe_domestic*.csv
if git diff --cached --quiet; then
  echo "无变化"
else
  git -c user.name="NAS probe" -c user.email="probe@nas.local" \
    commit -m "probe: $(date '+%F %T') 国内可达性探测"
  git push origin "$BRANCH_PROBE"
  echo "已推送 $BRANCH_PROBE"
fi
echo "[$(date '+%F %T')] 完成"
