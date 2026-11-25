# MINIMAL_EXPERIMENT_DESIGN.md — 最小可执行配对实验设计

任务：EXP-02-R0.1 Phase 5。性质：**实验规格，本轮不执行**。目标：给出一个最小、可控的配对实验，判定 B4（有序 Agentic 轨迹）相对 B2（SAGE 式扁平共现）是否带来超出任务语义与命名空间伪相关的授权推断增益，并据此决定 GO / NO-GO。

设计前提（来自 Phase 3/4）：
- 数据：ACL Benchmark 提供主体、ACL、时点真值；ASQ 生成流程可复用其多步记录机制但需三项改造（自定义索引/retriever、ACL 拦截、主体身份字段）——见 `AGENT_GENERATION_AUDIT.md`。
- 架构：**主实验采用架构 C（加密/隐私保护 ACL 过滤）的威胁模型**——服务端不持明文 ACL 但可见结果 ID/数量/轮次；架构 A 作阴性对照、B 不用于主实验——见 `OBSERVABILITY_AUDIT.md`。所有 B0–B4 只使用服务端可见字段。

---

## 1. 三个要分离的因子

| 因子 | 记号 | 操作化定义 |
|---|---|---|
| F1 任务语义相关性 | T | 任务的查询主题 / QA 类别（如 `multi_hop`、`temporal`、`acl_differentiated`） |
| F2 文档访问集合及跨调用共现 | D | 服务端可见的返回 docid 集合、跨调用共现、返回数量、轮次 |
| F3 ACL 状态变化 | P | 主体在某时点的有效权限 / 角色 / 撤权事件前后状态 |

**目标**：证明 B4 相对 B2 的增益来自 F3（或至少 F2 中超出扁平共现的部分），而非 F1 或对 ID 命名空间（语义化 docid）的解码。

---

## 2. 数据准备（本轮不执行，仅规格）

1. **语料与 ID**：取 ACL Benchmark `data/documents_manifest.jsonl` 的 12,214 文档；建立**全局一致的随机 opaque 映射** `doc_id → OPQ-<rand>`，所有 B0–B4 共用同一映射。禁止把 `confluence:<SPACE>:...` 语义化 ID 喂给任何攻击者特征。
2. **检索轨迹生成**：用 ASQ 的生成流程（`build_agent` + 自定义 retriever + ACL 拦截 + 主体字段扩展）为每个主体/时点生成多步轨迹；记录字段仅 `subject_id, asked_at, session_id, call_order, returned_opaque_docids, result_count`。生成时不把 `query/thought/answer` 暴露给攻击者特征。
3. **标签**：
   - 角色标签 = 主体 `team_id`（9 类，含 is_lead/is_exec/is_contractor 属性另作多标签）；
   - 有效权限范围 = 主体在 `asked_at` 时可访问容器/文档集合（由 `initial_acl` + 时点事件重建，`ACL Benchmark` 支持）；
   - 权限状态 = `pre/post revocation`、`pre/post role-change`；撤权/角色变更事件来自 32 条触及 golden 用户的事件、3 个 move_date 主体、52 条 `acl_time_travel` QA、148 条 `post_revocation_ask` 探针。

---

## 3. 对照设计（A/B/C/D）

### 对照 A：同一任务，不同权限状态
- 固定任务 qid 与语料，仅改变主体 ACL 状态（如 u4 在 2026-07-01 转队前/后；或某容器撤权前/后）。
- 观察服务端可见轨迹（opaque docid 序列、返回数量、轮次）是否随 P 改变。
- **判据**：若轨迹在 P 变化前后完全一致（opaque 映射下），则该主体上不存在服务端可见的权限状态信号 → 该项记为不可推断。

### 对照 B：不同角色，相同任务内容
- 选取任务语义相同/高度相近、但主体角色不同的样本对；控制 T 使模型不能仅凭任务内容预测角色。
- 若某角色分类性能在"仅 F1 特征"与"F1+F2"下相同，则角色信号可由任务语义解释，不构成授权推断证据。

### 对照 C：相同权限，不同任务内容
- 固定主体与权限状态，改变任务内容；测量任务语义对角色/权限推断的干扰（即模型是否其实在学 T）。
- 与对照 B 互为反向控制，共同分离 F1 与 F3。

### 对照 D：语义化 ID vs opaque ID
- 正式结果**只用 opaque ID**；语义化 ID（`confluence:<SPACE>:...`）**仅作为伪相关上界**运行一次，用于量化"从 ID 字符串解码 team 标签"能拿到多少虚高准确率。
- 若 opaque 条件下 B4−B2 增益消失，而语义化 ID 条件下存在 → 增益来自命名空间解码，命中 NO-GO。

