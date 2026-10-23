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

# 筛选参数默认值
DEFAULT_FILTER = {
    # 参与判定的最近 N 轮探测历史
    'rounds': 6,
    # 至少出现这么多轮才做判定；只出现一轮的判为「未定」，保守保留
    'min_rounds': 2,
    # 存活轮数占比达到多少算「跨轮全活」。1.0 = 每一轮都活
    'alive_ratio': 1.0,
    # 国内延迟上限（毫秒）。超过则从「大陆可用」里剔除。0 = 不限制
    'max_latency_ms': 0,
    # 美国侧延迟上限（毫秒）。用于「全量」和「美国侧筛选」两份订阅。
    # 0 = 不限制
    'max_latency_ms_us': 0,
}


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


def filter_settings(repo_root: str = REPO_ROOT) -> Dict[str, Any]:
    """筛选参数。CLI 参数没给时用这里的值。"""
    out = dict(DEFAULT_FILTER)
    f = load_config(repo_root).get('filter')
    if isinstance(f, dict):
        for k in out:
            if k in f:
                out[k] = f[k]
    try:
        out['min_rounds'] = int(out['min_rounds'])
    except (TypeError, ValueError):
        out['min_rounds'] = DEFAULT_FILTER['min_rounds']
    try:
        out['alive_ratio'] = float(out['alive_ratio'])
    except (TypeError, ValueError):
        out['alive_ratio'] = DEFAULT_FILTER['alive_ratio']
    try:
        out['rounds'] = int(out['rounds'])
    except (TypeError, ValueError):
        out['rounds'] = DEFAULT_FILTER['rounds']
    try:
        out['max_latency_ms'] = int(out['max_latency_ms'])
    except (TypeError, ValueError):
        out['max_latency_ms'] = DEFAULT_FILTER['max_latency_ms']
    try:
        out['max_latency_ms_us'] = int(out['max_latency_ms_us'])
    except (TypeError, ValueError):
        out['max_latency_ms_us'] = DEFAULT_FILTER['max_latency_ms_us']
    return out


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
