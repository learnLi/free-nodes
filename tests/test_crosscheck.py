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
print("=== 9. is_alive：握手失败不算活着 ===")
from rounds import is_alive, median_latency
check("TCP=Y 且 TLS=Y -> 活", is_alive({'TCP': 'Y', 'TLS': 'Y', 'QUIC': 'N/A'}), True)
check("TCP=Y 且 TLS=N/A（协议不走 TLS）-> 活",
      is_alive({'TCP': 'Y', 'TLS': 'N/A', 'QUIC': 'N/A'}), True)
# 回归：TCP 通了但 TLS 握手超时/失败 -> 节点实际不可用
check("TCP=Y 但 TLS=N（握手失败）-> 不活",
      is_alive({'TCP': 'Y', 'TLS': 'N', 'QUIC': 'N/A'}), False)
check("TCP=Y 但 TLS=N（握手超时）-> 不活",
      is_alive({'TCP': 'Y', 'TLS': 'N', 'QUIC': 'N/A'}), False)
check("QUIC=Y -> 活", is_alive({'TCP': 'N/A', 'TLS': 'N/A', 'QUIC': 'Y'}), True)
check("QUIC=N -> 不活", is_alive({'TCP': 'N/A', 'TLS': 'N/A', 'QUIC': 'N'}), False)
check("TCP=N -> 不活", is_alive({'TCP': 'N', 'TLS': 'N/A', 'QUIC': 'N/A'}), False)
check("全 N/A -> 不活", is_alive({'TCP': 'N/A', 'TLS': 'N/A', 'QUIC': 'N/A'}), False)

print()
print("=== 10. 延迟中位数 ===")
rounds = [
    {('1.1.1.1', 443): {'alive': True, 'latency': 100.0}},
    {('1.1.1.1', 443): {'alive': True, 'latency': 300.0}},
    {('1.1.1.1', 443): {'alive': True, 'latency': 200.0}},
    {('2.2.2.2', 443): {'alive': False, 'latency': 5000.0}},   # 超时不算
]
check("三轮 100/300/200 -> 中位 200",
      median_latency(rounds, ('1.1.1.1', 443)), 200.0)
check("只有失败轮次 -> None",
      median_latency(rounds, ('2.2.2.2', 443)), None)
check("不存在的地址 -> None", median_latency(rounds, ('9.9.9.9', 443)), None)
rounds2 = [
    {('1.1.1.1', 443): {'alive': True, 'latency': 100.0}},
    {('1.1.1.1', 443): {'alive': True, 'latency': 400.0}},
]
check("两轮取平均", median_latency(rounds2, ('1.1.1.1', 443)), 250.0)

print()
print("=== 11. 延迟上限的判定 ===")
check("延迟超限 -> 剔除",
      decide('stable_alive', 'stable_alive', 2000.0, 1500)[1], 'drop')
check("延迟在限内 -> 保留",
      decide('stable_alive', 'stable_alive', 800.0, 1500)[1], 'keep')
check("延迟为 None（没测出来）-> 不因延迟剔除",
      decide('stable_alive', 'stable_alive', None, 1500)[1], 'keep')
check("上限为 0 -> 不限制",
      decide('stable_alive', 'stable_alive', 99999.0, 0)[1], 'keep')
check("延迟超限的判定名固定",
      decide('stable_alive', 'stable_alive', 2000.0, 1500)[0], '延迟过高')

print()
print("=== 12. 原版 Clash（老内核）的大陆可用版 ===")
# 原版 Clash 不认识 flow / grpc-opts / obfs / client-fingerprint 等
# Meta 专有字段，用 list.meta.cn.yml 会加载失败，必须单独出一份。
# 回归：verdict 查找的端口类型必须与 rows 里的一致（都用 int），
# 否则原版 Clash 版会一个都剔不掉。
import subprocess
with tempfile.TemporaryDirectory() as td:
    meta = os.path.join(td, 'meta.yml')
    clash = os.path.join(td, 'clash.yml')
    with open(meta, 'w', encoding='utf-8') as f:
        f.write("proxies:\n"
                "- name: a\n  type: vless\n  server: 1.1.1.1\n  port: 443\n"
                "- name: b\n  type: vless\n  server: 2.2.2.2\n  port: 443\n"
                "proxy-groups:\n"
                "- name: g1\n  type: select\n  proxies: [a, b]\n")
    with open(clash, 'w', encoding='utf-8') as f:
        f.write("proxies:\n"
                "- name: a\n  type: vmess\n  server: 1.1.1.1\n  port: 443\n"
                "- name: b\n  type: vmess\n  server: 2.2.2.2\n  port: 443\n"
                "proxy-groups:\n"
                "- name: g1\n  type: select\n  proxies: [a, b]\n")
    # 需要**两轮**才判定：min_rounds=2 时只出现一轮的判「未定」，保守保留。
    # 两轮里 a 都活、b 都死 -> b 判死
    def write_probe(path, latency):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write("名称,类型,服务器,端口,TCP,TLS,QUIC,耗时ms,错误\n")
            f.write("a,vless,1.1.1.1,443,Y,Y,N/A,%d,\n" % latency)
            f.write("b,vless,2.2.2.2,443,N,N/A,N/A,5002,timeout\n")
    us1 = os.path.join(td, 'us1.csv')
    us2 = os.path.join(td, 'us2.csv')
    cn1 = os.path.join(td, 'cn1.csv')
    cn2 = os.path.join(td, 'cn2.csv')
    write_probe(us1, 100)
    write_probe(us2, 110)
    write_probe(cn1, 120)
    write_probe(cn2, 130)
    out_meta = os.path.join(td, 'cn_meta.yml')
    out_clash = os.path.join(td, 'cn_clash.yml')
    r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'crosscheck.py'),
                        '--us', us1, '--us-history', us2,
                        '--cn', cn1, '--cn-history', cn2,
                        '--out-csv', os.path.join(td, 'x.csv'),
                        '--out-md', os.path.join(td, 'x.md'),
                        '--input-list', meta, '--out-cn-list', out_meta,
                        '--input-list-clash', clash, '--out-cn-list-clash', out_clash],
                       capture_output=True, text=True, encoding='utf-8')
    check("退出码 0", r.returncode, 0)
    if r.returncode == 0:
        dm = yaml.safe_load(open(out_meta, encoding='utf-8'))
        dc = yaml.safe_load(open(out_clash, encoding='utf-8'))
        check("Meta 版只留活的", [p['name'] for p in dm['proxies']], ['a'])
        check("原版 Clash 版也只留活的（端口类型对齐）",
              [p['name'] for p in dc['proxies']], ['a'])
        check("原版 Clash 版的组引用同步清理",
              dc['proxy-groups'][0]['proxies'], ['a'])
    else:
        print('   stderr:', r.stderr[:300])

