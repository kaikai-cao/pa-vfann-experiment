# H1-RM.3A.3 — Paired ACL Leakage Feasibility & Protocol Freeze

**类型**：设计与可行性审计（只读核查 + 协议冻结）。不运行实验、不生成新数据、不修改任何冻结产物。

> **H1-RM.3A.3-R1（ACL 秘密性与评估独立性勘误）**：本轮在原冻结文档上做两处设计修正，**裁决 CONDITIONAL 原样保留、不进入 H1-RM.3B**。修正 A：当前 `authorized()` 是无密钥公开 hash 谓词，**当前冻结数据不具备 ACL 秘密性**，不能作为"攻击者不知道授权状态"的成员推断证据；新增未来私有 ACL 模型与研究者/攻击者视图边界表。修正 B：统计独立单位由 query 改为**独立 ACL instance**，区分固定成员推断与成员泛化推断，禁止把同一目标的 A0/A1 反事实轨迹当作两个独立攻击样本。所有受影响的原有表述均带 `[R1]` 标记。基线 HEAD `72440e82502e240ca64bcb2dfc43062e61e394d4`，本分支 `research/h1-rm-3a3-r1-acl-secrecy-independence`，唯一修改文件即本文档。

> **`[R1.1]` H1-RM.3A.3-R1.1（Target Selection & Baseline Metadata Erratum）**：本轮为**文档一致性修正**，只处理目标成员选择、类别先验解释与基线元数据三处文字，**裁决 CONDITIONAL 与所有硬边界原样保留、不进入 H1-RM.3B**。修正 A：删除 Phase 1-D 中依赖公开 hash 授权集合选目标的旧规则，改为 ACL 生成前用预注册种子从完整公开候选集合独立预选；修正 B：区分自然授权先验 $p=0.1$、Balanced Accuracy 与类别平衡诊断集三个独立概念；修正 C：§0 明确原始 3A.3 / R1 / R1.1 三层基线与提交关系。所有受影响的原有表述带 `[R1.1]` 标记。本次直接基线 HEAD `1e0149746b28a0fe99f0a5cc7ab79b50f7249722`，目标分支 `research/h1-rm-3a3-r1-1-target-selection`，唯一修改文件即本文档。

**研究假设**（待验证，本阶段不判定成立与否）：

> 对同一个 HNSW 索引 $G$ 和查询 $q$，仅改变一个目标成员 $u$ 的授权状态，加入 K-hit 停止后，攻击者能否比观察普通过滤搜索获得更多关于 $u$ 授权状态的信息？

## 0. 基线与边界

| 项目 | 固定值 |
| --- | --- |
| 仓库 | `kaikai-cao/pa-vfann-experiment` |
| 对象存储链（common gitdir） | `pa-vfann-exp10-hnswlib-probe-workspace/.git` |

**`[R1.1]` 文档历史层级**（同一份文档在三轮审计中的状态；下列"本分支 / 唯一新增文件"是**各轮当时的记录**，不得误读为当前分支状态）：

| 层级 | 分支 | HEAD（该轮产出提交） | 本文档在该轮的角色 | 该轮起点基线 |
| --- | --- | --- | --- | --- |
| 原始 3A.3 设计阶段 | `research/h1-rm-3a3-paired-acl-feasibility` | `72440e82502e240ca64bcb2dfc43062e61e394d4` | **新增文件**（原始唯一新增文件） | 分支 `research/h1-rm-3a2-r1-evidence-erratum` / HEAD `4babeaa2aad2a02604cf5a448709690e67f3a43d` / 父 `dd6d28c2c5aad37189dd82114e2b5a07103919b4` |
| R1 ACL 秘密性修正 | `research/h1-rm-3a3-r1-acl-secrecy-independence` | `1e0149746b28a0fe99f0a5cc7ab79b50f7249722` | **修改文件**（R1 唯一修改文件） | 3A.3 HEAD `72440e82502e240ca64bcb2dfc43062e61e394d4` |
| 本次 R1.1 修正的直接基线 | `research/h1-rm-3a3-r1-acl-secrecy-independence` | `1e0149746b28a0fe99f0a5cc7ab79b50f7249722` | **修改文件**（R1.1 唯一修改文件） | R1 HEAD `1e0149746b28a0fe99f0a5cc7ab79b50f7249722` |

