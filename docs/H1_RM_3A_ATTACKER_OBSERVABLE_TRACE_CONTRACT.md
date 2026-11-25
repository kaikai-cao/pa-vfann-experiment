# H1-RM.3A — Attacker-Observable Trace Contract Audit

- 基线：`ea7b7bdbd3c76ec08549a452bd4c631d32705ef6`（父提交 `20c1e5a98477da6123be68f2e5575513ab5d3d68`）
- 分支：`research/h1-rm-3a-attacker-observable-trace`
- 性质：**只读架构与观测契约审计**。不修改源码、过滤算法、事件采集器、实验数据或冻结产物；不重跑 HNSW 实验；不生成成员推断结果；不启动 H1-RM.3B。
- 核心结论：当前 hnswlib 实现只有**进程内指针访问 + 本地事件日志**，尚未实现任务假设中的可信执行侧与不可信存储侧之间的外部读取接口。因此当前不能把内部 trace 直接当作攻击者观测。准入门槛为 **CONDITIONAL — 需要先补足桥接**。

---

## A. 系统架构

### A.1 当前 hnswlib 单进程测试架构（已实现）

```
[Harness: experiments/h1_rm2_native_stop/main.cpp]
  - base / query 向量在进程内生成
  - ACL = authorized(label) 纯函数，位于同一进程
  - RecordingFilter 调用 authorized()，可选地 emit filter_check
  - 每个 (query, group) 设置 g_rm2_current_query_id / g_rm2_group
        |
        v
[Instrumented hnswlib: third_party/hnswlib-v0.9.0-rm2-instrumented/]
  - data_level0_memory_ / linkLists_ 为同进程 malloc 得到的内存缓冲区
  - searchKnn / searchBaseLayerST / searchStopConditionClosest 直接指针算术读取
  - RM2_EV(...) -> rm2_emit(...) -> 进程内 std::vector<Rm2Event> g_events
        |
        v
[查询结束后] ofstream 写 events.jsonl / topk.jsonl / run_summary.jsonl
```

事实边界：

1. 当前代码中 ACL 与搜索、过滤、索引数据处于同一进程；不存在独立的可信侧/不可信存储侧进程边界。
2. 当前节点与邻接表访问是 `data_level0_memory_` / `linkLists_` 上的指针算术，不是发往存储侧的请求。证据：`hnswalg.h:64-65`（两个内存缓冲）、`216-217`（`getDataByInternalId`）、`511-512`（`get_linklist0`）、`521-522`（`get_linklist`）。
3. 唯一的外部写文件发生在查询循环之后，用于保存实验日志（`main.cpp:280-283`、`321-333`、`335-344`、`346-378`）。这不是搜索过程中的存储读取 I/O。
4. 仓库中不存在 `node_read`、`neighbor_list_read`、`query_end` 事件或同名外部接口（全文检索无匹配）。

### A.2 本任务假设的可信/不可信架构（未实现）

```
Trusted execution side                         Untrusted storage side
---------------------------------------------------------------------
- holds ACL bitmap                             - holds / serves HNSW index payload
- receives query q                             - observes data-read requests it receives
- executes HNSW search                         - does NOT hold ACL bitmap
- runs authorization callback                  - does NOT know whether a node was allowed
- decides stop                                  - does NOT see final authorized result
- handles final Top-K

        |  read node vector / read neighbor list (conceptual bridge)
        | ---------------------------------------------------------->
        |                                              observes request order
        | <---------------------------------------------------------- node/adjacency payload
        |
        |  [no implemented request_end signal in current code]
```

该架构是本任务的**假设**，不是当前代码已实现的事实。当前 hnswlib 没有 RPC、socket、远程文件读取或任何按节点粒度的外部访问接口；也没有查询作用域的请求 ID / 会话边界。

### A.3 尚未实现或验证的桥接假设

要把 A.2 变成可实验的观测契约，至少需要明确并验证：

