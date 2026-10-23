#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage 3：结合中美两侧的多轮探测历史，产出「大陆可用」订阅。

判定分两层：
  Stage 1（fetch.yml）用美国侧多轮历史筛出「确实能用」的子集，交给 NAS
  Stage 2（NAS）在该子集上做国内探测，结果推回 probe-domestic 分支
  Stage 3（本脚本）用中美两侧的多轮历史做最终判定，产出 list.meta.cn.yml

为什么用多轮：单轮探测噪声很大。同一批地址连续几轮测下来，单轮说「活」的
结果并不稳定；跨轮一致的才是真信号。实测 409 个地址连测 5 轮，
314 个跨轮全活、87 个跨轮全死。

判定表（us = 美国侧跨轮状态，cn = 国内侧跨轮状态）：

  cn=stable_alive  -> 保留   国内跨轮全活，这是真正的大陆可用节点
  cn=stable_dead   -> 剔除   国内跨轮全死
  cn=unknown + us=stable_alive -> 保留   国内没定论，但美国一直活
  cn=unknown + us=stable_dead  -> 剔除
  两端都 unknown    -> 保留   数据不足，保守
"""
import argparse
import csv
import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rounds import (addr_of, classify, keep_recent, load_rounds,
                   median_latency)  # noqa: E402
from prune import clean_group_refs  # noqa: E402
from prefs import filter_settings, protocol_order, sort_proxies  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='中美多轮探活交叉比对')
    p.add_argument('--us', required=True, help='美国侧本轮 probe.csv')
    p.add_argument('--cn', required=True, help='国内侧本轮 probe.csv')
    p.add_argument('--us-history', default='', help='美国侧历史，逗号分隔')
    p.add_argument('--cn-history', default='', help='国内侧历史，逗号分隔')
    p.add_argument('--out-csv', default='crosscheck.csv')
    p.add_argument('--out-md', default='crosscheck_summary.md')
    p.add_argument('--out-cn-list', default='', help='「大陆可用」子集的 YAML 路径')
    p.add_argument('--input-list', default='list.meta.full.yml')
    p.add_argument('--min-rounds', type=int, default=0,
                   help='至少出现这么多轮才做判定（默认取配置里的 filter.min_rounds）')
    p.add_argument('--alive-ratio', type=float, default=0.0,
                   help='存活占比阈值（默认取配置里的 filter.alive_ratio）')
    p.add_argument('--rounds', type=int, default=0,
                   help='只用最近 N 轮历史（0 = 全用；默认取配置里的 filter.rounds）')
    p.add_argument('--max-latency-ms', type=int, default=0,
                   help='国内延迟上限，超过则剔除（0 = 不限制；'
                        '默认取配置里的 filter.max_latency_ms）')
    p.add_argument('--us-release-url', default='', help='Release 资产基础 URL')
    p.add_argument('--us-candidates', default='', help='美国侧候选资产名，逗号分隔')
    p.add_argument('--cn-file-name', default='', help='国内侧文件名（带时间戳）')
    p.add_argument('--input-list-clash', default='',
                   help='原版 Clash 配置（list.yml），用于产出老内核的大陆可用版')
    p.add_argument('--out-cn-list-clash', default='',
                   help='原版 Clash 大陆可用版的输出路径（list.cn.yml）')
    return p.parse_args()


def decide(us_state: str, cn_state: str,
           cn_latency: Optional[float] = None,
           max_latency_ms: int = 0) -> Tuple[str, str]:
    """(美国跨轮状态, 国内跨轮状态, 国内延迟中位数, 延迟上限) -> (判定, 动作)"""

    # 延迟是硬指标：超过上限就不该进「大陆可用」列表。
    # 用**国内侧**的延迟——美国到亚洲天生就慢（200~400ms），
    # 按美国侧筛会误杀「离美国远但离大陆近」的好节点。
    if (max_latency_ms and cn_latency is not None
            and cn_latency > max_latency_ms):
        return '延迟过高', 'drop'

    if cn_state == 'stable_alive':
        return '国内跨轮全活', 'keep'
    if cn_state == 'stable_dead':
        return '国内跨轮全死', 'drop'
    if us_state == 'stable_alive':
        return '美国跨轮全活，国内未定', 'keep'
    if us_state == 'stable_dead':
        return '美国跨轮全死', 'drop'
    return '两端都未定', 'keep'


def main() -> int:
    import yaml
    args = parse_args()
    cfg = filter_settings()
    min_rounds = args.min_rounds or cfg['min_rounds']
    alive_ratio = args.alive_ratio or cfg['alive_ratio']
    rounds_n = args.rounds or cfg['rounds']

    us_paths = keep_recent([h for h in args.us_history.split(',') if h.strip()],
                            args.us, rounds_n)
    cn_paths = keep_recent([h for h in args.cn_history.split(',') if h.strip()],
                            args.cn, rounds_n)
    us_rounds = load_rounds(us_paths)
    cn_rounds = load_rounds(cn_paths)
    if not us_rounds:
        print('美国侧没有可用探测数据')
        return 1
    if not cn_rounds:
        print('国内侧没有可用探测数据')
        return 1
    print('美国侧 %d 轮，国内侧 %d 轮（min_rounds=%d alive_ratio=%s）' % (
        len(us_rounds), len(cn_rounds), min_rounds, alive_ratio))

    with open(args.input_list, encoding='utf-8') as f:
        text = f.read()
    data = yaml.safe_load(text) or {}
    proxies = list(data.get('proxies') or [])

    rows: List[Dict] = []
    kept: List[Dict] = []
    state_by_addr: Dict[Tuple[str, int], Tuple[str, str]] = {}
    max_latency_ms = args.max_latency_ms or cfg.get('max_latency_ms', 0)
    for p in proxies:
        a = addr_of(p)
        us_state, us_seen, us_alive = classify(a, us_rounds,
                                               min_rounds, alive_ratio)
        cn_state, cn_seen, cn_alive = classify(a, cn_rounds,
                                               min_rounds, alive_ratio)
        cn_lat = median_latency(cn_rounds, a)
        verdict, action = decide(us_state, cn_state, cn_lat, max_latency_ms)
        state_by_addr[(a[0], a[1])] = (us_state, cn_state)
        rows.append({
            '服务器': a[0], '端口': a[1], '类型': p.get('type', ''),
            '名称': p.get('name', ''),
            '美国': us_state, '美国轮数': us_seen, '美国存活': us_alive,
            '国内': cn_state, '国内轮数': cn_seen, '国内存活': cn_alive,
            '国内延迟ms': '' if cn_lat is None else '%.0f' % cn_lat,
            '判定': verdict, '动作': action,
        })
        if action == 'keep':
            kept.append(p)

    with open(args.out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    cross = Counter((r['美国'], r['国内']) for r in rows)
    verdicts = Counter(r['判定'] for r in rows)
    total = len(rows)
    by_proto: Dict[str, Counter] = {}
    for r in rows:
        by_proto.setdefault(r['类型'] or '?', Counter())[r['判定']] += 1

    lbl = {'stable_alive': '跨轮全活', 'stable_dead': '跨轮全死',
           'unknown': '未定'}
    md = ['# 中美多轮探活交叉表', '']
    md.append('参与判定的轮次：美国 %d 轮，国内 %d 轮' % (len(us_rounds), len(cn_rounds)))
    md.append('')
    md.append('| 美国 \\ 国内 | 跨轮全活 | 跨轮全死 | 未定 |')
    md.append('| :- | ---: | ---: | ---: |')
    for u in ('stable_alive', 'stable_dead', 'unknown'):
        cells = [str(cross.get((u, c), 0)) for c in
                 ('stable_alive', 'stable_dead', 'unknown')]
        if sum(int(c) for c in cells) == 0:
            continue
        md.append('| %s | %s |' % (lbl[u], ' | '.join(cells)))
    md.append('')
    md.append('## 判定汇总')
    md.append('')
    md.append('| 判定 | 节点数 | 占比 |')
    md.append('| :- | ---: | ---: |')
    for v, n in verdicts.most_common():
        md.append('| %s | %d | %.1f%% |' % (v, n, n / total * 100 if total else 0))
    md.append('')

    # 延迟分布（国内侧，中位数）
    lats = sorted(float(r['国内延迟ms']) for r in rows
                  if r['国内延迟ms'] != '' and r['国内延迟ms'] is not None)
    if lats:
        def pctile(p):
            return lats[min(len(lats) - 1, int(len(lats) * p))]
        md.append('## 国内延迟分布（中位数）')
        md.append('')
        md.append('| 分位 | 延迟 |')
        md.append('| :- | ---: |')
        for p, label in ((0.1, 'p10'), (0.5, 'p50（中位）'),
                         (0.75, 'p75'), (0.9, 'p90'), (0.99, 'p99')):
            md.append('| %s | %.0f ms |' % (label, pctile(p)))
        if max_latency_ms:
            over = sum(1 for x in lats if x > max_latency_ms)
            md.append('')
            md.append('延迟上限 **%d ms**，超过的 %d 个节点已剔除' % (max_latency_ms, over))
        md.append('')
    md.append('## 分协议')
    md.append('')
    md.append('| 协议 | 节点数 | 保留 | 剔除 |')
    md.append('| :- | ---: | ---: | ---: |')
    for t in sorted(by_proto):
        c = by_proto[t]
        keep = sum(v for k, v in c.items() if k in ('国内跨轮全活', '美国跨轮全活，国内未定', '两端都未定'))
        md.append('| %s | %d | %d | %d |' % (t, sum(c.values()), keep, sum(c.values()) - keep))
    md.append('')
    with open(args.out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md)+'\n')
    print('\n'.join(md))

    if args.out_cn_list:
        # 按协议偏好排序：实测国内可用率 vmess 79% > vless 62% > trojan 53%
        # > ss 25%，ss 排后面
        kept = sort_proxies(kept, protocol_order())
        data['proxies'] = kept
        dangling = clean_group_refs(data, kept)
        header = ''
        if text.startswith('#'):
            for line in text.splitlines():
                if line.startswith('#'):
                    header += line + '\n'
                else:
                    break
        with open(args.out_cn_list, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(yaml.dump(data, allow_unicode=True,
                              sort_keys=False).replace('!!str ', ''))
        if dangling:
            print('同步清理了 %d 处失效的 proxy-group 引用' % dangling)
        print('大陆可用子集：%d -> %d 个节点 -> %s' % (
            len(proxies), len(kept), args.out_cn_list))

    # ---- 原版 Clash（老内核）的大陆可用版 ----
    # 原版 Clash 不认识 flow / grpc-opts / obfs / client-fingerprint 等
    # Meta 专有字段，用 list.meta.cn.yml 会加载失败，所以要单独出一份。
    # 判定是按地址做的，两份订阅的节点是同一批，直接套用即可。
    if args.out_cn_list_clash and args.input_list_clash:
        if not os.path.exists(args.input_list_clash):
            print('找不到 %s，跳过原版 Clash 版' % args.input_list_clash)
            return 0
        with open(args.input_list_clash, encoding='utf-8') as f:
            ctext = f.read()
        cdata = yaml.safe_load(ctext) or {}
        cproxies = list(cdata.get('proxies') or [])
        # 地址 -> 判定结果
        verdict_by_addr = {}
        for r in rows:
            verdict_by_addr[(r['服务器'], r['端口'])] = r['动作']
        ckeep = []
        cdrop = 0
        for p in cproxies:
            a = addr_of(p)
            action = verdict_by_addr.get((a[0], a[1]), 'keep')
            if action == 'keep':
                ckeep.append(p)
            else:
                cdrop += 1
        ckeep = sort_proxies(ckeep, protocol_order())
        cdata['proxies'] = ckeep
        cdangling = clean_group_refs(cdata, ckeep)
        cheader = ''
        if ctext.startswith('#'):
            for line in ctext.splitlines():
                if line.startswith('#'):
                    cheader += line + '\n'
                else:
                    break
        with open(args.out_cn_list_clash, 'w', encoding='utf-8') as f:
            f.write(cheader)
            f.write(yaml.dump(cdata, allow_unicode=True,
                              sort_keys=False).replace('!!str ', ''))
        if cdangling:
            print('原版 Clash 版同步清理了 %d 处失效引用' % cdangling)
        print('原版 Clash 大陆可用子集：%d -> %d 个节点（剔除 %d）-> %s' % (
            len(cproxies), len(ckeep), cdrop, args.out_cn_list_clash))
    return 0


if __name__ == '__main__':
    sys.exit(main())