print()
print("=== 13. 香港桥接池版 ===")
# 桥接场景：节点由香港 VPS 去连，所以
#   * 延迟按香港视角算
#   * 「大陆被墙」对它不成立，必须保留（那正是香港最有价值的一批）
import subprocess
with tempfile.TemporaryDirectory() as td:
    lst = os.path.join(td, 'meta.yml')
    with open(lst, 'w', encoding='utf-8') as f:
        f.write("proxies:\n"
                "- name: good\n  type: vless\n  server: 1.1.1.1\n  port: 443\n"
                "- name: blocked_cn\n  type: vless\n  server: 2.2.2.2\n  port: 443\n"
                "- name: dead\n  type: vless\n  server: 3.3.3.3\n  port: 443\n"
                "- name: slow\n  type: vless\n  server: 4.4.4.4\n  port: 443\n"
                "proxy-groups:\n"
                "- name: g1\n  type: select\n"
                "  proxies: [good, blocked_cn, dead, slow]\n")

    def w(path, rows):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write("名称,类型,服务器,端口,TCP,TLS,QUIC,耗时ms,错误\n")
            for r in rows:
                f.write(r + "\n")

    us1 = os.path.join(td, 'us1.csv')
    us2 = os.path.join(td, 'us2.csv')
    cn1 = os.path.join(td, 'cn1.csv')
    cn2 = os.path.join(td, 'cn2.csv')
    hk1 = os.path.join(td, 'hk1.csv')
    # good: 两侧都活；blocked_cn: 美国活、大陆死；dead: 两侧都死；slow: 两侧都活但香港很慢
    w(us1, ["good,vless,1.1.1.1,443,Y,Y,N/A,100,",
             "blocked_cn,vless,2.2.2.2,443,Y,Y,N/A,100,",
             "dead,vless,3.3.3.3,443,N,N/A,N/A,5002,timeout",
             "slow,vless,4.4.4.4,443,Y,Y,N/A,100,"])
    w(us2, ["good,vless,1.1.1.1,443,Y,Y,N/A,110,",
             "blocked_cn,vless,2.2.2.2,443,Y,Y,N/A,110,",
             "dead,vless,3.3.3.3,443,N,N/A,N/A,5002,timeout",
             "slow,vless,4.4.4.4,443,Y,Y,N/A,110,"])
    w(cn1, ["good,vless,1.1.1.1,443,Y,Y,N/A,120,",
             "blocked_cn,vless,2.2.2.2,443,N,N/A,N/A,5002,timeout",
             "dead,vless,3.3.3.3,443,N,N/A,N/A,5002,timeout",
             "slow,vless,4.4.4.4,443,Y,Y,N/A,130,"])
    w(cn2, ["good,vless,1.1.1.1,443,Y,Y,N/A,125,",
             "blocked_cn,vless,2.2.2.2,443,N,N/A,N/A,5002,timeout",
             "dead,vless,3.3.3.3,443,N,N/A,N/A,5002,timeout",
             "slow,vless,4.4.4.4,443,Y,Y,N/A,135,"])
    # 香港：good 120ms、blocked_cn 90ms（香港通！）、slow 3000ms（超限）
    w(hk1, ["good,vless,1.1.1.1,443,Y,Y,N/A,120,",
             "blocked_cn,vless,2.2.2.2,443,Y,Y,N/A,90,",
             "slow,vless,4.4.4.4,443,Y,Y,N/A,3000,"])
    out_hk = os.path.join(td, 'hk.yml')
    r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'crosscheck.py'),
                        '--us', us1, '--us-history', us2,
                        '--cn', cn1, '--cn-history', cn2,
                        '--hk', hk1,
                        '--out-csv', os.path.join(td, 'x.csv'),
                        '--out-md', os.path.join(td, 'x.md'),
                        '--input-list', lst,
                        '--out-hk-list', out_hk,
                        '--max-latency-hk', '500'],
                       capture_output=True, text=True, encoding='utf-8')
    check("退出码 0", r.returncode, 0)
    if r.returncode == 0:
        d = yaml.safe_load(open(out_hk, encoding='utf-8'))
        names = [p['name'] for p in d['proxies']]
        check("保留活的", 'good' in names, True)
        check("保留「大陆被墙但香港通」的", 'blocked_cn' in names, True)
        check("剔除两端都死的", 'dead' in names, False)
        check("剔除香港延迟超限的", 'slow' in names, False)
        check("组的引用同步清理",
              sorted(d['proxy-groups'][0]['proxies']), ['blocked_cn', 'good'])
    else:
        print('   stderr:', r.stderr[:300])

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
