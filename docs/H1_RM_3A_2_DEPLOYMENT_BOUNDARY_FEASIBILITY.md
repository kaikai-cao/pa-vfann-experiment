# H1-RM.3A.2 — Deployment Boundary Feasibility Audit

部署边界可行性审计。目标单一：判断 H1 威胁模型能否映射到**现实、可实现的 HNSW 部署**，使 ACL 与停止逻辑位于可信侧、不可信存储侧能观察节点/邻接块读取顺序与请求结束位置；并据此决定是否值得进入 block-level trace 阶段（H1-RM.3B）。

本轮是**架构审计**：不写代码、不修改 `StorageAccess`、不创建 block storage backend、不运行攻击实验、不重跑 EXP-10 或 H1.1–H1.4、不启动 H1-RM.3B、不修改任何冻结实验。只新增本报告一份。

- 仓库：`kaikai-cao/pa-vfann-experiment`
- 基线分支：`research/h1-rm-3a1-r1-label-boundary`
- 基线 SHA：`4665f1658eea5dffb6a563a68d082d4f9762e3e7`
- 父提交：`c7e8189fe60a5d40a5f6aa16b8e0912e0a879e17`
- 本分支：`research/h1-rm-3a2-deployment-boundary`

**源码基准声明**：本报告 Phase 2 的行号一律指本 worktree 冻结的 `third_party/hnswlib-v0.9.0/hnswlib/hnswalg.h`（**未插桩原始版**）。前序 3A / R1 报告的行号指 `hnswlib-v0.9.0-rm2-instrumented` 插桩版，二者行号体系不同，不得直接套用同一行号。

---

## 0. 最终裁决（摘要，理由见 §5）

**CONDITIONAL — 需要缩小问题、改变观察粒度；不授权直接进入 H1-RM.3B。**

三句话理由：

1. **威胁模型可映射到真实架构，故不是 STOP。** 架构 B（TEE + 不可信 OS）由 FiT（USENIX Security 2025）直接证明：HNSW 在 CCE 内运行，控制 OS 的攻击者从页访问模式重建 HNSW 节点访问序列，且能通过网络 I/O syscall 识别每个请求的起止。这满足"ACL/搜索在可信侧、外部观察读取顺序与请求结束"的基本假设。
2. **但停止边界的增量未被证明，故不是 GO。** FiT 已从 page trace 重建 HNSW 节点访问序列，其中原则上已包含"在何处停止访问"的信息；Onyx / O2N2 这类"正确部署"用 ORAM / 双重 obliviousness 使访问模式与数据无关，停止边界被直接消除。没有任何证据表明停止边界提供**超出一般 HNSW 访问模式泄露**的授权成员信息。
3. **逻辑事件到物理事件存在粒度折叠，是必须先处理的硬约束。** R1 的 `label_read=8669` 是本地接口调用，不是 8669 次外部读取；vector / label / L0 邻接同处一个 204 B 节点块，一次块取回同时满足三类逻辑请求；`USE_SSE` 预取会在逻辑停止点之前把邻居向量拉入缓存。当前 hnswlib 源码为纯进程内指针算术，无 block 概念；把它变成"外部 SSD / 远程块存储"需重设计存储层（本阶段禁止）。

---

## 1. Phase 1 — 三种现实部署架构

对每种架构逐一回答八个问题。结论基于原文可核验内容；二手来源已明确标注，不当作原文事实。

### 1.1 架构 A：TEE + 外部 SSD / Block Storage（任务称"首选候选"）

