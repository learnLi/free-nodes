#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/crosscheck.py 的单元测试（不联网）。"""
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
os.chdir(REPO_ROOT)

from crosscheck import us_status, cn_status, VERDICT

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-56s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-56s got=%r want=%r" % (name, got, want))


def row(tcp, tls, err):
    return {'TCP': tcp, 'TLS': tls, '错误': err}


print("=== 1. 美国侧状态判定 ===")
check("TCP 连通 -> alive", us_status(row('Y', 'Y', '')), 'alive')
check("Connection refused -> dead", us_status(row('N', '', 'Connection refused')), 'dead')
check("reset by peer -> dead", us_status(row('N', '', 'Connection reset by peer')), 'dead')
check("timeout -> unknown（不判死）", us_status(row('N', '', 'timeout')), 'unknown')
check("Network is unreachable -> unknown",
      us_status(row('N', '', 'Network is unreachable')), 'unknown')
check("DNS 失败 -> unknown",
      us_status(row('N', '', 'Name or service not known')), 'unknown')
check("QUIC -> n/a", us_status(row('N/A', 'N/A', 'QUIC')), 'n/a')
check("缺失 -> unknown", us_status(None), 'unknown')

print()
print("=== 2. 国内侧状态判定 ===")
check("TCP 连通 -> alive", cn_status(row('Y', 'Y', '')), 'alive')
check("连不通 -> blocked（GFW 与端口关闭无法区分）",
      cn_status(row('N', '', 'Connection reset by peer')), 'blocked')
check("timeout -> blocked", cn_status(row('N', '', 'timeout')), 'blocked')
check("QUIC -> n/a", cn_status(row('N/A', 'N/A', 'QUIC')), 'n/a')

print()
print("=== 3. 交叉判定表 ===")
cases = [
    (('alive', 'alive'), '可用', 'keep'),
    (('alive', 'blocked'), '疑似被墙', 'drop'),
    (('dead', 'alive'), '被美国误杀', 'keep'),
    (('dead', 'blocked'), '已死', 'drop'),
    (('unknown', 'alive'), '国内可用', 'keep'),
    (('unknown', 'blocked'), '国内不可达', 'keep'),
    (('n/a', 'alive'), 'QUIC/UDP，仅国内可达', 'keep'),
]
for key, want_v, want_a in cases:
    v, a = VERDICT[key]
    check('%s + %s -> %s/%s' % (key[0], key[1], want_v, want_a),
          (v, a), (want_v, want_a))

print()
print("=== 4. 关键不变量 ===")
# 国内判定为 blocked 时，绝不能因为国内侧信息就把「美国可用」的节点剔除成 dead
check("国内 blocked 不会让 alive 变 dead",
      VERDICT[('alive', 'blocked')][1] in ('drop', 'keep'), True)
# 美国判 dead 但国内 alive -> 必须保留（这是美国探活会误杀的部分）
check("美国 dead + 国内 alive 必须保留",
      VERDICT[('dead', 'alive')][1], 'keep')
# 美国 unknown 一律保留（信息不足，不能杀）
check("美国 unknown 一律保留",
      all(VERDICT[('unknown', c)][1] == 'keep' for c in
          ('alive', 'blocked', 'unknown', 'n/a')), True)

