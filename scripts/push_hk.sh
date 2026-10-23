#!/bin/sh
# 把香港 VPS 的探测结果推到 probe-hk 分支（跑在 NAS 上）。
#
# 香港 VPS 没有 GitHub 写权限，探测结果放在它的共享目录里，
# 由 NAS 取走代推。NAS 自己的国内探测结果走 probe-domestic 分支，
# 两条线互不影响。
#
# 用的是独立的推送目录（/root/free-nodes/hkpush），不去动 NAS 主仓库的
# 工作区 —— 主仓库的分支会被探测流程切来切去，别把两件事搅在一起。
set -e

REPO_URL="${REPO_URL:-git@github.com:learnLi/free-nodes.git}"
VPS="${VPS:-hkprobe@45.192.192.65}"
REMOTE_DIR="${REMOTE_DIR:-/var/lib/free-nodes-probe}"
INBOX="${INBOX:-/root/free-nodes/in-hk}"
PUSHDIR="${PUSHDIR:-/root/free-nodes/hkpush}"
SSH_KEY="${SSH_KEY:-/root/.ssh/nas_probe}"
KNOWN_HOSTS="${KNOWN_HOSTS:-/root/.ssh/github_known_hosts}"
VPS_KEY="${VPS_KEY:-/root/.ssh/vps_hk}"
VPS_KNOWN_HOSTS="${VPS_KNOWN_HOSTS:-/root/.ssh/vps_known_hosts}"

mkdir -p "$INBOX"

# ---- 1. 取回香港侧结果 ----
scp -q -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$VPS_KNOWN_HOSTS" \
  -i "$VPS_KEY" "$VPS:$REMOTE_DIR/probe_hk_*.csv" "$INBOX/" 2>/dev/null || true
COUNT=$(ls -1 "$INBOX"/probe_hk_*.csv 2>/dev/null | wc -l)
if [ "$COUNT" -eq 0 ]; then
  echo "香港侧暂无结果（VPS 上还没有产出），跳过"
  exit 0
fi
echo "取回香港侧结果 $COUNT 个"

# ---- 2. 在独立目录里提交并推送 ----
rm -rf "$PUSHDIR"
if ! git clone --depth=1 --branch probe-hk "$REPO_URL" "$PUSHDIR" 2>/dev/null; then
  # 分支还不存在（第一次推送）：建一个只含结果文件的空仓库
  mkdir -p "$PUSHDIR"
  git -C "$PUSHDIR" init -q -b probe-hk
  git -C "$PUSHDIR" remote add origin "$REPO_URL"
fi
cd "$PUSHDIR"
git config user.name 'NAS probe'
git config user.email 'probe@nas.local'
git config core.sshCommand "ssh -i $SSH_KEY -o UserKnownHostsFile=$KNOWN_HOSTS -o StrictHostKeyChecking=yes"

cp "$INBOX"/probe_hk*.csv .
git add -A
if git diff --cached --quiet; then
  echo "香港侧无变化"
  exit 0
fi
git commit -q -m "probe: $(date '+%F %T') 香港可达性探测"
git push origin HEAD:refs/heads/probe-hk
echo "已推送 probe-hk"
