# H1-RM.3A.1-R1 — External Label Read Boundary Closure

局部修正报告。目标单一：修复 `getExternalLabel()` 的存储读取边界，使代码实现与
`StorageAccess` 接口契约一致。不重新设计适配层，不重跑 50-query 全量实验，
不启动 H1-RM.3B，不修改任何冻结产物。

- 仓库：`kaikai-cao/pa-vfann-experiment`
- 基线分支：`research/h1-rm-3a1-storage-access-bridge`
- 基线 SHA：`c7e8189fe60a5d40a5f6aa16b8e0912e0a879e17`
- 父提交：`6d63c070fd3e64da3cbb08514a231dde8dd48f38`
- 本分支：`research/h1-rm-3a1-r1-label-boundary`

---

## 1. 原始问题及精确源码证据

### 1.1 节点内存块布局（基线 `hnswlib_bridge/hnswalg.h` 构造区，原行 151–157）

```
size_links_level0_      = maxM0_ * sizeof(tableint) + sizeof(linklistsizeint);
size_data_per_element_  = size_links_level0_ + data_size_ + sizeof(labeltype);
offsetData_             = size_links_level0_;                    // 向量起点
label_offset_           = size_links_level0_ + data_size_;       // label 起点
offsetLevel0_           = 0;                                     // L0 邻接表起点
data_level0_memory_     = malloc(max_elements_ * size_data_per_element_);
```

`labeltype = size_t`（`hnswlib.h:125`），本次为 64 位 = 8 字节。单个节点块
`base = data_level0_memory_ + i * size_data_per_element_` 的字节布局：

| 偏移 | 内容 | 大小 |
| --- | --- | --- |
| `offsetLevel0_ = 0` | L0 邻接表 count + ids | `size_links_level0_` |
| `offsetData_` | 向量数据 | `data_size_`（16×4=64 B） |
| `label_offset_` | external label | `sizeof(labeltype)`（8 B） |

三个字段同处一个连续节点块，`label_offset_ + sizeof(labeltype) == size_data_per_element_`。

### 1.2 三处不一致的证据

| 位置 | 基线代码 | 问题 |
| --- | --- | --- |
| `hnswalg.h` 原 216–220 `getExternalLabel()` | `memcpy(&label, data_level0_memory_ + id*size_data_per_element_ + label_offset_, ...)` | 直接读裸指针，**完全绕过 `storage_access_`**。bridge=1 时 label 读取不出现在请求日志。 |
| `storage_access.h` 原 73–82 `read_node()` | 返回 `char* = ... + offsetData_`（向量起点） | 无 `size`、无 label 偏移信息；返回指针按契约只覆盖向量，label 不在其范围内。 |
| `storage_access.h` 原 41–43 注释 | 声称 "Metadata fields (external label, delete mark) live inside the same node block and are parsed from the returned view" | 与实现矛盾：`getExternalLabel()` 从不解析任何 view。 |

结论：3A.1 报告 §2.2 中"label 随同一次节点块读取的块内视图获得、不额外触发读取"
属于**接口设计意图**，但实现并未兑现——查询期 label 读取实际走裸内存。本轮闭合此差距。

### 1.3 区分四种 label 读取场景（不得混为一谈）

| 场景 | 调用点（修复后行号） | 是否进入查询请求轨迹 |
| --- | --- | --- |
| 搜索查询期：filter 授权判断 | 397、487（`(*isIdAllowed)(getExternalLabel(...))`） | **是**，应走接口 |
| 搜索查询期：结果集维护 | 405、491、506（`add_point_to_result` / `remove_point_from_result`） | **是**，应走接口 |
| 搜索查询期：C0 结果序列化 | 1415（`searchKnn` 的 `result.push`） | **是**，应走接口 |
| 事件记录（RM2_EV 宏） | 27 | **否**，可信侧测试插桩，必须走 raw |
| 索引加载 / 替换更新 | 890、1074（+1075 写） | **否**，构建/更新期，走 raw |
| 写操作 | 1075 `setExternalLabel`、1296 `getExternalLabeLp`+`memcpy` | **否**，本轮明确不改 |