| 问题 | 回答 | 依据 |
| --- | --- | --- |
| 1. 谁持有 ACL | 可信侧（TEE 内）。As-conceived：搜索逻辑与策略在 enclave；原文未讨论 ACL，标注 `NOT_STUDIED` | Onyx 摘要/引言：索引存外部 SSD，搜索在 TEE 内 |
| 2. 谁执行 `isIdAllowed` | 可信侧（若存在）。Onyx 无过滤语义，标注 `NOT_STUDIED` | 同上 |
| 3. 谁执行 `should_stop_search` | 可信侧。Onyx 采用 ANN 层的 traverse→prune→refine 与 ORAM 固定调度，访问与数据无关 | Onyx 摘要：Onyx-ANNS / Onyx-ORAM co-design |
| 4. 谁持有解密密钥 | TEE / enclave 内（可信侧） | Onyx 设定：索引加密存于外部 SSD |
| 5. 存储观察者可见字段 | **在 Onyx 的正确部署下：只见 ORAM 访问序列（与查询无关）**。原始"不加密索引 + 直读 SSD"设定下 host 可见 block ID / 顺序 / 数量 | 摘要原文："external SSDs, which leaks user queries through disk access patterns to the host"；"ORAM can hide these access patterns" |
| 6. 查询起止可观察 | 条件可见：需存储请求会话边界；原文未定义 query handle / session | 摘要与二手解读均未给出边界协议，标注 `UNKNOWN` |
| 7. 缓存/预取/批量 | **有**：Onyx-ANNS 把压缩遍历提示放 TEE 内存、剪枝提示放外部；ORAM 层重排访问 | conceptio / emergentmind 二手解读（非原文逐字），标注 `SECONDARY` |
| 8. 停止位置影响外部序列 | **在 ORAM 部署下：否**，访问 data-independent，停止点被掩盖。这是本架构的强反例 | Onyx 目标即"disk-oblivious"；ORAM 消除 data-dependent 访问 |

**关键限制（反例，不得忽略）**：Onyx 的部署动机是"索引大到无法经济地放进可信内存"。本实验规模 N=1000、dim=16、M=16，按 v0.9.0 布局 `size_data_per_element_ = 132 + 64 + 8 = 204 B`，L0 数据仅 `1000 × 204 = 204000 B ≈ 200 KB`（约 50 个 4 KB 页）。该规模可完整置于可信内存，**"必须外部化到 SSD"的前提在本实验中不成立**。要把当前纯内存 hnswlib 跑成架构 A，必须新增 block 分块与按需 fetch 的存储层——这正是本阶段禁止的工作，且不是"加一个日志桥接"能解决。

### 1.2 架构 B：TEE + 不可信 OS / Hypervisor（最现实的观察边界）

| 问题 | 回答 | 依据 |
| --- | --- | --- |
| 1. 谁持有 ACL | 可信侧（enclave 内进程地址空间） | FiT 威胁模型：敏感应用运行在 CCE 内 |
| 2. 谁执行 `isIdAllowed` | 可信侧。FiT 未研究 ACL/filter（全文关键词 `filter`/`ACL` 无命中），标注 `NOT_STUDIED` | FiT 全文 PDF 检索 |
| 3. 谁执行 `should_stop_search` | 可信侧。FiT 研究对象是 HNSW 一般搜索访问，非 ACL 触发的提前终止，标注 `NOT_STUDIED` | 同上 |
| 4. 谁持有解密密钥 | enclave（硬件保护内存，明文仅在寄存器/cache 内） | FiT §2："Data in the protected region is also automatically encrypted and remains accessible in plaintext only within the processor registers and caches" |
| 5. 存储观察者可见字段 | **页级访问序列**（PTE accessed bit / page fault），**不是逻辑节点**。页→对象多对一 | FiT §1："a sequence of page accesses alone cannot reveal the specific objects (i.e., embedding table entries or HNSW graph nodes) accessed, as there is a many-to-one mapping from pages to objects" |
| 6. 查询起止可观察 | **是**。FiT 明确通过监控网络 I/O syscall 标记请求与响应来识别每个请求起止 | FiT §3："The system-level adversary can identify the start and end of each request by monitoring the network I/O syscalls that mark each request and the corresponding response" |
| 7. 缓存/预取/批量 | 页级聚合本身即粗粒度化；同一页内多节点被折叠为一次"访问" | FiT §1 多对一论述；本实验 204 B/节点 → 约 20 节点/4 KB 页 |
| 8. 停止位置影响外部序列 | **部分**：仅当停止使原本会访问的**新页**未被访问时才体现；若停止点所在页此前已被访问，页级 trace 不区分。当前为 `HYPOTHESIS`，未测 | 由 §2 节点布局与页粒度推算，非已证事实 |