**`[R1.1]` 本次（R1.1）任务固定值**：基线分支 `research/h1-rm-3a3-r1-acl-secrecy-independence`，基线 HEAD `1e0149746b28a0fe99f0a5cc7ab79b50f7249722`，父提交 `72440e82502e240ca64bcb2dfc43062e61e394d4`，目标分支 `research/h1-rm-3a3-r1-1-target-selection`，唯一允许修改文件 `docs/H1_RM_3A_3_PAIRED_ACL_LEAKAGE_FEASIBILITY.md`。

**Phase 0 门禁**：原始 3A.3 阶段记录——common gitdir 为 `pa-vfann-exp10-hnswlib-probe-workspace/.git`（对象可解析）；分支/HEAD/父提交精确匹配；工作区 clean；目标分支本地与远端不存在；目标 worktree 路径空闲；基线报告 blob = `7e6dcf63ef6ee88e4b54f36dcdb3296dd2bb4bdb` 与冻结提交一致。**全部 PASS**（历史记录）。**`[R1.1]` 本次门禁**：common gitdir、分支 `research/h1-rm-3a3-r1-acl-secrecy-independence`、HEAD `1e01497…`、父提交 `72440e8…`、工作区 clean、目标分支本地与远端均不存在、目标 worktree 路径空闲、报告 blob = `9b3e433c7956d2386b566e0525d5215395478dda` 与冻结提交三处一致。**全部 PASS**。

**硬边界**：本轮只读核查代码与冻结数据、设计配对协议、冻结攻击者模型与统计量。禁止修改 C++/Python/`StorageAccess`、禁止生成四格数据、禁止运行 C0/C1/C2、禁止重跑 EXP-10 或 H1.1–H1.4、禁止创建 block backend、禁止声称已获得真实 TEE page trace、禁止启动 H1-RM.3B、禁止修改冻结产物、禁止建 PR。**无论本阶段裁决为何，均不自动启动 H1-RM.3B。**

**行号体系声明**：下文带行号引用一律指本 worktree 内冻结源码——`experiments/h1_rm2_native_stop/main.cpp`、`experiments/h1_rm_3a1_storage_bridge/main.cpp`、`experiments/h1_rm_3a1_storage_bridge/storage_access.h`、插桩头 `experiments/h1_rm_3a1_storage_bridge/hnswlib_bridge/hnswalg.h`。前序报告引用的 `third_party/hnswlib-v0.9.0-rm2-instrumented/` 为另一份插桩副本；同一路径在 `third_party/hnswlib-v0.9.0/` 是未插桩原始版。三者行号体系不同，不得混用。

---

## Phase 1 — 现有代码与数据可行性核查

### A. ACL 是否可以精确配对？——**机制可行；当前冻结实现不具备；且当前 ACL 不具秘密性 `[R1]`**

> **`[R1]` 关键修正——当前 ACL 无秘密性**：`authorized()` 是**无密钥的确定性 hash 谓词**（固定乘子 `2654435761ULL`，:96–99），授权规则与其实现代码对仓库读取者完全公开；manifest 又明文给出 `auth_rule` 与 `authorized_nodes=100`（`results/h1_rm2/manifest.json :18–19`）。攻击者只要知道目标 label 与规则，即可**直接离线算出该成员的授权状态**，无需任何轨迹。**因此当前冻结实验数据不能作为"攻击者不知道授权状态"的有效成员推断实验**——它仍可作为搜索机制研究与控制流分析材料，但**不得描述为秘密 ACL 下的成员推断证据**。原报告把"当前 hash 谓词对外不公开"写入攻击者模型（Phase 2 未知项）与裁决，与此处矛盾，本轮一并纠正。

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

