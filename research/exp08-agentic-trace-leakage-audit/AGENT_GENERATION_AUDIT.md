# AGENT_GENERATION_AUDIT.md — ASQ Agent 生成代码可行性核验

任务：EXP-02-R0.1 Phase 3。性质：**只读源码审计**，不运行完整生成、不调用付费模型、不修改 ASQ 上游、不把接口兼容性推测写成已验证事实。

核验对象：`https://github.com/fpezzuti/ASQ`，`main` HEAD `be49cce309efd002101610e92e733dde32533d63`（2026-10-22），MIT。源码通过 `https://raw.githubusercontent.com/fpezzuti/ASQ/main/<path>` 下载到临时目录逐文件阅读；文件树经 GitHub API `git/trees/main?recursive=1` 核验（`truncated=false`，55 条目）。本轮只读，未执行 `agent(...)`，未下载模型权重。

## 0. 结论摘要

| 核验项 | 结论 |
|---|---|
| `build_agent()` 实际定义与参数 | 已核验（两个同名函数：公共 API 在 `rag_agent/agent.py`，便捷包装在 `utils.py`） |
| `DataFrameExtractor` 输入输出 | 已核验（输入 agent 返回 DataFrame，输出 4 类 TSV） |
| PyTerrier retriever 数据接口 | 已核验（`search_pipeline.search(query, qid=...)`；需 qid/query 列，产出 docno/text/rank） |
| 每轮检索调用产生位置 | 已核验（`search_r1.py::search()` 第 44–59 行；在生成循环 `transform_iter` 第 184 行调用） |
| 能否替换成 ACL Benchmark 文档集合 | **源码层面可行但需改造**：需自建 PyTerrier 索引 + 自定义 retriever transformer；不是开箱即用 |
| 能否每次检索前接入 ACL 判断 | **可行但需改造**：`search()` 是单点拦截位；上游无 ACL 概念，须注入包装 transformer |
| 能否保留调用顺序 / 返回 docid / 主体身份 | 顺序与 docid **可**；主体身份**不可直接**——上游仅有 `qid`/`query`，无 `user_id` 列，须扩展输入 schema |
| 是否要求额外模型 / API 密钥 / 不可复现服务 | **是**：search_r1 需 HuggingFace 本地权重（Qwen 等）；gpt_oss 需 Terrier OpenAI 兼容 API + `OPENAI_API_KEY`/`TERRIER_API_KEY`；retrieval 需 Java + PyTerrier + 预建索引 |

**总判定：PARTIAL-FEASIBLE（有条件可行，非开箱即用）。** 源码证据支持"可替换语料、可拦截检索、可记录顺序与 docid"，但存在三个必须由实验方自行改造的点：自定义索引/retriever、ACL 拦截包装、主体身份字段扩展；且生成器模型或 API 是本轮明确禁止调用/下载的外部依赖。本轮不执行，故所有"可行"均为**源码结构支持**，非"已验证跑通"。

---

## 1. `build_agent()` 实际定义

### 1.1 公共 API：`src/trace_generation/rag_agent/agent.py:131`

```
def build_agent(model_type, model_id, retrieval_pipeline, agent_k,
                retriever_batch_size=1, retriever_batch_wait_ms=25)
```
- 通过 `RagAgentBuilder`（`agent.py:79`，frozen dataclass）工厂实现：
  - `__post_init__`（第 98–114 行）从 `BUILDER_REGISTRY[model_type]` 取 builder；
  - `resolve_model()`（第 121–125 行）把 `model_id` 映射到 checkpoint 字符串；
  - 把 `retrieval_pipeline`、`agent_k`、`model_id` 传给 builder（第 103–107 行）。
- `register_agent()`（第 61 行）支持注册新 agent family 与 builder —— 这是接入自定义组件的官方扩展点。

### 1.2 便捷包装：`src/trace_generation/utils.py:90`

```
def build_agent(args, pipeline):
    from .rag_agent import build_agent
    agent = build_agent(model_type=args.model_type, model_id=args.model_id,
        retrieval_pipeline=pipeline, agent_k=args.agent_k,
        retriever_batch_size=getattr(args,"retriever_batch_size",1),
        retriever_batch_wait_ms=getattr(args,"retriever_batch_wait_ms",25))
    return agent.agent
```
教程主流程 `tutorial_main.py:115` 调用的是这个包装（`agent = build_agent(args, pipeline)`）。

### 1.3 核验结论
- `retrieval_pipeline` 是**参数注入**的 `pt.Transformer`（`agent.py:92` 类型标注），这是"能否换语料/能否加 ACL 拦截"的关键结构事实——检索器与 agent 解耦。
- 模型族注册表 `MODEL_REGISTRY`（`agent.py:12–17`）：`search_r1`、`autorefine`、`gpt_oss`。`SUPPORTED_MODEL_TYPES` 由命令行 `--model_type` 限定（`tutorial_main.py:71` `choices=SUPPORTED_MODEL_TYPES`）。

## 2. `DataFrameExtractor` 输入 / 输出

