#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe.py 的单元测试（不访问外网）。

用本地临时监听端口验证 TCP 连接与 TLS 判定逻辑。
"""
import os
import socket
import sys
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from probe import (is_udp_protocol, wants_tls, pick_sni, strip_brackets,
                   probe_one, tcp_connect, load_proxies)

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-52s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-52s got=%r want=%r" % (name, got, want))


print("=== 1. 协议分类 ===")
check("hysteria2 是 QUIC/UDP", is_udp_protocol('hysteria2'), True)
check("tuic 是 QUIC/UDP", is_udp_protocol('tuic'), True)
check("hy2 别名也是 UDP", is_udp_protocol('hy2'), True)
check("vmess 不是 UDP", is_udp_protocol('vmess'), False)
check("trojan 不是 UDP", is_udp_protocol('trojan'), False)
check("ss 不是 UDP", is_udp_protocol('ss'), False)
check("大小写不敏感", is_udp_protocol('Hysteria2'), True)

print()
print("=== 2. TLS 判定 ===")
check("trojan 走 TLS", wants_tls({'type': 'trojan'}), True)
check("hysteria2 走 TLS", wants_tls({'type': 'hysteria2'}), True)
check("vmess tls=True 走 TLS", wants_tls({'type': 'vmess', 'tls': True}), True)
check("vmess tls='tls' 走 TLS", wants_tls({'type': 'vmess', 'tls': 'tls'}), True)
check("vless tls=False 不走 TLS", wants_tls({'type': 'vless', 'tls': False}), False)
check("ss 不走 TLS", wants_tls({'type': 'ss'}), False)
check("ssr 不走 TLS", wants_tls({'type': 'ssr'}), False)

print()
print("=== 3. SNI 与地址处理 ===")
check("优先取 sni", pick_sni({'sni': 'a.com', 'server': 'b.com'}), 'a.com')
check("其次取 servername", pick_sni({'servername': 'b.com', 'server': 'c.com'}), 'b.com')
check("都没有则用 server", pick_sni({'server': 'c.com'}), 'c.com')
check("去掉 IPv6 方括号", strip_brackets('[2001:db8::1]'), '2001:db8::1')
check("普通地址不变", strip_brackets('1.2.3.4'), '1.2.3.4')

print()
print("=== 4. 实际连接（本地临时监听端口）===")
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('127.0.0.1', 0))
srv.listen(8)
port = srv.getsockname()[1]


def serve():
    while True:
        try:
            c, _ = srv.accept()
            c.close()
        except OSError:
            return


threading.Thread(target=serve, daemon=True).start()

ok, ms, err = tcp_connect('127.0.0.1', port, 2.0)
check("本地监听端口可连通", ok, True)
ok2, _, _ = tcp_connect('127.0.0.1', port + 1, 1.0)
check("未监听端口不可连通", ok2, False)

row = probe_one({'name': 'n', 'type': 'ss', 'server': '127.0.0.1', 'port': port}, 2.0)
check("probe_one: TCP=Y", row['TCP'], 'Y')
check("probe_one: ss 不做 TLS 握手", row['TLS'], 'N/A')

row = probe_one({'name': 'n', 'type': 'hysteria2', 'server': '127.0.0.1', 'port': port}, 2.0)
check("probe_one: hysteria2 标记 N/A", row['TCP'], 'N/A')
check("probe_one: hysteria2 走 QUIC 分支", row['QUIC'] in ('Y', 'N'), True)
check("probe_one: hysteria2 有说明", row['错误'] != '', True)

row = probe_one({'name': 'n', 'type': 'vmess', 'server': '', 'port': 0}, 1.0)
check("probe_one: 地址不完整被拒", row['TCP'], '')
check("probe_one: 给出错误原因", '地址不完整' in row['错误'], True)

row = probe_one({'name': 'n', 'type': 'vmess', 'server': '127.0.0.1', 'port': port + 1}, 1.0)
check("probe_one: 连不上记为 N", row['TCP'], 'N')
check("probe_one: 记录错误", row['错误'] != '', True)

srv.close()

print()
print("=== 5. 读取 Clash 配置 ===")
import tempfile
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, 'c.yml')
    with open(p, 'w', encoding='utf-8') as f:
        f.write("proxies:\n"
                "- name: a\n  type: vmess\n  server: 1.1.1.1\n  port: 443\n"
                "- name: b\n  type: trojan\n  server: 2.2.2.2\n  port: 443\n")
    ps = load_proxies(p)
    check("解析出 2 个节点", len(ps), 2)
    check("第一个节点的类型", ps[0]['type'], 'vmess')

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
