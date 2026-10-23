#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 Clash 配置的内部一致性。

Mihomo / Clash 遇到 proxy-group 引用了不存在的节点时，会直接报
"proxy <name> not found" 并拒绝加载整个配置——用户在客户端里看到的
就是「订阅无效」。这类问题在 YAML 上完全看不出来，只能靠校验。

检查项：
  1. proxy-groups 里的每个引用都能解析（节点 / 其他组 / 内置策略）
  2. 组名不重复
  3. 每个节点有 name / type / server / port，且 port 合法
  4. rules 里引用的策略组都存在
"""
import argparse
import sys
from typing import Any, Dict, List, Set

BUILTIN = {'DIRECT', 'REJECT', 'PASS', 'COMPATIBLE', 'GLOBAL'}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='校验 Clash 配置')
    p.add_argument('files', nargs='+', help='要校验的 Clash YAML 文件')
    return p.parse_args()


def validate(path: str) -> List[str]:
    import yaml
    errs: List[str] = []
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f.read()) or {}

    proxies = data.get('proxies') or []
    groups = data.get('proxy-groups') or []

    names: Set[str] = set()
    for p in proxies:
        n = str(p.get('name') or '')
        if not n:
            errs.append('有节点缺少 name')
            continue
        if n in names:
            errs.append('节点名重复：%s' % n)
        names.add(n)
        for field in ('type', 'server'):
            if not p.get(field):
                errs.append('节点 %s 缺少 %s' % (n, field))
        port = p.get('port')
        if not isinstance(port, int) or not (0 < port < 65536):
            errs.append('节点 %s 的 port 非法：%r' % (n, port))

    gnames: Set[str] = set()
    for g in groups:
        n = str(g.get('name') or '')
        if not n:
            errs.append('有组缺少 name')
            continue
        if n in gnames:
            errs.append('组名重复：%s' % n)
        gnames.add(n)

    known = names | gnames | BUILTIN
    for g in groups:
        for r in (g.get('proxies') or []):
            if r not in known:
                errs.append('组 %s 引用了不存在的节点：%s' % (g.get('name'), r))
        if not g.get('type'):
            errs.append('组 %s 缺少 type' % g.get('name'))
        if g.get('type') in ('url-test', 'fallback', 'load-balance'):
            if not g.get('url'):
                errs.append('组 %s（%s）缺少 url' % (g.get('name'), g.get('type')))

    for rule in (data.get('rules') or []):
        parts = str(rule).split(',')
        if len(parts) >= 3:
            policy = parts[2]
            if policy and policy not in known:
                errs.append('规则 %s 引用了不存在的策略：%s' % (rule[:60], policy))

    return errs


def main() -> int:
    args = parse_args()
    bad = 0
    for path in args.files:
        try:
            errs = validate(path)
        except Exception as e:  # noqa: BLE001
            print("  %-34s 解析失败：%s" % (path.split('/')[-1], e))
            bad += 1
            continue
        if errs:
            bad += 1
            print("  %-34s %d 个问题：" % (path.split('/')[-1], len(errs)))
            for e in errs[:10]:
                print("      - %s" % e)
            if len(errs) > 10:
                print("      ... 还有 %d 个" % (len(errs) - 10))
        else:
            print("  %-34s OK" % path.split('/')[-1])
    if bad:
        print("校验未通过")
        return 1
    print("全部通过")
    return 0


if __name__ == '__main__':
    sys.exit(main())
