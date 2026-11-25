# EXP-02-R0 — Agentic RAG 授权轨迹泄漏预研（审计包）

本目录是一次**只读预研**的全部产物。它不实现攻击、不实现密码学方案、不修改既有实验代码；只在 `pa-vfann-experiment` 的独立分支 `exp08-agentic-trace-leakage-audit` 上新增本目录。

## 结论摘要

**HOLD**（EXP-02-R0 与 EXP-02-R0.1 一致）。核心问题尚未被证伪，但当前没有任何单一数据集同时具备「真实 Agentic 多步检索轨迹」和「可信的授权范围 / 权限状态真值」。ASQ 有轨迹无 ACL；Permission-Aware Enterprise RAG Benchmark 有 ACL 时点真值无轨迹。两个数据集不能合法拼接。

EXP-02-R0.1 进一步收敛了阻塞项：**研究问题是否成立取决于 ACL 执行架构**。架构 A（客户端过滤）权限信号不在服务端可见面内，架构 B（服务端过滤）服务端已知 ACL（推断=循环论证），仅架构 C（加密/隐私保护过滤）使"服务端不持 ACL 但从轨迹推断权限状态"自洽。因此主阻塞变为：先确认目标系统采用架构 C；若确认，再在 ACL Benchmark 上用开源 Agent 独立生成带 opaque ID 的轨迹并执行 B2/B4 配对对照。详见 `DECISION.md` 与 `R0_1_DECISION.md`。

三问速答：

1. **是否存在真正的授权推断信号？** 现有数据无法回答。ACL Benchmark 的权限真值可信，但文档 ID 命名空间与团队确定性耦合，存在无法排除的合成伪相关；必须用 opaque ID 对照。
2. **B4 是否比 B2 多知道东西？** 本轮不能测。B3/B4 还依赖「任务分组 / 会话标识是否暴露给服务端」这一架构事实，ASQ 的 `qid` 是评测标识，不得默认服务端可见。
3. **是否有合理密码学落点？** 尚不能确认。ObliSC 证明可在 TEE+ORAM 假设下获得完全遗忘，PP-RFANNS 显式接受访问模式泄露；没有证据支持现在引入新的 ZK/PIR/ORAM 贡献。

## 目录结构

```
research/exp08-agentic-trace-leakage-audit/
├── README.md                   本文件
├── DATA_AUDIT.md               Phase 1-2：数据集/文献证据与可用性
├── THREAT_MODEL.md             Phase 3：可见/不可见信息与推断目标
├── BASELINE_MATRIX.md          Phase 4：B0-B4 规格与公平比较约束
├── DECISION.md                 R0：GO/HOLD/NO-GO 与阻塞项
├── AGENT_GENERATION_AUDIT.md   R0.1 Phase 3：ASQ 生成源码可行性核验
├── OBSERVABILITY_AUDIT.md      R0.1 Phase 4：三种 ACL 架构的服务端可见性
├── MINIMAL_EXPERIMENT_DESIGN.md R0.1 Phase 5：最小配对实验规格
├── R0_1_DECISION.md            R0.1 Phase 6：本轮裁决与收敛阻塞项
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
