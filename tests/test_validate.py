#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/validate_config.py 的单元测试。"""
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
os.chdir(REPO_ROOT)

from validate_config import validate

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-56s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-56s got=%r want=%r" % (name, got, want))


def write(tmp, text, name='c.yml'):
    p = os.path.join(tmp, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    return p


print("=== 1. 正常配置 ===")
with tempfile.TemporaryDirectory() as td:
    p = write(td, """
proxies:
  - name: a
    type: vless
    server: 1.2.3.4
    port: 443
  - name: b
    type: ss
    server: 5.6.7.8
    port: 8443
proxy-groups:
  - name: ♻ 自动选择
    type: fallback
    url: https://www.gstatic.com/generate_204
    proxies: [a, b]
  - name: 🚀 选择代理
    type: select
    proxies: [♻ 自动选择, DIRECT]
rules:
  - DOMAIN-SUFFIX,example.com,♻ 自动选择
  - MATCH,DIRECT
""")
    check("无错误", validate(p), [])

print()
print("=== 2. proxy-group 引用不存在的节点（核心回归）===")
with tempfile.TemporaryDirectory() as td:
    p = write(td, """
proxies:
  - name: a
    type: vless
    server: 1.2.3.4
    port: 443
proxy-groups:
  - name: ♻ 自动选择
    type: fallback
    url: https://www.gstatic.com/generate_204
    proxies: [a, c]
""")
    errs = validate(p)
    check("抓到了悬空引用", len(errs), 1)
    check("错误信息含节点名", 'c' in errs[0], True)

print()
print("=== 3. 其它一致性问题 ===")
with tempfile.TemporaryDirectory() as td:
    p = write(td, """
proxies:
  - name: a
    type: vless
    server: 1.2.3.4
    port: 99999
  - name: a
    type: ss
    server: 5.6.7.8
    port: 443
proxy-groups:
  - name: g1
    type: url-test
    proxies: [a]
  - name: g1
    type: select
    proxies: [a]
rules:
  - DOMAIN-SUFFIX,x.com,不存在组
""")
    errs = validate(p)
    joined = ' | '.join(errs)
    check("端口非法被报出", 'port 非法' in joined, True)
    check("节点名重复被报出", '节点名重复' in joined, True)
    check("组名重复被报出", '组名重复' in joined, True)
    check("url-test 缺 url 被报出", '缺少 url' in joined, True)
    check("规则引用不存在的策略被报出", '不存在的策略' in joined, True)

print()
print("=== 4. 内置策略与组名引用是合法的 ===")
with tempfile.TemporaryDirectory() as td:
    p = write(td, """
proxies:
  - name: a
    type: vless
    server: 1.2.3.4
    port: 443
proxy-groups:
  - name: g1
    type: select
    proxies: [DIRECT, REJECT, PASS, COMPATIBLE]
  - name: g2
    type: select
    proxies: [g1]
""")
    check("内置策略与组名引用不算错", validate(p), [])

print()
print("=== Mihomo 专有字段检查 ===")
import tempfile, yaml as _y
from validate_config import validate, META_ONLY_GROUP_FIELDS

with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, 'c.yml')
    with open(p, 'w', encoding='utf-8') as f:
        f.write("proxies:\n"
                "- name: a\n  type: vmess\n  server: 1.2.3.4\n  port: 443\n"
                "proxy-groups:\n"
                "- name: g1\n  type: select\n  proxies: [a]\n")
    check("干净配置无问题", validate(p, False, True), [])

    with open(p, 'w', encoding='utf-8') as f:
        f.write("proxies:\n"
                "- name: a\n  type: vmess\n  server: 1.2.3.4\n  port: 443\n"
                "proxy-groups:\n"
                "- name: g1\n  type: url-test\n  url: https://x/\n"
                "  interval: 600\n  tolerance: 20\n  lazy: true\n"
                "  max-failed-times: 3\n  proxies: [a]\n")
    errs = validate(p, False, True)
    check("检出 lazy", any('lazy' in e for e in errs), True)
    check("检出 max-failed-times", any('max-failed-times' in e for e in errs), True)
    check("tolerance 不算 Mihomo 专有", any('tolerance' in e for e in errs), False)
    check("不加开关则不报", validate(p, False, False), [])

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