1. 是否存在按节点/邻接表粒度的外部读取接口；若存在，请求中携带 internal `tableint` 还是 external label；
2. 节点向量与邻接表是两个独立请求，还是打包为同一节点负载返回；
3. 请求是否能关联到具体查询（query handle / session / request ID）；
4. 是否存在显式 `request_end` / end-of-query 信号；
5. 是否允许批量读取；若允许，批内顺序是否对存储侧可见；
6. 停止决定是否以任何形式跨边界传递；若无，存储侧最多只能从“不再有后续读取”推断停止；
7. 查询向量是否跨越边界；当前代码只在可信侧内部使用 `qv`，未作为独立存储请求字段定义。

以上任一项未定义时，相关可观测字段记为 `UNKNOWN`，不得从内部 logger 推导为存储侧能力。

---

## B. 事件可见性表

行号均指基线中 `third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib/hnswalg.h`，除另注。`RM2_EV` 定义见 `hnswalg.h:13-25`，其 sink 实现见 `experiments/h1_rm2_native_stop/main.cpp:63-80`。

### B.1 逐事件源码审计

| 事件 | 源码位置 / 函数 | 触发条件 | 外部 I/O | 节点 ID | 授权结果 | 当前存储侧 | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 节点读取（概念事件 `node_read`） | `getDataByInternalId`, `hnswalg.h:216-217`；调用点 `341`、`408`、`492-493` 等 | 计算距离或结果维护时取向量指针 | 无；同进程指针算术 | 内部 `tableint` 用于寻址；RM2 trace 额外记录 external label（`15-20`） | 否 | 不可见 | 代码中**没有** `node_read` 事件；桥接后才可能成为可见读取请求 |
| 邻接表读取（概念事件 `neighbor_list_read`） | `get_linklist0`, `hnswalg.h:511-512`；`get_linklist`, `521-522`；调用点 `382`、`1309`、`1371` | 候选节点被 pop 后展开邻居；上层 greedy descent 也读取高层邻接表 | 无；`data_level0_memory_` 与 `linkLists_` 是两个同进程缓冲（`64-65`） | 内部 `tableint` | 否 | 不可见 | 代码中**没有** `neighbor_list_read` 事件；是否独立读取取决于未实现的桥接契约 |
| `distance_eval` | `searchBaseLayerST`, `342-343`、`409-410`；`searchKnn`, `1300-1301`、`1319-1320`；`searchStopConditionClosest`, `1362-1363`、`1381-1382` | `fstdistfunc_` 计算完距离后由 `RM2_EV` 记录 | 无；距离函数在进程内调用 | trace 有 internal + external ID、level | 否 | 不可见 | 内部 trace 有 `dist_bits`，但存储侧不能观察距离值/位模式；不假设 cache/时序侧信道 |
| `candidate_consider` | `searchBaseLayerST`, `412-420` | `should_consider_candidate`（或标准 `size<ef \|\| lowerBound>dist`）判定后 | 无 | trace 有 internal + external ID、距离、考虑决策位 | 否 | 不可见 | 纯内部候选判定；不属于存储请求 |
| `candidate_pop` | `searchBaseLayerST`, `378-379` | `candidate_set.pop()` 后 | 无 | trace 有当前候选 ID | 否 | 不可见 | 纯内部优先队列操作 |
| `filter_check` | `isIdAllowed` 调用点 `340`、`430`；`BaseFilterFunctor` 定义 `hnswlib.h:128-131`；实验实现 `main.cpp:109-134` | 入口点或候选通过 consider 后，调用 `(*isIdAllowed)(getExternalLabel(id))` | 无；回调在进程内执行 | 回调参数是 external label；trace 另记录恢复出的 internal ID | trace 的 `extra` 承载 ok/fail；存储侧**不知道** | 不可见（直接） | 不能把 `filter_check.extra=1` 写成攻击者可见授权结果；间接路径依赖属于待研究问题，不是已证事实 |
| `result_add` | `searchBaseLayerST`, `345-346`、`431-432`；stop-condition 镜像 `348`、`434` | filter 通过后将节点加入 `top_candidates` / 结果集合 | 无 | trace 有 internal + external ID | 否 | 不可见 | 内部结果维护；最终 Top-K 按模型不暴露给存储侧 |
| `result_remove` | `searchBaseLayerST`, `444-453` | 结果集合超过 ef 规则时 pop 并调用 stop-condition 回调 | 无 | trace 有 internal ID | 否 | 不可见 | 纯内部结果维护 |
| `stop_check` | `searchBaseLayerST`, `362-373`；`BaseSearchStopCondition` 接口 `hnswlib.h:134-150` | 每轮 `candidate_set` 循环顶部判定是否停止 | 无 | trace 有当前候选 ID、决策位 | 否 | 不可见 | C2 的 `KHitStopCondition::should_stop_search` 在 `main.cpp:186-189` 读取 `g_rm2_auth_hits`；该计数不跨边界 |
| `search_stop` | `searchBaseLayerST`, `374-377` | `flag_stop_search` 为真时 `break` | 无 | trace 有当前候选 ID | 否 | 不可见（直接） | 存储侧最多从“后续读取停止”觉察结束；不能观察该内部事件或对应节点。H1-RM.2 的 27.58 事件序号差是内部 trace 量，不是存储侧时序量 |
| `query_end` | 无源码事件；harness 查询循环 `main.cpp:287-317`，日志写在其后 `321-378` | harness 完成一个 `(q,group)` 调用 | 无 | trace 的 `query_id` 是 harness 全局（`37`、`289`） | 否 | 不可见 | 仓库无 `query_end`；当前 hnswlib 接口不接收 query ID，也没有跨边界查询结束信号 |

