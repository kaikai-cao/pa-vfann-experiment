# EXP-02-R0 — Agentic RAG 授权轨迹泄漏预研（审计包）

本目录是一次**只读预研**的全部产物。它不实现攻击、不实现密码学方案、不修改既有实验代码；只在 `pa-vfann-experiment` 的独立分支 `exp08-agentic-trace-leakage-audit` 上新增本目录。

## 结论摘要

**HOLD**（EXP-02-R0 / R0.1 / R0.2 / R0.2.1 / R0.2.1a 一致，理由逐轮修订）。核心问题尚未被证伪，但当前没有任何单一数据集同时具备「真实 Agentic 多步检索轨迹」和「可信的授权范围 / 权限状态真值」。ASQ 有轨迹无 ACL；Permission-Aware Enterprise RAG Benchmark 有 ACL 时点真值无轨迹。两个数据集不能合法拼接。

**R0.2 修订要点**：独立审查指出 R0.1 初稿有一处逻辑跳步——架构 A（客户端过滤）虽无**直接**过滤结果泄漏，但存在**间接**通道：ACL 改变 Agent 上下文 → 后续自适应检索变化 → 服务端可见轨迹变化。这正是 Agentic RAG 相比单轮检索新增的泄漏面，不能因"混有任务自适应行为"就在实验前排除。架构 C 不再是单一模型——TEE/ORAM/PIR/加密过滤可见性截然不同。

**R0.2.1 修订要点（本轮，重要）**：
1. **查询隐私执行边界**：源码审计确认 ASQ 默认是 **A1 本地检索**——Agent 明文查询经 `search_pipeline.search(query, qid)` 直传本地 PyTerrier Retriever，全程无网络边界、无外包服务端观察主体。因此"日志不记录明文"不等于"服务端看不到明文"。A2 明文外包只能作 `QUERY-VISIBLE DIAGNOSTIC`；只有经核验的 A3 后端才可能符合查询隐私威胁模型，当前 `NO VERIFIED QUERY-PRIVATE RETRIEVAL BACKEND`。ASQ 的 Agent 生成器可复用，但默认 BM25 检索器**不能直接当隐私保护外包服务**。
2. **统计独立性勘误**：148 条撤权探针实测为 **1 主体（全 u4）、1 时间点、19 目标组合、无事件关联字段**；49 条 ACL 事件仅 **21 时间戳**且含 20 条继承传播事件；u019/u044 无 golden QA。两类 estimand 分开：任务 I（跨主体推断）`NOT_EVALUABLE`，任务 II（同主体状态变化）按独立事件簇而非探针记录数。禁止 "148 probes + 32 events" 相加当样本量。

**R0.2.1a 修订要点（本轮，统计口径精确化）**：仅修三处统计口径，不改裁决等级、不重审 ASQ 源码、不找后端、不生成轨迹。① 19 个 `(user,doc,canary)` 只是 distinct 目标键，**不是** 19 个独立统计簇（独立簇 `UNKNOWN`）；148 探针 0 事件关联、0 前后轨迹 → 任务 II `NOT_EVALUABLE`。② 49 事件精确独立簇数 `UNKNOWN`，只有 4 组由 event_id 命名家族识别、reason 交叉印证的继承传播家族（每组 1 根 + 5 传播，共 20 条传播记录），21 时间戳 ≠ 21 独立事件。③ 静态角色标签主体为 **186/186**（全部有 `team_id`），3 个 `move_date` 主体只用于角色变化检测；组覆盖 186/186 含 `all-hands` 通用组，不代表可区分组标签；并纠正"组历史为空"的事实错误（全局 14 组共 19 条历史，u4/u019/u044 分别有 8/3/2 条主体级记录）。可评估性硬阻塞仍是"无轨迹 + 无事件关联"，事实勘误不等于可评估性提升。**R0.2.1a.1 最终勘误**：继承依据补全为 event_id 命名家族 + reason 交叉印证（非仅 reason，也非外键）；组覆盖限定为 membership coverage；Task II 措辞从"独立簇严重不足"改为"独立簇 `UNKNOWN` + 无可确认关联/配对"。详见 `MINIMAL_EXPERIMENT_DESIGN.md` §7。

修订后的核心研究问题：**在客户端执行 ACL 过滤、Agent 根据授权上下文多步自适应检索的条件下，外包检索服务能否仅凭跨调用可见轨迹推断主体的权限范围或权限状态变化？**（待检验假设，非已成立创新点。）

修订后的 HOLD 理由（三层并列阻塞）：**研究问题层**架构 A 间接泄漏待检验；**实验后端层**缺合规查询隐私后端；**统计层**跨主体与同主体两类任务分别划分且独立单位不足。详见 `R0_1_DECISION.md` §0 与 `MINIMAL_EXPERIMENT_DESIGN.md` §6–7。

三问速答：