#### `[R1]` 未来有效实验的 ACL 模型

当前 fixture 与未来实验设计必须分开。**未来**的 ACL 应满足对攻击者保密，两种候选方案：

- **首选：每个 ACL instance 独立生成私有随机 ACL bitmap**（本轮倾向此方案，避免引入不必要的密码学构造）。bitmap 仅研究者持有，不进入公开产物。
- **备选：公开算法 + 秘密 seed 的 keyed 生成机制**。攻击者可知道生成算法与授权比例先验 $p=0.1$，但**不知道秘密 seed、实际 bitmap 与目标成员授权位**。

**统计信息泄露细节**：当前 manifest 公开 `authorized_nodes=100` 这一**精确授权总数**。未来若采用独立 Bernoulli ACL，必须区分**公开的期望授权比例**（$p=0.1$，可作为先验）与**实际授权总数/逐位取值**（保密），不得把真实 ACL 的精确计数、hash 或逐位统计写入对外可见的 manifest/日志。**A0/A1 构造保持**：

$$A_{j,u}^{(0)}=A_{j,-u}\cup\{u=0\},\qquad A_{j,u}^{(1)}=A_{j,-u}\cup\{u=1\}$$

两者除 $u$ 的授权位之外**逐位相同**；配对元数据本身也是保密项（见下表）。

#### `[R1]` 研究者视图与攻击者视图分离（数据边界）

| 字段 | 研究者内部记录 | 攻击者可见 |
| --- | --- | --- |
| 目标成员身份 | 是 | 按威胁模型决定 |
| 真实授权状态 | 是 | 否 |
| ACL instance ID | 是 | 不作为分类器输入 |
| A0/A1 配对标记 | 是 | 否 |
| 私有 ACL seed / bitmap | 是 | 否 |
| ACL 摘要 | 是 | 不自动公开 |
| 页面访问序列 | 是 | 是 |
| 公开查询与图参数 | 是 | 是 |

**防泄露要求**：override 参数、运行文件名、目录名称、日志字段与公开 manifest 均不得泄露真实授权状态或 A0/A1 配对关系；分类器输入只含攻击者可见行，且需经字段白名单校验。

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

**独立单位 `[R1]`**：原报告称"现有 50 个 query 是独立单位"——需纠正：在同一 ACL、同一目标 $u$ 下，50 个 query 是**同一授权状态下的 50 次重复观察**，**不是 50 个独立授权标签**，随机划分 query 不能声称训练/测试在标签上独立（详见修正 B 与 Phase 4）。四格要求每个 $(j,u,q)$ 四跑，且真正的独立标签单位应是 **ACL instance $j$**（见 Phase 1-D、Phase 3）。当前数据均不满足。

### D. 目标成员 $u$ 如何选取？——**必须预先固定；现有样本不足以定义攻击者训练分布**

**选择依据（冻结）`[R1.1]`——目标成员从完整、公开的候选成员集合中预先选择，不依赖 ACL**：

1. **在生成 ACL instance 之前**，用预注册的固定随机种子与确定性规则，从**完整候选成员集合**（全部公开 label，而非任何授权子集）中选出目标成员集合 $U$。
2. 成员选择**不得依赖**真实 ACL、授权状态、轨迹、K-hit 位置或任何搜索结果。
3. 目标集合、选择规则与随机种子由研究者记录；攻击者是否知道目标身份**由具体威胁模型决定**（见 Phase 2 攻击者模型）。
4. 每个独立 ACL instance 的授权状态**独立生成**，遵循预设的自然先验 $p=0.1$（见 Phase 4 自然先验定义）。
5. **固定成员推断**与**成员泛化推断**继续严格区分（见下）。

