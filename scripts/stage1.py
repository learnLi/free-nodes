#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage 1：用美国侧的多轮探测历史筛出「确实能用」的节点子集。

输入：Clash 配置（list.meta.full.yml）+ 本轮 probe.csv + 历史 probe_<ts>.csv
输出：list.meta.us.yml（筛过的子集）+ stage1.csv（每个地址的判定明细）

为什么要有 Stage 1：
  * 单轮探测噪声大。同一批地址连续 5 轮探测，单轮说「活」的结果不稳定。
  * 跨轮一致的才是真信号：实测 409 个地址里，314 个跨 5 轮全活、87 个跨 5 轮全死。
  * 交给 NAS 做国内探测时，节点池小一半，探测更快、结果更集中。
  * 同时把「跨轮全死」的节点提前剔掉，它们大概率在国内也是死的。

判定规则（--min-rounds / --alive-ratio 可调）：
  stable_alive —— 出现的每一轮都活着     -> 保留
  stable_dead  —— 出现的每一轮都死了     -> 剔除
  unknown      —— 死活不定 / 只出现一轮  -> 保守保留
"""
import argparse
import csv
import os
import sys
from collections import Counter
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rounds import addr_of, classify, keep_recent, load_rounds  # noqa: E402
from prefs import filter_settings  # noqa: E402

# 复用 prune.py 的组引用清理逻辑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prune import clean_group_refs  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Stage 1：多轮一致性筛选')
    p.add_argument('--input', required=True, help='输入的 Clash YAML')
    p.add_argument('--output', required=True, help='输出的 Clash YAML')
    p.add_argument('--probe', required=True, help='本轮 probe.csv')
    p.add_argument('--history', default='',
                   help='历史 probe 文件，逗号分隔（按时间从旧到新）')
    p.add_argument('--rounds', type=int, default=0,
                   help='只用最近 N 轮历史（0 = 全用；默认取配置里的 filter.rounds）')
    p.add_argument('--min-rounds', type=int, default=0,
                   help='至少出现这么多轮才做判定（默认取配置里的 filter.min_rounds）')
    p.add_argument('--alive-ratio', type=float, default=0.0,
                   help='存活占比阈值（默认取配置里的 filter.alive_ratio）')
    p.add_argument('--report', default='stage1.csv', help='判定明细 CSV')
    p.add_argument('--drop-unknown', action='store_true',
                   help='连 unknown 也剔除（默认保守保留）')
    return p.parse_args()


def main() -> int:
    import yaml
    args = parse_args()
    cfg = filter_settings()
    min_rounds = args.min_rounds or cfg['min_rounds']
    alive_ratio = args.alive_ratio or cfg['alive_ratio']
    rounds_n = args.rounds or cfg['rounds']

    hist = [h for h in args.history.split(',') if h.strip()]
    paths = keep_recent(hist, args.probe, rounds_n)
    rounds = load_rounds(paths)
    if not rounds:
        print('没有可用的探测数据')
        return 1
    print('载入 %d 轮探测数据（min_rounds=%d alive_ratio=%s）' % (
        len(rounds), min_rounds, alive_ratio))

    with open(args.input, encoding='utf-8') as f:
        text = f.read()
    data = yaml.safe_load(text) or {}
    proxies = list(data.get('proxies') or [])

    kept: List[Dict] = []
    report: List[List] = []
    stat = Counter()
    for p in proxies:
        a = addr_of(p)
        state, seen, alive = classify(a, rounds, min_rounds, alive_ratio)
        stat[state] += 1
        report.append([a[0], a[1], p.get('type', ''), p.get('name', ''),
                       state, seen, alive])
        if state == 'stable_alive':
            kept.append(p)
        elif state == 'unknown' and not args.drop_unknown:
            kept.append(p)

    data['proxies'] = kept
    dangling = clean_group_refs(data, kept)

    header = ''
    if text.startswith('#'):
        for line in text.splitlines():
            if line.startswith('#'):
                header += line + '\n'
            else:
                break
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write(yaml.dump(data, allow_unicode=True,
                          sort_keys=False).replace('!!str ', ''))

    with open(args.report, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['服务器', '端口', '类型', '名称', '判定', '出现轮数', '存活轮数'])
        for r in report:
            w.writerow(r)

    print('Stage 1：%d -> %d 个节点' % (len(proxies), len(kept)))
    for k in ('stable_alive', 'unknown', 'stable_dead'):
        print('  %-14s %d' % (k, stat.get(k, 0)))
    if dangling:
        print('  同步清理了 %d 处失效的 proxy-group 引用' % dangling)
    return 0


if __name__ == '__main__':
    sys.exit(main())
