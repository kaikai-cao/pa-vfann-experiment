# H1-RM.3A.3 — Paired ACL Leakage Feasibility & Protocol Freeze

**类型**：设计与可行性审计（只读核查 + 协议冻结）。不运行实验、不生成新数据、不修改任何冻结产物。

**研究假设**（待验证，本阶段不判定成立与否）：

> 对同一个 HNSW 索引 $G$ 和查询 $q$，仅改变一个目标成员 $u$ 的授权状态，加入 K-hit 停止后，攻击者能否比观察普通过滤搜索获得更多关于 $u$ 授权状态的信息？

## 0. 基线与边界

| 项目 | 固定值 |
| --- | --- |
| 仓库 | `kaikai-cao/pa-vfann-experiment` |
| 对象存储链（common gitdir） | `pa-vfann-exp10-hnswlib-probe-workspace/.git` |
| 基线分支 | `research/h1-rm-3a2-r1-evidence-erratum` |
| 基线 HEAD | `4babeaa2aad2a02604cf5a448709690e67f3a43d` |
| 父提交 | `dd6d28c2c5aad37189dd82114e2b5a07103919b4` |
| 本分支 | `research/h1-rm-3a3-paired-acl-feasibility` |
| 唯一新增文件 | 本文档 |

**Phase 0 门禁**：common gitdir 为 `pa-vfann-exp10-hnswlib-probe-workspace/.git`（对象可解析）；分支/HEAD/父提交精确匹配；工作区 clean；目标分支本地与远端不存在；目标 worktree 路径空闲；基线报告 blob = `7e6dcf63ef6ee88e4b54f36dcdb3296dd2bb4bdb` 与冻结提交一致。**全部 PASS**。

**硬边界**：本轮只读核查代码与冻结数据、设计配对协议、冻结攻击者模型与统计量。禁止修改 C++/Python/`StorageAccess`、禁止生成四格数据、禁止运行 C0/C1/C2、禁止重跑 EXP-10 或 H1.1–H1.4、禁止创建 block backend、禁止声称已获得真实 TEE page trace、禁止启动 H1-RM.3B、禁止修改冻结产物、禁止建 PR。**无论本阶段裁决为何，均不自动启动 H1-RM.3B。**

**行号体系声明**：下文带行号引用一律指本 worktree 内冻结源码——`experiments/h1_rm2_native_stop/main.cpp`、`experiments/h1_rm_3a1_storage_bridge/main.cpp`、`experiments/h1_rm_3a1_storage_bridge/storage_access.h`、插桩头 `experiments/h1_rm_3a1_storage_bridge/hnswlib_bridge/hnswalg.h`。前序报告引用的 `third_party/hnswlib-v0.9.0-rm2-instrumented/` 为另一份插桩副本；同一路径在 `third_party/hnswlib-v0.9.0/` 是未插桩原始版。三者行号体系不同，不得混用。

---

## Phase 1 — 现有代码与数据可行性核查

### A. ACL 是否可以精确配对？——**机制可行；当前冻结实现不具备；需最小代码改动（本轮禁止）**

**当前 ACL 生成方式**：`main.cpp`（RM.2 版 :95–100，3A.1 版 :120–125）是纯确定性 hash 谓词：

```cpp
static bool authorized(labeltype label) {
    uint64_t h = static_cast<uint64_t>(label) * 2654435761ULL;
    h ^= h >> 15;
    return (h % 100) < 10;
}
```

无 ACL bitmap、无目标成员参数、无 per-query override。manifest 固定 `authorized_nodes=100`、`auth_rule="hash(label)*odd >>15 %100 <10"`（`results/h1_rm2/manifest.json :18–19`）。

**`isIdAllowed` 实际检查什么**：`RecordingFilter::operator()`（RM.2 版 :109–135，3A.1 版 :134–160）对传入的 `external label` 调用 `authorized(id)`，并在 `ok` 时无条件累加全局 `g_rm2_auth_hits`（C2 停止机制的计数源）。搜索侧在入口点（插桩 `hnswalg.h :397`）与候选节点（`hnswalg.h :487`）两处调用 `(*isIdAllowed)(getExternalLabel(...))`。

