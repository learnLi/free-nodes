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
from typing import Dict, List, Optional, Set, Tuple

# 探活结果里表示「活着」的字段
ALIVE_FIELDS = ('TCP', 'TLS', 'QUIC')


def is_alive(row: Dict[str, str]) -> bool:
    for f in ALIVE_FIELDS:
        if row.get(f) == 'Y':
            return True
    return False


def load_round(path: str) -> Dict[Tuple[str, int], bool]:
    """读一轮探测结果 -> {地址: 是否活着}。"""
    out: Dict[Tuple[str, int], bool] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            try:
                port = int(row.get('端口') or 0)
            except (TypeError, ValueError):
                continue
            out[(row.get('服务器') or '', port)] = is_alive(row)
    return out


def load_rounds(paths: List[str]) -> List[Dict[Tuple[str, int], bool]]:
    return [load_round(p) for p in paths if os.path.exists(p)]


def classify(addr: Tuple[str, int],
             rounds: List[Dict[Tuple[str, int], bool]],
             min_rounds: int = 2,
             alive_ratio: float = 1.0) -> Tuple[str, int, int]:
    """判定一个地址的跨轮状态。

    返回 (状态, 出现轮数, 存活轮数)，状态取
    stable_alive / stable_dead / unknown。
    """
    seen = 0
    alive = 0
    for r in rounds:
        if addr in r:
            seen += 1
            if r[addr]:
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