> **`[R1.1]` 删除的旧规则**：原报告示例"对授权节点集合（100 个，label 空间可由公开 hash 规则离线复算）按 `label` 升序取前 $P$ 个"依赖**当前公开 hash ACL**，与未来**私有随机 bitmap** 模型不兼容（私有 bitmap 下授权集合对研究者选点前亦不应成为选择依据），故删除。示例"对全部 1000 个 label 用固定种子 hash 排序取前 $P$"符合上述协议，予以保留。**禁止**先看轨迹 gap/K-hit 位置再挑"差异最大"的节点（对测试集的隐式调参，会使 BA 虚高）。选择规则、随机种子与 $P$ 值必须在 ACL 生成前预注册。

**多目标成员的类别分布检查 `[R1.1]`**：允许研究者在生成 ACL **之后**检查目标集合的实际类别分布（授权/未授权各多少），但**不得**依据轨迹挑选成员，也**不得**把依据真实授权状态筛出的样本误称为"自然部署分布"——此类条件化筛选会改变先验，须如实标注。

**两种样本单位的统计含义 `[R1]`**：

- **固定单 u × 多 query（同一 ACL）**：query 是**同一授权状态下的重复观察**，$u$ 的授权位在全部 query 中恒定。n 不是 query 数，而是**独立 ACL instance 数**——同一 ACL 下的 query 不能跨训练/测试划分。估计的是"该特定成员在不同 ACL 实例下的可推断性"，不能靠划分 query 得到独立标签。
- **预选 u 集合 × 多 ACL instance**：可支持成员泛化，但同一 ACL instance 内多个 u、多个 query、A0/A1 反事实与 C1/C2 结果全部相关，必须作为**同一簇**处理（见 Phase 4）。

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

- **已知**：查询 $q$；HNSW 索引版本、公开图结构与参数（$N=1000,d=16,M=16,ef=64,k=10$）；节点→页映射规则；目标成员 $u$ 的公开逻辑身份（其 label）；授权比例先验 $p=0.1$ 与 ACL 生成算法（若为 keyed 方案）。**`[R1]` 在当前 fixture 下还额外知道 `auth_rule` 与固定 hash 常量，因此可直接算出 $u$ 的授权状态——这正是当前数据不具备 ACL 秘密性的原因（见 Phase 1-A）。下述"未知"仅在未来的私有 ACL / 秘密 seed 模型下成立。**
- **未知（仅未来私有 ACL 模型下）** `[R1]`：私有 ACL bitmap / 秘密 seed；$u$ 的授权状态；filter 判定结果；K-hit 计数；候选集、距离值、最终授权结果。**当前冻结 fixture 不满足此未知条件，不得据此宣称成员推断实验。**
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

#### `[R1]` 冻结层次结构

| 层次 | 含义 |
| --- | --- |
| ACL instance $j$ | 一份独立生成的秘密 ACL（私有 bitmap 或秘密 seed） |
| Target member $u$ | 被推断授权状态的成员 |
| Query $q$ | 同一授权状态下的一次观察（**非独立标签**） |
| Condition $c$ | C1 或 C2 |
| State $a$ | 目标成员未授权（0）或已授权（1） |

**实验单位** = 同一 $(j, q, G, u)$，其余 ACL 位固定、$u$ 按 Phase 1-D 预注册规则选取，索引 $G$ 由固定 seed 与插入顺序构建。四格配对样本记为：

$$T_{j,u,q,a,c}=T(q,G_j,A_{j,u}^{(a)},C_c),\quad A_{j,u}^{(0)}=A_{j,-u}\cup\{u=0\},\ A_{j,u}^{(1)}=A_{j,-u}\cup\{u=1\}$$

| 授权状态 | C1 普通过滤 | C2 增加 K-hit |
| --- | --- | --- |
| $U=0$ | $T_{j,u,q,0,1}$ | $T_{j,u,q,0,2}$ |
| $U=1$ | $T_{j,u,q,1,1}$ | $T_{j,u,q,1,2}$ |

