# EXP-10A Phase 0 Report — hnswlib 有序距离计算轨迹可行性探针

**日期**：2026-11-25
**分支**：`exp10-hnswlib-trace-feasibility`
**基线**：`a03364d3c050b4bd65d91d12d8cddc5731cd4923`（EXP-10 Faiss Phase 0 停止提交，零修改）
**裁决**：**PASS — Phase 0 通过**。仅表示 hnswlib v0.9.0 的小规模 `searchKnn` 距离计算轨迹可被完整、可复现地采集；**不自动批准 FiQA 全量实验**。

---

## 0. 本轮边界

本轮为独立的 Phase 0 可行性探针，不是 FiQA 实验，不是 PA-VFANN 新方案选型。未下载 FiQA / qrels / embedding 模型，未构建全量索引，未移植 E1/E2，未设计停止规则，未重建 Faiss，未修改 EXP-01/EXP-08/EXP-09/EXP-09.1 冻结内容，`docs/EXP10_PHASE0_STOP.md` 保持原样。

---

## 1. hnswlib v0.9.0 完整源码 SHA

| 项 | 值 |
| --- | --- |
| Repository | `https://github.com/nmslib/hnswlib` |
| Tag | `v0.9.0`（稳定版；未用 `master`，未用 `v0.10.0-rc.*`） |
| 完整 commit SHA | `d9b3608c83d83b46c96e25088cb1d729b29dcfe9` |
| tree SHA | `1b59aaa0fa12b1ea6faec19c9f0fc387db5d935d` |
| License | Apache-2.0，原文随快照保留 |

实际参与编译文件的 SHA-256（工作区快照，Windows `core.autocrlf=true` 下为 CRLF）与上游 blob 规范化 SHA-256 双列记录于 `third_party/SOURCE_INFO.md`。其中 `hnswalg.h` 工作区 SHA-256 为 `7e5eb7f353c71ed71b3900eff9a47c7a478ed7ca92264f5a6bce4a700614bc43`，上游 blob 规范化 SHA-256 为 `483d3b3193969ef4c35239849b6385dd1086434a7bae1d8181acf287e46666fc`。两组哈希内容语义一致，仅行尾不同；本轮所有编译均使用工作区快照。

插桩后文件 SHA-256：
- `hnswalg.h`: `f232688dee3f5c91d9f3edfc829f814827f120f7b37b1a123616a1505f6a843c`
- 新增 `hnsw_trace_sink.h`: `5e3102a9030ea17cc5c5108039dc244cb1137f3da1b888ab3ee49a876bb0c54d`

patch 已实测：`patch --binary -p1 --dry-run < patches/hnswlib-v0.9.0-query-trace.patch` 对 pristine 快照成功，实际应用后产物与 `third_party/hnswlib-v0.9.0-instrumented/` 逐字节一致。

---

## 2. 编译器版本与完整编译参数

编译器：`g++.exe (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r1) 16.2.0`

上游版：

```
g++ -std=c++17 -O2 -Wall -Wextra \
  -ID:\Research\pa-vfann-exp10-hnswlib-probe-workspace\experiments\exp10a_hnswlib_probe \
  -ID:\Research\pa-vfann-exp10-hnswlib-probe-workspace\third_party\hnswlib-v0.9.0\hnswlib \
  D:\Research\pa-vfann-exp10-hnswlib-probe-workspace\experiments\exp10a_hnswlib_probe\main.cpp \
  -o D:\Research\pa-vfann-exp10-hnswlib-probe-workspace\build\exp10a\exp10a_upstream.exe
```

插桩版：

```
g++ -std=c++17 -O2 -Wall -Wextra -DHNSWLIB_TRACE_ENABLED=1 \
  -ID:\Research\pa-vfann-exp10-hnswlib-probe-workspace\experiments\exp10a_hnswlib_probe \
  -ID:\Research\pa-vfann-exp10-hnswlib-probe-workspace\third_party\hnswlib-v0.9.0-instrumented\hnswlib \
  D:\Research\pa-vfann-exp10-hnswlib-probe-workspace\experiments\exp10a_hnswlib_probe\main.cpp \
  -o D:\Research\pa-vfann-exp10-hnswlib-probe-workspace\build\exp10a\exp10a_instrumented.exe
```

编译日志中的 warning 均来自 hnswlib 上游源码（`unused parameter`、`cand < 0` 对无符号类型恒假、`AVX512Capable` 未使用），插桩未引入新 warning。无 SWIG / BLAS / LAPACK / pybind11 / Python wheel 依赖。构建脚本：`experiments/exp10a_hnswlib_probe/build.ps1`、`run_probe.ps1`。

---

## 3. 实际插桩的函数与代码位置

所有插桩均在 `third_party/hnswlib-v0.9.0-instrumented/hnswlib/hnswalg.h`（行号为插桩版）：

