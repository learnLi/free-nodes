#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""scripts/crosscheck.py 与 scripts/rounds.py 的单元测试（不联网）。"""
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
os.chdir(REPO_ROOT)

from rounds import addr_of, classify, is_alive, load_round, load_rounds
from crosscheck import decide

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-56s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-56s got=%r want=%r" % (name, got, want))


def check_true(name, got):
    check(name, bool(got), True)


def write_csv(path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write("名称,类型,服务器,端口,TCP,TLS,QUIC,耗时ms,错误\n")
        for r in rows:
            f.write(r + "\n")


print("=== 1. is_alive ===")
check("TCP=Y 即活", is_alive({'TCP': 'Y', 'TLS': 'N/A', 'QUIC': 'N/A'}), True)
check("TLS=Y 即活", is_alive({'TCP': 'N', 'TLS': 'Y', 'QUIC': 'N/A'}), True)
check("QUIC=Y 即活", is_alive({'TCP': 'N/A', 'TLS': 'N/A', 'QUIC': 'Y'}), True)
check("全 N 即死", is_alive({'TCP': 'N', 'TLS': 'N', 'QUIC': 'N'}), False)
check("全 N/A 即死", is_alive({'TCP': 'N/A', 'TLS': 'N/A', 'QUIC': 'N/A'}), False)

print()
print("=== 2. load_round / classify ===")
with tempfile.TemporaryDirectory() as td:
    r1 = os.path.join(td, 'r1.csv')
    r2 = os.path.join(td, 'r2.csv')
    r3 = os.path.join(td, 'r3.csv')
    write_csv(r1, ['a,vless,1.1.1.1,443,Y,Y,N/A,10,',
                   'b,vless,2.2.2.2,443,N,N,N/A,10,timeout',
                   'c,vless,3.3.3.3,443,Y,Y,N/A,10,'])
    write_csv(r2, ['a,vless,1.1.1.1,443,Y,Y,N/A,10,',
                   'b,vless,2.2.2.2,443,Y,Y,N/A,10,',
                   'd,vless,4.4.4.4,443,Y,Y,N/A,10,'])
    write_csv(r3, ['a,vless,1.1.1.1,443,Y,Y,N/A,10,',
                   'b,vless,2.2.2.2,443,N,N,N/A,10,timeout',
                   'c,vless,3.3.3.3,443,Y,Y,N/A,10,'])
    rounds = load_rounds([r1, r2, r3])
    check("载入 3 轮", len(rounds), 3)
    check("A 三轮全活 -> stable_alive",
          classify(('1.1.1.1', 443), rounds)[0], 'stable_alive')
    check("B 死活死 -> unknown",
          classify(('2.2.2.2', 443), rounds)[0], 'unknown')
    check("C 两轮 -> seen=2 alive=2",
          classify(('3.3.3.3', 443), rounds)[1:], (2, 2))
    check("D 只出现一轮 -> unknown（数据不足）",
          classify(('4.4.4.4', 443), rounds)[0], 'unknown')
    check("只出现一轮时 seen=1",
          classify(('4.4.4.4', 443), rounds)[1], 1)
    check("不存在的地址 -> unknown",
          classify(('9.9.9.9', 443), rounds)[0], 'unknown')

    # 只出现一轮时，即使 min_rounds=2 也应判 unknown 而不是 stable_alive
    check("min_rounds=2 时单轮不算稳定",
          classify(('4.4.4.4', 443), rounds, min_rounds=2)[0], 'unknown')
    check("min_rounds=1 时单轮可判稳定",
          classify(('4.4.4.4', 443), rounds, min_rounds=1)[0], 'stable_alive')
    # alive_ratio 放宽：2.2.2.2 是 1/3 存活
    check("alive_ratio=0.5 时 1/3 不算 stable_alive",
          classify(('2.2.2.2', 443), rounds, alive_ratio=0.5)[0], 'unknown')
    check("alive_ratio=0.3 时 1/3 算 stable_alive",
          classify(('2.2.2.2', 443), rounds, alive_ratio=0.3)[0], 'stable_alive')

print()
print("=== 3. decide：中美双侧判定 ===")
cases = [
    (('stable_alive', 'stable_alive'), ('国内跨轮全活', 'keep')),
    (('stable_alive', 'stable_dead'), ('国内跨轮全死', 'drop')),
    (('stable_alive', 'unknown'), ('美国跨轮全活，国内未定', 'keep')),
    (('stable_dead', 'stable_alive'), ('国内跨轮全活', 'keep')),
    (('stable_dead', 'stable_dead'), ('国内跨轮全死', 'drop')),
    (('stable_dead', 'unknown'), ('美国跨轮全死', 'drop')),
    (('unknown', 'stable_alive'), ('国内跨轮全活', 'keep')),
    (('unknown', 'stable_dead'), ('国内跨轮全死', 'drop')),
    (('unknown', 'unknown'), ('两端都未定', 'keep')),
]
for key, want in cases:
    check('%s + %s' % key, decide(*key), want)

print()
print("=== 4. 关键不变量 ===")
# 国内跨轮全活 -> 一定保留（不管美国侧怎么判）
check("国内全活必保留", decide('stable_dead', 'stable_alive')[1], 'keep')
# 国内跨轮全死 -> 一定剔除
check("国内全死必剔除", decide('stable_alive', 'stable_dead')[1], 'drop')
# 美国判死但国内未定 -> 剔除（美国跨轮全死是强信号）
check("美国全死+国内未定 -> 剔除", decide('stable_dead', 'unknown')[1], 'drop')
# 两端都未定 -> 保守保留
check("两端都未定 -> 保留", decide('unknown', 'unknown')[1], 'keep')

print()
print("=== 5. addr_of ===")
check("取 server/port", addr_of({'server': '1.2.3.4', 'port': 443}), ('1.2.3.4', 443))
check("去掉 IPv6 方括号",
      addr_of({'server': '[2001:db8::1]', 'port': 443}), ('2001:db8::1', 443))
check("port 非法时返回 0",
      addr_of({'server': '1.2.3.4', 'port': 'x'}), ('1.2.3.4', 0))

print()
print("=== 6. 端到端：跑一遍交叉比对 ===")
import csv
import yaml
with tempfile.TemporaryDirectory() as td:
    lst = os.path.join(td, 'list.yml')
    with open(lst, 'w', encoding='utf-8') as f:
        f.write("proxies:\n"
                "- name: a\n  type: vless\n  server: 1.1.1.1\n  port: 443\n"
                "- name: b\n  type: vless\n  server: 2.2.2.2\n  port: 443\n"
                "- name: c\n  type: vless\n  server: 3.3.3.3\n  port: 443\n"
                "proxy-groups:\n"
                "- name: g1\n  type: select\n  proxies: [a, b, c]\n")
    us1 = os.path.join(td, 'us1.csv')
    us2 = os.path.join(td, 'us2.csv')
    cn1 = os.path.join(td, 'cn1.csv')
    cn2 = os.path.join(td, 'cn2.csv')
    # a: 两侧都全活 -> 保留
    # b: 国内全死 -> 剔除
    # c: 美国全活但国内未定 -> 保留
    write_csv(us1, ['a,vless,1.1.1.1,443,Y,Y,N/A,10,',
                     'b,vless,2.2.2.2,443,Y,Y,N/A,10,',
                     'c,vless,3.3.3.3,443,Y,Y,N/A,10,'])
    write_csv(us2, ['a,vless,1.1.1.1,443,Y,Y,N/A,10,',
                     'b,vless,2.2.2.2,443,Y,Y,N/A,10,',
                     'c,vless,3.3.3.3,443,Y,Y,N/A,10,'])
    write_csv(cn1, ['a,vless,1.1.1.1,443,Y,Y,N/A,10,',
                     'b,vless,2.2.2.2,443,N,N,N/A,10,timeout',
                     'c,vless,3.3.3.3,443,Y,Y,N/A,10,'])
    write_csv(cn2, ['a,vless,1.1.1.1,443,Y,Y,N/A,10,',
                     'b,vless,2.2.2.2,443,N,N,N/A,10,timeout'])
    import subprocess
    out_list = os.path.join(td, 'out.yml')
    r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'crosscheck.py'),
                        '--us', us1, '--us-history', us2,
                        '--cn', cn1, '--cn-history', cn2,
                        '--out-csv', os.path.join(td, 'x.csv'),
                        '--out-md', os.path.join(td, 'x.md'),
                        '--input-list', lst, '--out-cn-list', out_list],
                       capture_output=True, text=True, encoding='utf-8')
    check("退出码 0", r.returncode, 0)
    d = yaml.safe_load(open(out_list, encoding='utf-8'))
    names = [p['name'] for p in d['proxies']]
    check("a 被保留", 'a' in names, True)
    check("b 被剔除（国内跨轮全死）", 'b' in names, False)
    check("c 被保留（美国全活）", 'c' in names, True)
    check("组的引用同步清理", d['proxy-groups'][0]['proxies'],
          [n for n in d['proxy-groups'][0]['proxies'] if n in names])
    md = open(os.path.join(td, 'x.md'), encoding='utf-8').read()
    check_true("摘要含交叉表", '跨轮全活' in md)

print()
print("=== 7. 轮次选择：必须保留本轮 ===")
from rounds import keep_recent
hist = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7']
check("n=6 保留本轮+5 轮历史", keep_recent(hist, 'CUR', 6),
      ['h3', 'h4', 'h5', 'h6', 'h7', 'CUR'])
check("本轮一定在最后", keep_recent(hist, 'CUR', 6)[-1], 'CUR')
check("n=3 保留本轮+2 轮历史", keep_recent(hist, 'CUR', 3), ['h6', 'h7', 'CUR'])
check("n=1 只留本轮", keep_recent(hist, 'CUR', 1), ['CUR'])
check("n=0 全留", len(keep_recent(hist, 'CUR', 0)), 8)
check("历史不足时也带本轮", keep_recent(['h1'], 'CUR', 6), ['h1', 'CUR'])

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
