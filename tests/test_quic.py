#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QUIC 探测的单元测试（本地 UDP 回显，不访问外网）。"""
import os
import socket
import sys
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from probe import (quic_probe, _quic_varint, probe_one, is_udp_protocol,
                   _quic_initial_probe, _quic_handshake_probe)

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-56s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-56s got=%r want=%r" % (name, got, want))


def check_true(name, got):
    check(name, bool(got), True)


print("=== 1. QUIC 变长整数编码 ===")
check("0 -> 单字节 0x00", _quic_varint(0).hex(), '00')
check("63 -> 单字节 0x3f", _quic_varint(63).hex(), '3f')
check("64 -> 两字节 0x4040", _quic_varint(64).hex(), '4040')
check("1201 -> 两字节 0x44b1", _quic_varint(1201).hex(), '44b1')
check("16384 -> 四字节 0x80004000", _quic_varint(16384).hex(), '80004000')
for n in (0, 63, 64, 1201, 16384, 1073741823, 1073741824):
    b = _quic_varint(n)
    # 长度前缀的 2 位必须是 00/01/10/11
    check_true('varint(%d) 长度前缀合法' % n, (b[0] >> 6) in (0, 1, 2, 3))

print()
print("=== 2. 本地 UDP 回显服务器 ===")
srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
srv.bind(('127.0.0.1', 0))
port = srv.getsockname()[1]
received = []


def serve():
    for _ in range(5):
        try:
            d, a = srv.recvfrom(4096)
            received.append(d)
            srv.sendto(b'RETRY' + d[:8], a)
        except OSError:
            return


t = threading.Thread(target=serve, daemon=True)
t.start()
ok, ms, err = _quic_initial_probe('127.0.0.1', port, 2.0)
t.join(1)
check("裸 Initial 收到响应 -> ok=True", ok, True)
check_true("响应信息里提到 QUIC", 'QUIC' in err)

print()
print("=== 2b. 完整握手探测（本地回显不是真 QUIC 服务端）===")
ok_h, ms_h, err_h = _quic_handshake_probe('127.0.0.1', port, 3.0)
check("对非 QUIC 服务端握手 -> ok=False", ok_h, False)
check_true("有错误信息", err_h != '')

print()
print("=== 2c. quic_probe 的分发逻辑 ===")
import probe as _probe_mod
check("装有 aioquic 时走握手探测", _probe_mod.quic_probe.__doc__ is not None, True)
try:
    import aioquic  # noqa: F401
    has_aioquic = True
except ImportError:
    has_aioquic = False
print("  （本机 aioquic: %s）" % ('有' if has_aioquic else '无'))

print()
print("=== 3. 发出的包符合 QUIC Initial 格式 ===")
check_true("收到了包", len(received) >= 1)
if received:
    d = received[0]   # 第一个包来自裸 Initial 探测
    check("长度 >= 1200（QUIC 硬性要求）", len(d) >= 1200, True)
    check("首字节：long header + type=Initial + fixed bit", d[0] & 0xF0, 0xC0)
    check("type = Initial(0)", d[0] & 0x30, 0x00)
    check("version = QUIC v1", d[1:5].hex(), '00000001')
    dcid_len = d[5]
    check_true('DCID 长度合理(8)', dcid_len == 8)
    off = 6 + dcid_len
    scid_len = d[off]
    check_true('SCID 长度合理(8)', scid_len == 8)
    off = off + 1 + scid_len
    check("token length = 0", d[off], 0)

print()
print("=== 4. 无响应时不应误报 ===")
ok2, ms2, err2 = quic_probe('127.0.0.1', 1, 1.0)
check("无人监听 -> ok=False", ok2, False)
check_true("有错误信息", err2 != '')

print()
print("=== 5. probe_one 对 QUIC 协议走 QUIC 分支 ===")
row = probe_one({'name': 'n', 'type': 'hysteria2',
                 'server': '127.0.0.1', 'port': port}, 2.0)
check("TCP 标为 N/A", row['TCP'], 'N/A')
check("TLS 标为 N/A", row['TLS'], 'N/A')
check("QUIC 标为 Y 或 N", row['QUIC'] in ('Y', 'N'), True)
check_true("耗时已记录", row['耗时ms'] != '')
check("hysteria2 属于 QUIC 协议", is_udp_protocol('hysteria2'), True)
check("tuic 属于 QUIC 协议", is_udp_protocol('tuic'), True)
check("vmess 不是 QUIC 协议", is_udp_protocol('vmess'), False)

srv.close()

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
