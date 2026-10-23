#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节点可达性探测（海外出口视角）。

对 Clash Meta 配置里的每个节点做 TCP 连接探测，对走 TLS 的协议追加一次
TLS 握手，最后输出 probe.csv 与统计摘要。

重要边界：
  * 本脚本从 CI runner 发起，runner 在**美国**，因此探测结果代表
    「海外可达」，不等于「中国大陆可达」。被墙 / 跨境拥塞的节点在本脚本
    眼里依然是「活的」。
  * hysteria2 / tuic 走 QUIC（UDP），TCP 探测对它们无意义，会被标为 N/A
    并从统计中剔除，否则会凭空产生大量「死节点」。

本脚本只做测量，不修改任何产物。是否用结果做过滤，由数据决定。
"""
import argparse
import csv
import json
import os
import re
import socket
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

# QUIC / UDP 协议：TCP 探测不适用
UDP_PROTOCOLS = {'hysteria2', 'tuic', 'hy2'}

# 走 TLS 的协议（用于决定是否追加 TLS 握手）
# trojan / hysteria2 / tuic 天然是 TLS；vmess / vless 取决于 tls 字段
ALWAYS_TLS = {'trojan', 'hysteria2', 'tuic'}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='节点可达性探测')
    p.add_argument('--input', default='list.meta.yml',
                   help='待探测的 Clash Meta 配置（默认 list.meta.yml）')
    p.add_argument('--output', default='probe.csv',
                   help='探测结果 CSV 输出路径（默认 probe.csv）')
    p.add_argument('--timeout', type=float, default=3.0,
                   help='单次连接超时秒数（默认 3）')
    p.add_argument('--workers', type=int, default=64,
                   help='并发探测数（默认 64）')
    p.add_argument('--limit', type=int, default=0,
                   help='最多探测多少个节点，0 表示不限（默认 0）')
    p.add_argument('--ref', action='append', default=[],
                   help='对照探测地址，host:port，可重复')
    return p.parse_args()


def load_proxies(path: str) -> List[Dict[str, Any]]:
    import yaml
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f.read()) or {}
    return list(data.get('proxies') or [])


def is_udp_protocol(ptype: str) -> bool:
    return (ptype or '').lower() in UDP_PROTOCOLS


def wants_tls(proxy: Dict[str, Any]) -> bool:
    ptype = (proxy.get('type') or '').lower()
    if ptype in ALWAYS_TLS:
        return True
    if proxy.get('tls') is True:
        return True
    if ptype == 'vmess' and str(proxy.get('tls', '')).lower() == 'tls':
        return True
    return False


def pick_sni(proxy: Dict[str, Any]) -> str:
    for key in ('sni', 'servername', 'peer'):
        v = proxy.get(key)
        if v:
            return str(v)
    return str(proxy.get('server') or '')


def strip_brackets(host: str) -> str:
    host = (host or '').strip()
    if host.startswith('[') and host.endswith(']'):
        return host[1:-1]
    return host


def tcp_connect(host: str, port: int, timeout: float) -> Tuple[bool, float, str]:
    """返回 (是否连通, 耗时毫秒, 错误摘要)。"""
    start = time.monotonic()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True, (time.monotonic() - start) * 1000, ''
    except socket.timeout:
        return False, (time.monotonic() - start) * 1000, 'timeout'
    except OSError as e:
        return False, (time.monotonic() - start) * 1000, (e.strerror or str(e))[:60]


def tls_handshake(host: str, port: int, sni: str, timeout: float) -> Tuple[bool, float, str]:
    """在 TCP 之上完成一次 TLS 握手。

    不校验证书——免费节点的证书普遍有问题，这里只关心「对端是否真的在
    跑 TLS 服务」，不是「证书是否可信」。
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            with ctx.wrap_socket(sock, server_hostname=sni or host) as ssock:
                cipher = ssock.version() or ''
                return True, (time.monotonic() - start) * 1000, cipher
    except socket.timeout:
        return False, (time.monotonic() - start) * 1000, 'timeout'
    except ssl.SSLError as e:
        return False, (time.monotonic() - start) * 1000, ('ssl: ' + str(e))[:60]
    except OSError as e:
        return False, (time.monotonic() - start) * 1000, (e.strerror or str(e))[:60]
    except Exception as e:  # noqa: BLE001 - 探测脚本不应因单个节点异常而崩
        return False, (time.monotonic() - start) * 1000, (type(e).__name__ + ': ' + str(e))[:60]