**external label ↔ internal ID 对应**：索引以 `labeltype(LABEL_BASE + LABEL_STEP*i)` 插入（`main.cpp :202–205` / `:227–230`，`LABEL_BASE=100000, LABEL_STEP=17`），reverse 映射 `internal_of(label) = (label − 100000)/17`（:102–105 / :127–130），是一一对应的确定性整除法。**因此可在 label 空间精确定位 $u$**，不存在 ID 歧义。

**能否构造仅翻 $u$ 一位的 $A_0,A_1$**：机制上可以——把 `authorized()` 替换为 `authorized_A(label) = base_rule(label) XOR (label==label(u)) ∧ (A==1)`，其余位不变；由于 $u$ 的 label 唯一，翻转是局部的。**但当前冻结代码没有该 override 入口**，且在 `searchBaseLayerST` 内 `getExternalLabel()` 经 R1 桥接读取（3A.1 版 `hnswalg.h`）也是如此。结论：**需在未来的最小实验准备中新增一个 ACL override 参数（原子翻转点），本轮按硬边界不改代码**。

**其余量能否保持不变**：`base`/`queries` 由 `std::mt19937 rng(SEED)` 单一流生成（RM.2 版 :272–278，3A.1 版 :302–308），索引构建、两组 vector、ACL 判定函数在同一二进制内按固定顺序执行，$A_0/A_1$ 两跑若仅注入 label override，则索引、query、种子、$M$/$ef$/K 全部相同——**前提是该 override 不进入 RNG 流、不改变插入顺序**（写入协议见 Phase 3）。

### B. C1/C2 是否具有可比性？——**主体可比（唯一代码差异是 K-hit 判断）；但须显式列出 3 项下游差异，不得"视为只差一个停止条件"**

**冻结定义**（与 RM.2 manifest :21–25 一致）：C1 = `searchStopConditionClosest` + `EfReplayStopCondition(ef=64, 真实结果集)`，不启用 K-hit；C2 = 同一路径 + `KHitStopCondition`，即在相同普通过滤与搜索配置上增加 K-hit 停止。

**唯一实现差异**：`EfReplayStopCondition`（RM.2 版 :147–179，3A.1 版 :172–204）实现标准 ef 规则的镜像结果集 $R$：`should_stop_search = (candidate_dist > lowerBound && R.size()==ef)`（:166–168 / :191–193）。`KHitStopCondition`（:183–190 / :208–215）仅 override 一个方法：

```cpp
bool should_stop_search(float candidate_dist, float lowerBound) override {
    if (g_rm2_auth_hits >= K) return true;              // 唯一新增分支
    return EfReplayStopCondition::should_stop_search(candidate_dist, lowerBound);
}
```

两组的 `filter`（同一 `RecordingFilter` 类型）、`add_point_to_result`/`remove_point_from_result`/`should_consider_candidate`/`should_remove_extra`/`filter_results` 全部继承同一实现；`searchBaseLayerST<false>`（`hnswalg.h :382–522`）为同一函数。**从"第一次满足 auth_hits≥K 的 stop_check"起两组控制流分叉，分叉前逐事件一致**——这是分离 $D_{filter}$ 与 $D_{stop}$ 的机制基础。

**必须显式列出的差异**（均为 K-hit 提前终止的下游后果，而非独立实现变量，但会影响可观察轨迹与结果分布）：

1. **返回集大小不同**：C1 `returned_size=64`（跑满 ef），C2 `returned_size=10–14`（manifest :56–60；query 0 实测 C1=64 / C2=10）。$R$ 未满会改变 `filter_results` 前的候选池规模。
2. **filter 调用次数不同**：C1 平均 `auth_hits≈76.88`（`summary.csv`），C2 停在 `auth_hits=10–14`；被 filter 访问的候选集合不同，不只是"停止点早晚"。
3. **事件数与 stops 位置**：query 0 的 C0/C1 各 4166 事件、C2 仅 312（`events_audit.jsonl`）；C2 的 K-hit 与 search_stop 之间存在事件窗口（manifest :61–70 的 gap 统计），停止不在 K-hit 当刻，而在下一候选循环边界。

