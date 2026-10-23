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
| `sources.list` / `fetch_config.yml` / `abpwhite.txt` | ✅ 每日自动覆盖 |
| `config.yml` | ❌ **不覆盖**，由本仓库自行维护 |
| `fetch.py` / `dynamic.py` | ❌ **不覆盖**，由本仓库自行维护 |

`config.yml` 不再自动覆盖，是为了能自由定制分流规则与健康检查参数。代价是**会错过上游的规则更新**，
所以 `sync.yml` 会额外产出一份**规则差异报告**（artifact `upstream-config-diff`），
列出上游新增/删除了哪些规则，人工按需合并即可。

本仓库自己的定制统一放在 `fetch_config.local.yml`（覆盖层，永不被同步覆盖），加载顺序：

```
fetch_config.yml（上游） → fetch_config.local.yml（本仓库） → local_fetch_config.yml（本地调试）
```

### 多源共识统计

`fetch.py` 会统计每个节点被**几个独立来源**同时收录，输出到 `consensus.csv` 并附在 Release 说明里。

这里的「独立来源」是**按仓库归并**后的计数 —— 同一个仓库的多个文件（同一份订阅的不同格式）
只算一个来源。否则 `sources.list` 里 `free9999` 的 3 条、`proxypool` 的 2 条会灌水，
把共识强度严重高估。当前 13 个订阅 URL 实际只对应 **8 个独立来源**。

被多个独立来源同时收录的节点，存活概率显著更高——这是目前唯一**零带宽、零主动探测**
的质量信号（本项目不做连通性探测，详见下方「安全须知」）。

### 实测结论：共识信号在当前源结构下不可用

2026-10-23 的实测数据（8 个独立来源、475 个服务器地址）：

```
节点哈希,1,510,98.1%      ← 绝大多数节点只被一个源收录
节点哈希,2,10,1.9%
服务器地址,1,463,97.5%    ← 换成 server:port 口径，几乎没变化
服务器地址,2,12,2.5%
```

而且每个源的**独占率高得离谱**：SS-Collector 230/238、shaoyouvip 73/77、TGParse 38/38。

**这 8 个源各自抓的是完全不同的节点池，彼此几乎零重叠**——所以「多源共识」这个信号
在当前源结构下根本不存在。统计代码保留了下来（`consensus.csv` / `sources.csv`），
但**不用于任何过滤**。

### 可达性探测（海外出口视角）

`probe.py` 对发布配置里的每个节点做 TCP 连接探测，对走 TLS 的协议追加一次 TLS 握手，
输出 `probe.csv` / `probe_summary.md` / `probe_summary.json`。

> ⚠️ **边界必须说清楚**：CI runner 在**美国**，探到的是「**海外可达**」，不等于「中国大陆可达」。
> 服务器关机的节点会被过滤掉（TCP 连不上），但「服务器活着、被墙或跨境拥塞」的节点
> 在这里依然显示为「活」——探针对此无能为力。
>
> 另外 `hysteria2` / `tuic` 走 QUIC（UDP），TCP 探测对它们无意义，会标为 `N/A`
> 并从统计中剔除，否则会凭空产生大量「死节点」。

每次探测都带三个**对照目标**（`1.1.1.1:443`、`8.8.8.8:443`、`github.com:443`），
用来区分「节点死了」和「runner 整体网络不通」——对照全挂时，本次结果不可信。

本项目在本地运行时探针基本无效：直连 TCP 出国会被墙（对照目标会全部超时）。
要得到有效数据必须在 CI 或具备出境能力的机器上跑。

### 国内探活（可选，NAS 方案）

> **默认不启用。** 上游 NoMoreWalls 本身不做任何节点质量判断，节点可用性由客户端的
> `fallback` / `url-test` 组实测决定。本仓库的探活只用来剔除**确凿已死**的节点
> 和明文开放代理，不需要为「国内优化」额外投入。
>
> 下面这套 NAS 方案是给愿意多花点力气的人准备的**可选路径**，没有定时调度，
> 不部署 NAS 就完全用不到。

