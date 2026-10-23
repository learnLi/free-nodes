#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按探测结果裁剪 Clash 配置。

读入 probe.csv 的探测结论，对 Clash YAML 里的 proxies 列表做保守裁剪，
输出裁剪后的配置。被剔除的节点会逐条记录原因，便于复查。

裁剪规则（刻意保守，只剔除「确凿」的问题，避免误杀国内可用节点）：

  1. 明文 HTTP / SOCKS 代理 —— 公开开放的代理服务器，代理方可以明文
     看到经由它的 HTTP 流量，且这类节点本身也不是「免费节点」，是爬来的
     开放代理。可通过 --keep-plaintext-proxy 保留。
  2. TCP 连接被「拒绝」—— 端口无人监听，确凿已死。
  3. TLS 握手被对端明确拒绝（SSLV3_ALERT_HANDSHAKE_FAILURE /
     WRONG_VERSION_NUMBER 等）—— 该端口跑的不是预期的 TLS 服务。

以下情况一律保留：

  * TCP 超时 —— 可能是防火墙丢包，也可能服务器只放行中国大陆 IP，
    对国内用户仍然可用，仅凭美国出口的超时无法判定其已死。
  * QUIC / UDP 协议（hysteria2 / tuic）—— TCP 探测不适用，未被探测。
