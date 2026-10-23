#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dynamic.py 的单元测试（用假 session，不联网）。"""
import os
import sys
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-56s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-56s got=%r want=%r" % (name, got, want))


# ---- 假 session ----
class FakeResp:
    def __init__(self, code, size):
        self.status_code = code
        self.content = b'x' * size


class FakeSession:
    """按「文件名里的日期」决定返回什么，模拟 clashfree 的空文件规律。"""

    def __init__(self, empty_days=(), missing_days=()):
        self.empty_days = set(empty_days)
        self.missing_days = set(missing_days)
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        day = url[-12:-4]  # clashYYYYMMDD.yml -> YYYYMMDD
        if day in self.missing_days:
            return FakeResp(404, 0)
        if day in self.empty_days:
            return FakeResp(200, 0)      # 存在但 0 字节
        return FakeResp(200, 690000)


import dynamic
from fetch import session as real_session


def run(fake):
    dynamic.session = fake
    try:
        return dynamic.clashfree()
    finally:
        dynamic.session = real_session


print("=== 1. 正常：当天就有非空文件 ===")
f = FakeSession()
u = run(f)
check("返回当天日期的 URL", u is not None and 'clash' in u and u.endswith('.yml'), True)
check("只请求了 1 次", len(f.requested), 1)

print()
print("=== 2. 当天与昨天为空，��溯到前天 ===")
import datetime
d = datetime.datetime.now()
today = d.strftime('%Y%m%d')
yest = (d - datetime.timedelta(days=1)).strftime('%Y%m%d')
f = FakeSession(empty_days=(today, yest))
u = run(f)
check("回溯成功", u is not None, True)
check("命中前天", today not in u and yest not in u, True)
check("请求了 3 次", len(f.requested), 3)

print()
print("=== 3. 文件不存在（404）也要回溯 ===")
f = FakeSession(missing_days=(today,))
u = run(f)
check("回溯成功", u is not None, True)
check("请求了 2 次", len(f.requested), 2)

print()
print("=== 4. 连续 8 天都空 -> 返回 None ===")
days = [(d - datetime.timedelta(days=i)).strftime('%Y%m%d') for i in range(8)]
f = FakeSession(empty_days=tuple(days))
u = run(f)
check("返回 None", u, None)
check("最多请求 8 次", len(f.requested), 8)

print()
print("=== 5. AUTOURLS 注册 ===")
check("clashfree 已注册到 AUTOURLS", dynamic.clashfree in dynamic.AUTOURLS, True)
check("AUTOURLS 长度", len(dynamic.AUTOURLS), 1)

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