| 位置 | 函数 | 事件位点 | `event_site` |
| --- | --- | --- | --- |
| 1315 | `searchKnn` | 入口点距离计算之后 | `entrypoint` |
| 1337 | `searchKnn` | 上层 greedy descent 候选距离计算之后 | `upper_layer_neighbor` |
| 354 | `searchBaseLayerST` | level-0 入口点距离计算之后 | `level0_entrypoint` |
| 419 | `searchBaseLayerST` | visited 检查通过后的候选距离计算之后 | `level0_neighbor` |

另有两个**非事件**插桩点：构造函数（第 126 行）与 `loadIndex`（第 785 行）把 `fstdistfunc_` 替换为独立计数包装器。包装器保存在 `hnsw_trace_sink.h`，逻辑为：

1. 保存上游 `DISTFUNC` 指针与其参数；
2. `++g_hnsw_dist_call_count`；
3. 直接调用上游函数并返回原结果；
4. 不重写任何向量距离公式；
5. `dist_func_param_` 保持上游原值不变（避免影响 `loadIndex` 读取维度）。

`HNSW_TRACE_SITE` 宏在 `HNSWLIB_TRACE_ENABLED` 未定义时展开为空，因此同一份 `main.cpp` 可编译出上游版与插桩版。trace sink 运行时可关闭：`g_hnsw_trace_sink_enabled=false` 时四类位点均不写日志。

---

## 4. V1–V5 逐项结果

合成配置：1000 向量、dim 16、Inner Product、M=16、efConstruction=200、efSearch=64、k=10、50 查询、建图/查询均单线程、种子 2026、external label = `100000 + 17*i`（非连续）。

| 验证 | 结果 | 证据摘要 |
| --- | --- | --- |
| **V1 完整事件覆盖** | **PASS** | 50/50 查询事件流非空；逐查询 `event_count == distance_call_count`；50/50 含 level-0 事件；50/50 含 level>0 事件；最大观测层级 2；28031 个事件全部可映射回真实文档（映射错误 0）；`event_index` 逐查询从 0 连续（错误 0）；sink-off 事件数 0。 |
| **V2 搜索结果不变** | **PASS** | 三组 top-k（未插桩上游 / 插桩 sink-on / 插桩 sink-off）共 500 行逐行比较 `(query_id, rank, external_id, float32 bit pattern)`，差异 0 行。未用 Recall 或集合相等替代。 |
| **V3 轨迹可复现** | **PASS** | 50/50 同索引重复运行 trace hash 一致；50/50 同种子同插入顺序重建索引后 trace hash 一致；unique first-touch 视图可从完整流独立复算（27047 条派生记录，逐查询比对一致）。 |
| **V4 层级与重复语义** | **PASS** | query 0：557 个完整事件、536 个唯一文档、21 次重复距离计算；四类位点均有事件（entrypoint 1、upper 32、level0_entrypoint 1、level0_neighbor 523）。详见第 7 节。 |
| **V5 插桩范围审计** | **PASS** | patch 新增 98 行，全部落在观测允许清单内；禁止 token（邻居选择、候选队列、停止条件、`addPoint` 等）命中 0；未在建图路径写查询事件；sink 关闭时无日志；仅测试单线程查询，不对并发 trace 安全作结论。 |

事件位点分布（全 50 查询）：`level0_neighbor` 26687、`upper_layer_neighbor` 1244、`entrypoint` 50、`level0_entrypoint` 50；层级分布：level 0 = 26737、level 1 = 888、level 2 = 406。

---

## 5. 上游与插桩版本 top-k 对比

| 对比 | 行数 | 精确匹配 | 差异 |
| --- | --- | --- | --- |
| 上游 vs 插桩 sink-on | 500 | 500 | 0 |
| 插桩 sink-on vs 插桩 sink-off | 500 | 500 | 0 |

比较字段为 `(query_id, rank, external_id, dist_bits)`，其中 `dist_bits` 为 float32 的位模式（如 `0xc01d66e8`）。`rank` 为 `searchKnn` 返回优先队列的 pop 顺序，确定性序列；不以距离数值四舍五入后比较代替位模式比较。

---

## 6. 独立距离函数计数与事件数量对比

| 项 | 值 |
| --- | --- |
| 查询数 | 50 |
| 完整事件总数 | 28031 |
| 独立 DISTFUNC 调用总数 | 28031 |
| 逐查询 `event_count == distance_call_count` | 50/50 |
| 差值最大值 | 0 |

独立计数器来自包装后的 `DISTFUNC`，不是 hnswlib 的聚合 `metric_distance_computations`。每次查询前计数器归零，查询结束后与事件日志条数比较。sink-off 运行仍会计数但不写事件，用于区分“未采集”与“未发生”。

---

## 7. 完整事件样例与 first-touch 派生（query 0）

