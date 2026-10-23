#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""读取本仓库的配置覆盖层（fetch_config.local.yml）。

配置加载顺序与 fetch.py 保持一致：
    fetch_config.yml（上游，每日同步） → fetch_config.local.yml（本仓库）
"""
import os
from typing import Any, Dict, List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PROTOCOL_ORDER = [
    'vmess', 'vless', 'trojan', 'hysteria2', 'anytls', 'ss',
    'http', 'https', 'socks5', 'socks',
]


def load_config(repo_root: str = REPO_ROOT) -> Dict[str, Any]:
    import yaml
    conf: Dict[str, Any] = {}
    for fn in ('fetch_config.yml', 'fetch_config.local.yml'):
        path = os.path.join(repo_root, fn)
        if not os.path.exists(path):
            continue
        try:
            data = yaml.safe_load(open(path, encoding='utf-8').read())
        except OSError:
            continue
        if data:
            conf.update(data)
    return conf


def protocol_order(repo_root: str = REPO_ROOT) -> List[str]:
    order = load_config(repo_root).get('protocol_order')
    if not isinstance(order, list) or not order:
        return list(DEFAULT_PROTOCOL_ORDER)
    return [str(x) for x in order]


def sort_key_factory(order: List[str]):
    """返回一个给代理字典用的排序键。"""
    rank = {p: i for i, p in enumerate(order)}

    def key(proxy):
        ptype = str((proxy or {}).get('type') or '').lower()
        return (rank.get(ptype, len(order)), ptype,
                str((proxy or {}).get('name') or ''))
    return key


def sort_proxies(proxies, order: List[str]):
    return sorted(proxies, key=sort_key_factory(order))