**这是三架构中唯一由原文直接证明"HNSW + 页访问可观察 + 请求边界可识别"的架构**。FiT 的实验证据：HNSW 用案的页→节点重建，攻击精度跨三个用案 71.7%–99.9%（HNSW 用案中位归一化汉明距离 0.76，见 artifact 与正文）。

### 1.3 架构 C：可信客户端 + 远程存储服务器

| 问题 | 回答 | 依据 |
| --- | --- | --- |
| 1. 谁持有 ACL | 可信客户端 / 可信服务端 enclave | ShieldStore：客户端远程证明服务器 enclave |
| 2. 谁执行 `isIdAllowed` | 可信侧（若存在）。ShieldStore 是 KV store，无 HNSW 过滤语义，标注 `NOT_STUDIED` | ShieldStore 二手笔记，标注 `SECONDARY` |
| 3. 谁执行 `should_stop_search` | 可信侧。同上，`NOT_STUDIED` | 同上 |
| 4. 谁持有解密密钥 | 客户端与服务器 enclave 交换 session key；SSK/TSK/FEK 层次由安全世界持有 | OP-TEE secure storage §4（REE/RPMB 密钥层次）与 ShieldStore 笔记 |
| 5. 存储观察者可见字段 | 密文、索引结构、数字对象 ID / FAT 元数据、块读写顺序与时序。**不隐藏访问模式** | OP-TEE 文档原文："All normal world files are integrity protected and encrypted"；RPMB "The FAT is not encrypted"；"device operations all have to go through the normal world" |
| 6. 查询起止可观察 | 条件可见：可通过网络连接/会话边界划分；需显式协议，原文未定义 HNSW 场景 | ShieldStore 用 secure channel 收发请求，标注 `UNKNOWN` |
| 7. 缓存/预取/批量 | OP-TEE secure storage **不提供** padding / batching / ORAM；HNSW 节点如何映射为 KV 未定义 | OP-TEE 文档与 ShieldStore 笔记均无访问隐藏机制 |
| 8. 停止位置影响外部序列 | 条件可见：若每节点/邻接为独立网络请求，提前停止使请求序列变短；若批量/缓存则被掩盖 | 由架构推断，`HYPOTHESIS`，未测 |

**来源诚实边界**：ShieldStore 仅取得二手 paper_summary 笔记（EuroSys'19 原文未获取），相关判断标注 `SECONDARY`，不作为原文可核验事实；OP-TEE secure storage 为官方文档原文，可核验。Intel OP-TEE 架构文章仅用于佐证"不可信 OS/Hypervisor 控制平台服务"的通用设定，未据此推断具体可观察字段。

### 1.4 跨架构小结

- 三种架构都**真实存在**，H1 的信任边界假设不是凭空假设。
- 但"观察者能看到什么"从强到弱：架构 C（块/网络请求，最细但可由批量掩盖）> 架构 B（页级，多对一折叠）> 架构 A（**正确部署下 ORAM 使访问与数据无关，几乎看不到停止边界**）。
- 唯一由原文证明"HNSW + 可观察读取顺序 + 请求边界"的是架构 B（FiT），其观察粒度是**页**，不是逻辑节点。

---

## 2. Phase 2 — HNSW 内存布局映射到外部存储

以本 worktree 冻结的**未插桩 v0.9.0** 为准。

### 2.1 节点块布局（源码 `hnswalg.h:120–126`）