---

## 4. 基线（B0–B4）与公平比较

沿用 `BASELINE_MATRIX.md`，补充本实验约束：
- **输入字段统一**：所有方法只用 `returned_opaque_docids`（集合/序列）、`result_count`、`call_order`、`session_id`（服务端可见者）。`query/thought/answer/user_id/role` **不得**进入攻击者特征（`user_id` 仅在数据划分与配对时使用，不作为推断输入）。
- **信息量与容量匹配**：B2/B3/B4 使用同等规模的共现图/序列模型；B4 仅多"组内顺序"，不得额外给更多参数或训练轮次。B4−B2 的差值是本实验核心量。
- **标签辅助**：若用已知标签辅助（如 SAGE-Known 式锚点），必须在 B2 与 B4 上使用**相同比例与相同锚点集合**，否则不公平。

---

## 5. 评估指标（主要 / 次要 / 不可评估）

- **主要指标**
  - Role Macro-F1（多类，类别不平衡——9 团队 + 属性多标签用 macro 平均）；
  - Effective Permission Scope：多标签宏观 F1（每个容器/权限组为标签）或子集准确率；
  - Policy-state Accuracy（pre/post 二分类或三态）；
  - Revocation Detection AUROC（撤权前/后轨迹判别）。
- **核心比较量**：`Δ = B4 − B2`（各指标上的配对差值），报告均值、配对 Bootstrap 95% CI 下界。
- **次要指标**：Task-category Accuracy、Recall@K。
- **不可评估（本数据集不支持则明确标注）**：若无法从某个主体生成足够时点轨迹，则该主体的 revocation AUROC 标为 N/A，不补造样本。

## 6. 统计可行性与划分

- **配对 Bootstrap**：以主体为配对单位，对 `Δ` 做 ≥1000 次重采样，报告 CI。**判死**：主要指标 CI 下界 ≤ 0 视为无稳定增益。
- **主体划分**：train/test 按 `subject_id` 不相交划分（禁同一主体跨集）；角色变更主体（u4/u019/u044）单独成组，避免泄漏。
- **时间划分**：撤权/转队样本按 `asked_at` 时序切分，训练用事件前数据、测试用事件后数据，防未来事件泄漏。
- **多随机种子**：≥5 seeds，报告均值与方差，不只报单次最好值。
- **样本规模现实检查（来自 Phase 1 实测）**：
  - 权限变化事件 49 条 / 45 容器；触及 golden 用户（u1–u6）的事件 32 条；
  - 角色变更主体仅 3 个（u4/u019/u044）；`acl_time_travel` QA 52 条且**全部针对 u4**；`post_revocation_ask` 探针 148 条。
  - **判定**：撤权检测可凑出统计样本（148 探针 + 32 事件），但**角色变更推断仅 3 个主体**，若按主体不重叠划分，测试主体可能仅 1 个 → **无法支持可信的主体级 Macro-F1 结论**。必须通过 ASQ 生成器在 ACL 语料上扩充主体轨迹后才可能支撑；若无法扩充，则 Role Inference 指标标为**统计不足**，不得用重复采样制造样本量。

## 7. 判死标准（写死，避免事后换指标）

进入 R1 后若出现以下任一，直接 NO-GO 停止该候选方向，不改名/换指标/扩威胁模型：
1. opaque ID 下 B4−B2 主要指标配对 Bootstrap CI 下界 ≤ 0；
2. 增益仅在语义化 ID 条件下出现（=命名空间解码伪相关）；
3. 增益依赖 query/thought/answer/user_id 等服务端不可见字段；
4. 无法区分任务语义（F1）与权限状态（F3）——对照 B/C 不通过；
5. 角色变更主体样本经扩充后仍不足以支撑主体级统计结论，且撤权检测也无稳定增益。

## 8. 与 R0 唯一阻塞项的衔接
R0 的唯一阻塞是"没有单一数据集同时具备 Agentic 轨迹与权限真值，且不能拼接两个数据集"。本设计给出的路径是：以 ACL Benchmark 为真值与语料源，用 ASQ 开源生成器**独立生成**带 opaque docid 的轨迹（记录主体/时间/session/顺序），在同一数据、同一划分、同一辅助知识下跑 B2/B4 配对对照。本轮（R0.1）只确认该路径的源码可行性（Phase 3：PARTIAL-FEASIBLE）与威胁模型自洽性（Phase 4：仅架构 C 自洽），**不执行生成**，故是否进入 R1 见 `R0_1_DECISION.md`。