### B.2 任务要求的可见性摘要

| 事件 | 可信侧可见 | 存储侧可见 | 可见内容 | 证据 |
| --- | --- | --- | --- | --- |
| 节点读取请求 | 是（同进程指针访问） | 当前否；桥接后条件可见 | 当前无外部内容；桥接后可能含节点标识，命名空间未定义 | `hnswalg.h:216-217`, `64-65`; 无 `node_read` 事件 |
| 邻接表读取 | 是（同进程指针访问） | 当前否；桥接后条件可见 | 当前无外部内容；桥接后是否独立请求未定义 | `hnswalg.h:511-512`, `521-522`, `382`, `1309`, `1371`; 无 `neighbor_list_read` 事件 |
| `distance_eval` | 是（内部计算 + trace） | 否 | 内部 trace：internal/external ID、level、`dist_bits`；存储侧无 | `hnswalg.h:15-20`, `342-343`, `409-410`, `1300-1301`; `main.cpp:63-80` |
| `filter_check` | 是（回调 + trace） | 否（直接） | 内部 trace：external/internal ID 与 ok/fail；存储侧无 ACL、无布尔结果 | `hnswalg.h:340`, `430`; `hnswlib.h:128-131`; `main.cpp:109-134` |
| `search_stop` | 是（内部 break + trace） | 否（直接） | 内部 trace：事件序号与候选 ID；存储侧最多观察读取停止 | `hnswalg.h:362-377`; `results/h1_rm2/gate.json` |
| `query_end` | 是（harness 循环边界） | 当前否；桥接后才可能 | 当前仅有本地日志写入；无跨边界请求结束 | `main.cpp:287-317`, `321-378`; 无 `query_end` 事件 |

**禁止推导**：事件被 `rm2_emit` 写入 `events.jsonl` 只说明同一进程中的实验记录器可见，不说明不可信存储侧可见。

---

## C. 攻击者最终观测向量

### C.1 候选定义

\[
O(q) = (r_1, r_2, \ldots, r_n, \text{request\_end})
\]

其中每一项是候选桥接后的读取记录，而不是当前代码已产生的事件：