**ACL 的"非 K-hit"效应确实存在**：`hnswalg.h :397/:487` 的 filter 判定决定候选是否进入 `top_candidates`，:514 `lowerBound = top_candidates.top().first` 随之更新，:471 `should_consider_candidate` 又用 `lowerBound` 剪枝；授权命中还在 :405/:491 触发 `add_point_to_result` 改变 $R$ 内部状态。**因此翻转 $u$ 的授权位必然先改变普通过滤轨迹（$D_{filter}$），再改变 K-hit 停止轨迹（$D_{stop}$ 的载体）——两者必须用配对设计分离，不能只比较同一 ACL 下 C1 与 C2 的轨迹长度。**

### C. 现有数据是否能支持四格设计？——**不能：无 ACL 配对、无 target member、无四格；禁止事后重标注**

现有冻结数据穷举如下：

| 数据集 | query | 组 | ACL | target 字段 | 四格 |
| --- | --- | --- | --- | --- | --- |
| `results/h1_rm2/` | 50 | C0/C1/C2（150 组） | 单一固定 hash | 无 | 无 |
| `results/h1_rm_3a1/` | 50（_full_）/ 5（audit 子集） | C0/C1/C2 | 同一固定 hash | 无 | 无 |
| `results/h1_rm_3a1_r1/` | 5 | C0/C1/C2 | 同一固定 hash | 无 | 无 |

**字段证据**：`requests_audit.jsonl` 的键仅 `query_id/group/seq/request_type/node_id/level/boundary`（90 条）；`run_summary.jsonl` 键含 `query_id/group/auth_hits/khit_event_index/...`；`events_audit.jsonl` 为每 (query,group) 的计数 + `distance_eval_hash` + C2 的 gap 窗口。所有 manifest 均无 ACL 配置摘要、target member ID、ACL 状态 U、trace 类型或轨迹哈希字段。**现有数据是"一份 ACL × 三个条件"的对照，不是"$2\times2$ 配对"**。

**明确的反事实边界**：一份固定 ACL 下的 `events.jsonl`（含 `filter_check` 的 pass/fail 于 `extra`）**不能**通过事后把某条 `filter_check` 改标为相反授权状态来充当 $A_1$ 的轨迹——因为授权位翻转会改变 `top_candidates`/`lowerBound`/候选集推进顺序，整条轨迹要重跑，而非单点重标注。**没有真实配对记录，本阶段不生成、不伪造。**

**独立 query 单位**：现有 50 个 query 在同一 ACL 下是独立单位，但四格要求每个 (q,u) 四跑；若固定 1 个 u × 50 query，单位是 query（n=50）；若用预选 u 集合形成 query×target 配对，独立单位更小且需按 query 分组（见 Phase 4）。当前数据均不满足。

### D. 目标成员 $u$ 如何选取？——**必须预先固定；现有样本不足以定义攻击者训练分布**

**选择依据（冻结）**：$u$ 必须从**公开逻辑身份**中按与轨迹无关的规则预先确定——例如对授权节点集合（100 个，label 空间可由公开 hash 规则离线复算）按 `label` 升序取前 $P$ 个，或对全部 1000 个 label 用固定种子 hash 排序取前 $P$。**禁止**先看轨迹 gap/K-hit 位置再挑"差异最大"的节点（那是对测试集的隐式调参，会使 BA 虚高）。选择规则、随机种子与 $P$ 值必须在数据生成前写入 manifest。

**两种样本单位的统计含义**：

- **固定单 u × 多 query**：n = query 数。估计的是"该特定成员在多个查询下的可推断性"，不能推广到成员总体；攻击者训练样本只能是同一 u 的其他 query。
- **预选 u 集合 × query 配对**：每个 (q,u) 为一个单位，可估计成员总体；但同一 query 的多个 u 共享轨迹前缀，必须按 query 分组 bootstrap，否则高估有效样本量。

**攻击者训练样本来源（关键，不得默认已知）**：真实部署中攻击者**只观测真实 ACL 的一份轨迹**，并不知道同一 $u$ 在"授权/未授权"两状态下的标签；$A_0/A_1$ 是研究者构造的反事实。因此分类器必须在**shadow 数据**上训练——由攻击者用自己控制的索引与 ACL 生成带标签轨迹（shadow index + shadow ACL），再在目标真实 ACL 上推断。**当前冻结材料不含 shadow 索引/shadow ACL 生成机制**，故现阶段攻击评估只能降级为"配对轨迹敏感性分析"，不能宣称成员推断能力已被证明。