def _quic_varint(n: int) -> bytes:
    """QUIC 变长整数（2 位长度前缀）。

    1 字节：6 位值    2 字节：14 位值
    4 字节：30 位值   8 字节：62 位值
    """
    if n < 64:
        return n.to_bytes(1, 'big')
    if n < 16384:
        return bytes([0x40 | (n >> 8)]) + (n & 0xFF).to_bytes(1, 'big')
    if n < 1073741824:
        return bytes([0x80 | (n >> 24)]) + (n & 0xFFFFFF).to_bytes(3, 'big')
    return bytes([0xC0 | (n >> 56)]) + (n & 0x3FFFFFFFFFFFFFFF).to_bytes(7, 'big')


def quic_probe(host: str, port: int, timeout: float) -> Tuple[bool, float, str]:
    """QUIC over UDP 的存活探测。

    hysteria2 / tuic 走 QUIC，TCP 探测对它们完全无效（服务端根本不监听 TCP），
    会被误判成「已死」。

    做法：发一个 QUIC v1 Initial 包，**不需要**构造真正的 TLS ClientHello——
    按 RFC 9000，服务端收到 DCID 未知的 Initial 时**可以**回一个 Retry，
    而 DCID 是明文放在头里的，所以不需要解密就能回包。用 PADDING 帧把包
    撑到 1200 字节（QUIC 要求客户端 Initial 不小于 1200 字节）。

    局限：回 Retry 是「可以」而非「必须」（RFC 9000 §17.2.5.2），
    有些服务端（如 quic-go 默认配置）根本不发 Retry，而是直接丢弃。
    因此「无响应」**不能**直接判定为已死——它同时可能是：
      * 服务端不发 Retry（包构造没问题，但没回应）
      * UDP 路径被阻断（GFW 对 QUIC 的干扰，或服务商的 UDP 限速）
    真正确凿的死亡只有一种：ICMP port unreachable（表现为 refused）。
    所以裁剪规则只认 refused，timeout 一律保留。
    """
    start = time.monotonic()
    dcid = os.urandom(8)
    scid = os.urandom(8)
    padding = b'\x00' * 1200
    # long header | type=Initial(0) | fixed bit | PN length=1
    first = 0xC0 | 0x01
    pkt = (bytes([first]) + b'\x00\x00\x00\x01'
           + bytes([len(dcid)]) + dcid
           + bytes([len(scid)]) + scid
           + b'\x00'                      # token length = 0
           + _quic_varint(1 + len(padding))  # length = PN(1) + payload
           + b'\x00'                      # packet number
           + padding)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    except socket.gaierror as e:
        return False, (time.monotonic() - start) * 1000, 'DNS 解析失败'
    last_err = 'no response'
    for family, socktype, proto, _, sockaddr in infos:
        try:
            s = socket.socket(family, socktype, proto)
        except OSError as e:
            last_err = (e.strerror or str(e))[:40]
            continue
        try:
            s.settimeout(timeout)
            s.sendto(pkt, sockaddr)
            data, _ = s.recvfrom(2048)
            return True, (time.monotonic() - start) * 1000, 'QUIC 响应 %d 字节' % len(data)
        except socket.timeout:
            last_err = 'timeout'
        except OSError as e:
            last_err = (e.strerror or str(e))[:40]
        finally:
            try:
                s.close()
            except OSError:
                pass
    return False, (time.monotonic() - start) * 1000, last_err


