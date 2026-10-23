# free-nodes

> 自动抓取并合并互联网上公开的免费节点，**用中美双出口的多轮探测**筛出真正
> 能用的节点，输出 Clash Meta / Clash / V2Ray 订阅。

核心代码与规则集源自 [peasoft/NoMoreWalls](https://github.com/peasoft/NoMoreWalls)（反 996 许可证）。
上游只做「抓取 + 合并 + 按名称分类」，**不判断节点是否可用**；本项目加了一整条
**探测 → 筛选 → 分发**的流水线。

---

## 订阅链接

### 先看你用的是什么内核

**不同内核要用不同的订阅文件** —— 用错了会加载失败或功能缺失。

| 你的客户端 | 内核 | 大陆可用（推荐） | 全量 |
| :- | :- | :- | :- |
| Clash Verge Rev / Mihomo Party / FlClash / Clash Meta for Android | **Clash Meta (Mihomo)** | **`list.meta.cn.yml`** | `list.meta.yml` |
| 老版 Clash for Windows / Clash（经典内核） | **原版 Clash** | **`list.cn.yml`** | `list.yml` |
| v2rayN / v2rayNG / Nekoray / sing-box | — | `list.txt` | — |

> **为什么原版 Clash 要单独一份**：`list.meta.cn.yml` 里含 `flow`、`grpc-opts`、
> `obfs`、`client-fingerprint`、`xhttp-opts` 等 **Meta 专有字段**，
> 原版 Clash 内核不认识，导入会直接报配置错误。
> `list.cn.yml` 是同样一批节点、同样经过中美判定与延迟筛选，
> 但只含老内核认识的字段（`alpn` / `alterId` / `cipher` / `network` / …）。
>
> 两份的节点数不同是正常的：原版 Clash 不支持 vless / hysteria2 / tuic，
> 它的候选池本来就小一圈（但判定用的是同一批地址，结论一致）。

### 全部订阅

| 订阅 | 节点数 | 用途 |
| :- | :-: | :- |
| **`list.meta.cn.yml`** | ~120 | **Clash Meta，大陆可用（推荐）** —— 中美多轮联合判定 + 延迟上限 + 协议偏好排序 |
| **`list.cn.yml`** | ~40 | **原版 Clash，大陆可用** |
| `list.meta.yml` | ~370 | Clash Meta，全量（美国侧视角筛的）|
| `list.meta.us.yml` | ~290 | Clash Meta，美国侧多轮筛选 |
| `list.yml` | ~110 | 原版 Clash，全量 |
| `list.txt` | ~450 条 | V2Ray / 通用（Base64）|
| `list_raw.txt` | ~450 行 | V2Ray 明文（查看用）|

**主通道（GitHub Releases）** — 稳定 URL，无需跟随分支：

```
# Clash Meta（Mihomo）—— 大陆可用
https://github.com/learnLi/free-nodes/releases/latest/download/list.meta.cn.yml
# 原版 Clash（老内核）—— 大陆可用
https://github.com/learnLi/free-nodes/releases/latest/download/list.cn.yml
# 全量
https://github.com/learnLi/free-nodes/releases/latest/download/list.meta.yml
https://github.com/learnLi/free-nodes/releases/latest/download/list.yml
# 其他
https://github.com/learnLi/free-nodes/releases/latest/download/list.meta.us.yml
https://github.com/learnLi/free-nodes/releases/latest/download/list.txt
```

**备用通道（output 分支）** — 走 raw.githubusercontent / jsDelivr：

```
https://raw.githubusercontent.com/learnLi/free-nodes/output/list.meta.cn.yml
https://cdn.jsdelivr.net/gh/learnLi/free-nodes@output/list.meta.cn.yml
```

**配置片段（rule-providers / proxy-providers）** — 单独的 Release：

| 用途 | 链接 |
| :- | :- |
| 节点列表（Meta） | `.../releases/download/snippets/nodes.meta.yml` |
| 节点列表（原版 Clash） | `.../releases/download/snippets/nodes.yml` |
| 广告拦截 | `.../releases/download/snippets/adblock.yml` |
| 需代理域名 | `.../releases/download/snippets/proxy.yml` |
| 直连域名 | `.../releases/download/snippets/direct.yml` |
| 锁区域名 | `.../releases/download/snippets/region.yml` |

> Release 的资产名不允许包含 `/`，因此顶层订阅与配置片段分装在两个 Release（`latest` / `snippets`）中。
>
> 交叉表（判定过程）：`.../releases/latest/download/crosscheck_summary.md`

---

## 使用方法

1. 从上表复制对应链接，在客户端里添加为订阅。Clash Meta 用户把订阅类型选为 **Meta**。
2. 导入后建议：
   - `🐟 漏网之鱼` 保持 `DIRECT`
   - 遇到跳转反诈中心时，把 `❓ 疑似国内` 切到 `🚀 选择代理`
   - 想自动选快节点，用 `♻ 自动选择` / `🔰 延迟最低` 组（依赖客户端自身的 health-check）

---

## 三阶段筛选流水线

```
              ┌───────────── GitHub Actions（美国出口）─────────────┐
 抓节点 ─▶ 探测(US) ─▶ 单轮裁剪 ─▶ Stage 1 ─▶ Stage 3
            probe.py    prune.py   stage1.py  crosscheck.py
                             │         │            │
                     list.meta.yml  list.meta.us.yml  list.meta.cn.yml
                             │         │            │
                             │         ▼            │
                             │   output 分支        │
                             │  list.meta.us_<ts>.yml│
                             │         │            │
                             │         ▼            │
                             │  ┌─── NAS（中国出口）───┐ │
                             │  │ 探测 Stage 1 产物   │ │
                             │  │ probe_domestic_<ts> │ │
                             │  └────────┬────────────┘ │
                             │           ▼              │
                             └───── 交叉比对 ◀───────────┘
```

| 阶段 | 做什么 | 产物 |
| :- | :- | :- |
| 全量 | 抓取 + 单轮裁剪（剔明文代理、确凿已死、延迟超限） | `list.meta.yml`（Meta）/ `list.yml`（原版 Clash）|
| **Stage 1** | 用**美国侧多轮历史**筛出跨轮一致的 | `list.meta.us.yml` |
| **Stage 2** | NAS 在 Stage 1 产物上做国内探测 | `probe_domestic_<ts>.csv` |
| **Stage 3** | 中美**多轮**历史联合判定 | `list.meta.cn.yml`（Meta）/ `list.cn.yml`（原版 Clash）|

### 为什么用多轮而不是单轮

单轮探测噪声很大。同一批 409 个地址连测 5 轮，单轮说「活」的结果并不稳定；
**跨轮一致的才是真信号**。实测（美国 5 轮 + 国内 3 轮）：

```
美国跨 5 轮全活 314 / 全死 87 / 不定 8
中美交叉：真·大陆可用 120，美国说活国内说死 109，美国误杀 10
```

也就是说 —— **单轮美国探测会误导 27% 的节点**（美国说活、国内被墙），
而「美国跨轮全死」也不能当判死用（其中 10 个国内是活的）。

### 判定表

| 美国 \ 国内 | 跨轮全活 | 跨轮全死 | 未定 |
| :- | ---: | ---: | :-: |
| **跨轮全活** | ✅ 保留（真正的大陆可用） | ❌ 剔除 | ✅ 保留 |
| **跨轮全死** | ✅ 保留（**被美国侧误杀**） | ❌ 剔除 | ❌ 剔除 |
| **未定** | ✅ 保留 | ❌ 剔除 | ✅ 保留（数据不足，保守）|

另有一条**硬指标**独立于上表：国内延迟超过 `max_latency_ms`（默认 1000ms）的节点直接剔除。

### 「活着」的判定不是「任一握手成功」

走 TLS 的协议（vmess / vless / trojan）如果 **TCP 通了但 TLS 握手失败或超时**，
说明代理服务没起或 SNI 不对，节点实际上**不可用**。

早期版本只判断「TCP / TLS / QUIC 任一为 Y」，导致这批节点被算成活着 ——
它们同时污染了「跨轮存活」判定（误判为稳定存活）和延迟统计（把 5 秒超时值
当成真实延迟，让 p90 从 1282ms 虚高到 5002ms）。实测有 64 个这样的节点。

修法：`TLS=N` 或 `QUIC=N` 一律不算活着（协议不走 TLS 时该字段是 `N/A`，不受影响）。

### 时间戳的含义是「节点池的版本」

这是整套东西能对上的关键：

```
CI 抓节点 ─▶ 算出时间戳 ts
              ├─▶ 发布 list_<ts>.full.yml   到 output 分支
              ├─▶ 发布 list.meta.us_<ts>.yml 到 output 分支
              └─▶ 发布 probe_<ts>.csv        到 Release
NAS 拉 output 分支最新的 list.meta.us_<ts>.yml ─▶ 探测
              └─▶ 结果命名 probe_domestic_<ts>.csv ─▶ 推到 probe-domestic 分支
交叉比对按 ts 配对 probe_domestic_<ts>.csv ↔ probe_<ts>.csv
```

**如果时间戳表示「探测时刻」就会错位**：NAS 探测时 output 分支上的列表往往是上一版
（CI 那一轮还没推完），两边探测的节点池不是同一批。实测这种情况下节点池只重叠
**78%**，交叉表里 **32% 的节点只能判成「未测出」**，「可用」数被稀释到 110；
改成按节点池版本对齐后重叠 **100%**，「可用」数 110 → 201。

### 分协议的国内可用率

| 协议 | 可用率 | 说明 |
| :- | :-: | :- |
| http / socks5 | 100% | 明文开放代理，**已被剔除**，不进入推荐订阅 |
| **vmess** | **84.6%** | 最稳 |
| vless | 54.5% | |
| trojan | 31.4% | |
| **ss** | **25.0%** | 无 TLS、协议特征明显，最容易被 GFW 识别 |
| **hysteria2** | **2.5%** | QUIC/UDP，服务器两端都无响应 |

> **协议选择比节点数量重要得多。** `ss` 占节点总量的 12%，可用率只有 25%。
> 节点列表按这个偏好排序（见 `protocol_order`）。

---

## 技术细节

### 探测方法

`probe.py` 对每个节点做：

| 协议 | 探测方式 |
| :- | :- |
| vmess / vless / ss / ssr | TCP 连接 + TLS 握手（走 TLS 的协议才做握手）|
| trojan | TCP 连接 + TLS 握手 |
| **hysteria2 / tuic** | **QUIC Initial 探测**（aioquic 做真实 TLS 1.3 握手）|

QUIC 部分不能用「只发一个 Initial 包」的简化做法：按 RFC 9000 §17.2.5.2，回 Retry 是
「**可以**」而非「**必须**」，quic-go 等服务端默认直接丢弃 —— 实测美国侧 46 个 QUIC
节点只有 2 个有响应。必须做完整握手才有意义。

每次探测带三个**对照目标**（`1.1.1.1:443`、`8.8.8.8:443`、`github.com:443`），
用来区分「节点死了」和「runner 整体网络不通」—— 对照全挂时本次结果不可信。

> ⚠️ **边界**：CI runner 在**美国**，探到的是「**海外可达**」，不等于「中国大陆可达」。
> 这一点在设计里是刻意的 —— 见下面的三阶段流水线。

### 静态「过滤」

这些**都不是**连通性测试，全部基于节点字段本身：

- **假节点剔除** — 占位符地址（`8.8.8.8` / `127.0.0.0/8` / `0.0.0.0/8` / `169.254.0.0/16` /
  RFC 5737 文档保留网段）、假域名（`.google.com` / `.github.com`）、端口 < 20
  > 其中 `127.0.0.53`（systemd-resolved 的 DNS stub）特别重要：国内社区会植入指向它的
  > **哨兵节点**来检测客户端是否被 DNS 污染。上游只列了 `127.0.0.1`，漏掉了它。
- **SNI 修正** — SNI 含 `google.com` 的节点改为 `www.bing.com`（这类服务端并非面向国内设计）
- **协议兼容性判定** — cipher 是否在目标客户端白名单内、SSR 的 obfs/protocol 是否兼容、
  reality 的 public-key 长度是否合法
- **地区归类** — 纯**按节点名称关键词**匹配，与节点实际位置无关，仅供快速筛选

### 单轮裁剪（`prune.py`）

只剔除**确凿**的问题，判据是「路径通、但服务不在」（对端主动回 RST）：

| 剔除 | 保留 |
| :- | :- |
| `Connection refused` / `reset by peer` | `timeout`（防火墙丢包，可能只对中国 IP 放行）|
| TLS 被对端明确拒绝 | `Network is unreachable`（**探测端**没有该协议族的路由）|
| 明文 HTTP / SOCKS 代理 | DNS 解析失败（探测端 DNS 的问题）|

> 这里踩过一个坑：`Network is unreachable` 曾被当成「节点已死」，
> 结果**一次性误杀全部 IPv6 节点** —— GitHub 的 runner 根本没有 IPv6 出口。

### 配置一致性校验（硬门禁）

`scripts/validate_config.py` 会在构建时校验发布的所有配置：组引用是否都能解析、
组名/节点名是否重复、节点字段是否完整、port 是否合法、rules 引用的策略组是否存在、
`url-test`/`fallback` 组有没有 `url`。

**Mihomo / Clash 遇到 proxy-group 引用了不存在的节点时，会直接报
`proxy <name> not found` 并拒绝加载整个配置** —— 用户在客户端里看到的就是「订阅无效」，
而在 YAML 上完全看不出来。校验不过就**中止构建，绝不发布坏配置**。

### 客户端健康检查调优

上游的 `config.yml` 里两个自动选组都是 `interval: 300` + `url: https://www.google.com/`
+ `include-all: true`（探测全部节点）。现在有几百个节点，客户端启动时并发探测全部
是开机卡顿的主因。调优（`lazy` 与 `max-failed-times` 是 Mihomo 字段，原版 Clash 会忽略）：

| 项 | 上游 | 现在 |
| :- | :- | :- |
| `url` | `https://www.google.com/` | `https://www.gstatic.com/generate_204`（204 空响应）|
| `interval` | 300 | 600 |
| `timeout` | 未设 | 5000 |
| `lazy` | 未设 | **`true`** —— 只在组真正被使用时才探测 |
| `max-failed-times` | 未设 | **3** —— 连续失败 3 次后不再探测 |

---

## 配置

**所有可调参数集中在 [`fetch_config.local.yml`](fetch_config.local.yml)**，改完直接生效
（CI 与 NAS 每次跑都重新读它）：

```yaml
filter:                     # Stage 1 与 Stage 3 共用
  rounds: 6                  # 参与判定的最近 N 轮探测历史
  min_rounds: 2              # 至少这么多轮才判定（只出现一轮的判「未定」，保守保留）
  alive_ratio: 1.0           # 存活占比阈值：1.0 = 跨轮全活；调到 0.7 更宽松
  max_latency_ms: 1000       # 国内延迟上限，用于 list.meta.cn.yml
  max_latency_ms_us: 1000    # 美国侧延迟上限，用于 list.meta.yml / list.meta.us.yml

> **两个阈值用在哪**：
>
> | 阈值 | 作用范围 | 用的延迟 |
> | :- | :- | :- |
> | `max_latency_ms` | `list.meta.cn.yml` | **国内侧**中位延迟 |
> | `max_latency_ms_us` | `list.meta.yml`、`list.meta.us.yml` | 美国侧中位延迟 |
>
> 必须是两个值：美国到亚洲天生就慢（200~400ms），拿美国侧的延迟去筛
> 「国内可用」那份，会误杀「离美国远但离中国近」的好节点。
>
> 实测国内延迟分布：p50 = 434ms、p75 = 573ms、p90 = 1282ms、p99 = 2559ms。
> 1000ms 大约落在 p85 附近，会剔掉约 4% 的节点。想更宽松改 3000，
> 想更严格改 500。
>
> 延迟只对**成功**的探测有意义 —— 失败时耗时记的是超时上限（5 秒），
> 混进来会让分布图出现假尖刺（曾经把 p90 虚高到 5002ms）。

protocol_order:              # 节点排序依据实测国内可用率
  - vmess
  - vless
  - trojan
  - hysteria2
  - ss
  - ...

consensus:                   # 诊断用，不参与任何过滤
  enable_stats: true
  min_sources: 0
```

> `alive_ratio` 调到 0.7 会更宽松（允许 70% 的轮次存活即算稳定），节点更多但
> 质量下降。随着历史积累，1.0 的门槛会自然变严，节点数缓慢下降 —— 这是好事，
> 说明淘汰机制在工作。

### 为什么还保留「多源共识」统计

`fetch.py` 会统计每个节点被**几个独立来源**收录（`consensus.csv` / `sources.csv`）。
「独立来源」按**仓库归并**计数 —— 同一仓库的多个文件只算一个来源。

但实测结论是**这个信号不可用**：8 个独立来源之间几乎零重叠（独占率 95~100%），
98.1% 的节点只被一个源收录。换 `server:port` 口径也没改善 —— 因为那不是口径问题，
是**源生态本身长尾**。统计代码保留作为诊断数据，**不用于任何过滤**。

---

## 部署

### 国内探测端（NAS）

GitHub **没有**中国大陆区域的 runner（探针自报出口恒为美国，见 `probe_summary.md`）。
但**家里的设备反而是更好的探测点**：

| 维度 | GitHub runner（美国） | NAS（国内） |
| :- | :- | :- |
| 出口路径 | 境外机房 → 境外节点 | **中国住宅宽带 → 境外节点**，与目标用户一致 |
| IP 信誉 | Azure 机房段，部分节点直接拒绝 | **住宅 IP**，更可能被放行 |
| IPv6 | **没有**（实测所有 IPv6 节点 `Network is unreachable`）| 家宽通常有公网 IPv6 |

NAS 侧只需要一个定时任务。**本项目实际部署用的是 Docker 版**：

```bash
git clone --depth=1 https://github.com/learnLi/free-nodes.git
cd free-nodes
docker build -t free-nodes-probe -f docker/Dockerfile .
```

分工是刻意分开的：

| 谁 | 做什么 |
| :- | :- |
| **宿主机** | git：拉代码、取 output 分支的 Stage 1 产物、提交推送 |
| **容器** | 探测：TCP 连接 + TLS 握手 + QUIC 握手 |

仓库通过 `-v` 挂载到容器的 `/app`，所以 **`probe.py` 改了 git pull 一下就生效，
不需要重建镜像**。入口脚本放在镜像的 `/entrypoint.sh`（不是 `/app`），避免被挂载覆盖。

定时任务：

```cron
# 每 6 小时一次；脚本内部有 0~15 分钟随机抖动，打散固定周期的外连特征
17 */6 * * * /root/free-nodes/repo/docker/run.sh /root/free-nodes/repo /root/free-nodes >> /root/free-nodes/probe.log 2>&1
```

> **为什么要有随机抖动**：住宅 IP 每 6 小时固定向几百个境外 IP 发连接，形态很规整。
> 加上 0~15 分钟的随机等待，特征就没那么明显了。

> **不用 Docker 的话**：`scripts/probe_domestic.sh` 是等价的原生脚本，
> 只依赖 `python3` + 5 个 pip 包（`aioquic` / `PyYAML` / `requests` /
> `requests-file` / `typing_extensions`；aarch64、arm64 都有预编译轮子，不用编译）。

> **想在 1Panel 里管理**：1Panel 的「定时任务」支持 Shell 脚本类型，
> 填上面那条 cron 命令即可。**注意别和 crontab 里的条目重复** ——
> 1Panel 的任务也是写进 crontab 的，两边都配会跑两遍。
> （1Panel v1 的 API 接口默认是关的，`ApiInterfaceStatus = disable`，
> 所以只能从面板 UI 里建。）

**推回 GitHub** 需要一把能 push 的 SSH 密钥：

```bash
ssh-keygen -t ed25519 -C 'nas-probe' -f ~/.ssh/nas_probe -N ''
cat ~/.ssh/nas_probe.pub    # 加到 GitHub 账号的 Settings → SSH keys
```

> 加到**账号**的 SSH keys，不是仓库的 Deploy keys —— 后者需要仓库 admin 权限。
>
> 建议同时用 `ssh-keyscan github.com` 固定主机密钥，并与 GitHub 官方公布的指纹核对
> （ED25519 `SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM`，
> RSA `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`）。

也提供了 Docker 方案（[`docker/`](docker/)）：容器只做探测（不含 git），推送由宿主机负责。

#### 实测参考：Orange Pi 3（aarch64）+ Ubuntu 22.04

| 项 | 结果 |
| :- | :- |
| 出口 IP | `113.75.38.207`（中国电信广州）—— 与同宽带的 PC 完全同一个出口 |
| 单轮耗时 | **51.9 秒**（441 节点） |
| 流量 | 约 0.9 MB/轮 |
| TCP 连通率 | 54.7% |
| QUIC 响应率 | 1/46（2.2%）|

GFW 干扰特征（用于自检探针出口是否正常）：

```
1.1.1.1:443        超时
8.8.8.8:443        超时
35.158.96.132:443  超时
104.16.111.193:443 正常（Cloudflare）
www.gstatic.com:443 正常
```

---

## 路线图

项目的阶段划分、验收标准与待决策项见 **[docs/ROADMAP.md](docs/ROADMAP.md)**。

---

## 上游同步策略

`Sync upstream config` 工作流每天自动同步**配置类**文件：

| 文件 | 是否跟随上游同步 |
| :- | :- |
| `sources.list` / `fetch_config.yml` / `abpwhite.txt` | ✅ 每日自动覆盖 |
| `config.yml` | ❌ **不覆盖**，由本仓库自行维护 |
| `fetch.py` / `dynamic.py` | ❌ **不覆盖**，由本仓库自行维护 |

`config.yml` 不再自动覆盖，是为了能自由定制分流规则与健康检查参数。代价是**会错过上游的
规则更新**，所以 `sync.yml` 会额外产出一份**规则差异报告**（artifact `upstream-config-diff`），
列出上游新增/删除了哪些规则，人工按需合并。

本仓库自己的定制统一放在 `fetch_config.local.yml`，加载顺序：

```
fetch_config.yml（上游） → fetch_config.local.yml（本仓库） → local_fetch_config.yml（本地调试）
```

---

## 本地开发

```bash
git clone --depth=1 git@github.com:learnLi/free-nodes.git
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
| `local_fetch_config.yml` | 覆盖配置（优先级最高）|

### 跑测试

```bash
python tests/test_consensus.py
python tests/test_crosscheck.py
python tests/test_dynamic.py
python tests/test_fake_filter.py
python tests/test_prefs.py
python tests/test_probe.py
python tests/test_prune.py
python tests/test_quic.py
python tests/test_validate.py
```

9 个文件、约 240 项断言，**全部离线**（不联网）。

### 目录约定

```
fetch.py                  核心：协议解析、去重、分类、规则生成、产物写出
dynamic.py                动态订阅源
probe.py                  可达性探测（TCP / TLS / QUIC）
prune.py                  按探测结论裁剪
scripts/
  rounds.py               多轮探测的公共逻辑
  stage1.py               Stage 1：美国多轮一致性筛选
  crosscheck.py           Stage 3：中美多轮联合判定
  prefs.py                读配置（协议偏好、筛选参数）
  get_setting.py          给 shell 读配置用
  validate_config.py      配置一致性校验
  probe_domestic.sh       NAS 侧探测脚本
docker/                   Docker 方案
tests/                    单元测试
```

生成物（`list*` / `snippets/` 下除 `example.yml` 外 / `consensus.csv` 等）**不进 git**，
由 CI 打包上传到 Release。

---

## 工作流

| 工作流 | 触发 | 作用 |
| :- | :- | :- |
| `Fetch` | 每 3 小时 + 手动 | 抓取 → 探测(US) → 裁剪 → Stage 1 → 发布 → 输出分支 |
| `Cross-check` | 由 Fetch 调用（每 3 小时）+ 定时（每 6 小时）+ 手动 | 取中美多轮数据 → 联合判定 → 发布大陆可用订阅 |
| `Sync upstream config` | 每天 + 手动 | 同步上游配置类文件，产出规则差异报告 |

三个工作流都配了 `concurrency` 与 `timeout-minutes`。`Cross-check` 作为可复用工作流
被 `Fetch` 调用时，**并发组必须与调用方区分开**（`${{ github.workflow }}-xcheck-...`），
否则会去抢调用方正持有的锁，表现为 job 根本不出现。

---

## 安全须知

- 本项目**不审计**来自第三方的节点内容。免费节点由陌生人自建，流量经过其服务器，
  **请勿用于敏感通信**。
- 订阅内容来自多个第三方仓库，其中任何一方被投毒，都可能向你的客户端注入指向
  攻击者服务器的节点。
- 广告拦截规则同样来自远程列表，理论上可被用于屏蔽正常站点。
- 明文 HTTP / SOCKS 开放代理**已被剔除**（代理方可见明文流量，且本就不是「免费节点」）。
- 请自行评估风险。本仓库仅供学习交流使用。

---

## 许可证

[反 996 许可证 v1.0](LICENSE.md)（继承自上游）。上游项目的许可证明确禁止实行 996 工作制的
公司使用，请知悉。