```
size_links_level0_     = maxM0_*sizeof(tableint) + sizeof(linklistsizeint);   // :120
size_data_per_element_ = size_links_level0_ + data_size_ + sizeof(labeltype); // :121
offsetData_            = size_links_level0_;                                  // :122
label_offset_          = size_links_level0_ + data_size_;                     // :123
offsetLevel0_          = 0;                                                   // :124
data_level0_memory_    = malloc(max_elements_ * size_data_per_element_);      // :126
```

本实验常量（`typedef` 见 `hnswalg.h:14-15`、`hnswlib.h:125`）：`maxM0_ = M×2 = 32`；`tableint = unsigned int(4B)`；`linklistsizeint = unsigned int(4B)` → `size_links_level0_ = 32×4+4 = 132 B`；`data_size_ = 16×4 = 64 B`；`labeltype = size_t(8B)`；`size_data_per_element_ = 132+64+8 = 204 B`。L0 总量 `1000×204 = 204000 B ≈ 200 KB`（约 50 个 4 KB 页），约 20 节点/页。此结果与 §1.1 一致，且与 R1 报告的 132/204 数值相同（原始版与插桩版此布局未改）。

单节点块 `base = data_level0_memory_ + i*size_data_per_element_` 的字节布局：

| 偏移 | 内容 | 大小 | 读取函数（原始版行号） |
| --- | --- | --- | --- |
| `offsetLevel0_=0` | L0 邻接表 count + ids | `size_links_level0_` | `get_linklist0()` :486–488 |
| `offsetData_` | 向量 | `data_size_` | `getDataByInternalId()` :202–204 |
| `label_offset_` | external label | `sizeof(labeltype)` | `getExternalLabel()` :185–189 |

三者**同处一个连续节点块**，且 `label_offset_ + sizeof(labeltype) == size_data_per_element_`。

### 2.2 完整映射表（任务要求六项）

| 数据结构 | 当前实现位置（行号） | 能否映射独立 block | 与谁共用 | 备注 |
| --- | --- | --- | --- | --- |
| Level-0 adjacency | `data_level0_memory_` + `offsetLevel0_`（:486–488, :362） | 否（与向量/label 同块） | vector、label、delete mark | 块首 2 B count + ids |
| Vector | `data_level0_memory_` + `offsetData_`（:202–204） | 否 | L0 邻接、label | — |
| External label | 节点块尾部 `label_offset_`（:185–189） | 否 | vector、L0 邻接 | R1 已将其纳入 `read_label()`，但物理上同一块 |
| Delete mark | L0 linklist 区 `get_linklist0(id)+2`（:933–937 `isMarkedDeleted`；:872–884 `markDeletedInternal`） | 否 | L0 邻接表 | `linklistsizeint=4B`，`getListCount` 只读前 2 B（:939–941），删除标记存第 3 B（`+2`）；随节点块读取；R1 未纳入 `NodeView`，记为风险 |
| Upper-level adjacency | `linkLists_[id]` 独立 `malloc`（:138–141, :496–498） | **是**（独立分配与读取路径） | 无（每层 `size_links_per_element_`） | 查询 greedy descent :1283；构建 :1221 |
| Index metadata | 头部标量字段（:658–683 `indexFileSize`；:685–712 `saveIndex`；:715–815 `loadIndex`） | 是（可信侧常驻） | — | 含 `enterpoint_node_` / `maxlevel_` / `label_offset_` 等；留可信侧 |

### 2.3 按访问路径核对（不得只看 `getDataByInternalId` / `get_linklist0`）

