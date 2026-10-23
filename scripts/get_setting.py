#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从仓库配置里取一个值，供 GitHub Actions 的 shell 使用。

用法：
    python3 scripts/get_setting.py filter.rounds 6
    python3 scripts/get_setting.py protocol_order

支持 'a.b' 形式的嵌套路径。取不到时打印第二个参数（默认值）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prefs import load_config  # noqa: E402


def get(path: str, default: str = '') -> str:
    val = load_config()
    for part in path.split('.'):
        if isinstance(val, dict) and part in val:
            val = val[part]
        else:
            return default
    if isinstance(val, (list, tuple)):
        return ','.join(str(v) for v in val)
    return str(val)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: get_setting.py <路径> [默认值]', file=sys.stderr)
        sys.exit(2)
    print(get(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ''))
