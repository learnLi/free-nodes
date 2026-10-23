#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""scripts/prefs.py 的单元测试（协议偏好排序）。"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
os.chdir(REPO_ROOT)

from prefs import (DEFAULT_PROTOCOL_ORDER, load_config, protocol_order,
                    sort_key_factory, sort_proxies)

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-56s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-56s got=%r want=%r" % (name, got, want))


print("=== 1. 读取配置 ===")
conf = load_config()
check("能读到配置", isinstance(conf, dict), True)
check("protocol_order 是列表", isinstance(conf.get('protocol_order'), list), True)
order = protocol_order()
check('protocol_order 非空', len(order) > 0, True)
check('vmess 排在最前', order[0], 'vmess')
check('ss 在 vmess/vless/trojan 之后',
      order.index('ss') > order.index('trojan'), True)
check('http 在 ss 之后', order.index('http') > order.index('ss'), True)

print()
print("=== 2. 排序 ===")
ps = [
    {'type': 'ss', 'name': 'a'},
    {'type': 'vmess', 'name': 'b'},
    {'type': 'vless', 'name': 'c'},
    {'type': 'trojan', 'name': 'd'},
    {'type': 'hysteria2', 'name': 'e'},
    {'type': 'http', 'name': 'f'},
]
got = [p['type'] for p in sort_proxies(ps, order)]
check('按偏好排序', got, ['vmess', 'vless', 'trojan', 'hysteria2', 'ss', 'http'])

print()
print("=== 3. 边界 ===")
# 未知协议排最后
mixed = [{'type': 'zzz', 'name': 'x'}, {'type': 'vmess', 'name': 'y'}]
check('未知协议排最后',
      [p['type'] for p in sort_proxies(mixed, order)], ['vmess', 'zzz'])
# 同协议内按名称排（稳定、可预期）
same = [{'type': 'vmess', 'name': 'b'}, {'type': 'vmess', 'name': 'a'}]
check('同协议内按名称排',
      [p['name'] for p in sort_proxies(same, order)], ['a', 'b'])
# 缺少 type 的节点不崩
nodefault = [{'name': 'x'}, {'type': 'vmess', 'name': 'y'}]
check('缺少 type 不崩', len(sort_proxies(nodefault, order)), 2)
# 大小写不敏感
mixedcase = [{'type': 'VMESS', 'name': 'a'}, {'type': 'ss', 'name': 'b'}]
check('协议名大小写不敏感',
      [p['type'] for p in sort_proxies(mixedcase, order)], ['VMESS', 'ss'])
# 空列表
check('空列表', sort_proxies([], order), [])

print()
print("=== 4. 配置缺失时的兜底 ===")
check('有默认顺序', len(DEFAULT_PROTOCOL_ORDER) > 0, True)
check('默认顺序里 vmess 在前', DEFAULT_PROTOCOL_ORDER[0], 'vmess')

print()
print("=== 5. 筛选参数 ===")
from prefs import DEFAULT_FILTER, filter_settings
fs = filter_settings()
check('拿到 rounds', 'rounds' in fs, True)
check('拿到 min_rounds', 'min_rounds' in fs, True)
check('拿到 alive_ratio', 'alive_ratio' in fs, True)
check('rounds 是整数', isinstance(fs['rounds'], int), True)
check('min_rounds 是整数', isinstance(fs['min_rounds'], int), True)
check('alive_ratio 是浮点', isinstance(fs['alive_ratio'], float), True)
check('默认 alive_ratio 为 1.0（跨轮全活）', DEFAULT_FILTER['alive_ratio'], 1.0)
check('配置里的值生效', fs['rounds'], 6)

print()
print("=== 6. get_setting.py ===")
import subprocess
r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'get_setting.py'),
                    'filter.rounds', '6'], capture_output=True, text=True, encoding='utf-8')
check('读到 filter.rounds', r.stdout.strip(), '6')
r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'get_setting.py'),
                    'filter.alive_ratio', '1.0'], capture_output=True, text=True, encoding='utf-8')
check('读到 filter.alive_ratio', r.stdout.strip(), '1.0')
r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'get_setting.py'),
                    '不存在的键', '兜底'], capture_output=True, text=True, encoding='utf-8')
check('取不到时用默认值', r.stdout.strip(), '兜底')
r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'get_setting.py'),
                    'protocol_order'], capture_output=True, text=True, encoding='utf-8')
check('列表用逗号连接', r.stdout.strip().startswith('vmess,vless'), True)

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
