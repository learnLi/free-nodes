#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""假节点过滤的单元测试（不联网）。"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from fetch import Node, FAKE_NETWORKS

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-52s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-52s got=%r want=%r" % (name, got, want))


def mk(server, port=443, name="x"):
    return Node({"name": name, "type": "vmess", "server": server, "port": port})


print("=== 保留地址网段 ===")
check("FAKE_NETWORKS 覆盖 127.0.0.0/8", any(
    str(n) == '127.0.0.0/8' for n in FAKE_NETWORKS), True)

print()
print("=== isfake 判定 ===")
# 关键回归：127.0.0.53 是 systemd-resolved 的 DNS stub，
# 国内免费节点社区会植入指向它的「哨兵节点」，原先被漏掉
check("127.0.0.53 判为假节点", mk("127.0.0.53").isfake, True)
check("127.0.0.1 判为假节点", mk("127.0.0.1").isfake, True)
check("127.1.2.3 判为假节点", mk("127.1.2.3").isfake, True)
check("0.0.0.0 判为假节点", mk("0.0.0.0").isfake, True)
check("8.8.8.8 判为假节点", mk("8.8.8.8").isfake, True)
check("114.114.114.114 判为假节点", mk("114.114.114.114").isfake, True)
check("169.254.1.1 判为假节点（链路本地）", mk("169.254.1.1").isfake, True)
# RFC 5737 文档保留网段：一些订阅拿它们当占位服务器
check("192.0.2.1 判为假节点（TEST-NET-1）", mk("192.0.2.1").isfake, True)
check("192.0.2.1:1 占位节点被剔除", mk("192.0.2.1", 1).isfake, True)
check("198.51.100.7 判为假节点（TEST-NET-2）", mk("198.51.100.7").isfake, True)
check("203.0.113.9 判为假节点（TEST-NET-3）", mk("203.0.113.9").isfake, True)
check("普通公网 IP 不判假", mk("1.2.3.4").isfake, False)
check("域名服务器不判假", mk("example.com").isfake, False)
check("IPv6 公网地址不判假", mk("2001:db8::1").isfake, False)

print()
print("=== 假节点不进 Clash 输出 ===")
n = mk("127.0.0.53")
check("supports_clash 拒绝假节点", n.supports_clash(), False)
check("supports_meta 拒绝假节点", n.supports_meta(), False)
check("supports_ray 拒绝假节点", n.supports_ray(), False)

print()
print("=== 正常节点仍可通过 ===")
n = mk("1.2.3.4")
check("正常节点 supports_clash", n.supports_clash(), True)

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