文件：`src/trace_generation/extraction/extractor_df.py`
- 类 `DataFrameExtractor`（第 109 行），`__init__(extraction_order, verbose)`；`extract_all_and_save(results_df, output_paths)`（第 141 行）为入口。
- **输入**（`_prepare_df` 第 133–138 行）固定列：`qid, query, answer, iteration, all_queries, all_docids`（可选 `all_thoughts`）。这些正是 agent 返回 DataFrame 的列（对照 `search_r1.py:177` 的返回 dict）。
- **输出** 4 类 TSV（由 `ExtractionType` 第 20–24 行枚举 + `EXTRACTION_FUNCTIONS` 第 101–106 行分派）：
  - `answers.tsv`：`qid, answer`
  - `iter_queries.tsv`：`qid, iteration, llm_query`
  - `retrieved_docs.tsv`：`qid, iteration, docid, rank`
  - `thoughts.tsv`（可选）：`qid, iteration, thought`
- 落盘 `save_or_append_df`（第 13 行）用 TAB 分隔、append 模式。

### 关键约束（对 opaque ID 适配有直接影响）
- 第 93 行：`df_exploded["docid"] = df_exploded["docid"].astype("Int64")` —— **docid 被强制转可空整数**。若 ACL Benchmark 使用非数字 opaque 字符串 ID，此 extractor 会报类型转换错误。适配需改这一行（保留字符串/或用整数不透明 ID）。
- 第 89 行：`rank` 由 `groupby(["qid","iteration"]).cumcount()+1` 生成，即 rank 是返回顺序的位次；这与"服务端可见结果数量/顺序"的威胁模型字段直接对应。

## 3. PyTerrier retriever 数据接口与检索调用位置

### 3.1 检索单点：`src/trace_generation/rag_agent/search_r1/search_r1.py:44`
```
def search(search_pipeline: pt.Transformer, query: str, qid='1') -> str:
    res = search_pipeline.search(query, qid=qid)
    ...
    retrieved_docids.append(doc_item.docno)   # 第 57 行
    return format_reference, retrieved_docids  # 第 59 行
```
- 输入：`query`（文本）+ `qid`（这里被用作 `"%s-%d" % (qid, cnt)`，即 `qid-轮次`，见第 184 行）。
- 输出：拼给 LLM 的文本 + 返回 docid 列表（来自 PyTerrier 的 `docno` 列）。
- **这就是每轮检索调用的产生位置**：生成循环 `transform_iter`（第 135 行起，`@pta.transform.by_query`）在 `while True`（第 154 行）中，LLM 产出 `<search>...</search>` 时由 `regex_extractor.get_query()` 解析（第 182 行），随后第 184 行调用 `search()`。`all_docids.append((cnt, retrieved_docids))`（第 187 行）记录"轮次→返回 docid"，`all_queries` 记录每轮查询文本。

### 3.2 retriever 构造：`src/data_utils/retrieval_utils.py:110`
- `build_retrieval_pipeline(dataset, k1=1000, k2=None, batch_size=128, wmodel="BM25")` 返回 `pt.Transformer`：
  - `index_lexical()`（第 30 行）用 `pt.terrier.IterDictIndexer` 从 `load_dataset(dataset, queries=False)` 的语料建 BM25 索引；
  - 检索器 `pt.terrier.Retriever(index, wmodel=..., metadata=["docno","text"])`（第 125 行）；可选 `ElectraScorer` 重排（第 127–128 行，需 CUDA）。
- 自定义 transformer 范例：`CW22BLexicalRetriever(pt.Transformer)`（第 73 行），其 `transform(inp)` 接收含 `qid`/`query` 的 DataFrame，返回 `qid, docno, title, text, rank`。**这是替换成 ACL Benchmark 语料时可参照的接口模板**。

### 3.3 数据加载：`src/data_utils/load_mydataset.py:37`
- `load_dataset(dataset, queries, judged, qrels)` 仅支持：`researchy-*`、`msmarco-dev`、`hotpotqa-test`，其余走 `irds:{dataset}`（`pt.datasets.get_dataset`）。
- **不支持直接从本地自定义 DataFrame/语料加载**—— ACL Benchmark 语料须先落成 PyTerrier 可索引语料并改造 `load_dataset` 或绕过它自建索引。

## 4. 逐项可行性裁定

### 4.1 能否替换成 ACL Benchmark 文档集合 —— 源码可行，需改造（未验证跑通）
- 支持证据：`retrieval_pipeline` 参数注入（`agent.py:92/103`）；`CW22BLexicalRetriever` 提供自定义 transformer 模板，`transform()` 接口清晰（`retrieval_utils.py:86`）。
- 需改造：ACL 语料（`data/documents_manifest.jsonl`，12,214 文档）不在 `load_dataset` 支持列表；须自建 BM25 索引 + 一个返回 `qid,docno,text,rank` 的 transformer，并通过 `build_agent(..., retrieval_pipeline=<自定义>)` 注入。
- 未验证：本轮未建索引、未运行，故"可替换"仅为源码结构结论。