**`[R1]` 研究者视图 vs 攻击者视图的数据用途（关键）**：研究者可以生成 $A_0/A_1$ 四格反事实轨迹（两世界都可见，用于配对机制比较与 $D_{filter}$/$D_{stop}$ 分离）；**攻击者不能同时观察同一目标在两个反事实世界里的轨迹**——真实部署中只有一个 ACL instance 的一个真实状态。因此：

- **A0/A1 四格**：仅用于研究者的配对机制比较；**禁止**把同一目标的 A0 与 A1 轨迹当作两个独立攻击样本交给分类器（会引入反事实配对信息泄露，虚高 BA）。
- **攻击训练/测试数据**：每个独立 ACL instance–target 在**一个真实状态**下提供观察，授权状态是该实例中的固定标签；训练与测试按 ACL instance 隔离（见 Phase 4）。

**必须记录的核对元数据（8 项）**：query ID、target member ID（label+internal）、ACL 配置摘要（含被翻位与其余位 hash，**保密**）、索引摘要（seed+插入序列+图结构 hash）、搜索参数（$M/ef/k/LABEL$ 常量）、C1/C2 条件标识、trace 类型（search/logical/synthetic-page）、轨迹哈希（对页面 ID 序列含重复项做规范化 hash）。缺任一项则该格不进入分析；配对标记与 ACL 摘要按 Phase 1-A 视图表保护，不进分类器。

**有效性前置**：若 B 节三项下游差异未被显式建模，不得进入统计；$A_0/A_1$ 必须证明除 $u$ 位外逐位相同（写入 ACL 摘要比对）。本阶段**不生成四格数据**。

---

## Phase 4 — 冻结统计量与攻击成功标准

#### `[R1.1]` 三个必须区分的概念：自然先验 / Balanced Accuracy / 类别平衡诊断集

原报告"授权/未授权平衡先验"一句把三件事混为一谈，现拆为相互独立的三个概念：

1. **自然授权先验**：$P(U=1)=p=0.1$。这是未来实验中 ACL 生成机制（独立 Bernoulli bitmap）的授权比例先验，**也是攻击者可以知道的先验信息**（见 Phase 2 已知项）。它是数据生成的真实分布，不是评价时的重采样设定。
2. **Balanced Accuracy**：$BA=\frac{TPR+TNR}{2}$——对正类（授权）与负类（未授权）分别计算召回率后**等权平均**。BA 对两类等权是**指标的构造方式**，**不意味着**实际 ACL 中授权与未授权成员各占一半；BA 的随机猜测基线恒为 $0.5$（与 $p=0.1$ 无关）。因此 $\operatorname{Adv}_c=BA_c-\tfrac12$ 中的 $\tfrac12$ 是 BA 的随机基线，不是"自然分布下猜多数的准确率"。
3. **类别平衡诊断集**：研究者**可另行**构造授权/未授权 1:1 的类别平衡诊断评估集，但**必须明确标注其采样方式**（重采样/加权），不得把它当作自然授权分布（$p=0.1$）。正式结果应保留自然先验；在适用时**同时报告自然分布下**的准确率（accuracy）、精确率（precision）、PR-AUC 等指标，避免仅以 BA 掩盖 $p=0.1$ 下的类别不平衡表现。

> 本轮**不新增**分类器、数据集或指标计算，以上仅为协议文字澄清。

**评价量**（对固定攻击者、留出测试集，C1 与 C2 分别评估）：

$$\operatorname{Adv}_c=\operatorname{BA}_c-\tfrac12,\qquad \boxed{\ \Delta_{\mathrm{adv}}=\operatorname{BA}_{C2}-\operatorname{BA}_{C1}\ }$$

$\operatorname{Adv}_{C1}$ = 普通过滤下推断能力；$\operatorname{Adv}_{C2}$ = 加 K-hit 后推断能力；$\Delta_{\mathrm{adv}}$ = 该固定攻击者与分布下的**经验攻击增益**。**不是**互信息差、**不是**对最优攻击者的密码学保证、**不是**"轨迹编辑距离之差"——轨迹距离只是变化指标，不代表攻击者能推断授权状态。

