# H1-RM.2 — Native HNSW Filter/Stop Semantics

- 基线：`exp10-hnswlib-trace-feasibility` @ `68ed142a234428bafc85be5cbad8de12371688f2`（工作区 clean，EXP-10A manifest 与原始事件文件齐全，只读未改）
- hnswlib：上游 `nmslib/hnswlib` v0.9.0，`d9b3608c83d83b46c96e25088cb1d729b29dcfe9`（`_tmp_hnswlib_src` HEAD 与 `third_party/SOURCE_INFO.md`、`docs/EXP10A_PHASE0_REPORT.md` 三方一致）
- 分支：`research/h1-rm-2-native-stop-semantics`（从 EXP-10A 提交建独立 worktree；原 EXP-10A 与 H1.1–H1.4 工作区未触碰）
- 性质：**接口语义可行性验证**。不开展 ACL 泄露攻击，不重跑 H1.x，不新增数据/图/查询参数，不研究 E2/H2，不设计防御。

---

## 1. 本轮要回答的问题

上一轮提出：hnswlib 的 `searchStopConditionClosest` 把 `ef` 设为 `0`，让 `BaseSearchStopCondition` 接管候选考虑、结果维护与停止判断。因此必须先回答两个接口语义问题，才能决定后续是否能在此路径上研究 K-hit 停止：

1. **C1 能否在不改搜索算法的前提下，精确复现标准过滤搜索 `searchKnn + filter`？**
2. **若能，C2 的 K-hit 停止在什么控制流边界生效，相对成功过滤检查序列引入多少额外可观察事件？**

本轮只回答这两点。即便 C1 对齐，也**不**自动构成论文贡献——它只是证明原生停止条件接口可被用来表达标准语义。

---

## 2. 源码接口核对（Phase 0）

对 pristine v0.9.0 `hnswalg.h` 的逐行核对：

| 项 | `searchKnn`（有 filter） | `searchStopConditionClosest` |
| --- | --- | --- |
| 调用 | `searchBaseLayerST<false>(ep, q, ef=max(ef_,k), filter, nullptr)` | `searchBaseLayerST<false>(ep, q, **ef=0**, filter, &stop_condition)` |
| 候选考虑 | `top_candidates.size() < ef \|\| lowerBound > dist` | `stop_condition->should_consider_candidate(dist, lowerBound)` |
| 结果加入 | filter 通过后 `top_candidates.emplace(...)` | 同一 if 内额外 `add_point_to_result(...)` |
| 结果剔除 | `while (top_candidates.size() > ef)` → pop | `should_remove_extra()` → pop + `remove_point_from_result(...)` |
| 停止 | `candidate_dist > lowerBound && top_candidates.size()==ef` | `should_stop_search(candidate_dist, lowerBound)` |
| 返回 | `priority_queue<pair<dist,labeltype>>`（external label） | `vector<pair<dist,labeltype>>`，末调用 `filter_results(...)` |

结论：`ef=0` **不等于**接口不可用；停止条件对象只要用真实结果集合复现上表左侧四规则，即可在回调内表达标准 ef 语义。源码回调顺序支持该实现。是否真能逐事件对齐由 C0/C1 实验判定，不以推理代替实测。

---

## 3. 插桩与三组对照（Phase 1–2）

- 插桩版：`third_party/hnswlib-v0.9.0-rm2-instrumented/`，由 `scripts/build_rm2_instrumented.py` 从 pristine CRLF 快照生成，`patches/hnswlib-v0.9.0-rm2-stop-semantics.patch` 为可复现产物。pristine `hnswalg.h` SHA-256 `7e5eb7f3…bc43` 与 SOURCE_INFO 一致；插桩版 `f686c579…e64e72`。
- 插桩为**纯观测**：11 个位点全部是 `RM2_EV(...)` 调用，包在 `HNSWLIB_RM2_TRACE_ENABLED` 内；未改任何分支、候选选择、结果维护、`lowerBound` 更新或停止逻辑（测试 `test_patch_inserts_only_rm2_ev_observation_calls` / `test_patch_does_not_touch_search_logic_tokens` 固化）。
- 8 类事件：`distance_eval`、`candidate_pop`、`candidate_consider`、`filter_check`、`result_add`、`result_remove`、`stop_check`、`search_stop`，每条含 query ID、external/internal ID、事件序号、距离位模式与必要 extra 字段。`filter_check` 只在过滤回调被实际调用时由 harness 的记录型 filter 发出；成功授权检查数与结果集合当前成员数分别统计；`result_add` 累计次数未被当作结果集合大小。
- 三组（同一索引、同一 50 查询、同一过滤规则、单次建图）：
  - **C0** `searchKnn(q, 10, filter)`，标准路径，`ef=max(64,10)=64`。
  - **C1** `searchStopConditionClosest`，`EfReplayStopCondition(ef=64)`：内部用真实 `priority_queue` 结果集合镜像标准 top 候选，`should_consider/should_remove/should_stop` 逐条复现标准规则；`remove_point_from_result` 同样 pop 镜像顶部（不依赖上游传入的当前候选距离）；`filter_results` 不做额外改变。
  - **C2** 在 C1 基础上，`should_stop_search` 增加 `auth_hits >= K=10`。授权命中由记录型 filter 无条件计数，emit 受 sink 开关门控。
- 固定规模：1000 向量、dim 16、Inner Product、M=16、efConstruction=200、efSearch=64、k=10、50 查询、seed=2026、label=`100000+17i`、授权节点 100 个（10%，确定性 hash 规则）。未引入 FiQA/ACL 生成，未扩参数网格。

---

## 4. C0 与 C1 语义等价：通过

顶层结果（每个 (query, rank) 单元，共 50×10=500）：