### 4.2 能否每次检索前接入 ACL 判断 —— 单点可行，需包装改造（未验证跑通）
- 支持证据：所有检索都过 `search()`（`search_r1.py:44`），而 `search()` 调用的是注入的 `search_pipeline.search(query, qid)`。因此用一个"ACL 感知的包装 transformer"替代 `retrieval_pipeline`，即可在 `search()` 内、`docno` 返回前插入权限过滤/审计。
- 阻塞细节：
  1. `search()` 的 `qid` 参数是 `"%s-%d"%(qid,cnt)`（第 184 行），**主体身份 user_id 不在调用签名里**；
  2. `transform_iter` 从 `inp` 只取 `query`、`qid`（第 139–140 行），无 user 字段；
  3. 上游无 ACL / 权限概念，过滤须实验方实现。
- 结论：拦截点存在（`search()` / 包装 transformer），但"按主体过滤"要求把 user_id 透传到 retriever —— 上游 schema 不支持，需改造。

### 4.3 能否保留调用顺序 / 返回 docid / 主体身份
- **调用顺序**：可。`iteration`（`cnt`）在 `all_queries`/`all_docids`/`all_thoughts` 中均记录（`search_r1.py:175/185/187/193`），extractor 输出 `iteration` 列。
- **返回 docid**：可，但受 2.2 节 `astype("Int64")` 约束——数字 ID 可直接落盘；非数字 opaque 字符串 ID 需改 extractor 第 93 行。
- **主体身份**：**不可直接**。全链路 `qid`+`query` 两列（`load_mydataset.py:25-26`、`utils.py:86`、extractor `_prepare_df` 第 134 行），无 `user_id`/`asked_at`/`role`。要在轨迹中记录主体，须扩展 queries DataFrame  schema 并让 extractor 透传新列（当前 `_prepare_df` 仅取固定列，会丢弃额外列）。

### 4.4 额外模型 / API 密钥 / 不可复现服务依赖
| 依赖 | 证据 | 本轮状态 |
|---|---|---|
| 生成器模型（search_r1） | `search_r1.py:159` `self.model.generate(...)`；`model_id` 映射到 HF checkpoint（`agent.py:121-125`）；README:209 表列 Qwen 等 | 未下载、未运行（本轮禁止） |
| gpt_oss 外部 API | README:81–82："requires either `OPENAI_API_KEY` or `TERRIER_API_KEY`"；`builder` 传 `retriever_batch_size/wait_ms` | 未调用（本轮禁止） |
| Java + PyTerrier | README:34 "Ensure you have **Java** installed"；`tutorial_main.py:94` `pt.java.set_memory_limit()` | 未安装验证 |
| 预建索引 | `retrieval_utils.py:118` `index_lexical()` 首跑建索引 | 未建（本轮禁止完整生成） |

## 5. 对 EXP-02-R0.1 核心问题的影响

核心问题：能否在攻击者看不到任务明文/角色/ACL 时，仅凭真实可见轨迹推断权限状态变化。本审计对"能否生成这样的轨迹"给出：
- 结构上可以复用 ASQ 的"多步调用 + 返回 docid + 轮次"记录机制；
- 但要构造 `对照 A/B/C/D` 所需的可控轨迹，必须补足三件上游没有的东西：**(i) 自定义语料索引与 retriever；(ii) 每次检索前的 ACL 拦截；(iii) 主体身份与时间戳字段**。
- 这三项均为**实验方代码改造**，且生成器涉及本轮禁止的模型/API。因此本轮只能确认"路径存在、改造点明确"，不能宣布"生成流程已验证可行"。

## 6. 证据索引（可复核）

| 结论 | 源码路径:行 | 核验方式 |
|---|---|---|
| build_agent 工厂 + 注入 pipeline | `rag_agent/agent.py:79,98-114,131`；`utils.py:90` | 读取下载源码 |
| 注册扩展点 | `agent.py:61 register_agent` | 同上 |
| Extractor 输入列 / docid 强转 Int64 / rank 生成 | `extraction/extractor_df.py:133-138,93,89` | 同上 |
| 检索单点 + docno 来源 | `rag_agent/search_r1/search_r1.py:44-59` | 同上 |
| 生成循环每轮调用 | `search_r1.py:154,182,184,187` | 同上 |
| retriever 接口 + 自定义模板 | `data_utils/retrieval_utils.py:110,73,86` | 同上 |
| load_dataset 仅支持固定数据集 | `data_utils/load_mydataset.py:37-67` | 同上 |
| API 密钥依赖 | README.md:81-82 | 同上 |
| 源码版本 | GitHub API commits/main = `be49cce`；trees API truncated=false | API 回读 |

下载源码 SHA256（临时目录 `asq_src/`，仅用于本轮核验，未入仓）：`agent.py=76a541302880`、`utils.py=7c11b6eaa5d5`、`extractor_df.py=2382ee5934c7`、`search_r1.py`（重试后下载）、`retrieval_utils.py=db6509443a35`、`load_mydataset.py=2aecaf5f4828`、`README.md=0b56620ba6d3`（均为前缀）。