---

## Phase 2 — 冻结攻击者观察模型

### 三类轨迹（严格区分）

| 轨迹 | 含义 | 能否直接作为攻击者输入 |
| --- | --- | --- |
| Search trace | `distance_eval`、`filter_check`、`candidate_pop`、`candidate_consider`、`result_add/remove`、`stop_check`、`search_stop`（`events.jsonl`，8 类事件） | **否**——含 ACL 判定与停止事件，仅研究者机制解释用 |
| Logical trace | `read_node`/`read_label`/`read_neighbors`/`boundary`（`requests.jsonl`，字段见 storage_access.h :29–43） | **否**——逻辑请求元数据，非物理读取，R1 已明确 |
| Page trace | TEE 内存实际页访问序列（FiT 类观察者） | **是**（模型目标），但当前数据无法产出真实实例 |

**当前数据只能构造**：把 internal node ID / logical request 按"节点块 204 B → 4 KB 页"规则映射得到的 **`Synthetic page-level proxy trace`（合成页级代理轨迹）**。不得称为真实 TEE page trace。依据 3A.2-R1 的证据，FiT 的页级观测是**带重复访问事件的页面序列**（反复检查邻接表 PTE accessed bit；HNSW 用例中位归一化汉明距离 FiT=0.05、Naive Bayes=0.76），代理轨迹必须保留重复与时序，不能退化为唯一页面集合。

### 冻结的强攻击者模型（上界可行性测试）

- **已知**：查询 $q$；HNSW 索引版本、公开图结构与参数（$N=1000,d=16,M=16,ef=64,k=10$）；节点→页映射规则；目标成员 $u$ 的公开逻辑身份（其 label）。
- **未知**：ACL bitmap（当前为 hash 谓词，对外不公开）；$u$ 的授权状态；filter 判定结果；K-hit 计数；候选集、距离值、最终授权结果。
- **观察**：带重复访问事件的页面 ID 序列；查询请求边界（按 3A.2-R1，FiT 已证网络 I/O syscall 可提供请求起止；当前本地 harness 无外部 wrapper 属实现限制，非架构障碍）。
- **禁止交给分类器**：内部 `filter_check` 的 pass/fail、`candidate_pop`、`search_stop`、$R$ 状态、`khit_event_index`、任何 `dist_bits`。这些只用于研究者做机制解释与对齐检验。

### 页级代理的额外约束（五项核实结果）

1. **基地址 / 页内偏移 —— 不存在于冻结数据，为未确定变量 $\delta$**。核实：`requests_audit.jsonl` 键仅 `{query_id,group,seq,request_type,node_id,level,boundary}`；全 `results/` 内 `addr/base/page/frame` 命中仅为 `label_base`/`base_commit`，`0x…` 命中全是 `dist_bits`。**不得假定 `data_level0_memory_` 从页边界开始**。敏感性分析：$\delta\in\{0,100,512,2048\}$ 时跨页节点数为 49/48/48/49，说明页映射对 $\delta$ 敏感，须把 $\delta$ 作为扫描参数并在报告中给出区间结论，不得单点下定论。
2. **204 B 节点块跨页**：`size_data_per_element_ = 132(L0 link) + 64(vector) + 8(label) = 204 B`；每 4 KB 页约 20.078 个节点，1000 节点中 **49 个跨越页边界**（节点 20/40/60/…），总 L0 ≈ 204 KB ≈ 49.8 页。跨页节点一次节点块读取触及两页。
3. **L0 邻接 / 向量 / label / 删除标记的可重建性**：`storage_access.h :52–57` 定义节点块布局（`offsetLevel0_=0` → L0 link，`offsetData_` → vector，`label_offset_` → label）；R1 的 `NodeView` 覆盖整块，故可从 `node_id` 重建"同一节点块内的字段访问"，**但无物理地址**，删除标记位于 L0 linklist 区（R1 未单列 `NodeView`，3A.2-R1 记为风险）。upper-layer 邻接在 `linkLists_` 独立 malloc。
4. **SSE 预取改变页面序列**：插桩 `hnswalg.h :447–461/:480–484` 的 `_mm_prefetch` 直接对 `data_level0_memory_ + id*size_data_per_element_ + offsetData_` 与 `visited_array` 预取邻居，**不经过 `StorageAccess`、不记录到 `requests.jsonl`**。真实页级观察者可能看到这些提前 touch，代理轨迹会漏记 → 代理与真实页 trace 存在系统性偏差，须作为偏差项声明。
5. **日志遗漏的其他内存访问**：`visited_array`、两个 `priority_queue`（`top_candidates`/`candidate_set`）、stop condition 的镜像结果集 $R$、（若部署为位图的）ACL bitmap 均不在任何冻结日志中；这些区域的页访问同样可能被观察者看到。**结论：当前只能构造受限合成页级代理，不具备真实页级观测条件。**