GitHub **没有**中国大陆区域的 runner（探针自报出口恒为美国，见 `probe_summary.md`）。
但**家里的 NAS 反而是更好的探测点**：

| 维度 | GitHub runner（美国） | NAS（国内） |
| :- | :- | :- |
| 出口路径 | 境外机房 → 境外节点 | **中国住宅宽带 → 境外节点**，与目标用户一致 |
| IP 信誉 | Azure 机房段，部分节点直接拒绝 | **住宅 IP**，更可能被放行 |
| IPv6 | **没有**（实测所有 IPv6 节点返回 `Network is unreachable`） | 家宽通常有公网 IPv6（电信/联通给 /56） |

架构是**各司其职**，NAS 只需要跑一个 cron 任务：

```
GitHub Actions（美国）                     NAS（国内）
  抓节点 → 探活(US) → 裁剪 → 发布 output  ──▶  拉 output 分支
                                              跑 probe.py（直连，不走代理）
                                              写 probe_domestic.csv
  交叉比对 workflow  ◀── 推回 probe-domestic 分支
  产出 crosscheck.csv + list.meta.cn.yml
```

NAS 侧脚本：[`scripts/probe_domestic.sh`](scripts/probe_domestic.sh)
（只依赖 `git` + `python3`，不需要 Docker、不需要 GitHub Actions）

### 中美交叉表怎么读

**关键陷阱**：GFW 的 RST 注入，和「服务端端口没开」在客户端看来完全一样，都是
`Connection reset by peer`。所以国内侧的失败**不能**用来判定节点已死。

| | 国内可用 | 国内不可用 |
| :- | :-: | :-: |
| **美国可用** | ✅ 真正可用 | ⚠️ 疑似被墙 → **应剔除**（美国版留下的坑） |
| **美国不可用** | 🔥 被美国误杀 → **应保留** | ❌ 真死 → 剔除 |

所以**裁剪判据继续只用美国侧结果**（那边没有 GFW 干扰，`refused` 才是可信的"已死"）；
国内侧的价值在于识别「被墙」和「被美国误杀」。

脚本：[`scripts/crosscheck.py`](scripts/crosscheck.py)，
工作流：[`.github/workflows/crosscheck.yml`](.github/workflows/crosscheck.yml)（仅手动触发）。

### 假节点过滤的一处补漏

国内免费节点社区会植入指向 `127.0.0.53`（systemd-resolved 的 DNS stub）的**哨兵节点**，
节点名固定为「防范境外势力渗透」，用来检测客户端是否被 DNS 污染。
上游的 `FAKE_IPS` 只列了 `127.0.0.1` 这一个具体地址，`127.0.0.53` 漏网——
实测每次有约 10 个这类节点混进发布的订阅。

本仓库把保留地址改为按网段判定（`127.0.0.0/8`、`0.0.0.0/8`、`169.254.0.0/16`），
这类哨兵节点不再进入任何输出。

### 客户端健康检查调优

上游的 `config.yml` 里，`♻ 自动选择`（fallback）和 `🔰 延迟最低`（url-test）两个组
都是 `interval: 300` + `url: https://www.google.com/`，且 `include-all: true`
（即探测全部节点）。现在有 369 个节点，客户端启动时会并发探测全部 —— 这是开机卡顿的主因。

本仓库的调优（`config.yml` 已改为自行维护，不会被上游同步覆盖）：

| 项 | 上游 | 现在 | 理由 |
| :- | :- | :- | :- |
| `url` | `https://www.google.com/` | `https://www.gstatic.com/generate_204` | 后者返回 204 空响应，前者要传整页 HTML |
| `interval` | 300 | 600 | 探测频率减半 |
| `timeout` | 未设 | 5000 | 单次探测超时上限（毫秒） |
| `lazy` | 未设 | `true` | **只在代理组真正被使用时才探测**，启动时不再并发探全部节点 |
| `max-failed-times` | 未设 | 3 | 连续失败 3 次后不再探测该节点 |

