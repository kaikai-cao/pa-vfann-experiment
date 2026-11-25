# H1-RM.3A.1 — Storage Access Bridge Feasibility Probe

## 结论摘要

在本地工程探针范围内，**访问桥接成立（PASS）**：不改变 HNSW 搜索、过滤、候选维护与停止语义，可以把全部**节点向量读取**与**邻接表读取**统一经过一个可记录的 `StorageAccess` 接口。适配前后在完全相同的 50 查询 × 3 组固定配置下，`events.jsonl`、`topk.jsonl`、`run_summary.jsonl` **逐字节一致**；请求轨迹有序、可关联到查询、无批量、带查询边界。

**边界声明（不可省略）**：这是一份**本地单进程**适配层验证。它没有实现远程不可信存储、TEE 隔离或真实网络侧观测；它证明的是"统一读取接口可作为未来可信侧/存储侧边界的工程基础"，**不是**真实远程存储架构已经验证，**也不是**成员推断攻击已成立。

---

## 1. 基线与范围

| 项目 | 值 |
| --- | --- |
| 基线分支 | `research/h1-rm-3a-attacker-observable-trace` |
| 基线 SHA | `6d63c070fd3e64da3cbb08514a231dde8dd48f38` |
| 父提交 | `ea7b7bdbd3c76ec08549a452bd4c631d32705ef6` |
| 本轮分支 | `research/h1-rm-3a1-storage-access-bridge` |
| 任务性质 | 独立工程可行性探针；不进入攻击实验 |
| 固定配置 | N=1000, DIM=16, IP, M=16, efC=200, efS=64, K=10, 50 查询, seed=2026, label=100000+17·i |
| 对照设计 | **同一份 runner 源码**，运行时 `bridge=0`（不注入 storage）vs `bridge=1`（注入），仅此一个变量不同 |

禁止项核验：未修改 H1.1–H1.4、EXP-10A、H1-RM.2、H1-RM.2-R1、H1-RM.3A 及其产物；未做 ACL 成员推断、未做性能优化、未引入新数据集；未引入 ORAM/TEE/ZKP 实现。

---

## 2. Phase 1：读取路径完整性审计

审计对象：`third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib/hnswalg.h`（H1-RM.2 基线源码，未改动）。行号为该基线源码位置。

### 2.1 全部相关读取路径

| 读取类型 | 源码位置（基线 hnswalg.h） | 调用函数 / helper | 访问对象 | 是否统一封装 |
| --- | --- | --- | --- | --- |
| 节点向量（搜索入口点） | 1300（`searchKnn`）、1362（`searchStopConditionClosest`） | `getDataByInternalId(enterpoint_node_)` | `data_level0_memory_ + i·size_data_per_element_ + offsetData_` | **是** → `read_node` |
| 节点向量（level-0 候选） | 341、408、449（`searchBaseLayerST`） | `getDataByInternalId(...)` | 同上 | **是** → `read_node` |
| 节点向量（高层贪心） | 250、296、1319、1381 | `getDataByInternalId(...)` | 同上 | **是** → `read_node` |
| 节点向量（建图启发式） | 492–493、616、624、641 | `getDataByInternalId(...)` | 同上 | **是** → `read_node`（建索引期，本轮不记录） |
| level-0 邻接表 | 382（`searchBaseLayerST`）、273、560、584 | `get_linklist0(...)` | `data_level0_memory_ + i·size_data_per_element_ + offsetLevel0_` | **是** → `read_neighbors(level=0)` |
| 高层邻接表 | 1309、1371（贪心下降）、275、562、586 | `get_linklist(..., level)` | `linkLists_[i] + (level-1)·size_links_per_element_` | **是** → `read_neighbors(level≥1)` |
| 按层分派邻接表 | 527 | `get_linklist_at_level(...)` | 分派到上面两者 | **是**（间接） |
| 删除标记 | 958–960（`isMarkedDeleted`） | `get_linklist0(id) + 2` 读 `DELETE_MARK` 位 | level-0 邻接表块内偏移 | **是**（经 `read_neighbors(level=0)` 同一视图） |
| external label | 199–202（`getExternalLabel`） | `memcpy` from `label_offset_` | 同一节点块内 `label_offset_` | 视作同一节点读取的元数据字段，见 §2.3 |
| entrypoint / maxlevel / cur_element_count | 49、59、38（index 头字段） | 直接成员访问 | 索引头标量 | 索引头元数据，见 §2.3 |

