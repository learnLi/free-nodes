#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prune.py 的单元测试（不联网）。"""
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from prune import decide, load_probe, extract_addr, prune_v2ray

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-56s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-56s got=%r want=%r" % (name, got, want))


def keep(proxy, probe, keep_plaintext=False):
    return decide(proxy, probe, keep_plaintext)[0]


PROBE = {
    ('1.2.3.4', 443): {'服务器': '1.2.3.4', '端口': '443', '类型': 'trojan',
                       'TCP': 'Y', 'TLS': 'N',
                       '错误': 'ssl: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] sslv3 alert handshake failure'},
    ('5.6.7.8', 443): {'服务器': '5.6.7.8', '端口': '443', '类型': 'vmess',
                       'TCP': 'N', 'TLS': '', '错误': 'Connection refused'},
    ('9.9.9.9', 443): {'服务器': '9.9.9.9', '端口': '443', '类型': 'vless',
                       'TCP': 'N', 'TLS': '', '错误': 'timeout'},
    ('8.8.8.8', 443): {'服务器': '8.8.8.8', '端口': '443', '类型': 'hysteria2',
                       'TCP': 'N/A', 'TLS': 'N/A', '错误': 'QUIC/UDP 协议，TCP 探测不适用'},
    ('7.7.7.7', 443): {'服务器': '7.7.7.7', '端口': '443', '类型': 'trojan',
                       'TCP': 'Y', 'TLS': 'N', '错误': 'timeout'},
    ('1.1.1.1', 443): {'服务器': '1.1.1.1', '端口': '443', '类型': 'vless',
                       'TCP': 'Y', 'TLS': 'Y', '错误': ''},
}


def p(server, port, ptype):
    return {'name': 'n', 'type': ptype, 'server': server, 'port': port}


print("=== 1. 明文代理剔除 ===")
check("http 节点被剔除", keep(p('11.1.1.1', 9002, 'http'), PROBE), False)
check("socks5 节点被剔除", keep(p('11.1.1.1', 1080, 'socks5'), PROBE), False)
check("http 节点在 --keep-plaintext-proxy 下保留",
      keep(p('11.1.1.1', 9002, 'http'), PROBE, keep_plaintext=True), True)
check("普通 trojan 不受影响", keep(p('1.1.1.1', 443, 'trojan'), PROBE), True)

print()
print("=== 2. 确凿已死（连接被拒绝）===")
check("Connection refused 被剔除", keep(p('5.6.7.8', 443, 'vmess'), PROBE), False)
ok, reason = decide(p('5.6.7.8', 443, 'vmess'), PROBE, False)
check("剔除原因写明", '拒绝' in reason, True)

print()
print("=== 3. 超时必须保留（可能国内可用）===")
check("TCP timeout 保留", keep(p('9.9.9.9', 443, 'vless'), PROBE), True)
check("TLS timeout 保留", keep(p('7.7.7.7', 443, 'trojan'), PROBE), True)

print()
print("=== 4. TLS 被明确拒绝 ===")
check("SSL 握手告警被剔除", keep(p('1.2.3.4', 443, 'trojan'), PROBE), False)

print()
print("=== 5. QUIC / UDP 与未探测节点 ===")
check("hysteria2 保留", keep(p('8.8.8.8', 443, 'hysteria2'), PROBE), True)
check("探测表里没有的节点保留", keep(p('4.4.4.4', 443, 'vless'), PROBE), True)

print()
print("=== 6. 读取 probe.csv ===")
with tempfile.TemporaryDirectory() as td:
    p_csv = os.path.join(td, 'probe.csv')
    with open(p_csv, 'w', encoding='utf-8', newline='') as f:
        f.write("名称,类型,服务器,端口,TCP,TLS,耗时ms,错误\n")
        f.write("a,trojan,1.2.3.4,443,Y,N,100,ssl: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]\n")
        f.write("b,vmess,5.6.7.8,443,N,,200,Connection refused\n")
    pr = load_probe(p_csv)
    check("读出 2 条", len(pr), 2)
    check("键为 (server, port)", ('5.6.7.8', 443) in pr, True)
    check("端口解析为 int", pr[('5.6.7.8', 443)]['端口'], '443')

print()
print("=== 7. IPv6 方括号 ===")
check("带方括号的 server 能匹配", keep(
    {'name': 'n', 'type': 'vless', 'server': '[1.1.1.1]', 'port': 443}, PROBE), True)

print()
print("=== 8. V2Ray 链接的地址提取 ===")
import base64
import json


def b64(s):
    return base64.b64encode(s.encode()).decode()


vmess = 'vmess://' + b64(json.dumps(
    {'v': '2', 'ps': 'n', 'add': '1.2.3.4', 'port': '443', 'id': 'x'}))
ssr = 'ssr://' + base64.urlsafe_b64encode(
    b'1.2.3.4:443:origin:aes-128-cfb:tls1.2_ticket_auth').decode()
check("vmess 链接取地址", extract_addr(vmess), ('1.2.3.4', 443))
check("ssr 链接取地址", extract_addr(ssr), ('1.2.3.4', 443))
check("trojan 链接取地址",
      extract_addr('trojan://pw@1.2.3.4:443?sni=a.com#name'), ('1.2.3.4', 443))
check("vless 链接取地址",
      extract_addr('vless://uuid@1.2.3.4:443?type=ws#name'), ('1.2.3.4', 443))
check("ss 链接取地址",
      extract_addr('ss://' + b64('aes-128-gcm:pw') + '@1.2.3.4:443#name'),
      ('1.2.3.4', 443))
check("垃圾输入不抛异常", extract_addr('not-a-url'), ('', 0))

print()
print("=== 9. V2Ray 列表裁剪 ===")
with tempfile.TemporaryDirectory() as td:
    src = os.path.join(td, 'raw.txt')
    dst = os.path.join(td, 'out.txt')
    with open(src, 'w', encoding='utf-8') as f:
        f.write('\n'.join([
            'http://u:p@11.1.1.1:9002',
            'socks5://u:p@11.1.1.1:1080',
            'trojan://pw@5.6.7.8:443#dead',      # Connection refused -> 剔除
            'trojan://pw@9.9.9.9:443#timeout',   # timeout -> 保留
            'trojan://pw@1.1.1.1:443#alive',     # 正常 -> 保留
        ]) + '\n')
    n, _removed = prune_v2ray(src, dst, PROBE, keep_plaintext=False)
    out = open(dst, encoding='utf-8').read().splitlines()
    check("剔除 3 条", n, 3)
    check("剩余 2 条", len(out), 2)
    check("timeout 的节点保留", any('timeout' in x for x in out), True)
    check("正常节点保留", any('alive' in x for x in out), True)
    check("明文代理被剔除", any('http://' in x or 'socks5://' in x for x in out), False)

with tempfile.TemporaryDirectory() as td:
    src = os.path.join(td, 'raw.txt')
    dst = os.path.join(td, 'out.txt')
    with open(src, 'w', encoding='utf-8') as f:
        f.write('http://u:p@11.1.1.1:9002\ntrojan://pw@1.1.1.1:443#alive\n')
    n, _removed = prune_v2ray(src, dst, PROBE, keep_plaintext=True)
    check("保留明文代理时只剔除确凿死的", n, 0)

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