| 判据 | 结果 |
| --- | --- |
| Top-10 节点 ID 一致（external 映射后） | **500 / 500** |
| Top-10 距离 float32 位模式一致 | **500 / 500** |
| `distance_eval` 全序列逐条一致 | 50998 / 50998（internal_id、dist_bits、level 均一致） |
| 8 类事件计数 C0 vs C1 | 全部相同 |
| C0 / C1 / upstream 三通道 top-k | 完全一致 |

三通道指：插桩版 trace on、插桩版 trace off（sink 关闭）、pristine 上游版（无任何插桩）。三组 top-k 在三个通道逐行一致，说明对齐结论既不依赖观测开关，也不依赖插桩本身。

**必要的口径说明（工程语义差异）**：`searchKnn` 返回的 `pair<dist,labeltype>` 第二元素是 **external label**；而 `searchStopConditionClosest` 在 `searchBaseLayerST` 返回后把 `priority_queue<pair<dist,tableint>>` 直接写入 `pair<dist,labeltype>` 结果向量，第二元素是 **internal tableint**（隐式转为 labeltype），并未调用 `getExternalLabel`。因此 C1 结果的 ID 字段数值落在 `0..999`（例如 `17、25、43`），而非 `100000+17i`。本报告的 "Top-10 节点 ID 一致" 是在 `mapped_id = 100000 + 17 × internal_id` 的显式映射后成立；原始 C1/C2 输出保留上游原样，未改写。这是原生停止条件接口与标准搜索接口在**结果标签语义**上的真实差异，后续若在此路径上工作必须处理。

C1 对齐成立，因此按任务包停止条件，C2 的结果可继续按“C1 上的 K-hit”解释，而不是“标准搜索上的 K-hit”。

---

## 5. C2：K-hit 停止的实际控制流边界

50 个查询的 C2 统计：

| 量 | 值 |
| --- | --- |
| 第 K 次成功过滤检查 → 实际 `search_stop` 的事件序号差（gap） | 均值 **27.58**，范围 **3–52** |
| gap 内严格居间的事件（50 查询合计） | `distance_eval` 398、`candidate_consider` 398、`filter_check` 398、`result_add` 85、`stop_check` 50、`candidate_pop` **0** |
| 授权命中计数 | 精确：每查询 `auth_hits == n_filter_ok == returned_size`，范围 10–14 |
| 每查询 `search_stop` 次数 | 恰 1 |
| C0 / C1 / C2 返回集合大小 | 10 / 64 / 10–14 |

解释（严格限于观测到的控制流）：

- K-hit 命中**不是**命中即停。第 10 次成功过滤检查发生后，搜索仍继续处理当前邻接表剩余邻居；直到 `candidate_set` 循环顶部下一次 `should_stop_search` 才 break。
- gap 内 `candidate_pop = 0` 是关键证据：这段时间没有弹出下一个候选，全部是对当前候选邻接表的展开与授权检查；`stop_check` 恰 50 条（每查询一次），与“边界检查”一致。
- 因此相对“成功授权检查序列”，K-hit 停止额外引入可观的距离计算/候选考虑/过滤检查事件——这正是本轮的目标量。原抽象模型里“达到 K 即停”的原子语义，在真实 hnswlib 回调路径上表现为“达到 K 后到下一个循环顶部之间仍有额外可观察事件”。
- 这些是**控制流事件计数**，不是硬件/缓存/内存访问轨迹；未测 recall 代价（K-hit 会改变返回集合大小 10–14 且 top-k 与 C0 仅 69/500 一致，本报告不把它解读为好或坏的召回结论，只作为停止改变结果的观测）。

---

## 6. 交付文件

- 探针：`experiments/h1_rm2_native_stop/main.cpp`、`build_and_run.sh`、`analyze.py`
- 生成/审计：`scripts/build_rm2_instrumented.py`、`patches/hnswlib-v0.9.0-rm2-stop-semantics.patch`
- 插桩源码：`third_party/hnswlib-v0.9.0-rm2-instrumented/hnswlib/*`（新增目录，pristine 快照未改）
- 测试：`tests/test_h1_rm2_native_stop.py`（12 项；全仓 55 passed = 43 基线 + 12 新增）
- 结果：`results/h1_rm2/{trace_on,trace_off,upstream}/*.jsonl`（完整事件日志 trace on 67MB 由 `.gitignore` 排除、可经 `build_and_run.sh` 重建）、`events_audit.jsonl`（176KB，入库的精简审计集：每 (query,group) 的各类事件计数 + distance_eval 序列 FNV-1a 哈希 + C2 gap 窗口全部事件）、`summary.csv`、`gate.json`、`manifest.json`
- 本报告：`docs/H1_RM_2_NATIVE_STOP_SEMANTICS.md`

`gate.json` 18/18 判据 PASS；pytest 55 passed（43 基线 + 12 新增）全部可从入库文件复跑，不依赖 67MB 原始日志。manifest 固定 9 个入库文件哈希、源码哈希、完整原始日志哈希/行数，以及全部配置。

---

## 7. 边界与不作声称

- 本轮**不**证明任何授权成员泄露的新规律：C2 的 K-hit 只是驱动停止，未做成员推断评分，未与 H1.1–H1.4 的攻击比较。
- 未声称硬件/cache/物理内存轨迹；仅 HNSW 查询控制流事件，单索引、单线程，不对并发作结论。
- C1 对齐证成的是“原生停止条件接口可表达标准过滤搜索语义（含结果标签需映射这一差异）”，属工程适配结论；是否产生新的可量化泄露或有效缓解，留给后续独立决策，本轮不启动 H1-RM.3/H2。
- 未改 EXP-01/EXP-08/EXP-09/EXP-10 冻结内容；未下载 FiQA/qrels/模型；未建 PR。