### 2.2 是否存在绕过候选接口的直接内存访问

**存在，但均为非数据依赖、非外部 I/O 的本地访问**，分类如下：

1. **SSE 预取（`#ifdef USE_SSE`）**：行 393、402、424 等处 `_mm_prefetch(data_level0_memory_ + …)` 直接做地址算术。这是 CPU cache hint，**不是逻辑读取、不产生外部可见请求、不改变数据值**；搜索结果不依赖其是否命中。本轮未改动，也不把它计为存储请求。
2. **建索引路径**：`addPoint` / `getNeighborsByHeuristic2` 的读取也经过同一 helper（因此同样被统一封装），但本轮 recorder 仅在查询期开启，建索引期不记录（避免把非查询期读取混入观测向量）。
3. **索引头标量**：`enterpoint_node_` / `maxlevel_` / `cur_element_count` 为索引对象字段，不属于逐节点存储块，按"可信侧已知的索引元信息"处理。

### 2.3 无法统一封装的关键读取路径评估

**没有发现无法统一封装的关键数据读取路径。** 三类核心数据读取（节点向量、level-0 邻接表、高层邻接表）全部由 5 个 inline helper 产生，可在 helper 层单点封装，无需改动搜索控制流。

- `getExternalLabel`（external label，199–202）读取的是**同一节点块内的元数据字段**，地址与节点向量共享 `size_data_per_element_` 基址。本适配把它视为"一次节点读取同时返回的块内字段"，不单独记为请求；这样既保持 ID 映射不变，也避免为记录而额外触发读取。
- 删除标记位于 level-0 邻接表块内偏移（`+2`），经 `read_neighbors(level=0)` 的同一视图覆盖。

---

## 3. Phase 2：最小存储访问适配层

### 3.1 接口

新增 `experiments/h1_rm_3a1_storage_bridge/storage_access.h`：

```
class StorageAccess {
    virtual char*          read_node(uint64_t node_id) = 0;
    virtual unsigned int*  read_neighbors(uint64_t node_id, int level) = 0;
};

class RequestRecorder {
    virtual void record(const StorageRequest&) = 0;
};

struct StorageRequest {
    query_id, seq, request_type, node_id, level, boundary
};
```

`LocalMemoryStorage` 返回**零拷贝视图**（直接指向现有 `data_level0_memory_` / `linkLists_` 的正确偏移），因此距离函数读到的数据与上游 hnswlib 完全相同。

### 3.2 注入点与路由

适配版头文件 `experiments/h1_rm_3a1_storage_bridge/hnswlib_bridge/hnswalg.h` 由 H1-RM.2 头文件复制而来，仅做最小改动（`#ifdef HNSWLIB_RM31_BRIDGE` 保护）：

- 在 `HierarchicalNSW` 加 `mutable StorageAccess* storage_access_{nullptr}` 与 `setStorageAccess()`；
- `getDataByInternalId`：`storage_access_ != nullptr` 时走 `read_node`，否则原路径；
- `get_linklist0`：`storage_access_ != nullptr` 时走 `read_neighbors(id, 0)`，否则原路径；
- `get_linklist`：`storage_access_ != nullptr` 时走 `read_neighbors(id, level)`，否则原路径。

**搜索逻辑（`searchKnn` / `searchBaseLayerST` / `searchStopConditionClosest` / 停止条件 / filter）一行未改。**

### 3.3 观察契约（设计要求逐条核验）