---

## Phase 3 — 冻结四格配对实验（设计，不执行）

**实验单位** = 同一 $(q, G, u)$，其余 ACL 位固定。索引 $G$ 由固定 seed 与固定插入顺序构建；$q$ 为 50 query 之一（或预注册子集）；$u$ 按 Phase 1-D 的预注册规则选取。

$$A_0 = A_{-u}\cup\{u\text{ 未授权}\},\qquad A_1 = A_{-u}\cup\{u\text{ 已授权}\}$$

$$T_{a,c}=T(q,G,A_a,C_c),\quad a\in\{0,1\},\ c\in\{1,2\}$$

| 授权状态 | C1 普通过滤 | C2 增加 K-hit |
| --- | --- | --- |
| $U=0$ | $T_{0,1}$ | $T_{0,2}$ |
| $U=1$ | $T_{1,1}$ | $T_{1,2}$ |

**必须记录的核对元数据（8 项）**：query ID、target member ID（label+internal）、ACL 配置摘要（含被翻位与其余位 hash）、索引摘要（seed+插入序列+图结构 hash）、搜索参数（$M/ef/k/LABEL$ 常量）、C1/C2 条件标识、trace 类型（search/logical/synthetic-page）、轨迹哈希（对页面 ID 序列含重复项做规范化 hash）。缺任一项则该格不进入分析。

**有效性前置**：若 B 节三项下游差异未被显式建模，不得进入统计；$A_0/A_1$ 必须证明除 $u$ 位外逐位相同（写入 ACL 摘要比对）。本阶段**不生成四格数据**。

---

## Phase 4 — 冻结统计量与攻击成功标准

**评价量**（对固定攻击者、留出测试集，C1 与 C2 分别评估）：

$$\operatorname{Adv}_c=\operatorname{BA}_c-\tfrac12,\qquad \boxed{\ \Delta_{\mathrm{adv}}=\operatorname{BA}_{C2}-\operatorname{BA}_{C1}\ }$$

$\operatorname{Adv}_{C1}$ = 普通过滤下推断能力；$\operatorname{Adv}_{C2}$ = 加 K-hit 后推断能力；$\Delta_{\mathrm{adv}}$ = 该固定攻击者与分布下的**经验攻击增益**。**不是**互信息差、**不是**对最优攻击者的密码学保证、**不是**"轨迹编辑距离之差"——轨迹距离只是变化指标，不代表攻击者能推断授权状态。

**机制分离量（研究者诊断用，不作攻击结论）**：$D_{filter}=d(T_{1,1},T_{0,1})$（纯过滤效应），$D_{total}=d(T_{1,2},T_{0,2})$，$\Delta_{trace}=D_{total}-D_{filter}$（K-hit 额外轨迹变化）。只有当 $\Delta_{adv}>0$ 且其 CI 下界 >0 时，才谈"额外推断能力"；$\Delta_{trace}>0$ 本身不构成证据。

**统计要求**：① 授权/未授权平衡先验；② 保留两种 ACL 状态的配对；③ 同一 query 的所有四格记录放同一训练或测试分组（防配对泄露）；④ 训练与调参只用训练集，测试集不参与模型选择；⑤ 对 $\Delta_{adv}$ 用 **query-level paired bootstrap**（保持四格配对结构，重采样单位为 query）；⑥ 同时报 BA、AUC、95% CI 及每个目标成员的结果；⑦ 独立样本不足以支撑独立测试集时，**不得**用训练准确率或未分组交叉验证替代。