def probe_one(proxy: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    ptype = (proxy.get('type') or '').lower()
    host = strip_brackets(str(proxy.get('server') or ''))
    try:
        port = int(proxy.get('port') or 0)
    except (TypeError, ValueError):
        port = 0
    row: Dict[str, Any] = {
        '名称': str(proxy.get('name') or ''),
        '类型': ptype,
        '服务器': host,
        '端口': port,
        'TCP': '',
        'TLS': '',
        'QUIC': '',
        '耗时ms': '',
        '错误': '',
    }
    if not host or not port:
        row['错误'] = '地址不完整'
        return row
    if is_udp_protocol(ptype):
        # QUIC over UDP：TCP 探测无意义，改用 QUIC Initial 探测
        ok, ms, err = quic_probe(host, port, timeout)
        row['TCP'] = 'N/A'
        row['TLS'] = 'N/A'
        row['QUIC'] = 'Y' if ok else 'N'
        row['耗时ms'] = '%.0f' % ms
        row['错误'] = err
        return row

    ok, ms, err = tcp_connect(host, port, timeout)
    row['TCP'] = 'Y' if ok else 'N'
    if not ok:
        row['耗时ms'] = '%.0f' % ms
        row['错误'] = err
        return row

    if wants_tls(proxy):
        tok, tms, terr = tls_handshake(host, port, pick_sni(proxy), timeout)
        row['TLS'] = 'Y' if tok else 'N'
        row['耗时ms'] = '%.0f' % tms
        row['错误'] = terr
    else:
        row['TLS'] = 'N/A'
        row['耗时ms'] = '%.0f' % ms
    return row


def _raw_http_ip(urls: List[str], timeout: float) -> str:
    """用裸 TCP(+TLS) 请求 IP 回显服务，拿到**直连**出口。

    探测本身走的是 socket.create_connection（裸 TCP，不走任何 HTTP 代理），
    所以自报出口必须用同样的路径。urllib 会读取 http_proxy 环境变量，
    在有代理的机器上它报的是**代理的**出口 IP，与探测实际走的路径不符——
    那会让「从哪儿探的」这个前提失真。
    """
    import ssl
    for url in urls:
        try:
            from urllib.parse import urlparse
            p = urlparse(url)
            host = p.hostname or ''
            port = p.port or (443 if p.scheme == 'https' else 80)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((host, port), timeout=timeout) as sock:
                if p.scheme == 'https':
                    sock = ctx.wrap_socket(sock, server_hostname=host)
                req = ("GET %s HTTP/1.1\r\nHost: %s\r\n"
                       "User-Agent: free-nodes-probe\r\nConnection: close\r\n\r\n"
                       % (p.path or '/', host))
                sock.sendall(req.encode())
                buf = b''
                while len(buf) < 4096:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                body = buf.split(b'\r\n\r\n', 1)[-1].decode('utf-8', 'ignore').strip()
                m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', body)
                if m:
                    return m.group(1)
        except Exception:  # noqa: BLE001
            continue
    return ''


def detect_egress(timeout: float = 8.0) -> Dict[str, Any]:
    """探测发起方的公网出口 IP 与归属地。

    探针结果的一切解读都取决于「从哪儿探的」——海外出口探到的「通」
    不代表中国大陆可达。这个自报信息随每轮结果一起发布，让结论可核查。

    优先用裸 TCP 查直连出口（与探测路径一致）；查不到再退回 urllib，
    并明确标注 method='proxy'，因为那种情况下报的是代理出口，与探测
    实际走的路径可能不同。
    """
    import json as _json
    import urllib.request
    out: Dict[str, Any] = {}
    ip = _raw_http_ip(['https://api.ipify.org/?format=json',
                        'https://ifconfig.co/json'], timeout)
    method = 'direct'
    if not ip:
        method = 'proxy'
        for url in ('https://api.ipify.org?format=json',
                    'https://ifconfig.co/json',
                    'https://api.ip.sb/geoip'):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'free-nodes-probe'})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = _json.loads(r.read().decode('utf-8', 'ignore'))
                ip = str(data.get('ip') or data.get('origin') or '').split(',')[0].strip()
                if ip:
                    out['country'] = data.get('country') or data.get('country_name') or ''
                    out['city'] = data.get('city') or ''
                    out['org'] = data.get('org') or data.get('organization') or ''
                    break
            except Exception:  # noqa: BLE001
                continue
    if not ip:
        return {}
    out['ip'] = ip
    out['method'] = method
    if not out.get('country'):
        # 归属地接口失败时再单独查一次
        try:
            req = urllib.request.Request('https://ipwho.is/' + ip,
                                         headers={'User-Agent': 'free-nodes-probe'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = _json.loads(r.read().decode('utf-8', 'ignore'))
            out['country'] = data.get('country') or ''
            out['city'] = data.get('city') or ''
            out['org'] = out.get('org') or data.get('connection', {}).get('isp', '')
        except Exception:  # noqa: BLE001
            pass
    return out


def main() -> int:
    args = parse_args()
    if not os.path.exists(args.input):
        print("找不到输入文件：%s" % args.input)
        return 1

    proxies = load_proxies(args.input)
    if args.limit and len(proxies) > args.limit:
        proxies = proxies[:args.limit]
    print("待探测节点：%d 个" % len(proxies))

    # 探测出口自报：结果的一切解读都取决于从哪儿探的
    egress = detect_egress()
    if egress:
        print("探测出口：%s  %s %s  %s" % (
            egress.get('ip', '?'), egress.get('country', '?'),
            egress.get('city', ''), egress.get('org', '')))
    else:
        print("探测出口：无法确定（自报接口不可达）")

    # 对照探测：区分「节点死了」和「runner 整体网络不通」
    refs: List[Tuple[str, int, bool, float, str]] = []
    for ref in args.ref:
        if ':' not in ref:
            continue
        h, _, p = ref.rpartition(':')
        try:
            port = int(p)
        except ValueError:
            continue
        ok, ms, err = tcp_connect(h, port, args.timeout)
        refs.append((h, port, ok, ms, err))
        print("  对照 %-22s %s  %.0fms %s" % (ref, 'OK ' if ok else 'FAIL', ms, err))

    rows: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(probe_one, p, args.timeout): p for p in proxies}
        done = 0
        for fut in as_completed(futures):
            try:
                rows.append(fut.result())
            except Exception as e:  # noqa: BLE001
                print("探测异常：%s" % e)
            done += 1
            if done % 50 == 0:
                print("  已探测 %d/%d" % (done, len(proxies)), flush=True)

    rows.sort(key=lambda r: (r['类型'], r['服务器'], r['端口']))

    fields = ['名称', '类型', '服务器', '端口', 'TCP', 'TLS', 'QUIC', '耗时ms', '错误']
    with open(args.output, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---- 统计 ----
    tcp_applicable = [r for r in rows if r['TCP'] != 'N/A']
    tcp_ok = [r for r in tcp_applicable if r['TCP'] == 'Y']
    tls_applicable = [r for r in rows if r['TLS'] in ('Y', 'N')]
    tls_ok = [r for r in tls_applicable if r['TLS'] == 'Y']
    quic_applicable = [r for r in rows if r['QUIC'] in ('Y', 'N')]
    quic_ok = [r for r in quic_applicable if r['QUIC'] == 'Y']
    udp_skipped = [r for r in rows if r['TCP'] == 'N/A']

    def pct(a: int, b: int) -> str:
        return '%.1f%%' % (a / b * 100) if b else '-'

    print()
    print("=== 探测结果 ===")
    print("总计节点        : %d" % len(rows))
    print("TCP 可探测      : %d" % len(tcp_applicable))
    print("TCP 连通        : %d  (%s)" % (len(tcp_ok), pct(len(tcp_ok), len(tcp_applicable))))
    print("TLS 握手可测    : %d" % len(tls_applicable))
    print("TLS 握手成功    : %d  (%s)" % (len(tls_ok), pct(len(tls_ok), len(tls_applicable))))
    print("QUIC 可探测     : %d（hysteria2/tuic 等 UDP 协议）" % len(quic_applicable))
    print("QUIC 有响应     : %d  (%s)" % (len(quic_ok), pct(len(quic_ok), len(quic_applicable))))

    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for r in tcp_applicable:
        by_type.setdefault(r['类型'], []).append(r)
    if by_type:
        print()
        print("按协议（TCP 连通率）：")
        for t in sorted(by_type):
            rs = by_type[t]
            ok = sum(1 for r in rs if r['TCP'] == 'Y')
            print("  %-10s %4d/%4d  %s" % (t, ok, len(rs), pct(ok, len(rs))))
    if quic_applicable:
        print()
        print("按协议（QUIC 响应率）：")
        q_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for r in quic_applicable:
            q_by_type.setdefault(r['类型'], []).append(r)
        for t in sorted(q_by_type):
            rs = q_by_type[t]
            ok = sum(1 for r in rs if r['QUIC'] == 'Y')
            print("  %-10s %4d/%4d  %s" % (t, ok, len(rs), pct(ok, len(rs))))

    # 汇总成 JSON，方便后续步骤消费
    summary = {
        'total': len(rows),
        'egress': egress,
        'tcp_applicable': len(tcp_applicable),
        'tcp_ok': len(tcp_ok),
        'tcp_rate': pct(len(tcp_ok), len(tcp_applicable)),
        'tls_applicable': len(tls_applicable),
        'tls_ok': len(tls_ok),
        'tls_rate': pct(len(tls_ok), len(tls_applicable)),
        'quic_applicable': len(quic_applicable),
        'quic_ok': len(quic_ok),
        'quic_rate': pct(len(quic_ok), len(quic_applicable)),
        'udp_skipped': len(udp_skipped),
        'refs': [{'host': h, 'port': p, 'ok': ok, 'ms': round(ms), 'err': err}
                 for h, p, ok, ms, err in refs],
        'by_type': {t: {'total': len(rs),
                        'ok': sum(1 for r in rs if r['TCP'] == 'Y')}
                    for t, rs in by_type.items()},
        'by_type_quic': {t: {'total': len(rs),
                              'ok': sum(1 for r in rs if r['QUIC'] == 'Y')}
                          for t, rs in q_by_type.items()} if quic_applicable else {},
    }
    with open('probe_summary.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 同时输出一份 Markdown，方便直接贴进 Release 说明
    md = ['```', '指标 | 数值', '--- | ---']
    md.append('探测出口 | %s %s %s（%s）' % (
        summary['egress'].get('ip', '未知'),
        summary['egress'].get('country', ''),
        summary['egress'].get('city', ''),
        '直连' if summary['egress'].get('method') == 'direct' else '经代理'))
    md.append('总节点数 | %d' % summary['total'])
    md.append('TCP 可探测（已剔除 QUIC/UDP） | %d' % summary['tcp_applicable'])
    md.append('TCP 连通 | %d（%s）' % (summary['tcp_ok'], summary['tcp_rate']))
    md.append('TLS 握手成功 | %d（%s）' % (summary['tls_ok'], summary['tls_rate']))
    md.append('QUIC 可探测（hysteria2/tuic 等 UDP） | %d' % summary['quic_applicable'])
    md.append('QUIC 有响应 | %d（%s）' % (summary['quic_ok'], summary['quic_rate']))
    md.append('QUIC/UDP 跳过 | %d' % summary['udp_skipped'])
    md.append('')
    md.append('按协议 TCP 连通率：')
    md.append('')
    md.append('| 协议 | 连通/总数 | 连通率 |')
    md.append('| :- | :-: | :-: |')
    for t, v in sorted(summary['by_type'].items()):
        r = ('%.1f%%' % (v['ok'] / v['total'] * 100)) if v['total'] else '-'
        md.append('| %s | %d/%d | %s |' % (t, v['ok'], v['total'], r))
    md.append('')
    md.append('对照探测（验证 runner 网络本身是否正常）：')
    md.append('')
    md.append('| 目标 | 结果 | 耗时 | 错误 |')
    md.append('| :- | :- | :-: | :- |')
    for r in summary['refs']:
        md.append('| %s:%s | %s | %sms | %s |' % (
            r['host'], r['port'], 'OK' if r['ok'] else 'FAIL', r['ms'], r['err']))
    md.append('```')
    with open('probe_summary.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(md)+'\n')

    print()
    print("已写出 %s、probe_summary.json、probe_summary.md" % args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