---

## 2. 节点内存布局（修复后，未改变）

布局常量与 1.1 完全相同，本轮**未改字节布局、未改 ID 映射、未改距离输入**。
`internal id = i` ↔ `external label = 100000 + 17*i` 映射保持不变。

---

## 3. 修复前后的接口契约

### 3.1 修复前

```
StorageAccess::read_node(id) -> char*               // 仅向量起点，无 size
StorageAccess::read_neighbors(id, level) -> uint*   // 邻接表
getExternalLabel(id) -> 裸 data_level0_memory_ 读取  // 绕过接口
```

### 3.2 修复后（`storage_access.h`）

```
struct NodeView { const char* base; std::size_t size;
                  bool covers(offset, bytes) const; };   // 完整节点块零拷贝视图
StorageAccess::read_node(id)   -> NodeView   // RequestType::node_read
StorageAccess::read_label(id)  -> NodeView   // RequestType::label_read（本轮新增）
StorageAccess::read_neighbors(id, level) -> unsigned int*  // 不变

getExternalLabel(id):
    bridge 已注入 -> read_label(id) 得到 NodeView，covers 校验后从 base+label_offset_ memcpy
    bridge 未注入 -> getExternalLabelRaw(id)（与冻结基线逐字节相同）
getDataByInternalId(id):
    bridge 已注入 -> read_node(id) 得到 NodeView，covers 校验后返回 base+offsetData_
    bridge 未注入 -> 原裸指针路径
getExternalLabelRaw(id): 保留原实现，供 RM2_EV / loadIndex / replacePoint 使用，不进请求轨迹
```

关键设计点：

1. **零拷贝**：`NodeView.base` 直接指向既有 `data_level0_memory_` 块，无 `memcpy` 节点数据。
2. **内存安全**：`NodeView::covers()` 显式校验 `label_offset_ + sizeof(labeltype) <= size` 与
   `offsetData_ + data_size_ <= size`；越界即 `throw`，不强行使用不安全指针。
3. **生命周期**：视图只在单次调用内使用，不缓存、不跨查询持有，指针有效性由 index 生命周期保证。
4. **写路径隔离**：`setExternalLabel()` / `getExternalLabeLp()` 完全未改，仍为裸写；未通过只读
   `read_node()` 处理写操作。
5. **事件记录隔离**：`RM2_EV` 宏改用 `getExternalLabelRaw()`，使 trace 开启时不会向请求日志
   注入 label 读取；请求日志只反映"搜索算法真正需要的 label 读取"。

### 3.3 修改文件清单

| 文件 | 修改 |
| --- | --- |
| `experiments/h1_rm_3a1_storage_bridge/storage_access.h` | 新增 `NodeView`；`read_node` 改返回 `NodeView`；新增 `read_label` 与 `label_read` 类型；`LocalMemoryStorage` 用单一 `block_view()` 生成视图 |
| `experiments/h1_rm_3a1_storage_bridge/hnswlib_bridge/hnswalg.h` | `getExternalLabel()` 走接口 + 安全校验；新增 `getExternalLabelRaw()`；`getDataByInternalId()` 走 `read_node()` 视图；`RM2_EV` 宏改用 raw |
| `experiments/h1_rm_3a1_storage_bridge/main.cpp` | 请求类型名加 `label_read`；新增可选第 4 参数 `nqueries`（默认 50，不改默认行为）供小规模验证 |
| `experiments/h1_rm_3a1_storage_bridge/verify_r1.py` | 新增：R1 逐字节与请求契约验证 |
| `experiments/h1_rm_3a1_storage_bridge/make_r1_artifacts.py` | 新增：审计子集/哈希/manifest 生成 |
| `.gitignore` | 新增 3 条 R1 全量日志忽略规则 |
| `results/h1_rm_3a1_r1/*` | 新增独立结果目录 |

