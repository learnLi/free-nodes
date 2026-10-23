#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fetch.py 的订阅解析测试（不联网）。"""
import base64
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from fetch import Source, _clean_node_lines  # noqa: E402

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-56s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-56s got=%r want=%r" % (name, got, want))


URI = ('vmess://eyJhZGQiOiIxLjIuMy40IiwicG9ydCI6IjQ0MyJ9',
       'vless://uuid@1.2.3.4:443?type=ws#n',
       'trojan://pw@5.6.7.8:443#n')

print("=== 1. 过滤订阅头部注释行 ===")
raw = ("#profile-title: base64:4pm+77iPIGIybi5pci92\n"
       "#subscription-userinfo: upload=1; download=1\n"
       "#profile-web-page-url: https://github.com/x/y\n"
       + "\n".join(URI) + "\n")
check("注释行被过滤", len(_clean_node_lines(raw)), 3)
check("保留的全是节点", all(x.startswith(('vmess://', 'vless://', 'trojan://'))
                          for x in _clean_node_lines(raw)), True)

print()
print("=== 2. base64 订阅 ===")
b64 = base64.b64encode(raw.encode()).decode()
s = Source('x')
s.content = b64
s.parse()
check("base64 订阅解析出 3 个节点", len(s.sub or []), 3)
check("base64 订阅无残留注释", all(not x.startswith('#') for x in (s.sub or [])), True)

print()
print("=== 3. 明文 URI 列表 ===")
s2 = Source('x')
s2.content = "\n".join(URI) + "\n"
s2.parse()
check("明文列表解析出 3 个节点", len(s2.sub or []), 3)

print()
print("=== 4. Clash YAML ===")
s3 = Source('x')
s3.content = ("proxies:\n"
               "- name: a\n  type: vmess\n  server: 1.2.3.4\n  port: 443\n"
               "- name: b\n  type: trojan\n  server: 5.6.7.8\n  port: 443\n")
s3.parse()
check("Clash YAML 解析出 2 个节点", len(s3.sub or []), 2)

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