1. **是否存在真正的授权推断信号？** 现有数据无法回答。ACL Benchmark 的权限真值可信，但文档 ID 命名空间与团队确定性耦合，存在无法排除的合成伪相关；必须用 opaque ID 对照。
2. **B4 是否比 B2 多知道东西？** 本轮不能测。B3/B4 依赖「session 标识是否暴露给服务端」这一架构事实，ASQ 的 `qid` 是评测标识，不得默认服务端可见；还需服务端可见的**稳定主体伪标识**才能做逐主体权限状态检测，研究者侧 `subject_id` 不得冒充服务端字段。R0.2.1 新增：即便可见，统计独立单位也不足——撤权探针仅 1 主体 / 19 目标，两类 estimand 须分开划分，不能用记录数当样本量。
3. **是否有合理密码学落点？** 尚不能确认。ObliSC 证明可在 TEE+ORAM 假设下获得完全遗忘，PP-RFANNS 显式接受访问模式泄露；没有证据支持现在引入新的 ZK/PIR/ORAM 贡献。R0.2.1 强调：查询隐私后端（A3）缺失是实验后端层的阻塞，但不得因此先定密码学机制再找问题。

## 目录结构

```
research/exp08-agentic-trace-leakage-audit/
├── README.md                   本文件
├── DATA_AUDIT.md               Phase 1-2：数据集/文献证据与可用性
├── THREAT_MODEL.md             Phase 3：可见/不可见信息与推断目标
├── BASELINE_MATRIX.md          Phase 4：B0-B4 规格与公平比较约束
├── DECISION.md                 R0：GO/HOLD/NO-GO 与阻塞项
├── AGENT_GENERATION_AUDIT.md   R0.1 Phase 3：源码可行性 + R0.2.1「Query Privacy and Execution Boundary Audit」章节
├── OBSERVABILITY_AUDIT.md      R0.1 Phase 4：三种 ACL 架构可见性 + R0.2.1 §4.3 执行模型对齐
├── MINIMAL_EXPERIMENT_DESIGN.md R0.1 Phase 5：实验规格 + R0.2.1 §6 两类 estimand / §7 统计独立性审计（R0.2.1a §7.1–7.6 口径修订）
├── R0_1_DECISION.md            R0.1 Phase 6：裁决（R0.2.1a 三层状态修订）
├── evidence/
│   ├── sources.md              原始来源、核验日期、状态
│   ├── claims_and_evidence.md  结论—原始证据—核验方法—状态
│   ├── dataset_manifest.json   版本/URL/SHA256/许可证（脚本生成）
│   ├── version_pinning.json    R0.1：固定 revision 下载与 SHA256 门禁日志
│   ├── sample_validation.json  25 条 ASQ 轨迹抽查记录（脚本生成）
│   ├── acl_audit.json          ACL 结构与时点真值统计（脚本生成）
│   └── audit_output.txt        脚本实际运行输出
└── scripts/
    └── audit_datasets.py       可重复的数据检查脚本（固定 revision + SHA 门禁）
```

## 复现命令

在仓库根目录（Windows Git Bash）：

```bash
# 若临时数据已存在
python research/exp08-agentic-trace-leakage-audit/scripts/audit_datasets.py \
  --data-dir "$TEMP/exp02_r0_data" \
  --out-dir research/exp08-agentic-trace-leakage-audit/evidence \
  --samples 25

# 从固定 revision 重新下载缺失文件（标准库 urllib，无第三方依赖）
python research/exp08-agentic-trace-leakage-audit/scripts/audit_datasets.py \
  --data-dir "$TEMP/exp02_r0_data" \
  --out-dir research/exp08-agentic-trace-leakage-audit/evidence \
  --samples 25 --download

# 强制全量重下载并生成版本锁定日志（R0.1 Phase 2 验收命令）
python research/exp08-agentic-trace-leakage-audit/scripts/audit_datasets.py \
  --data-dir "$TEMP/exp02_r0_data" \
  --out-dir research/exp08-agentic-trace-leakage-audit/evidence \
  --samples 25 --download --force-download
```

脚本依赖：Python 3.10+ **仅标准库**（不再依赖 `huggingface_hub`）；下载走 `resolve/<pinned revision>/`，每个文件做 SHA256 门禁，哈希不符硬报错且无 main 回退。脚本只读源数据，输出只含结构元数据，**不写出** `llm_query`、`thought`、`answer` 等研究者/agent 可见内容。

## 边界

- 论文作者声称与本审计独立验证结论在 `claims_and_evidence.md` 中分列；未核实的写 UNVERIFIED，不写成事实。
- 数据集原始文件只下载到系统临时目录，**未复制进仓库**，仓库内只保留哈希、统计与元数据。
- 不把合成数据写成真实企业验证；不把 qid 分组默认当成服务端可见；不把 PA-VFANN 的 E3 外推为抵御 SAGE。
- 本轮结束即停止，不自行启动 EXP-02-R1。
