#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py 新增逻辑的本地单元测试（不联网）。

覆盖：
  1. source_identity() —— 订阅 URL 归并到「独立来源」粒度
  2. consensus_of()    —— 节点 -> 独立来源集合
  3. write_consensus() —— 直方图输出
"""
import os
import sys
import io
import csv
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# fetch.py 在导入时会读 fetch_config.yml / fetch_config.local.yml，
# 需要在仓库根目录下运行
os.chdir(REPO_ROOT)

from fetch import source_identity, consensus_of, write_consensus, Node

FAILED = []


def check(name, got, want):
    if got == want:
        print("  OK   %-52s %r" % (name, got))
    else:
        FAILED.append(name)
        print("  FAIL %-52s got=%r want=%r" % (name, got, want))


print("=== 1. source_identity() ===")
# 真实 sources.list 里的 13 个 URL
URLS = [
    "https://gist.githubusercontent.com/peasoft/40b87245630092f30cc98af61190b4e2/raw/",
    "https://gitlab.com/free9999/ipupdate/-/raw/master/backup/img/1/2/ipp/clash.meta2/1/config.yaml?ref_type=heads",
    "https://gitlab.com/free9999/ipupdate/-/raw/master/backup/img/1/2/ipp/clash.meta2/3/config.yaml?ref_type=heads",
    "https://gitlab.com/free9999/ipupdate/-/raw/master/backup/img/1/2/ipp/clash.meta2/4/config.yaml?ref_type=heads",
    "https://raw.githubusercontent.com/Surfboardv2ray/TGParse/main/python/hy2",
    "https://raw.githubusercontent.com/Surfboardv2ray/TGParse/main/python/hysteria2",
    "https://raw.githubusercontent.com/lagzian/SS-Collector/main/configs/subscription-all.b64",
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/clash",
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub",
    "https://raw.githubusercontent.com/shaoyouvip/free/refs/heads/main/all.yaml",
    "https://raw.githubusercontent.com/snakem982/proxypool/main/source/clash-meta-2.yaml",
    "https://raw.githubusercontent.com/snakem982/proxypool/main/source/v2ray-2.txt",
    "https://raw.githubusercontent.com/zhangkaiitugithub/passcro/main/speednodes.yaml",
]
idents = [source_identity(u) for u in URLS]
for u, i in zip(URLS, idents):
    print("  %-70s -> %s" % (u[:70], i))

check("13 个 URL 归并后独立来源数", len(set(idents)), 8)
check("free9999 三条归为同一来源",
      len({source_identity(u) for u in URLS[1:4]}), 1)
check("TGParse 两条归为同一来源",
      len({source_identity(u) for u in URLS[4:6]}), 1)
check("freenode 两条归为同一来源",
      len({source_identity(u) for u in URLS[7:9]}), 1)
check("proxypool 两条归为同一来源",
      len({source_identity(u) for u in URLS[10:12]}), 1)
check("不同仓库不合并",
      source_identity(URLS[6]) != source_identity(URLS[9]), True)
check("raw / github 两种域名指向同一仓库",
      source_identity("https://raw.githubusercontent.com/a/b/main/x")
      == source_identity("https://github.com/a/b/blob/main/x"), True)
check("query 与 fragment 不影响归并",
      source_identity("https://raw.githubusercontent.com/a/b/main/x.yaml?ref=heads#max=100"),
      "github:a/b")
check("dynamic 源保留原样",
      source_identity("dynamic://somefunc"), "dynamic://somefunc")
check("未知域名回退为完整 URL",
      source_identity("https://example.com/foo/bar"), "https://example.com/foo/bar")

print()
print("=== 2. consensus_of() ===")
# 构造：节点 A 出现在源 0,1,2；节点 B 只在源 3
# 源身份：0/1 同属 github:x/y（一个来源），2 属 github:p/q，3 属 github:r/s
source_ids = {
    0: "github:x/y",
    1: "github:x/y",
    2: "github:p/q",
    3: "github:r/s",
}
used = {
    111: {0: "n1", 1: "n1b", 2: "n1c"},
    222: {3: "n2"},
}
cons = consensus_of(used, source_ids)
check("节点 A 的独立来源数（0/1 合并）", len(cons[111]), 2)
check("节点 B 的独立来源数", len(cons[222]), 1)
check("同仓库的两个 URL 只算一次", 0 in cons[111] and 1 in cons[111], True)

print()
print("=== 3. write_consensus() ===")


def mk_node(t, server="1.2.3.4", port=443):
    return Node({"name": "x", "type": t, "server": server, "port": port})


cwd = os.getcwd()

# --- 用例 A：三个节点地址各不相同 ---
merged = {
    1: mk_node("vmess", "1.1.1.1"),
    2: mk_node("vless", "2.2.2.2"),
    3: mk_node("trojan", "3.3.3.3"),
}
used2 = {
    1: {0: "a", 1: "b", 2: "c"},   # 节点 1 出现在 3 个不同身份的来源
    2: {0: "a"},                    # 节点 2 只在 1 个来源
    3: {0: "a", 2: "c"},            # 节点 3 在 2 个来源
}
sids = {0: "github:x/y", 1: "github:p/q", 2: "github:r/s"}
urls = ["https://example.invalid/0", "https://example.invalid/1",
        "https://example.invalid/2"]

with tempfile.TemporaryDirectory() as td:
    os.chdir(td)
    try:
        hist, ident_count = write_consensus(merged, used2, sids, urls)
        check("独立来源数", ident_count, 3)
        check("哈希级直方图 {3:1, 1:1, 2:1}", hist, {3: 1, 1: 1, 2: 1})
        rows = list(csv.reader(open("consensus.csv", encoding="utf-8")))
        check("CSV 表头", rows[0], ["层级", "独立来源数", "节点数", "占比"])
        check("CSV 行数（表头+3哈希级+3地址级）", len(rows), 7)
        check("哈希级首行", rows[1], ["节点哈希", "1", "1", "33.3%"])
        check("地址级首行", rows[4], ["服务器地址", "1", "1", "33.3%"])
        srows = list(csv.reader(open("sources.csv", encoding="utf-8")))
        check("sources.csv 表头", srows[0],
              ["源序号", "独立来源", "节点数", "地址数", "独占地址数", "URL"])
        check("sources.csv 行数（表头+3源）", len(srows), 4)
        # 源 0 有 3 个地址：1.1.1.1（被 identity1/2 共有）、3.3.3.3（被 identity2 共有）、
        # 2.2.2.2（只有源 0 有）-> 独占 1 个
        check("源 0 独占地址数", srows[1][4], "1")
        check("源 0 地址数", srows[1][3], "3")
        check("源 0 节点数", srows[1][2], "3")
        check("源 0 的 URL", srows[1][5], urls[0])
    finally:
        os.chdir(cwd)

# --- 用例 B：两个哈希指向同一地址（去重口径过严被拆开） ---
merged_b = {
    1: mk_node("vmess", "9.9.9.9", 443),
    2: mk_node("vless", "9.9.9.9", 443),
}
used_b = {1: {0: "a"}, 2: {1: "b"}}
with tempfile.TemporaryDirectory() as td:
    os.chdir(td)
    try:
        hist, ident_count = write_consensus(merged_b, used_b,
                                            {0: "github:a/b", 1: "github:c/d"},
                                            ["u0", "u1"])
        check("同一地址拆成 2 个哈希时，哈希级计数", hist, {1: 2})
        rows = list(csv.reader(open("consensus.csv", encoding="utf-8")))
        addr_rows = [r for r in rows[1:] if r[0] == "服务器地址"]
        check("地址级合并后只剩 1 个地址", len(addr_rows), 1)
        check("地址级计数", addr_rows[0][2], "1")
    finally:
        os.chdir(cwd)

print()
if FAILED:
    print("FAILED: %d 项 -> %s" % (len(FAILED), FAILED))
    sys.exit(1)
print("全部通过")
