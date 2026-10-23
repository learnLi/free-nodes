#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多轮探测数据的公共逻辑。

为什么要多轮：单轮探测噪声很大。实测同一批 409 个地址连续 5 轮探测，
单轮说「活」的节点里，换一轮就有一批变成「死」。跨轮的一致性才是
可靠的质量信号。

判定分三档：
  stable_alive —— 出现的每一轮都活着
  stable_dead  —— 出现的每一轮都死了
  unknown      —— 死活不定（或者只出现过一轮，数据不足）
"""
import csv
import os
from typing import Any, Dict, List, Optional, Set, Tuple

# 探活结果里表示「活着」的字段
ALIVE_FIELDS = ('TCP', 'TLS', 'QUIC')


def is_alive(row: Dict[str, str]) -> bool:
    """这一轮探测算不算「活着」。

    不能只看「TCP/TLS/QUIC 任一为 Y」：走 TLS 的协议（vmess/vless/trojan）
    如果 TCP 通了但 **TLS 握手失败或超时**，说明代理服务没起或 SNI 不对，
    节点实际上是不可用的。实测有一批节点正是这种（TCP=Y、TLS=N、
    错误=timeout），把它们算作活着会同时污染「跨轮存活」判定和延迟统计
    （它们的耗时记的是 5 秒超时值）。

    非 TLS 协议（ss/ssr）的 TLS 字段是 'N/A'，不受影响；
    QUIC 协议（hysteria2/tuic）看 QUIC 字段。
    """
    # 明确失败的握手一律不算活着
    if row.get('TLS') == 'N':
        return False
    if row.get('QUIC') == 'N':
        return False
    for f in ALIVE_FIELDS:
        if row.get(f) == 'Y':
            return True
    return False


def load_round(path: str) -> Dict[Tuple[str, int], Dict[str, Any]]:
    """读一轮探测结果 -> {地址: {'alive': bool, 'latency': ms|None}}。"""
    out: Dict[Tuple[str, int], Dict[str, Any]] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            try:
                port = int(row.get('端口') or 0)
            except (TypeError, ValueError):
                continue
            latency = None
            raw = row.get('耗时ms')
            if raw:
                try:
                    latency = float(raw)
                except (TypeError, ValueError):
                    latency = None
            out[(row.get('服务器') or '', port)] = {
                'alive': is_alive(row),
                'latency': latency,
            }
    return out


def load_rounds(paths: List[str]) -> List[Dict[Tuple[str, int], Dict[str, Any]]]:
    return [load_round(p) for p in paths if os.path.exists(p)]


def median_latency(rounds: List[Dict[Tuple[str, int], Dict[str, Any]]],
                    addr: Tuple[str, int]) -> Optional[float]:
    """取该地址在各轮里成功探测到的延迟中位数。

    用中位数而不是平均值或最小值：中位数代表「典型体验」，
    最小值会把「偶尔快一次」的节点也留下。
    """
    vals = []
    for r in rounds:
        e = r.get(addr)
        if e and e.get('alive') and e.get('latency') is not None:
            vals.append(float(e['latency']))
    if not vals:
        return None
    vals.sort()
    n = len(vals)
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def classify(addr: Tuple[str, int],
             rounds: List[Dict[Tuple[str, int], Dict[str, Any]]],
             min_rounds: int = 2,
             alive_ratio: float = 1.0) -> Tuple[str, int, int]:
    """判定一个地址的跨轮状态。

    返回 (状态, 出现轮数, 存活轮数)，状态取
    stable_alive / stable_dead / unknown。
    """
    seen = 0
    alive = 0
    for r in rounds:
        e = r.get(addr)
        if e is not None:
            seen += 1
            if e.get('alive'):
                alive += 1
    if seen == 0:
        return 'unknown', 0, 0
    if seen < min_rounds:
        # 数据不足：判为 unknown，由调用方决定保守处理
        return 'unknown', seen, alive
    if alive / seen >= alive_ratio:
        return 'stable_alive', seen, alive
    if alive == 0:
        return 'stable_dead', seen, alive
    return 'unknown', seen, alive


def addr_of(proxy: Dict) -> Tuple[str, int]:
    try:
        port = int(proxy.get('port') or 0)
    except (TypeError, ValueError):
        port = 0
    return (str(proxy.get('server') or '').strip('[]'), port)


def keep_recent(history: List[str], current: str, n: int) -> List[str]:
    """保留本轮 + 最近 (n-1) 轮历史。

    注意本轮必须放在**最后**。历史上如果写成 [本轮]+历史 再取尾部，
    会在轮次很多时把本轮切掉——判定就少了最新的一轮数据。
    """
    if n > 0 and n > 1:
        history = history[-(n - 1):]
    elif n == 1:
        history = []
    return list(history) + [current]