- \(r_i\) 只能是 `node_read` 或 `neighbor_list_read` 两类外部读取请求之一；
- \(r_i\) 是否包含节点 ID：**待定义**。当前 logger 同时持有 internal `tableint` 与 external label（`hnswalg.h:15-20`），但外部读取请求应携带哪一种尚无契约；
- 请求顺序：**桥接后可见**；当前代码只有内部 `event_index`，不能当作请求序号；
- 是否能关联到查询：**当前不可**。`query_id` 只在 harness 全局设置（`main.cpp:37`, `289`），未传入 hnswlib 或存储接口；需要显式 query handle / session；
- 批量读取：**UNKNOWN**。当前代码没有批量读取；桥接是否保留逐请求粒度未知；
- 停止位置精度：最多是最后一个 \(r_n\) 加 `request_end` 的序列位置；不能观察内部 `search_stop` 事件、其候选 ID 或 K-hit 事件序号差。

### C.2 当前不可观察字段

- ACL 位图、policy 类型、任何节点的授权布尔值；
- `filter_check` 的 ok/fail 结果（`main.cpp:119-124` 的 `extra` 只是本地 trace 字段）；
- `candidate_set`、`top_candidates`、`EfReplayStopCondition::R_`（`main.cpp:150-152`）等内部数据结构；
- 距离值、`dist_bits`、`lowerBound`、`candidate_consider` / `stop_check` 决策位；
- 最终 Top-K / 返回集合大小；按模型存储侧看不到结果处理；
- `search_stop` 事件本身、H1-RM.2 的 K-hit→stop 事件序号差；
- CPU cache、页表、物理内存访问（任务明确不赋予）；
- 反事实的完整 HNSW 路径（例如假设预算 \(B=1000\) 的未走分支）；
- 查询向量，除非桥接协议另行定义；当前只作为 `searchKnn` 参数在可信侧内部使用。

### C.3 缺失条件 / Required bridge assumptions

当前代码**无法支持**上述 \(O(q)\) 的直接实例化。缺失条件：

1. 无外部存储访问适配层；`getDataByInternalId` / `get_linklist*` 均为同进程指针运算；
2. 无请求 ID / query handle，因此无法把 \(r_i\) 关联到具体 \(q\)；
3. 无 `request_end` 或等价的查询结束消息；
4. 无节点读取与邻接表读取的打包/分离契约；
5. 无 ID 命名空间契约（internal `tableint` 还是 external label）；
6. 无批量读取契约；
7. 无停止信号跨边界传递，存储侧只能依赖“不再请求”这一弱观察。

在这些条件补足并验证前，`O(q)` 只是候选抽象，不是已观测数据。

---

## D. 与 H1.1–H1.4 的关系