最后两项是关键：国内网络下大量节点是「**被墙**」而不是「关闭」，这类节点会一直失败；
不设上限就会持续消耗探测资源。

> `lazy` 与 `max-failed-times` 是 **Mihomo（Clash Meta）** 的字段。
> 原版 Clash 不认识这两个字段会直接忽略，不影响使用。

### 按探测结论裁剪

`prune.py` 读入 `probe.csv`，对 Clash 配置做**保守**裁剪。只剔除三类「确凿」的问题：

| 剔除条件 | 依据 |
| :- | :- |
| 明文 HTTP / SOCKS 代理 | 公开开放的代理服务器（实测节点里有一批 `US_speednode_XXXX`，全部指向 `138.199.35.x:9002`），代理方可见明文流量，且本就不是「免费节点」 |
| TCP 连接被**拒绝** | 端口无人监听，确凿已死 |
| TLS 握手被对端**明确拒绝** | `SSLV3_ALERT_HANDSHAKE_FAILURE` / `WRONG_VERSION_NUMBER` 等，该端口跑的不是预期的 TLS 服务 |

以下情况**一律保留**：

- **TCP 超时** —— 可能是防火墙丢包，也可能服务器只放行中国大陆 IP，对国内用户仍然可用。
  仅凭美国出口的超时无法判定其已死，误杀风险高。
- **QUIC / UDP 协议** —— `hysteria2` / `tuic` 无法用 TCP 探测，从未被探测过。
- **探测端自身的网络能力问题** —— 这类错误反映的是探测端或链路侧，不是节点的问题：
  | 错误 | 含义 |
  | :- | :- |
  | `Network is unreachable` / `No route to host` | 探测端没有该协议族的路由 |
  | `Name or service not known` | 探测端 DNS 解析失败 |

  > 实测踩过的坑：**GitHub 的 runner 没有 IPv6 出口**，所有 IPv6 节点都报
  > `Network is unreachable`。若把它当成「节点已死」，会一次性误杀全部 IPv6 节点
  > —— 而 IPv6 节点对有 IPv6 的国内用户完全可用。

判据只有一条：**路径通、但服务不在**（对端主动回 RST，即 `Connection refused`
/ `Connection reset by peer`）才算确凿已死。

未裁剪版本以 `list.meta.full.yml` / `list.yml.full.yml` 一并发布，便于对照；
每个文件被剔除的节点及原因记录在 `pruned_*.csv` 里。

> 裁剪的前提是「探测结论可信」。对照目标全挂时（runner 网络异常），
> 裁剪结果同样不可信——`probe_summary.md` 里的对照表就是为此准备的。

### 配置一致性校验（硬门禁）

裁剪节点后，`proxy-groups` 里指向被剔除节点的引用必须同步清理。
**Mihomo / Clash 遇到 proxy-group 引用了不存在的节点时，会直接报
`proxy <name> not found` 并拒绝加载整个配置** —— 用户在客户端里看到的就是
「订阅无效」，而在 YAML 上完全看不出来。

`scripts/validate_config.py` 会在构建时校验发布的所有配置，检查项：

1. `proxy-groups` 里的每个引用都能解析（节点 / 其他组 / 内置策略）
2. 组名、节点名不重复
3. 每个节点有 name / type / server / port，且 port 合法
4. `rules` 里引用的策略组都存在
5. `url-test` / `fallback` 组必须有 `url`

**校验不过就中止构建，绝不发布坏配置。**

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
| `local_fetch_config.yml` | 覆盖 `fetch_config.yml` 的配置（优先级最高） |

### 跑测试

```bash
python tests/test_consensus.py
```

单元测试不联网，覆盖源身份归并、共识统计与直方图输出。

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
