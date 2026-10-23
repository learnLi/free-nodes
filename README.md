# free-nodes

> 自动抓取并合并互联网上公开的免费节点，按格式输出为 V2Ray / Clash / Clash Meta 订阅。

抓取、合并、去重、分类、分流规则整理全流程在 GitHub Actions 上跑，产物通过 **GitHub Releases** 与 **output 分支** 双通道分发，仓库本身不保存生成物。

---

## 订阅链接

**主通道（GitHub Releases）** — 稳定 URL，无需跟随分支：

| 客户端 | 链接 |
| :- | :- |
| Clash Meta | `https://github.com/learnLi/free-nodes/releases/latest/download/list.meta.yml` |
| Clash 原版 | `https://github.com/learnLi/free-nodes/releases/latest/download/list.yml` |
| V2Ray / 通用 | `https://github.com/learnLi/free-nodes/releases/latest/download/list.txt` |
| 明文（查看用） | `https://github.com/learnLi/free-nodes/releases/latest/download/list_raw.txt` |

**备用通道（output 分支）** — 走 raw.githubusercontent / jsDelivr：

```
https://raw.githubusercontent.com/learnLi/free-nodes/output/list.meta.yml
https://cdn.jsdelivr.net/gh/learnLi/free-nodes@output/list.meta.yml
```

**配置片段（rule-providers / proxy-providers）** — 单独的 Release，路径保持 `snippets/` 目录语义：

| 用途 | 链接 |
| :- | :- |
| 节点列表（Meta） | `https://github.com/learnLi/free-nodes/releases/download/snippets/nodes.meta.yml` |
| 节点列表（原版 Clash） | `https://github.com/learnLi/free-nodes/releases/download/snippets/nodes.yml` |
| 广告拦截 | `https://github.com/learnLi/free-nodes/releases/download/snippets/adblock.yml` |
| 需代理域名 | `https://github.com/learnLi/free-nodes/releases/download/snippets/proxy.yml` |
| 直连域名 | `https://github.com/learnLi/free-nodes/releases/download/snippets/direct.yml` |
| 锁区域名 | `https://github.com/learnLi/free-nodes/releases/download/snippets/region.yml` |

> Release 的资产名不允许包含 `/`，因此顶层订阅与配置片段分装在两个 Release（`latest` / `snippets`）中。
> `snippets` 被标记为**预发布**——这是必要的：GitHub 的 `releases/latest` 取「最近发布的非预发布」，
> 若不标记，片段 Release 会顶掉订阅 Release，导致 `/releases/latest/download/list.*` 全部 404。
> 工作流内已加入自检断言，指向错误会直接让构建失败。

> ⚠️ **Clash 原版与 Clash Meta 的节点数差异很大**。原版 Clash 不支持 vless / hysteria2 / tuic，
> 拿到的节点通常只有 Meta 的 1/5 左右。请优先使用 Meta 内核（Clash Verge Rev / Mihomo Party / FlClash 等）。

---

## 使用方法

1. 从上表复制对应链接，在客户端里添加为订阅。
2. Clash Meta 用户把订阅类型选为 **Meta**。
3. 导入后建议：
   - `🐟 漏网之鱼` 保持 `DIRECT`
   - 如果遇到跳转反诈中心，把 `❓ 疑似国内` 切换到 `🚀 选择代理`
   - 想自动选快节点，用 `♻ 自动选择` / `🔰 延迟最低` 组（依赖客户端自身的 health-check）

> **关于节点可用性**：本项目**不做连通性探测**，所有节点都是静态收集后原样分发。
> 公开免费节点存活率极低（通常几天内掉到 20% 以下），出现大量不可用节点属正常现象。

---

## 架构

```
sources.list (订阅源清单)  ──┐
dynamic.py   (动态抓取函数) ──┤
                              ↓
                         fetch.py  (单文件核心)
                              ↓
        解析 → 归一化 → 去重合并 → 静态过滤 → 按名称分地区
                              ↓
   ┌──────────────┬───────────────────┬────────────────────┐
list.txt        list.yml             list.meta.yml        snippets/*.yml
(V2Ray Base64)  (Clash 原版)          (Clash Meta)       (配置片段)
```