"""
import argparse
import csv
import os
import sys
from typing import Any, Dict, List, Set, Tuple

# 明文代理类型
PLAINTEXT_TYPES = {'http', 'https', 'socks5', 'socks'}

# 「确凿已死」的错误特征
#
# 判据是「路径通、但服务不在」：对端主动回了 RST，说明网络路径没问题，
# 只是那个端口没有服务在监听。
#
# 刻意**不**包含下面这些，它们反映的是探测端或网络侧的问题，不是节点的问题：
#   timeout                  —— 防火墙丢包，节点可能只对中国 IP 放行
#   Network is unreachable  —— 探测端没有该协议族的路由。实测 GitHub 的
#                              runner 就没有 IPv6 出口，所有 IPv6 节点都报
#                              这句，若据此裁剪会误杀全部 IPv6 节点
#   No route to host        —— 同上，路径不可达
#   Host is unreachable     —— ICMP 不可达，主机本身可能活着
#   Name or service not known —— DNS 解析失败，可能是探测端 DNS 的问题
DEAD_ERROR_MARKERS = (
    'refused',          # Connection refused
    'reset by peer',    # Connection reset by peer
)

# 对端明确拒绝 TLS —— 说明该端口不是预期的 TLS 服务
TLS_REJECT_MARKERS = (
    'SSLV3_ALERT_HANDSHAKE_FAILURE',
    'WRONG_VERSION_NUMBER',
    'SSL_WRONG_VERSION_NUMBER',
    'UNSUPPORTED_PROTOCOL',
    'no protocols available',
    'CERTIFICATE_VERIFY_FAILED',  # 证书与 SNI 完全不匹配，多半不是目标服务
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='按探测结果裁剪 Clash 配置')
    p.add_argument('--input', default='', help='输入的 Clash YAML（留空则只处理 V2Ray 列表）')
    p.add_argument('--output', default='', help='裁剪后的输出 YAML')
    p.add_argument('--probe', default='probe.csv', help='probe.csv 路径')
    p.add_argument('--keep-plaintext-proxy', action='store_true',
                   help='保留明文 HTTP / SOCKS 代理节点')
    p.add_argument('--keep-timeout', action='store_true',
                   help='保留 TCP 超时的节点（默认保留，此开关仅为显式声明）')
    p.add_argument('--removed-report', default='pruned.csv',
                   help='被剔除节点的记录文件')
    p.add_argument('--v2ray-input', default='',
                   help='额外处理 V2Ray 明文链接列表（每行一条），按同样规则剔除')
    p.add_argument('--v2ray-output', default='',
                   help='V2Ray 明文链接列表的输出路径')
    return p.parse_args()


# ---------------------------------------------------------------- V2Ray 明文链接

def extract_addr(url: str) -> Tuple[str, int]:
    """从一条 V2Ray 明文链接里取出 (server, port)。取不到就返回 ('', 0)。"""
    import base64
    import json
    import re
    from urllib.parse import unquote, urlparse
    try:
        if url.startswith('vmess://'):
            raw = url[len('vmess://'):].split('#')[0]
            raw += '=' * ((4 - len(raw) % 4) % 4)
            data = json.loads(base64.b64decode(raw).decode('utf-8', 'ignore'))
            return str(data.get('add', '')), int(data.get('port') or 0)
        if url.startswith('ssr://'):
            raw = url[len('ssr://'):].split('#')[0]
            raw += '=' * ((4 - len(raw) % 4) % 4)
            body = base64.urlsafe_b64decode(raw).decode('utf-8', 'ignore')
            parts = body.split(':')
            if len(parts) >= 2:
                return parts[0], int(parts[1] or 0)
            return '', 0
        parsed = urlparse(url)
        host = parsed.hostname or ''
        return host, int(parsed.port or 0)
    except Exception:  # noqa: BLE001 - 单条链接解析失败不应中断整批处理
        return '', 0


def prune_v2ray(path: str, out_path: str, probe: Dict[Tuple[str, int], Dict[str, str]],
                keep_plaintext: bool) -> Tuple[int, List[Tuple[str, str, str]]]:
    """按同样规则裁剪 V2Ray 明文链接列表。

    返回 (剔除条数, [(名称, 类型, 原因), ...])。
    """
    removed: List[Tuple[str, str, str]] = []
    kept_lines: List[str] = []
    with open(path, encoding='utf-8') as f:
        lines = f.read().splitlines()
    for url in lines:
        url = url.strip()
        if not url:
            continue
        scheme = url.split('://', 1)[0].lower() if '://' in url else ''
        if scheme in PLAINTEXT_TYPES and not keep_plaintext:
            removed.append((url[:60], scheme.upper(),
                            '明文 %s 代理（非免费节点，且代理方可见明文流量）'
                            % scheme.upper()))
            continue
        server, port = extract_addr(url)
        row = probe.get((server, port)) if server else None
        if row is not None and row.get('TCP') == 'N':
            err = row.get('错误') or ''
            if any(m.lower() in err.lower() for m in DEAD_ERROR_MARKERS):
                removed.append((url[:60], scheme.upper(),
                                'TCP 连接被拒绝，端口无人监听'))
                continue
        kept_lines.append(url)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(kept_lines) + ('\n' if kept_lines else ''))
    return len(removed), removed


def load_probe(path: str) -> Dict[Tuple[str, int], Dict[str, str]]:
    """(server, port) -> 探测结论。"""
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


def decide(proxy: Dict[str, Any], probe: Dict[Tuple[str, int], Dict[str, str]],
           keep_plaintext: bool) -> Tuple[bool, str]:
    """返回 (是否保留, 原因)。"""
    ptype = (proxy.get('type') or '').lower()

    if ptype in PLAINTEXT_TYPES and not keep_plaintext:
        return False, '明文 %s 代理（非免费节点，且代理方可见明文流量）' % ptype.upper()

    server = str(proxy.get('server') or '').strip('[]')
    try:
        port = int(proxy.get('port') or 0)
    except (TypeError, ValueError):
        port = 0
    row = probe.get((server, port))
    if row is None:
        return True, ''

    if row.get('TCP') == 'N':
        err = row.get('错误') or ''
        if any(m.lower() in err.lower() for m in DEAD_ERROR_MARKERS):
            return False, 'TCP 连接被拒绝，端口无人监听'
        # timeout / 其他 -> 保留，国内可能仍然可用
        return True, ''

    if row.get('TLS') == 'N':
        err = row.get('错误') or ''
        if any(m.lower() in err.lower() for m in TLS_REJECT_MARKERS):
            return False, 'TLS 握手被对端明确拒绝，该端口不是预期的 TLS 服务'

    return True, ''


def write_report(path: str, records: List[Tuple[str, str, str]]) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['名称', '类型', '剔除原因'])
        for n, t, r in records:
            w.writerow([n, t, r])


def main() -> int:
    import yaml
    args = parse_args()
    probe = load_probe(args.probe)

    # ---- V2Ray 明文链接列表 ----
    if args.v2ray_input and args.v2ray_output:
        if os.path.exists(args.v2ray_input):
            n, removed = prune_v2ray(args.v2ray_input, args.v2ray_output, probe,
                                     args.keep_plaintext_proxy)
            write_report(args.removed_report, removed)
            print("裁剪 %s：剔除 %d 条链接" % (args.v2ray_input, n))
            by_reason: Dict[str, int] = {}
            for _, _, r in removed:
                by_reason[r] = by_reason.get(r, 0) + 1
            for r, c in sorted(by_reason.items(), key=lambda x: -x[1]):
                print("  %-52s %d" % (r[:52], c))
            if not removed:
                print("  （无剔除）")
        else:
            print("跳过 V2Ray 列表（找不到 %s）" % args.v2ray_input)

    if not args.input:
        return 0
    if not os.path.exists(args.input):
        print("找不到输入文件：%s" % args.input)
        return 1

    with open(args.input, encoding='utf-8') as f:
        text = f.read()
    data = yaml.safe_load(text) or {}

    proxies: List[Dict[str, Any]] = list(data.get('proxies') or [])
    kept: List[Dict[str, Any]] = []
    removed: List[Tuple[str, str, str]] = []
    for p in proxies:
        ok, reason = decide(p, probe, args.keep_plaintext_proxy)
        if ok:
            kept.append(p)
        else:
            removed.append((str(p.get('name') or ''), str(p.get('type') or ''), reason))

    data['proxies'] = kept
    header = ''
    if text.startswith('#'):
        for line in text.splitlines():
            if line.startswith('#'):
                header += line + '\n'
            else:
                break
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write(yaml.dump(data, allow_unicode=True, sort_keys=False).replace('!!str ', ''))

    write_report(args.removed_report, removed)

    print("裁剪 %s：%d -> %d 个节点（剔除 %d 个）" % (
        args.input, len(proxies), len(kept), len(removed)))
    by_reason = {}
    for _, _, r in removed:
        by_reason[r] = by_reason.get(r, 0) + 1
    for r, c in sorted(by_reason.items(), key=lambda x: -x[1]):
        print("  %-52s %d" % (r[:52], c))
    if not removed:
        print("  （无剔除）")
    return 0


if __name__ == '__main__':
    sys.exit(main())