| 路径 | 关键代码 | 观察含义 |
| --- | --- | --- |
| 初始化/构造 | :120–143 两次 `malloc`：L0 大块 + `linkLists_` 指针数组 | 块布局在建立时固定；上层邻接独立分配 |
| 查询（L0） | `searchBaseLayerST` :311–440：stop check :346–358，`get_linklist0` :362，邻接遍历 :377–435，filter :407 | 停止点在候选循环顶部，早于邻接展开；外部只见"不再取块" |
| 查询（上层） | `searchKnn` :1270–1322 greedy descent :1277–1302：`get_linklist(currObj, level)` :1283 | 上层邻接为独立块，留可信侧可减小观察面 |
| `USE_SSE` 预取 | :266–289（searchBaseLayer）、:370–384 与 :400–403（searchBaseLayerST）、:1091–1096（addPoint）直接对 `data_level0_memory_` 地址 `_mm_prefetch` | **逻辑停止点 ≠ 物理访问点**：预取提前拉取邻居向量，物理取块可能先于逻辑读取发生 |
| 更新 | `addPoint` :1152+、`updatePoint` :953+、`mutuallyConnectNewElement` :506+ | 走裸内存写；非查询期，本审计不改 |
| 删除 | `markDeletedInternal` :872–884 写 `get_linklist0(id)+2` | 删除标记随 L0 邻接块；非查询期 |
| 序列化/反序列化 | `saveIndex` :685–712 连续写整块 `data_level0_memory_` 再逐 `linkLists_[i]`；`loadIndex` :715–815 对应读 | 序列化是"一次性整块 I/O"，与查询期逐块取回语义不同；不能据序列化布局推断查询期块边界 |

**Phase 2 结论**：物理块边界可由实现者重新定义（这是设计自由度），当前源码并未固定"一个节点=一个 block"。在"vector/label/邻接同块"的自然映射下，三类逻辑读取折叠为一次物理取块；上层邻接因独立分配是唯一天然可分离的块。删除标记与 label 均绑定 L0 节点块，无法从块级观察中单独分离。

---

## 3. Phase 3 — 攻击者实际观察到的 trace（三类严格区分）

### 3.1 三类 trace 定义

| 类别 | 定义 | 当前对应物 | 是否攻击者可见 |
| --- | --- | --- | --- |
| Logical trace | `read_node` / `read_label` / `read_neighbors` 接口调用序列 | 3A.1/R1 的 `requests.jsonl`；R1 中 `label_read=8669` | **否**（本地适配层调用，不是外部读取） |
| Storage trace | 实际外部 block/page fetch 序列 | **当前不存在**（无 block backend） | 架构 B 为页级、架构 C 为块/网络级、架构 A 正确部署为 ORAM 序列 |
| Search trace | `distance_eval` / `candidate_pop` / `filter_check` / `search_stop` 等内部搜索事件 | `events.jsonl`（RM2_EV 插桩） | **否**；`search_stop` 不跨边界 |

### 3.2 映射关系（文字时序图，架构 B / 页级）

```
可信侧 (enclave)                          不可信 OS / 存储观察者
----------------                          ----------------------
网络 I/O syscall: query in          ---->  标记请求起点，清 PTE accessed bits
isIdAllowed(label(x)) -> 允许                (看不到 label、看不到判定结果)
read_node(x) -> 向量 [同块]          ---->  页 P(x) 被 touch（PTE A bit=1）
read_label(x) -> label [同块]        ---->  无额外页访问（同块，已 touch）
read_neighbors(x) -> L0 邻接 [同块]  ---->  无额外页访问（同块，已 touch）
_mm_prefetch(邻居 y 向量)            ---->  页 P(y) 可能提前 touch（预取，早于逻辑读取）
... K 次授权命中 ...
stop_condition::should_stop_search()        (看不到该内部事件/命中计数)
break; 不再展开候选                  ---->  从此无新的页 touch（仅当新页未被访问过才体现）
网络 I/O syscall: query out         ---->  标记请求终点
```

### 3.3 直接回答"K-hit 导致停止时外部能看到什么"

不预设答案。可能情况与对攻击可行性的影响：

