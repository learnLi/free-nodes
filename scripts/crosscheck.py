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
from rounds import addr_of, classify, load_rounds  # noqa: E402
from prune import clean_group_refs  # noqa: E402
from prefs import protocol_order, sort_proxies  # noqa: E402


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
    p.add_argument('--min-rounds', type=int, default=2,
                   help='至少出现这么多轮才做判定（默认 2）')
    p.add_argument('--alive-ratio', type=float, default=1.0,
                   help='存活轮数占比达到多少算 stable_alive（默认 1.0 = 全活）')
    p.add_argument('--us-release-url', default='', help='Release 资产基础 URL')
    p.add_argument('--us-candidates', default='', help='美国侧候选资产名，逗号分隔')
    p.add_argument('--cn-file-name', default='', help='国内侧文件名（带时间戳）')
    return p.parse_args()


def decide(us_state: str, cn_state: str) -> Tuple[str, str]:
    """(美国跨轮状态, 国内跨轮状态) -> (判定, 动作)"""
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

    us_paths = [args.us] + [h for h in args.us_history.split(',') if h.strip()]
    cn_paths = [args.cn] + [h for h in args.cn_history.split(',') if h.strip()]
    us_rounds = load_rounds(us_paths)
    cn_rounds = load_rounds(cn_paths)
    if not us_rounds:
        print('美国侧没有可用探测数据')
        return 1
    if not cn_rounds:
        print('国内侧没有可用探测数据')
        return 1
    print('美国侧 %d 轮，国内侧 %d 轮' % (len(us_rounds), len(cn_rounds)))

    with open(args.input_list, encoding='utf-8') as f:
        text = f.read()
    data = yaml.safe_load(text) or {}
    proxies = list(data.get('proxies') or [])

    rows: List[Dict] = []
    kept: List[Dict] = []
    for p in proxies:
        a = addr_of(p)
        us_state, us_seen, us_alive = classify(a, us_rounds,
                                               args.min_rounds, args.alive_ratio)
        cn_state, cn_seen, cn_alive = classify(a, cn_rounds,
                                               args.min_rounds, args.alive_ratio)
        verdict, action = decide(us_state, cn_state)
        rows.append({
            '服务器': a[0], '端口': a[1], '类型': p.get('type', ''),
            '名称': p.get('name', ''),
            '美国': us_state, '美国轮数': us_seen, '美国存活': us_alive,
            '国内': cn_state, '国内轮数': cn_seen, '国内存活': cn_alive,
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
    return 0


if __name__ == '__main__':
    sys.exit(main())
