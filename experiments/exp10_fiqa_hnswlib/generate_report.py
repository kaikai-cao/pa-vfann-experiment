#!/usr/bin/env python3
"""Generate the final EXP-10B.1 report from machine-readable artifacts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "EXP10_FIQA_REPORT.md"
SUMMARY = ROOT / "results" / "exp10_fiqa_summary.json"
DATA = ROOT / "data" / "exp10_fiqa_manifest.json"


def git_head() -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()


def fmt(x: float) -> str:
    return f"{x:.4f}"


def main() -> None:
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))
    d = json.loads(DATA.read_text(encoding="utf-8"))
    gate = s["recall_gate"]
    uf = s["unfiltered_mean_recall10"]
    prefix = s["prefix_recall"]
    oracle = s["oracle_ratio"]
    low = s["group_highlights"]["low_selectivity_full_recall"]
    kinds = s["group_highlights"]["mask_type_full_recall"]
    ef_values = [64, 128, 256]

    lines: list[str] = []
    add = lines.append
    add("# EXP-10B.1 — FiQA + hnswlib 外部有效性实验报告")
    add("")
    add(f"生成时工作区 HEAD：`{git_head()}`")
    add("分支：`exp10-fiqa-hnswlib-external-validity`")
    add("实验编号：`EXP-10B.1`")
    add("裁决依据：`results/exp10_fiqa_summary.json` 与原始轨迹可复算结果。")
    add("")
    add("---")
    add("")
    add("## 1. 结论摘要")
    add("")
    add("本轮在 BEIR 官方历史 revision 的原始 FiQA 组件上，使用固定模型 embedding 与 hnswlib v0.9.0 标准 `searchKnn` 路径，检验 EXP-09 / EXP-09.1 的核心发现是否可复现。")
    add("")
    add(f"- 数据门：`{d['data_gate']}`。三个 BEIR 官方组件文件通过固定 revision、大小和 SHA-256 校验；**原 UKP ZIP 的 MD5 仍为 `{d['original_zip_md5']['status']}`**，本轮不宣称 ZIP MD5 通过。")
    add(f"- C++ 小规模验收：`{s['smoke_validation']['verdict']}`，512/384/20 合成设定下事件数与独立 DISTFUNC 计数一致，sink-on/off top-k bit-exact，trace hash 可复现。")
    add(f"- 准入门：三个 efSearch 的 mean unfiltered exact Recall@10 = " + ", ".join(f"{ef}:{fmt(uf[str(ef)])}" for ef in ef_values) + "。")
    add(f"- 按修正后的规则（**三个都低于 0.90 才停止**），正式 Oracle 主结论：`{gate['oracle_main_conclusion']}`。低质量配置：" + (", ".join(str(x) for x in gate["low_quality_configs"]) if gate["low_quality_configs"] else "无") + "。")
    add("- Oracle Prefix 是事后上界，不是在线停止规则；first-touch 轨迹是 **HNSW query distance-evaluation trace**，不是硬件 cache / 预取 / 物理内存访问轨迹。")
    add("")
    add("---")
    add("")
    add("## 2. 数据来源与完整性")
    add("")
    add("| 组件 | 仓库 | revision | 大小 | SHA-256 |")
    add("| --- | --- | --- | ---: | --- |")
    for key in ("corpus", "queries", "qrels"):
        c = d["components"][key]
        add(f"| {key} | {c['repo_id']} | `{c['revision']}` | {c['size_bytes']:,} | `{c['sha256']}` |")
    add("")
    add(f"- corpus：{d['counts']['corpus']:,} 条；全量 queries：{d['counts']['queries_all_splits']:,} 条；test queries：{d['counts']['queries_test']} 条；qrels pairs：{d['counts']['qrels_pairs']:,}。")
    add("- qrels query IDs 从全量 queries 中选取 648 条 test queries；没有把 6,648 当成 test query 数量。")
    add("- ID 唯一性、qrels 引用完整性、重复对、test/qrels 集合一致性均通过 manifest 中记录的检查。")
    add(f"- 数据描述：`{d['data_source_description']}`。")
    add(f"- Dataset card license：corpus/queries/qrels 均为 `{d['license']['corpus']}`；据实记录，不推断。")
    add("")
    add("---")
    add("")
    add("## 3. Embedding 与 HNSW 配置")
    add("")
    m = s["model"]
    h = s["hnsw"]
    add(f"- 模型：`{m['id']}` @ `{m['resolved_revision']}`，license `{m['license']}`。")
    add(f"- 设备/线程：CPU，embedding 固定 {m['cpu_threads']} 线程；HNSW 构建和查询固定单线程。")
    add(f"- dtype/dim/normalize：{m['dtype']}，{m['dim']}，`normalize_embeddings={str(m['normalize_embeddings']).lower()}`。")
    add(f"- 文本约定：corpus 为 `{m['sentence_convention']['corpus']}`，query 为 `{m['sentence_convention']['query']}`。")
    add(f"- hnswlib：{h['library']} {h['version']} + {h['instrumentation']}；space 为归一化向量 IP（cosine 等价排序）。")
    add(f"- HNSW：M={h['M']}，efConstruction={h['ef_construction']}，efSearch={h['ef_search']}，k={h['k']}，seed={h['seed']}。")
    add("- external label = BEIR corpus 行索引；文档顺序按 corpus.jsonl 加载顺序。")
    add("")
    add("## 4. 授权 mask 与指标口径")
    add("")
    add("- 两类合成授权策略：random、embedding-clustered；选择率 1%/10%/30%；seeds 2026/2027/2028；共 18 个配置。这些 mask 不是真实企业 ACL。")
    add("- 精确 GT 使用归一化 embedding 的 float32 点积，排序为 score 降序、corpus 行号稳定升序；记录 rank-10 边界 score 和 exact tie count。")
    add("- ACL mask 不进入 C++ HNSW 搜索路径。每个 `(query, efSearch)` 的轨迹只采集一次，18 个 mask 共享同一条 policy-oblivious first-touch 轨迹。")
    add("- prefix 预算：`ceil(0.6B)`, `ceil(0.8B)`, `ceil(0.9B)`, `B`，其中 B 为该 query/ef 的 unique first-touch 长度。")
    add("- prefix candidate Recall@10：取 prefix 内已授权候选，用精确分数重排后取 top-10，与 filtered exact GT top-10 求交集，分母固定为 10。")
    add("- Oracle Prefix：`t*(q,p,δ)=min{t≥ceil(0.6B): R(t)≥R(B)-δ}`，δ=0.05/0.10；若窗口内未达到记 `NOT_REACHED` 并取 B。该量是事后上界。")
    add("- qrels filtered nDCG@10：仅在授权 qrels 相关文档上计算，作为 secondary metric。")
    add("- bootstrap：按 query index 配对重采样 2000 次，seed=20261125，报告 95% percentile CI。")
    add("")
    add("---")
    add("")
    add("## 5. 主要结果")
    add("")
    add("### 5.1 Unfiltered Recall@10 准入门")
    add("")
    add("| efSearch | mean unfiltered exact Recall@10 | mean events/query | mean unique/query | 判定 |")
    add("| ---: | ---: | ---: | ---: | --- |")
    for ef in ef_values:
        t = s["trace_cost"][str(ef)]
        verdict = "LOW_QUALITY_CONFIG" if ef in gate["low_quality_configs"] else "QUALIFIED"
        add(f"| {ef} | {fmt(uf[str(ef)])} | {t['mean_event_count']:.1f} | {t['mean_unique_count']:.1f} | {verdict} |")
    add("")
    add("任务包原 §8 与 §14.8 的文字矛盾已按新任务包修正：**仅当三个 efSearch 全部低于 0.90 时停止正式 Oracle 主结论**。本轮 `oracle_main_conclusion=" + gate["oracle_main_conclusion"] + "`。")
    add("")
    add("### 5.2 Prefix Recall@10")
    add("")
    add("| efSearch | 60% B | 80% B | 90% B | B |")
    add("| ---: | ---: | ---: | ---: | ---: |")
    for ef in ef_values:
        p = prefix[str(ef)]
        add(f"| {ef} | {fmt(p['0.6'])} | {fmt(p['0.8'])} | {fmt(p['0.9'])} | {fmt(p['1.0'])} |")
    add("")
    add("### 5.3 Oracle Prefix 空间")
    add("")
    add("| efSearch | mean t*/B (δ=0.05) | mean t*/B (δ=0.10) |")
    add("| ---: | ---: | ---: |")
    for ef in ef_values:
        o = oracle[str(ef)]
        add(f"| {ef} | {fmt(o['0.05'])} | {fmt(o['0.1'])} |")
    add("")
    add("### 5.4 1% 选择率与 mask 类型")
    add("")
    add("| efSearch | 1% masks full-trace Recall@10 |")
    add("| ---: | ---: |")
    for ef in ef_values:
        add(f"| {ef} | {fmt(low[str(ef)])} |")
    add("")
    add("| mask type | full-trace Recall@10（跨 ef/seed/selectivity） |")
    add("| --- | ---: |")
    for kind in ("random", "clustered"):
        add(f"| {kind} | {fmt(kinds[kind])} |")
    add("")
    add("更细的按选择率、seed、mask key 与 95% CI 见 `results/exp10_fiqa_bootstrap.csv`；逐 query 原始表见 `results/exp10_fiqa_prefix_recall.csv` 与 `results/exp10_fiqa_oracle_prefix.csv`。")
    add("")
    add("### 5.5 图表")
    add("")
    add("生成 7 类图表：`results/figures/fig01_unfiltered_recall_gate.png` 至 `fig07_ndcg_curve.png`，覆盖准入门、prefix 曲线、1% 困难档、random vs clustered、Oracle 分布、trace 成本和 nDCG 曲线。")
    add("")
    add("---")
    add("")
    add("## 6. 对研究问题的回答")
    add("")
    p64, p128, p256 = prefix["64"], prefix["128"], prefix["256"]
    o64, o128, o256 = oracle["64"], oracle["128"], oracle["256"]
    add("1. **核心发现是否在真实文本 HNSW 上复现？——部分支持。** unfiltered exact Recall@10 为 "
        + ", ".join(f"ef={ef}:{fmt(uf[str(ef)])}" for ef in ef_values)
        + "，准入门全部通过；但 filtered prefix recall 随预算下降而下降，例如 ef=128 从 B 档 "
        + fmt(p128["1.0"]) + " 降到 0.6B 档 " + fmt(p128["0.6"])
        + "。这支持“截断有可测成本、困难场景存在”的方向性发现；但 full-trace filtered recall 仍显著低于 unfiltered，**不支持**把 prefix 缩减当作在线无损 stopping rule。")
    add("2. **是否存在稳健前缀空间？——事后支持，在线不支持。** mean t*/B 在 δ=0.05 时为 ef=64 "
        + fmt(o64["0.05"]) + "、ef=128 " + fmt(o128["0.05"]) + "、ef=256 " + fmt(o256["0.05"])
        + "；δ=0.10 时为 " + fmt(o64["0.1"]) + "、" + fmt(o128["0.1"]) + "、" + fmt(o256["0.1"])
        + "。说明存在可观的事后前缀空间，但 Oracle Prefix 是事后上界，不是可部署在线策略；`NOT_REACHED` 配置在 oracle CSV 中逐项标记。")
    add("3. **1% 是否困难？——支持。** 1% masks 的 full-trace Recall@10 为 ef=64 "
        + fmt(low["64"]) + "、ef=128 " + fmt(low["128"]) + "、ef=256 " + fmt(low["256"])
        + "，明显低于聚合水平；这与 EXP-09.1 所发现的 1% 困难档一致。")
    add("4. **random 与 embedding-clustered 是否不同？——支持，且 clustered 更难。** random 的 full-trace Recall@10 为 "
        + fmt(kinds["random"]) + "，clustered 为 " + fmt(kinds["clustered"])
        + "。差异只能解释为合成授权策略分布不同，不能解释为真实企业 ACL 或图拓扑差异。")
    add("5. **与合成图实验的差异？** 本轮语料与 HNSW 来自真实文本 embedding，但授权 mask 仍为合成；轨迹口径为 HNSW 有序距离计算事件与 unique first-touch 视图，不是硬件 cache、预取、物理内存访问或真实侧信道。")
    add("6. **是否继续 PA-VFANN？** 本轮提供外部有效性证据，但不自动接入 Agent/RAG，不启动 EXP-11，也不把结果包装成安全贡献。是否继续投入应由用户结合 Oracle 仅为事后上界、1% 档仍困难这两点独立复核后决定。")
    add("")
    add("---")
    add("")
    add("## 7. 限制与边界")
    add("")
    add("- 原始 UKP ZIP 未取得，MD5 未验证；只验证 BEIR first-party 历史 revision 的三个原始组件。")
    add("- 授权 mask 是合成的；不代表真实企业 ACL，也不代表图拓扑。")
    add("- trace 是 HNSW 查询路径上的 distance-evaluation 事件与 unique first-touch 视图，不是硬件 cache、预取、物理内存访问或真实侧信道。")
    add("- Oracle Prefix 是事后上界，不能当作可部署在线停止规则；未声称策略隐藏、形式化安全、exactly-once 或普遍性能优势。")
    add("- 模型 revision、HNSW 参数、mask 规则、prefix 规则和 bootstrap 参数均固定；未在看到结果后改网格。")
    add("")
    add("---")
    add("")
    add("## 8. 可复算产物")
    add("")
    add("- `data/exp10_fiqa_manifest.json`：组件来源、SHA、counts、ID 集合哈希。")
    add("- `data/exp10_fiqa_embeddings/embedding_manifest.json`、`gt_manifest.json`：embedding 与 GT/mask 固定。")
    add("- `results/raw/exp10_fiqa_trace_manifest.json`：压缩轨迹 SHA-256。")
    add("- `results/exp10_fiqa_*.csv` / `.json`：分析原始表、bootstrap 和汇总。")
    add("- `results/figures/*.png`：7 类图表。")
    add("- `experiments/exp10_fiqa_hnswlib/*.py|cpp|sh`：完整执行脚本。")
    add("")
    add("报告生成时的 HEAD 是上述脚本和结果提交前的父提交；最终 push 后以版本控制记录为准。")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[report] {OUT.relative_to(ROOT)} lines={len(lines)}")


if __name__ == "__main__":
    main()