| 设计要求 | 落实 |
| --- | --- |
| 搜索逻辑不直接依赖事件记录器 | 是：搜索逻辑只依赖 `StorageAccess`；记录器挂在 storage 实现内 |
| 节点与邻接表读取经过明确接口 | 是：5 类 helper 全部路由 |
| 记录器只能观察访问请求，不得获取 ACL | 是：`StorageRequest` 无 ACL 字段；ACL 仍在 `RecordingFilter` 内 |
| 不得传递 `filter_check` 结果给存储观察者 | 是：`StorageRequest` 无 `extra`/授权结果字段 |
| 不得传递距离值、候选集、最终结果 | 是：`StorageRequest` 无距离位模式、无集合内容 |
| 不得改变节点 ID 映射 | 是：label 仍为 `100000+17·i`，external label 读取未改 |
| 不得改变搜索参数与停止条件 | 是：C0/C1/C2 代码未改；EfReplay/KHit 停止条件未改 |
| 不得为记录额外触发索引读取 | 是：每次 `read_node/read_neighbors` 对应搜索原本就要做的一次读取；boundary 为 runner 注入的标记，非索引读取 |

### 3.4 请求记录器

`JsonlRequestRecorder` 只接收 `StorageRequest` 元数据，写入 `requests.jsonl`，字段：`query_id, group, seq, request_type, node_id, level, boundary`。每组起止各写一条 `boundary`（`query_start` / `query_end`），`seq` 在组内连续。

---

## 4. Phase 3：语义保持验证

对照：baseline（`bridge=0`）vs bridged（`bridge=1`），同配置、同查询、同 filter、同停止条件。

| 验证项 | 结果 |
| --- | --- |
| Top-K 节点 ID | 完全一致（topk.jsonl 逐字节相同，SHA `69fc51ea…`） |
| Top-K 距离 bit pattern | 完全一致（同上） |
| `events.jsonl` 全流 | 逐字节一致（SHA `9efcb897…`，69,394,286 B） |
| `distance_eval` 序列 | 0 mismatch（108,152 事件） |
| `candidate_consider` 序列 | 0 mismatch |
| `filter_check` 顺序及结果 | 0 mismatch（含 `extra` 授权结果字段） |
| `result_add` / `result_remove` 序列 | 0 mismatch |
| `stop_check` 顺序 | 0 mismatch |
| `search_stop` 位置 | 0 mismatch |
| 节点 ID 映射 | 一致（`external_id` 字段逐条相同） |
| 与 H1-RM.2 既有产物 | baseline 的 topk.jsonl / run_summary.jsonl 与 `results/h1_rm2/trace_on/` **逐字节一致** |

逐类型 mismatch 全为 0：`distance_eval, filter_check, stop_check, candidate_pop, candidate_consider, result_add, result_remove, search_stop`。

**C0/C1/C2 分别成立**：三组各自的事件流在所有 8 类事件上均 0 mismatch；与 H1-RM.2 一样，C0/C1 的对齐仅限本测试配置下的轨迹与 Top-10 前缀一致，不代表两个 API 的完整语义等价（沿用 H1-RM.2-R1 口径）。

### 4.1 请求记录验证

| 检查 | 结果 |
| --- | --- |
| 请求有序 | 是，150 个 (query, group) 单元内 `seq` 严格递增 |
| 重复请求键 | 0（`(type,node_id,level,seq)` 无重复） |
| 未记录索引读取 | 交叉验证：`node_read ≥ distance_eval` 在 150/150 单元成立；每个距离计算前均有对应节点读取。限于 §2 审计的三类 helper 覆盖范围 |
| 批量读取 | 无；一次请求记录对应一个节点或一条邻接表 |
| 查询关联 | 是，每条请求带 `query_id` 与 `group` |
| 请求结束边界 | 是，150/150 单元均有 `query_start` 与 `query_end` |
| 请求量 | 总 253,302 条：node_read 108,796 / neighbor_read 144,206 / boundary 300 |