**机制分离量（研究者诊断用，不作攻击结论）**：$D_{filter}=d(T_{j,u,q,1,1},T_{j,u,q,0,1})$（纯过滤效应），$D_{total}=d(T_{j,u,q,1,2},T_{j,u,q,0,2})$，$\Delta_{trace}=D_{total}-D_{filter}$（K-hit 额外轨迹变化）。只有按 ACL instance 配对统计的 $\Delta_{adv}>0$ 且其 CI 下界 >0 时，才谈"额外推断能力"；$\Delta_{trace}>0$ 本身不构成证据。

#### `[R1]` 统计独立单位：ACL instance，而非 query

**原报告"query-level paired bootstrap"不作为主要独立性方案**，修正如下。同一目标 $u$ 在同一份 ACL 下的 50 个 query，其授权状态恒定——50 次观察 ≠ 50 个独立授权标签；按 query 随机划分训练/测试会造成标签泄漏。

**`[R1]` 两种评估目标（结果不得混为一谈）**：

- **固定成员推断**：同一 $u$ 在**多个独立 ACL instance** 下评估。训练与测试必须**按 ACL instance 分组隔离**——同一份 ACL 及其衍生的所有 query、A0/A1、C1/C2 轨迹不得跨越训练/测试边界。
- **成员泛化推断**：除 ACL instance 隔离外，还须将**目标成员身份**按预先确定的规则分组留出，才能声称对未见过的成员具有泛化能力。

**`[R1]` Bootstrap 修正**：对 $\Delta_{adv}$ 的主要重采样单位改为**独立 ACL instance $j$**。同一 ACL instance 内的目标成员、所有 query、A0/A1 配对记录与 C1/C2 结果作为一个**相关簇**整体重采样；计算 C1/C2 经验增益时保留两种条件的配对关系。Query 仅作实例内重复观察，**不得当作独立 ACL 标签样本**。若采用多个目标成员，须显式说明同一 ACL instance 下多个目标共享 ACL 的相关性（簇内相关，按簇处理）。

**其余统计要求 `[R1.1]`**：① 自然授权先验 $p=0.1$（数据生成分布，攻击者可知），评价指标 BA 对两类等权、其随机基线为 0.5，二者不同；类别平衡诊断集须标注采样方式且不充当自然分布（见本节三段澄清）；② 保留两种 ACL 状态的配对（研究者视图）；③ 同一 ACL instance 的所有四格记录放同一训练或测试分组（防配对与实例泄露）；④ 训练与调参只用训练集，测试集不参与模型选择；⑤ 主 bootstrap 按 ACL instance 分簇（见上）；⑥ 同时报 BA、AUC、95% CI 及每个目标成员的结果；⑦ 独立 ACL instance 不足以支撑独立测试集时，**不得**用训练准确率或未分组交叉验证替代，须降级为敏感性分析。

**正面判据（须同时满足）**：C2 测试 BA 显著高于随机基线（0.5）；$\Delta_{adv}$ 的 95% 配对 CI（按 ACL instance）下界 >0；结果不由 ACL instance、query、成员身份、索引差异、A0/A1 配对标记或其他泄露字段直接造成；输入确为攻击者可观察轨迹而非内部 search trace 或反事实配对轨迹。

**降级规则 `[R1]`**：若只用合成页级代理，结论上限为"存在页级代理上的成员推断可行性迹象"，**不得声称已证明真实 TEE 攻击**；若缺乏可信 shadow training data，**或独立 ACL instance 数量不足以支撑按实例分组的训练/测试与配对 bootstrap**，攻击评估降级为配对轨迹敏感性分析，并明确不足以证明成员推断能力。当前 fixture 因 ACL 公开（修正 A）且只有单一实例（修正 B），属于双重不满足，**只能作机制分析，不能作成员推断评估**。

---

## Phase 5 — 最终裁决

### **CONDITIONAL — 只允许受限代理验证；不得进入 H1-RM.3B**