完整事件流前 8 条：

| event_index | internal_id | external_id | level | event_site |
| --- | --- | --- | --- | --- |
| 0 | 17 | 100289 | 2 | entrypoint |
| 1 | 50 | 100850 | 2 | upper_layer_neighbor |
| 2 | 459 | 107803 | 2 | upper_layer_neighbor |
| 3 | 537 | 109129 | 2 | upper_layer_neighbor |
| 4 | 719 | 112223 | 2 | upper_layer_neighbor |
| 5 | 17 | 100289 | 2 | upper_layer_neighbor |
| 6 | 50 | 100850 | 2 | upper_layer_neighbor |
| 7 | 537 | 109129 | 2 | upper_layer_neighbor |

重复事件被保留：文档 `100289` 在 event_index 0 以 `entrypoint` 记录一次，在 event_index 5 以 `upper_layer_neighbor` 再次记录；文档 `100850`、`109129`、`112223` 同样在 level 2 被重复计算距离。

unique first-touch 视图按完整流顺序对每个 external ID 只保留第一次出现：

| first_touch_index | event_index | external_id | level | event_site |
| --- | --- | --- | --- | --- |
| 0 | 0 | 100289 | 2 | entrypoint |
| 1 | 1 | 100850 | 2 | upper_layer_neighbor |
| 2 | 2 | 107803 | 2 | upper_layer_neighbor |
| 3 | 3 | 109129 | 2 | upper_layer_neighbor |
| 4 | 4 | 112223 | 2 | upper_layer_neighbor |
| 5 | 9 | 106120 | 1 | upper_layer_neighbor |
| 6 | 10 | 106970 | 1 | upper_layer_neighbor |
| 7 | 11 | 102482 | 1 | upper_layer_neighbor |

即被跳过的 event_index 5–8 都是已出现文档的重复距离计算。完整流与 first-touch 视图分别保存在 `results/raw/exp10a_synthetic_trace.jsonl` 与 `results/raw/exp10a_first_touch.jsonl`，派生脚本为 `analysis/exp10a_validate.py`。

---

## 8. 插桩代码相对于上游的 diff

完整 diff 见 `patches/hnswlib-v0.9.0-query-trace.patch`（152 行）。摘要：

- `hnswalg.h`：7 个 hunk，全部为 `#ifdef HNSWLIB_TRACE_ENABLED` 包裹的观测代码 —— 顶部宏定义（含 sink 关闭时的空展开）、两处构造路径的 DISTFUNC 包装、四个 `HNSW_TRACE_SITE(...)` 调用。
- 新增 `hnsw_trace_sink.h`：53 行，声明 sink 开关/独立计数器/emitter，定义 DISTFUNC 计数包装模板；不重写距离公式。
- **未修改**：邻居选择、候选队列、`lowerBound` 更新、visited 标记、停止条件、`addPoint`/建图路径。
- patch 以 CRLF 工作区快照为基线，应用需 `patch --binary -p1`。

静态审计由 `analysis/exp10a_validate.py` 的 V5 与 `tests/test_exp10a_probe.py::test_patch_contains_exactly_four_trace_sites` 共同覆盖。

---

## 9. 观测范围与不能声称的性质

统一口径：**HNSW query distance-evaluation trace（查询距离计算轨迹）**。

本轮证明：在 hnswlib v0.9.0 的标准 `searchKnn` 执行过程中，实际交给距离函数的文档 ID、事件顺序与层级可以被可靠采集，且采集不改变搜索结果。

**不得声称**：

- 完整物理内存访问轨迹；
- CPU cache trace；
- 真实硬件侧信道轨迹；
- Faiss HNSW trace（本轮与 Faiss 无关，EXP-10 停止结论不变）；
- 通用“HNSW 所有实现”的访问轨迹（仅 hnswlib v0.9.0 得到验证）。

原因：源码中的 `_mm_prefetch` 指令可能在距离函数调用之前触发数据预取；本轮事件日志不记录这些硬件层行为。另外只测试单线程查询，不对并发 trace 安全性作结论。

---

## 10. 测试与数据

- 仓库完整测试：`43 passed`（原有 38 项 + 本轮新增 5 项 `tests/test_exp10a_probe.py`）。
- 验证裁决文件：`results/raw/exp10a_validation.json`（`verdict=PASS`）。
- 原始数据：`exp10a_synthetic_trace.jsonl`（28031 行）、`exp10a_{upstream,instrumented,sinkoff}_topk.jsonl`（各 500 行）、`exp10a_probe_summary.jsonl`（100 行）、`exp10a_first_touch.jsonl`（27047 行）、`exp10a_trace_summary.csv`、`exp10a_sample_query0.json`。

**下一步不在本轮范围**：FiQA 是否进入下一阶段由用户在检查本报告后单独决定。