未触碰：EXP-10A、H1.1–H1.4、H1-RM.2、H1-RM.2-R1、H1-RM.3A、H1-RM.3A.1
已有产物与报告；未改搜索参数、过滤/停止条件、距离函数、索引数据。

---

## 4. 查询期间 label 读取调用路径（修复后）

| 行号 | 函数 | 场景 | 读取方式 |
| --- | --- | --- | --- |
| 397 | `searchBaseLayerST<false>` | entrypoint filter 授权 | `getExternalLabel()` → `read_label()` |
| 405 | `searchBaseLayerST<false>` | entrypoint 加入结果集 | `getExternalLabel()` → `read_label()` |
| 487 | `searchBaseLayerST<false>` | 候选 filter 授权 | `getExternalLabel()` → `read_label()` |
| 491 | `searchBaseLayerST<false>` | 候选加入结果集 | `getExternalLabel()` → `read_label()` |
| 506 | `searchBaseLayerST<false>` | 结果集剔除 | `getExternalLabel()` → `read_label()` |
| 1415 | `searchKnn` | C0 结果序列化 | `getExternalLabel()` → `read_label()` |

6 处查询期读取全部经 `read_label()`；`getExternalLabel()` 内 `bridge==nullptr` 时的
raw fallback 只在 bridge 未注入（baseline / 构建期）生效，运行期 bridge=1 时不会走到。

源码核对命令结果：
- `getExternalLabel(` 调用点：397/405/487/491/506/890/1074/1415（+定义 234）
- `getExternalLabelRaw` 调用点：27（RM2_EV 宏）、247（fallback 返回）
- 890/1074 为 loadIndex/replacePoint，非查询期；本 runner 用 addPoint 建索引，不触发。

---

## 5. C0/C1/C2 小规模验证结果

配置：与冻结实验完全相同（N=1000, dim=16, IP, M=16, efC=200, efS=64, k=10,
seed=2026, label=100000+17*i）。取**前 5 个 query**，每个跑 C0/C1/C2 三组，
共 15 个 (query, group) 单元。对照：

- 原始适配层基线：`bridge=0`（不注入 StorageAccess，走 raw 路径）
- 修复后桥接：`bridge=1`（注入 StorageAccess，向量与 label 读取全部走接口）

| 检查项 | 验收标准 | 结果 |
| --- | --- | --- |
| Top-K external ID | 完全一致 | ✅ topk.jsonl 逐字节一致（SHA `60c04c7d…`） |
| Top-K distance bits | 完全一致 | ✅ 同上（同一文件含 dist_bits） |
| `distance_eval` 序列 | 顺序和内容一致 | ✅ events.jsonl 逐字节一致（SHA `a4bfb447…`） |
| `filter_check` 顺序与结果 | 一致 | ✅ 同上，`extra` pass/fail 位一致 |
| `candidate_consider` | 一致 | ✅ 同上 |
| `result_add`/`remove` | 一致 | ✅ 同上 |
| `stop_check`/`search_stop` | 顺序和位置一致 | ✅ 同上，`khit_event_index`/`first_search_stop_index` 见 summary |
| internal/external ID 映射 | 完全一致 | ✅ 冻结基线 head 与 R1 head 逐字节一致 |
| 请求日志 label 读取 | 遵守新接口契约 | ✅ 新增 `label_read`，全部来自 `read_label()` 视图 |
| 请求顺序 | 严格递增 | ✅ 15/15 单元 seq 严格递增，0 违规 |
| 查询边界 | 开始/结束匹配 | ✅ 15/15 单元恰有 1 个 `query_start` 与 1 个 `query_end` |