| 阶段 | 标记 | 依据与结论 |
| --- | --- | --- |
| H1.1 公开固定路径假设 | **不可迁移（原假设）** | H1.1 用 `plan_fixed_trace(q, graph, 1000)` 从公开图/查询重建固定路径，并以 1600/1600 `trace_sha16` 匹配验证；当前 HNSW 路径是自适应且受过滤结果影响：`candidate_consider` 依赖 `top_candidates.size()` / `lowerBound`（`hnswalg.h:416`, `414`），`lowerBound` 又在结果维护后更新（`456-457`），C2 停止还直接依赖 `g_rm2_auth_hits`（`main.cpp:186-189`）。因此不能把存储侧看到的读取前缀当作 H1.1 的公开固定路径 \(\pi_q\)。 |
| H1.2 独立 ACL 统计设计 | **可直接复用（仅统计单位与重采样方法）** | H1.2 以 ACL 实例为唯一抽样单位、每个 cell 30 个 ACL、5,000 次 ACL-level bootstrap，不用 query-level bootstrap（`H1_2_INDEPENDENT_ACL_GENERALIZATION.md:92`）。该统计单位设计可复用到任何新的 HNSW 观测数据；但 H1.2 的 240 个 ACL、固定公开路径和结果表不可直接搬用。 |
| H1.3 前缀约束推断 | **不可迁移** | H1.3 的约束来自固定路径上的 E1 停止规则：`m<τ<B` 时 `Σ_{i=1}^{τ-1}a_{π[i]}=K-1` 且 `a_{π[τ]}=1`（`H1_3_PREFIX_CONSTRAINT_INFERENCE.md:28-34`）。当前 C2 的 K-hit 到 `search_stop` 有额外事件，且授权命中范围为 10–14、返回集合为 10–14（`gate.json`），停止点不再是 K-hit 点。固定路径与 τ 语义均不成立，原线性约束不能套用。 |
| H1.4 负成员推断结论 | **不可迁移** | H1.4 的结论建立在 H1.3 的负标签与固定先验对照上（`H1_4_PRIOR_AWARE_LEAKAGE_EVALUATION.md:20-33`, `86-90`）；H1.3 不可迁移，则该结论亦不可迁移。B0/B1/B2 + 配对 bootstrap 的**评估框架**可在有新攻击输出后复用，但 `ΔBA`、零误报和 `CANDIDATE_NEGATIVE_MEMBERSHIP_LEAKAGE` 裁决不能写成当前 HNSW 的已验证效果。 |

不得把 H1.1–H1.4 的合成图/固定路径结果表述为真实 HNSW 上的已验证攻击效果。

---

## E. H1-RM.3B 准入结论

**CONDITIONAL — 需要先补足桥接**

理由：

1. 任务定义的威胁模型与现有代码**不直接冲突**：当前实验用确定性 `authorized()` 模拟 ACL，存储侧在假设中不持有 ACL，也不看最终结果；这与“可信侧持 ACL、存储侧不持 ACL”的方向一致。
2. 但当前实现只有内部 trace：8 类事件全部由 `RM2_EV` / `rm2_emit` 写入进程内向量和本地 JSONL（`hnswalg.h:13-25`; `main.cpp:63-80`, `321-333`）。没有证据表明不可信存储侧能观察这些事件。
3. 攻击者观测向量 \(O(q)\) 所需的关键字段——读取请求、节点标识、顺序、查询关联、请求结束、停止粒度、批量规则——在当前代码中均缺失或未定义（C.3）。
4. 因此还不能进入 3B 的成员推断实验；需要先做一个**最小化、范围明确的存储访问适配层**验证，逐项确认 C.3 的桥接假设。该适配层不得改变过滤算法、停止语义或既有结果。

本轮到此停止，不创建攻击模型、不生成成员推断结果、不启动 H1-RM.3B。

---

## F. 一次性有限一致性检查

| 检查 | 结果 |
| --- | --- |
| 每个可见性判断有源码或明确架构契约支持 | PASS；A/B 节逐项给出文件、函数、行号或标注 UNKNOWN |
| 每个事件名称与实际实现一致 | PASS；实际事件为 `distance_eval`、`candidate_consider`、`candidate_pop`、`filter_check`、`result_add`、`result_remove`、`stop_check`、`search_stop`；`node_read` / `neighbor_list_read` / `query_end` 明确标注为不存在 |
| 内部日志与外部可见 I/O 不混淆 | PASS；`rm2_emit` 写入 `g_events`，`ofstream` 查询后写本地文件；均未称为外部存储请求 |
| H1.1–H1.4 迁移结论有依据 | PASS；逐项引用对应冻结报告的假设/统计单位/约束来源 |
| 准入结论与证据一致 | PASS；只有内部 trace 且桥接缺失 → CONDITIONAL |
| 文档没有把假设写成实验事实 | PASS；A.2 与 C.3 明确标注为假设/缺失条件 |

本轮未修改任何源码、事件采集器、CSV、JSONL、manifest、gate 或 EXP-10A / H1.1–H1.4 / H1-RM.2 冻结产物；未下载数据；未重跑 HNSW；未建 PR。
