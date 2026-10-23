#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中美探活结果交叉比对。

输入两份 probe.csv（同一 schema），按 (server, port) 关联，输出：

  crosscheck.csv       每个地址的判定结果
  crosscheck_summary.md 2x2 交叉表 + 分协议统计
  list.meta.cn.yml     「国内可用」的节点子集（可选输出）

判定逻辑（保守）：

  美国 alive  = TCP 连通        （美国无 GFW 干扰，可信）
  美国 dead   = 对端回 RST      （refused / reset by peer）
  美国 unknown= 其余            （timeout / 无路由 / DNS 失败，不作死判定）
  国内 alive  = TCP 连通
  国内 blocked= 连不通         （含被 GFW RST 注入，无法与「端口关闭」区分）

  美国 alive + 国内 alive  -> 可用，保留
  美国 alive + 国内 blocked-> 大概率被墙，剔除（这是美国版留下的坑）
  美国 dead  + 国内 alive  -> 被美国探活误杀，保留（这是美国版误杀的部分）
  美国 dead  + 国内 blocked-> 真死，剔除
  美国 unknown + 任意      -> 不确定，保留
"""
import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

# 复用 prune.py 里的组引用清理逻辑，避免两处实现分叉
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prune import clean_group_refs  # noqa: E402

# 美国侧：只有对端主动回 RST 才算确凿已死
US_DEAD_MARKERS = ('refused', 'reset by peer')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='中美探活结果交叉比对')
    p.add_argument('--us', required=True, help='美国侧 probe.csv')
    p.add_argument('--cn', required=True, help='国内侧 probe.csv')
    p.add_argument('--out-csv', default='crosscheck.csv')
    p.add_argument('--out-md', default='crosscheck_summary.md')
    p.add_argument('--out-cn-list', default='',
                   help='输出「国内可用」节点子集的 Clash YAML 路径')
    p.add_argument('--input-list', default='list.meta.full.yml',
                   help='用于筛选国内可用子集的 Clash 配置')
    p.add_argument('--min-us', action='store_true',
                   help='剔除「国内被墙」的节点（默认只统计不剔除）')
    return p.parse_args()


def load(path: str) -> Dict[Tuple[str, int], Dict[str, str]]:
    out: Dict[Tuple[str, int], Dict[str, str]] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            try:
                port = int(row.get('端口') or 0)
            except (TypeError, ValueError):
                continue
            out[(row.get('服务器') or '', port)] = row
    return out


def us_status(row: Optional[Dict[str, str]]) -> str:
    """alive / dead / unknown / n/a"""
    if row is None:
        return 'unknown'
    tcp = row.get('TCP')
    quic = row.get('QUIC', '')
    if tcp == 'N/A':
        # QUIC/UDP 协议：用 QUIC 探测结果判定
        if quic == 'Y':
            return 'alive'
        if quic == 'N':
            return 'dead'
        return 'n/a'
    if tcp == 'Y':
        return 'alive'
    if tcp == 'N':
        err = (row.get('错误') or '').lower()
        if any(m in err for m in US_DEAD_MARKERS):
            return 'dead'
    return 'unknown'


def cn_status(row: Optional[Dict[str, str]]) -> str:
    """alive / blocked / unknown / n/a"""
    if row is None:
        return 'unknown'
    tcp = row.get('TCP')
    quic = row.get('QUIC', '')
    if tcp == 'N/A':
        if quic == 'Y':
            return 'alive'
        if quic == 'N':
            return 'blocked'
        return 'n/a'
    if tcp == 'Y':
        return 'alive'
    if tcp == 'N':
        return 'blocked'
    return 'unknown'


# (美国状态, 国内状态) -> (判定, 动作)
VERDICT = {
    ('alive', 'alive'):   ('可用', 'keep'),
    ('alive', 'blocked'): ('疑似被墙', 'drop'),
    ('alive', 'unknown'): ('美国可用，国内未知', 'keep'),
    ('alive', 'n/a'):    ('美国可用，国内未测(QUIC)', 'keep'),
    ('dead', 'alive'):    ('被美国误杀', 'keep'),
    ('dead', 'blocked'):  ('已死', 'drop'),
    ('dead', 'unknown'):  ('美国判定已死', 'drop'),
    ('dead', 'n/a'):      ('美国判定已死', 'drop'),
    ('unknown', 'alive'): ('国内可用', 'keep'),
    ('unknown', 'blocked'): ('国内不可达', 'keep'),
    ('unknown', 'unknown'): ('两端都未测出', 'keep'),
    ('unknown', 'n/a'):   ('两端都未测出', 'keep'),
    ('n/a', 'alive'):     ('QUIC/UDP，仅国内可达', 'keep'),
    ('n/a', 'blocked'):   ('QUIC/UDP', 'keep'),
    ('n/a', 'unknown'):   ('QUIC/UDP，未测', 'keep'),
    ('n/a', 'n/a'):       ('QUIC/UDP', 'keep'),
}


def main() -> int:
    args = parse_args()
    us = load(args.us)
    cn = load(args.cn)
    if not us:
        print("美国侧结果为空：%s" % args.us)
        return 1
    if not cn:
        print("国内侧结果为空：%s" % args.cn)
        return 1

    addrs = sorted(set(us) | set(cn))
    rows: List[Dict[str, Any]] = []
    for a in addrs:
        u, c = us_status(us.get(a)), cn_status(cn.get(a))
        verdict, action = VERDICT.get((u, c), ('未知', 'keep'))
        meta = us.get(a) or cn.get(a) or {}
        rows.append({
            '服务器': a[0], '端口': a[1], '类型': meta.get('类型', ''),
            '名称': meta.get('名称', ''),
            '美国': u, '国内': c, '判定': verdict, '动作': action,
            '美国错误': (us.get(a) or {}).get('错误', ''),
            '国内错误': (cn.get(a) or {}).get('错误', ''),
        })

    with open(args.out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---- 统计 ----
    cross = Counter((r['美国'], r['国内']) for r in rows)
    verdicts = Counter(r['判定'] for r in rows)
    total = len(rows)
    by_proto: Dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_proto[r['类型'] or '?'][r['判定']] += 1

    md = ['# 中美探活交叉表', '']
    md.append('| 美国 | 国内 | 节点数 | 占比 | 判定 |')
    md.append('| :- | :- | ---: | ---: | :- |')
    label = {'alive': '可用', 'dead': '判定已死', 'unknown': '未测出', 'n/a': '不适用(QUIC)'}
    for u in ('alive', 'dead', 'unknown', 'n/a'):
        for c in ('alive', 'blocked', 'unknown', 'n/a'):
            n = cross.get((u, c), 0)
            if not n:
                continue
            v = VERDICT.get((u, c), ('未知', ''))[0]
            md.append('| %s | %s | %d | %.1f%% | %s |' % (
                label[u], label.get(c, c), n, n / total * 100, v))
    md.append('')
    md.append('## 判定汇总')
    md.append('')
    md.append('| 判定 | 节点数 | 占比 |')
    md.append('| :- | ---: | ---: |')
    for v, n in verdicts.most_common():
        md.append('| %s | %d | %.1f%% |' % (v, n, n / total * 100))
    md.append('')
    md.append('## 分协议')
    md.append('')
    md.append('| 协议 | 节点数 | 可用 | 被墙 | 已死 |')
    md.append('| :- | ---: | ---: | ---: | ---: |')
    for t in sorted(by_proto):
        c = by_proto[t]
        md.append('| %s | %d | %d | %d | %d |' % (
            t, sum(c.values()), c.get('可用', 0), c.get('疑似被墙', 0),
            c.get('已死', 0)))
    md.append('')
    with open(args.out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md)+'\n')

    print('\n'.join(md))

    # ---- 输出「国内可用」子集 ----
    if args.out_cn_list:
        import yaml
        keep_addrs = {(r['服务器'], str(r['端口'])) for r in rows
                      if r['动作'] == 'keep'}
        if args.min_us:
            drop = {(r['服务器'], str(r['端口'])) for r in rows
                    if r['判定'] == '疑似被墙'}
            keep_addrs -= drop
        if not os.path.exists(args.input_list):
            # 静默跳过是这类问题最大的帮凶——必须报错
            print("找不到 %s，无法生成子集" % args.input_list)
            return 1
        with open(args.input_list, encoding='utf-8') as f:
            text = f.read()
        data = yaml.safe_load(text) or {}
        proxies = list(data.get('proxies') or [])
        kept = [p for p in proxies
                if (str(p.get('server', '')).strip('[]'),
                    str(p.get('port', ''))) in keep_addrs]
        data['proxies'] = kept
        # 剔除节点后必须同步清理 proxy-groups 的引用，否则 Clash / Mihomo
        # 会报 "proxy <name> not found" 并拒绝加载整个配置
        dangling = clean_group_refs(data, kept)
        if dangling:
            print("同步清理了 %d 处失效的 proxy-group 引用" % dangling)
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
        print("国内可用子集：%d -> %d 个节点 -> %s" % (
            len(proxies), len(kept), args.out_cn_list))
    return 0


if __name__ == '__main__':
    sys.exit(main())