| 情况 | 外部可见内容 | 对 H1 的影响 |
| --- | --- | --- |
| (a) 停止点跨越到新的未访问节点块 | 请求/页访问序列提前终止于某块 | 停止位置可能可观察；仍与一般查询访问模式混杂 |
| (b) 停止点所在块已被访问（向量/label/邻接同块，且预取已触达） | 与不停止的查询在页集合上难以区分 | 停止边界在页级**不可分辨**；这是最可能的情况 |
| (c) 部署了缓存/批量/ORAM（架构 A 正确部署、架构 C 优化） | 访问序列被重排或填充，与数据无关 | 停止边界被**完全掩盖**，H1 信道关闭 |
| (d) 不同查询的请求边界无法可靠划分（无 session/query handle） | 无法切分单次查询的 trace | `O(q)` 无法实例化，H1 不可评估 |

当前源码同时满足 (b) 的结构条件（204 B/节点、同块、SSE 预取）与 (d) 的条件（无 query handle 跨边界）。因此**不能**把 `requests.jsonl` 直接称作攻击者 trace；R1 的 `label_read` 数量尤其不能当作外部读取次数。

---

## 4. Phase 4 — 与已有研究的实质差异

对比表（只写可核验或已标注二手的内容；禁止"首次""完全没有相关工作"等表述）：