分组：C0 node_read 50,998 / neighbor_read 69,405；C1 node_read 51,642 / neighbor_read 69,405；C2 node_read 6,156 / neighbor_read 5,396（boundary 各 100）。C2 请求量显著低，与其 K-hit 提前停止一致。

### 4.2 记录内容不包含什么（防过度声明）

请求轨迹**不包含**：ACL 位图、`filter_check` 布尔结果、距离值/位模式、候选集、结果集、Top-K 内容。它是一个**访问请求序列**，不是授权信息序列。是否从"访问了哪些节点/邻接表"能推断授权成员，属于 H1-RM.3B 的后续问题，本轮不研究、不下结论。

---

## 5. Phase 4：准入结论

**PASS — 访问桥接成立**（仅限本地适配层）。

- 关键读取路径全部经过统一接口：成立（§2、§3）。
- 请求可记录：成立（§4.1）。
- 适配前后搜索语义完全一致：成立（§4，逐字节）。

因此允许进入"研究请求轨迹是否包含授权成员信息"的后续阶段——但**必须**先满足下一阶段自身的准入门槛，且本结论**不**自动授权 H1-RM.3B 启动。

若按更严格口径把"SSE 预取直接地址算术"或"external label 字段读取未单独记为请求"视为未覆盖路径，则可降为 CONDITIONAL。本报告选择 PASS 的理由已在 §2.2–2.3 说明：二者分别是非语义 cache hint、与节点读取共享同一内存块的元数据字段，均不产生独立的外部可见请求。这一判定是**工程口径**，不是架构已验证的声明。

---

## 6. 限制与未验证假设

1. **本地 vs 远程边界**：本探针在单进程内运行；`StorageAccess` 返回本地内存指针。真实存储侧的可见性还需定义实际的请求/传输粒度（逐节点？逐邻接表？批量？）、网络协议、查询句柄与结束信号。
2. **未验证假设**：external label 随节点块一起可得、prefetch 不构成侧信道、索引头标量为可信侧已知——这些是建模假设，不是已验证的部署事实。任务包明确排除 cache/页表/物理内存观测，故 prefetch 不计入攻击者能力。
3. **未覆盖路径**：§2.2 列出的 SSE 预取与建索引期读取未纳入请求记录；后者不影响查询期观测向量，前者非逻辑读取。
4. **不声称**：不声称真实远程存储已验证、不声称 TEE 隔离、不声称成员推断成立、不声称跨存储原子性或任何性能优势。
5. **大日志处理**：完整 `events.jsonl`（69 MB×2）与 `requests.jsonl`（27 MB）为可再生原始产物，已 gitignore；提交的是 `events_audit.jsonl`、`requests_audit.jsonl` 子集与 `raw_hashes.json` 全量哈希。

---

## 7. 文件清单

新增（均在 `experiments/h1_rm_3a1_storage_bridge/` 或 `results/h1_rm_3a1/` 或 `docs/`）：

- `storage_access.h` — 接口、请求结构、LocalMemoryStorage
- `hnswlib_bridge/*` — 适配版 hnswlib 头（7 个，含复制的 6 个 + 改动的 hnswalg.h）
- `main.cpp` — runner（H1-RM.2 runner 派生，增加 bridge 开关与请求记录，搜索调用未改）
- `build_and_run.sh`、`compare.py`、`make_manifest.py`、`make_audit_subset.py`
- `results/h1_rm_3a1/` — baseline/、bridged/、comparison/、审计子集、哈希、manifest
- `docs/H1_RM_3A1_STORAGE_ACCESS_BRIDGE.md` — 本报告

修改的既有文件：仅 `.gitignore`（追加 3 条本轮大日志忽略规则）。

冻结产物（H1.1–H1.4、EXP-10A、H1-RM.2、H1-RM.2-R1、H1-RM.3A）与原始基线实验数据：未改。