逐字节语义对照同时与 H1-RM.3A.1 冻结基线前 5 query 完成比对：
`topk.jsonl` head(15) 与 `run_summary.jsonl` head(15) 均逐字节一致
（`TOPK_MATCHES_FROZEN_HEAD` / `SUMMARY_MATCHES_FROZEN_HEAD`）。

数据见 `results/h1_rm_3a1_r1/verification.json`、`raw_hashes.json`、
`events_audit.jsonl`、`requests_audit.jsonl`。

---

## 6. 请求日志变化及原因

冻结 3A.1（50-query）已提交请求审计子集类型：`boundary`/`node_read`/`neighbor_read`，
**无 `label_read`**。R1（5-query）请求类型分布：

| request_type | 数量 | 说明 |
| --- | --- | --- |
| `boundary` | 30 | 15 单元 × (start+end) |
| `node_read` | 10,914 | 向量读取（现返回完整块视图） |
| `neighbor_read` | 14,529 | 邻接表读取，未改 |
| `label_read` | 8,669 | **本轮新增**：查询期 label 读取经 `read_label()` |

分组明细：C0 `label_read=3,850`；C1 `label_read=4,242`；C2 `label_read=577`
（C2 因 K-hit 提前停止，`node_read=647`/`neighbor_read=575` 显著低于 C0/C1，与停止语义吻合）。

**变化原因**：修复前查询期 label 读取走裸指针、对接口不可见；修复后同一批真实存在的读取
经 `read_label()` 显式记录为 `label_read`。这是把已有读取纳入可观测接口，**不是新增物理读取**：
`label_read` 与对应 `node_read` 返回同一 `NodeView`（同一节点块），验证确认 15/15 单元中
所有 `label_read` 的 node_id 都是该单元 `node_read` node_id 的子集
（`label_read_subset_of_node_read=true`）。为保持请求数不被虚增，`RM2_EV` 事件记录改用
`getExternalLabelRaw()`：events 共 43,102 行而 `label_read` 仅 8,669 条，证明事件记录未注入
label 请求；没有为"让数字相等"而删除任何真实读取事件。

---

## 7. 仍未解决的限制

1. **本地 vs 远程**：本轮仍是单进程本地内存适配层。`PASS` 只表示本地读取边界闭合，
   **不代表**真实远程不可信存储、TEE 隔离或网络侧可观测性成立。
2. **C1/C2 输出标签语义沿用 3A.1**：`searchStopConditionClosest` 返回 internal `tableint`，
   由 runner 经确定性映射对齐 external label；本轮未改这一既有语义。
3. **构建/更新期 label 读取未纳入接口**：`loadIndex`(890)、`replacePoint`(1074/1075)、
   `addPoint`(1296) 仍走 raw。本 runner 建索引期未注入 bridge，这些路径不进入请求轨迹；
   若未来在 bridge 注入后执行更新，需单独扩展契约（本轮明确不扩大范围）。
4. **删除标记 `isMarkedDeleted`** 仍按原方式从 L0 linklist 读取（992–996），本轮未纳入
   `NodeView`；记录为后续风险，不擅自改造。
5. **小规模范围**：验证仅 5 个 query、15 单元，非 50-query 全量；统计功效有限，
   但语义一致性是逐字节判据，不依赖样本量。

---

## 8. Gate 结论

**PASS**。

判据：查询期间所有约定范围内的节点块（向量）、邻接表及 label 读取均经过 `StorageAccess`
接口（`read_node` / `read_neighbors` / `read_label`），`getExternalLabel()` 不再直接读裸内存；
5-query C0/C1/C2 语义保持逐字节通过；请求日志新增 `label_read` 且顺序、边界、归属校验全部通过；
零拷贝视图有 `covers()` 边界保护；写路径与事件记录路径未被误改。

PASS 仅限本地适配层读取边界闭合，不授权启动 H1-RM.3B，不构成真实远程存储可观察性证明，
也不构成成员推断成立或任何性能优势的结论。