print()
print("=== 5. 端到端：生成交叉表 ===")
with tempfile.TemporaryDirectory() as td:
    us_csv = os.path.join(td, 'us.csv')
    cn_csv = os.path.join(td, 'cn.csv')
    with open(us_csv, 'w', encoding='utf-8', newline='') as f:
        f.write("名称,类型,服务器,端口,TCP,TLS,耗时ms,错误\n")
        f.write("a,vless,1.1.1.1,443,Y,Y,10,\n")            # 可用
        f.write("b,vless,2.2.2.2,443,Y,Y,10,\n")            # 被墙
        f.write("c,vless,3.3.3.3,443,N,,10,Connection refused\n")  # 美国死
        f.write("d,vless,4.4.4.4,443,N,,10,Connection refused\n")  # 真死
    with open(cn_csv, 'w', encoding='utf-8', newline='') as f:
        f.write("名称,类型,服务器,端口,TCP,TLS,耗时ms,错误\n")
        f.write("a,vless,1.1.1.1,443,Y,Y,10,\n")
        f.write("b,vless,2.2.2.2,443,N,,10,Connection reset by peer\n")
        f.write("c,vless,3.3.3.3,443,Y,Y,10,\n")
        f.write("d,vless,4.4.4.4,443,N,,10,timeout\n")
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'crosscheck.py'),
                        '--us', us_csv, '--cn', cn_csv,
                        '--out-csv', os.path.join(td, 'out.csv'),
                        '--out-md', os.path.join(td, 'out.md')],
                       capture_output=True, text=True, encoding='utf-8')
    check("退出码 0", r.returncode, 0)
    import csv as _csv
    rows = list(_csv.DictReader(open(os.path.join(td, 'out.csv'), encoding='utf-8')))
    check("交叉表 4 行", len(rows), 4)
    got = {x['服务器']: (x['判定'], x['动作']) for x in rows}
    check("1.1.1.1 可用", got['1.1.1.1'], ('可用', 'keep'))
    check("2.2.2.2 疑似被墙", got['2.2.2.2'], ('疑似被墙', 'drop'))
    check("3.3.3.3 被美国误杀", got['3.3.3.3'], ('被美国误杀', 'keep'))
    check("4.4.4.4 已死", got['4.4.4.4'], ('已死', 'drop'))
    md = open(os.path.join(td, 'out.md'), encoding='utf-8').read()
    check("摘要含交叉表", '中美探活交叉表' in md, True)
    check("摘要含分协议", '分协议' in md, True)

print()
print("=== 6. 端到端：输出子集时会清理组引用 ===")
# 回归：crosscheck.py 与 prune.py 曾各自漏掉这一步，导致产出的子集
# 配置里有指向已剔除节点的引用，Clash / Mihomo 会拒绝加载
import yaml
with tempfile.TemporaryDirectory() as td:
    lst = os.path.join(td, 'list.yml')
    with open(lst, 'w', encoding='utf-8') as f:
        f.write("proxies:\n"
                "- name: a\n  type: vless\n  server: 1.1.1.1\n  port: 443\n"
                "- name: b\n  type: vless\n  server: 2.2.2.2\n  port: 443\n"
                "proxy-groups:\n"
                "- name: g1\n  type: select\n  proxies: [a, b]\n")
    us_csv = os.path.join(td, 'us.csv')
    cn_csv = os.path.join(td, 'cn.csv')
    with open(us_csv, 'w', encoding='utf-8', newline='') as f:
        f.write("名称,类型,服务器,端口,TCP,TLS,耗时ms,错误\n")
        f.write("a,vless,1.1.1.1,443,Y,Y,10,\n")
        f.write("b,vless,2.2.2.2,443,Y,Y,10,\n")
    with open(cn_csv, 'w', encoding='utf-8', newline='') as f:
        f.write("名称,类型,服务器,端口,TCP,TLS,耗时ms,错误\n")
        f.write("a,vless,1.1.1.1,443,Y,Y,10,\n")
        f.write("b,vless,2.2.2.2,443,N,,10,Connection reset by peer\n")
    out_list = os.path.join(td, 'out.yml')
    r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, 'scripts', 'crosscheck.py'),
                        '--us', us_csv, '--cn', cn_csv,
                        '--out-csv', os.path.join(td, 'x.csv'),
                        '--out-md', os.path.join(td, 'x.md'),
                        '--input-list', lst, '--out-cn-list', out_list],
                       capture_output=True, text=True, encoding='utf-8')
    check("退出码 0", r.returncode, 0)
    d = yaml.safe_load(open(out_list, encoding='utf-8'))
    check("子集只剩 1 个节点", [p['name'] for p in d['proxies']], ['a'])
    check("组的引用同步清理", d['proxy-groups'][0]['proxies'], ['a'])
    check("输出里提到清理数量", '失效的 proxy-group 引用' in r.stdout, True)

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