**逐项排除 `[R1]`**：

- **不是 STOP**：在**未来的私有 ACL 模型下**，配对机制（A：label↔internal 一一映射、单 label override 可审计）、C1/C2 可比性（B）、攻击者输入定义（带重复的页 ID 序列 + 请求边界）、四格协议与统计量（Phase 3/4）均已冻结，设计上可成立。STOP 所列的"不能翻位 / C1C2 不可比 / 无可定义输入 / 数据根本不能配对分析"指的是**设计不可能**，而非"当前 fixture 不满足"——后者由 CONDITIONAL 覆盖。
- **不是 GO**：`[R1]` 当前 ACL 公开（修正 A）+ 单一 ACL instance、query 非独立标签（修正 B），**双重不满足有效成员推断实验的必要条件**；再加无 $\delta$ 基地址、无真实 TEE page trace、无 shadow 训练机制、无四格配对记录。不能据此宣称成员推断能力。按硬边界本轮也未生成任何配对数据。
- **CONDITIONAL 的允许范围**：仅允许在将来的最小配对实验准备中，构造 `Synthetic page-level proxy trace`（并对 $\delta$ 做敏感性扫描）或 logical trace 做**受限配对敏感性分析**；结论按 Phase 4 降级规则表述。

**进入任何后续验证前的前置条件（全部满足才可重新裁决）`[R1]`**：

1. 真实 ACL 位图或秘密 seed **不向攻击者公开**——当前 fixture 的无密钥 hash 不满足，须替换为私有 bitmap（首选）或 keyed seed；
2. $A_0/A_1$ **仅翻转目标成员的一位**，且配对元数据（配对标记、ACL 摘要、override 参数、文件名/目录名/日志字段）受视图分离保护，不进分类器；
3. 有**多个独立 ACL instance**，能支持按 ACL instance 隔离训练与测试（非按 query 划分）；
4. 明确区分**固定成员推断**与**成员泛化推断**（后者额外按成员身份留出），结果不得混报；
5. 按 **ACL instance** 进行配对统计推断（paired bootstrap 以实例为簇），query 仅作实例内重复观察；
6. 若无法获得足够独立 ACL instance（或无 shadow ACL），**降级为敏感性分析**，不宣称完成成员推断评估。

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
| `[R1]` 公开 hash 规则与"ACL 对外秘密"假设的矛盾已消除；当前数据明确标为不具 ACL 秘密性 | PASS |
| `[R1]` 研究者视图 / 攻击者视图字段表齐备；防 override/文件名/目录名/日志/manifest 泄露真实授权位 | PASS |
| `[R1]` query 不再被误称独立授权样本；bootstrap 主单位改为独立 ACL instance，query 仅实例内重复观察 | PASS |
| `[R1]` shadow ACL、A0/A1 反事实与训练/测试隔离的单位定义一致；未把 A0/A1 当独立攻击样本 | PASS |
| `[R1]` 区分固定成员推断与成员泛化推断；CONDITIONAL 裁决原样保留 | PASS |
| `[R1.1]` 已删除"公开 hash 授权集合按 label 升序取前 P"的旧选点规则 | PASS |
| `[R1.1]` 目标成员在 ACL 生成前由预注册种子从完整公开候选集合独立预选，不依赖授权状态/轨迹/K-hit/搜索结果 | PASS |
| `[R1.1]` 自然先验 $p=0.1$、Balanced Accuracy（随机基线 0.5）、类别平衡诊断集三者明确区分，正式结果保留自然先验 | PASS |
| `[R1.1]` §0 分清原始 3A.3 / R1 / R1.1 三层基线、HEAD 与文件角色（新增/修改），历史"本分支/唯一新增文件"未误读为当前状态 | PASS |
| `[R1.1]` CONDITIONAL 裁决与全部硬边界原样保留；未改代码/数据/实验，未启动 3B、未建 PR | PASS |

本阶段到此停止；拿到真实配对证据后再裁决，不自动开始下一阶段。