| 对比维度 | FiT (USENIX Sec'25) | Onyx (arXiv 2604.20401, 2026) | O2N2 (arXiv 2611.03415, 2026) | H1（本提案） |
| --- | --- | --- | --- | --- |
| 主要保护目标 | 攻击方：从页访问重建对象访问（含 HNSW 节点） | 查询+数据库隐私，磁盘访问隐藏（single / external obliviousness） | 查询+数据库隐私，双重 obliviousness（外部+enclave 内访问均隐藏） | 提议：ACL 授权成员对外隐藏（**未证**） |
| 观察者 | 控制 OS/Hypervisor 的云服务方 | 控制 host / SSD 访问的一方 | 外部存储 + enclave 内页/缓存侧信道方 | 假设：不可信存储/平台侧（ architectures A/B/C，未选定） |
| 观察粒度 | **页级**（PTE accessed bits），多对一 | **块/磁盘访问**，ORAM 后与数据无关 | 访问模式被 data-independent 化 | 未定：逻辑 node（不可用）/ 页 / 块（需新后端） |
| 是否处理 ACL | 否（全文无 ACL/filter） | 未研究（`NOT_STUDIED`） | 未研究（`NOT_STUDIED`） | 是（核心研究对象，未证） |
| 是否分析停止边界 | 否（一般 HNSW 访问模式，非 ACL 触发终止） | 否（ORAM 固定调度消除 data-dependent 访问） | 否（fixed-schedule 去重/选择，访问与数据无关） | 是（核心研究问题，未证） |
| 是否推断授权成员 | 否 | 否 | 否 | 是（目标，未证） |
| 底层 ANN | HNSW | DiskANN 类图索引，graph-based | 随机旋转 k-d 树森林，tree-based | HNSW v0.9.0 |

**创新性边界（诚实陈述）**：

1. "ANN/HNSW 访问模式会泄露信息"**不是**本工作创新点——FiT 已对 HNSW 页访问建立攻击，Onyx/O2N2 已把访问隐藏作为设计目标。
2. "ANN 自适应终止/oblivious 调度"**不是**本工作创新点——O2N2 用 fixed schedule、Onyx 用 ORAM，均处理 data-dependent 访问。
3. 三项工作中**未发现**直接研究"ACL 对外隐藏 + 过滤可信执行场景下，停止边界是否泄露授权成员"的公开工作（在本轮核查范围内）。这只能写成"核查范围内未见"，不得写成"首次"或"完全没有相关工作"。
4. 反向风险：FiT 的页→节点重建原则上已覆盖"在何处停止访问"，H1 声称的停止边界可能是 FiT 一般访问模式攻击的一个**特例**而非独立信道。这一风险尚未排除。

---

## 5. Phase 5 — 最终决策与理由

### 5.1 三个结论逐项判定

- **GO（进入 H1-RM.3B）— 不成立。** 缺两块必要证据：(i) 停止边界相对 FiT 一般访问模式泄露的**增量**未证，甚至可能是其特例；(ii) 物理观察粒度未定，`requests.jsonl` 是逻辑事件、不是存储 trace，且当前源码无 block 概念，进入 3B 必须先构建 block/page 级观察模型（本阶段禁止实现）。若此时 GO，等于用逻辑 trace 冒充攻击者 trace，正是本任务要求避免的错误。

- **STOP（威胁模型不成立）— 不成立。** 架构 B 由 FiT 原文直接证明满足核心假设：搜索/敏感数据在 TEE 内、控制 OS 的攻击者观察页访问、网络 I/O 标识请求起止。ACL 由可信侧执行的设定与之一致。不存在"ACL 实际由不可信存储端执行"或"无任何合理部署能观察停止边界"的证据。因此不能判 STOP。

- **CONDITIONAL — 成立。** 威胁模型可映射，但必须缩小问题、改变观察粒度，并先证明停止边界的增量信息，才谈得上进入 3B。

### 5.2 收紧后的研究问题（唯一值得继续推进的表述）

> 在 ACL 对外隐藏、过滤与停止逻辑在可信执行环境内执行的 HNSW 部署中，**页级或块级**存储访问轨迹的**停止边界**，是否构成一种可区分于一般 HNSW 查询访问模式泄露（FiT 类）的**授权成员推断信道**？

不得再说"我们发现了 HNSW 访问模式泄露"（FiT 已覆盖），也不得说"我们发现了 ANN 提前停止会泄露信息"（oblivious ANN 已有相关研究）。

### 5.3 进入下一阶段前的前置条件（全部为分析性，不含写代码）

1. **固定架构**：三选一并写明理由。若选架构 A，需正面处理"正确部署用 ORAM → 停止边界关闭"的反例；若选 B，观察粒度必须是页；若选 C，须定义 HNSW 节点到 KV/块的映射与会话边界。
2. **重建 trace 契约**：把 `O(q)` 从逻辑读取改为存储 trace（页序列或块序列），显式定义 ID 命名空间（external label 是否出现在请求中）、请求边界、批量/预取规则。
3. **增量判据**：设计一个能把"停止边界信息"与"一般访问模式信息"分离的对照（例如匹配访问前缀但停止边界不同的查询对），否则无法证明不是 FiT 特例。
4. **规模前提**：若沿用当前 N=1000 规模，须解释为何不全部放入可信内存；否则架构 A 的动因不成立。

在上述条件未闭合前，**不启动 H1-RM.3B**。

### 5.4 下一阶段最小可验证实验设计建议（仅建议，本轮不执行）

- 形态：**纯分析 / 离线重放**，不新增代码 backend。用冻结的 `events.jsonl` 按"页映射"重放成 page-level trace（页大小 4 KB，节点块 204 B，约 20 节点/页），比较 C0（无停止）/ C1（预算停止）/ C2（K-hit 停止）在页级序列上的差异。
- 判据：若 C2 与 C0/C1 在页级序列上可区分，且区分度可由"停止点"而非"查询邻域本身"解释，则进入下一轮；若不可区分或差异完全由邻域解释，则收缩或放弃。
- 边界：该重放只用于判断"是否值得做 block-level trace"，不产出成员推断结论，不复用 H1.1–H1.4 的结果表。

---

## 6. 引用来源

**原文可核验（一手）**

1. Onyx: Cost-Efficient Disk-Oblivious ANN Search. Rathee, Watson, Zhao, Suh, Popa. arXiv:2604.20401, v1 2026-04-22. https://arxiv.org/abs/2604.20401 — 摘要与引言（TEE + 外部 SSD、disk access pattern 泄露、ORAM 隐藏、Onyx-ANNS/Onyx-ORAM co-design）；全文 PDF 未逐段核验。
2. Found in Translation: A Generative Language Modeling Approach to Memory Access Pattern Attacks (FiT). Jia, Wong, Khandelwal. USENIX Security 2025, pp.7957–7975. https://www.anuragkhandelwal.com/papers/fit.pdf — 全文 PDF 已下载并检索 §1/§2/§3/§4；附录 https://www.usenix.org/system/files/usenixsecurity25-appendix-jia-grace.pdf ；artifact https://zenodo.org/records/15602652 。
3. O2N2: Efficient Doubly Oblivious Approximate Nearest Neighbor Search. Li, Guo, Zhou, Shi, Hong. arXiv:2611.03415, v1 2026-11-02. https://arxiv.org/abs/2611.03415 ; https://arxiv.org/html/2611.03415v2 — 摘要与 Table I（single vs double obliviousness、数据模型、底层 ANN）；fixed-schedule 描述来自摘要。
4. OP-TEE documentation, Secure Storage (v4.9.0). https://optee.readthedocs.io/en/4.9.0/architecture/secure_storage.html — 机密性/完整性/原子性保证；REE FS 与 RPMB 的正常世界可见字段；SSK/TSK/FEK 密钥层次；无访问模式隐藏机制。

**二手来源（已标注，不作为原文事实）**

5. ShieldStore (EuroSys'19) paper summary. https://yzr95924.github.io/paper_summary/ShieldStore-EuroSys%2719.html — 用于架构 C 的加密 KV / remote attestation / secure channel 设定；原文未获取。
6. Onyx 技术解读：https://www.conceptio.app/document/123957/onyx-cost-efficient-disk-oblivious-ann-search ；https://www.emergentmind.com/topics/onyx-anns — 用于 Onyx-ANNS 三层表示与"索引放外部 SSD"动机的补充；非原文逐字。
7. Intel OP-TEE 架构文章（任务提供链接）— 仅作通用威胁模型佐证，未据此推断具体可观察字段。

**本地源码（本 worktree 冻结）**

8. `third_party/hnswlib-v0.9.0/hnswlib/hnswalg.h`（未插桩原始版），行号见 §2。
9. `docs/H1_RM_3A_ATTACKER_OBSERVABLE_TRACE_CONTRACT.md`、`docs/H1_RM_3A1_STORAGE_ACCESS_BRIDGE.md`、`docs/H1_RM_3A_1_R1_EXTERNAL_LABEL_READ_BOUNDARY.md`（前序冻结报告，用于承继内部 trace / 桥接 / label 边界结论）。

---

## 7. 一次性自检

| 检查 | 结果 |
| --- | --- |
| Phase 0 门禁全部通过后才建分支 | PASS；仓库/HEAD/父提交/工作区/目标分支本地与远端不存在/worktree 空闲逐项核对 |
| 三种架构都回答八问，且区分逻辑接口与物理事件 | PASS；§1.1–1.3 逐项，未定义字段标 `UNKNOWN`/`NOT_STUDIED` |
| Phase 2 覆盖六项数据结构与五类访问路径 | PASS；§2.2 六项、§2.3 初始化/查询/更新/删除/序列化 + `USE_SSE` |
| 明确"同块折叠"与"预取早于逻辑停止" | PASS；§2.1、§2.3、§3.2 |
| 三类 trace 严格区分，未把 `requests.jsonl` 当作攻击者 trace | PASS；§3.1–3.3，R1 的 `label_read=8669` 明确为接口调用 |
| 对比表覆盖 FiT/Onyx/O2N2/H1 六维 | PASS；§4，二手来源已标注 |
| 无"首次/完全没有相关工作"表述 | PASS；§4 仅称"核查范围内未见" |
| 反例未被忽略（ORAM 关闭信道、规模前提、FiT 特例风险） | PASS；§1.1、§5.1、§4.4 |
| 裁决与证据一致，且不是为 GO 而放宽 | PASS；CONDITIONAL，进入 3B 需四项前置条件 |
| 未改代码 / 未改 `StorageAccess` / 未建 backend / 未跑实验 / 未启动 3B / 未改冻结产物 / 未建 PR | PASS；本轮只新增本报告一份 |

本轮到此停止，拿到证据后再决定是否推进；不自动开始下一阶段。