**正面判据（须同时满足）**：C2 测试 BA 显著高于随机基线（0.5）；$\Delta_{adv}$ 的 95% 配对 CI 下界 >0；结果不由 query、成员身份、索引差异或其他泄露字段直接造成；输入确为攻击者可观察轨迹而非内部 search trace。

**降级规则**：若只用合成页级代理，结论上限为"存在页级代理上的成员推断可行性迹象"，**不得声称已证明真实 TEE 攻击**；若缺乏可信 shadow training data，攻击评估降级为配对轨迹敏感性分析，并明确不足以证明成员推断能力。

---

## Phase 5 — 最终裁决

### **CONDITIONAL — 只允许受限代理验证；不得进入 H1-RM.3B**

**逐项排除**：

- **不是 STOP**：ACL 可通过单 label override 精确配对（A：label↔internal 一一映射；改动点局部且可审计）；C1/C2 主体可比、分叉点明确（B）；攻击者输入可定义（带重复的页 ID 序列 + 请求边界）；四格协议与统计量已冻结（Phase 3/4）。用户所定义 STOP 的三类情形（不能翻位 / C1C2 不可比 / 无可定义输入 / 数据根本不能配对分析）中，前三项均不成立，第四项是"现有数据不足"而非"设计上不可能"。
- **不是 GO**：用户 GO 要求"有足够独立样本支撑后续实验"。当前无 $\delta$ 基地址、无真实 TEE page trace、无 shadow 训练机制、无四格配对记录；50 query 单一 ACL 不能直接支撑带独立测试集与 query-level bootstrap 的攻击评估。按硬边界本轮也未生成任何配对数据。
- **CONDITIONAL 的允许范围**：仅允许在将来的最小配对实验准备中，构造 `Synthetic page-level proxy trace`（并对 $\delta$ 做敏感性扫描）或 logical trace 做**受限配对敏感性分析**；结论按 Phase 4 降级规则表述。

**进入任何后续验证前的前置条件（全部满足才可重新裁决）**：

1. 新增最小 ACL override 参数，证明 $A_0/A_1$ 除 $u$ 位外逐位相同，且不改 RNG 流/插入顺序；
2. 按 Phase 3 生成四格数据并记录 8 项元数据，显式建模 Phase 1-B 的三项下游差异；
3. 页级代理把 $\delta$ 作为未确定变量扫描，声明 SSE 预取与遗漏内存访问的偏差；
4. 建立 shadow index + shadow ACL 训练机制，或明确将结论限制在敏感性分析；
5. 预注册 $u$ 选择规则、样本单位、分组 bootstrap 与独立测试集划分。

**研究问题收紧为**：在 ACL 对外隐藏、过滤可信执行的 HNSW 部署中，对同一查询改变一个隐藏授权位，**页级代理轨迹**上 K-hit 停止是否让攻击者比观察普通过滤后的轨迹获得关于该成员的额外信息（$\Delta_{adv}>0$）？若普通过滤已泄露全部相关信息（$\operatorname{Adv}_{C1}$ 已饱和、$\Delta_{adv}\approx0$），或 K-hit 无额外优势，亦为有价值结论——据实报告，不为填满四格而制造攻击结果。

---

## 6. 自检表

| 检查项 | 结论 |
| --- | --- |
| Phase 0 门禁全部 PASS，未自行修复基线 | PASS |
| Phase 1 四项结论均有代码/字段/数值支撑，未声称"理论上可以"了事 | PASS |
| C1/C2 唯一差异已定位（:183–190/:208–215），三项下游差异已显式列出 | PASS |
| 现有数据无配对的判定有 manifest/字段证据，未事后重标注、未伪造 | PASS |
| 三类 trace 严格区分；合成代理命名符合 3A.2-R1；未交出内部事件给分类器 | PASS |
| 页级代理五项约束逐项核实；$\delta$ 作为未确定变量并做敏感性分析 | PASS |
| 四格协议含 8 项元数据；统计量区分经验增益与轨迹距离；降级规则明确 | PASS |
| 裁决为 CONDITIONAL，未改成 GO；未启动 3B、未建 PR | PASS |
| 未改 C++/Python/StorageAccess/冻结产物；未跑实验、未生成数据 | PASS |

本阶段到此停止；拿到真实配对证据后再裁决，不自动开始下一阶段。