| 文件 | 作用 |
| :- | :- |
| `fetch.py` | 核心逻辑：协议解析、去重、分类、规则生成、产物写出 |
| `dynamic.py` | 动态订阅源（需要运行时抓取网页才能拿到 URL 的源） |
| `sources.list` | 订阅源清单，支持 `!` `*` `+date` `#max=N&ignore=xxx` 等指令 |
| `config.yml` | Clash 基础配置与分流规则（约 2000 条） |
| `fetch_config.yml` | 抓取行为开关：名称脱敏、地区分类词表、广告规则源等 |
| `abpwhite.txt` | 广告规则白名单（本地副本） |
| `snippets/example.yml` | `snippets/rules_online.yml` 的模板 |

### 产物如何分流

| 产物 | 覆盖范围 |
| :- | :- |
| `list.meta.yml` | vmess / ss / ssr / trojan / vless / hysteria2 / tuic |
| `list.yml` | vmess / ss / ssr / trojan（原版 Clash 能力有限） |
| `list.txt` | 上述全部 + http / https / socks5 |

### 静态「过滤」都做了什么

这些**都不是**连通性测试，全部基于节点字段本身：

- **假节点剔除** — 服务器地址是 `8.8.8.8` / `127.0.0.1` / `0.0.0.0` 等占位符、域名是 `.google.com` 之类的假域名、端口 < 20
- **SNI 修正** — SNI 含 `google.com` 的节点改为 `www.bing.com`（这类服务端并非面向国内设计，用 Google SNI 容易被污染）
- **协议兼容性判定** — cipher 是否在目标客户端白名单内、SSR 的 obfs/protocol 是否兼容、reality 的 public-key 长度是否合法
- **地区归类** — 纯**按节点名称关键词**匹配（`香港` / `🇭🇰` → HK），与节点实际位置无关，仅供快速筛选

---

## 上游同步策略

核心代码与规则集源自 [peasoft/NoMoreWalls](https://github.com/peasoft/NoMoreWalls)（MIT 之外的**反 996 许可证**）。

`Sync upstream config` 工作流每天自动同步**配置类**文件：

| 文件 | 是否跟随上游同步 |
| :- | :- |
| `sources.list` / `config.yml` / `fetch_config.yml` / `abpwhite.txt` | ✅ 每日自动覆盖 |
| `fetch.py` / `dynamic.py` | ❌ **不覆盖**，由本仓库自行维护 |

这样既能持续获得上游的规则更新，又不会把本地对代码的改动冲掉。若要修改规则集，请直接改 `config.yml`（下次同步会覆盖，**建议提交到本仓库的规则定制分支，或在 `sync.yml` 中改为 patch 方式合并**）。

---

## 本地开发

```bash
git clone git@github.com:learnLi/free-nodes.git --depth=1
cd free-nodes
pip install -r requirements.txt

# 中国大陆无代理时：先建空的 local_proxy.conf 让脚本走 ghproxy
touch local_proxy.conf

python fetch.py
```

有代理的话，在 `local_proxy.conf` 里写上代理地址（如 `http://127.0.0.1:7890/`），脚本会自动使用它。

调试开关（创建对应文件即可生效，**勿提交**）：

| 文件 | 作用 |
| :- | :- |
| `local_NO_NODES` | 不抓节点，只跑规则部分 |
| `local_NO_DYNAMIC` | 不抓动态节点 |
| `local_NO_ADBLOCK` | 不抓广告规则 |
| `local_fetch_config.yml` | 覆盖 `fetch_config.yml` 的配置 |

### 目录约定

生成物（`list*`、`snippets/` 下除 `example.yml` 外）**不进 git**，由 CI 打包上传。需要本地复现时请自行 `git checkout` 或从 Release 下载。

---

## 工作流

| 工作流 | 触发 | 作用 |
| :- | :- | :- |
| `Fetch` | 每 3 小时（`17 */3 * * *`）+ 手动 | 抓取 → 打包 → 上传 Release → 强制推送 `output` 分支 |
| `Sync upstream config` | 每天 03:23 + 手动 | 同步上游配置类文件 |

两个工作流都配置了 `concurrency` 与 `timeout-minutes`，避免任务撞车或挂死。

---

## 安全须知

- 本项目**不审计**来自第三方的节点内容。免费节点由陌生人自建，流量经过其服务器，**请勿用于敏感通信**。
- 订阅内容来自多个第三方仓库，其中任何一方被投毒，都可能向你的客户端注入指向攻击者服务器的节点。
- 广告拦截规则同样来自远程列表，理论上可被用于屏蔽正常站点。
- 请自行评估风险。本仓库仅供学习交流使用。

---

## 许可证

[反 996 许可证 v1.0](LICENSE.md)（继承自上游）。上游项目的许可证明确禁止实行 996 工作制的公司使用，请知悉。
