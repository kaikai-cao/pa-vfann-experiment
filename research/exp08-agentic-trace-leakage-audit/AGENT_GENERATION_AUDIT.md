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

---

# Query Privacy and Execution Boundary Audit（EXP-02-R0.2.1 Phase 1 新增）

任务：EXP-02-R0.2.1 Phase 1。性质：**只读源码审计**，不运行模型、不下载权重、不调用 API、不修改 ASQ 上游。

**本轮关键问题**：不能只看"检索明文有没有被写进审计日志"，必须确认**明文查询实际上有没有到达外包检索服务**。日志不记录 ≠ 服务端看不到。

源码版本：从固定 commit `be49cce309efd002101610e92e733dde32533d63` 重新下载 7 个关键文件，与本地审计副本逐文件 SHA256 比对 **7/7 MATCH**（`search_r1.py=e2e17cf14f6d`、`retrieval_utils.py=db6509443a35`、`agent.py=76a541302880`、`utils.py=7c11b6eaa5d5`、`tutorial_main.py=7fb8aaeabbd5`、`load_mydataset.py=2aecaf5f4828`、`search_r1/builder.py=7709129aae0c`，前缀）。据此确认下文引用的是指定版本源码。

## Q1. 查询数据流追踪（Agent → 索引执行位置）

完整调用链（逐行证据）：

| 环节 | 源码位置 | 事实 |
|---|---|---|
| Agent 生成查询 | `search_r1.py:182` `this_query = regex_extractor.get_query(...)` | 从 LLM 输出 `<search>…</search>` 抽取，是**自然语言明文字符串** |
| 传入检索 | `search_r1.py:184` `search(self.retriever, this_query, qid="%s-%d"%(qid,cnt))` | 明文直接作为 `query` 实参传入 |
| search() 内的调用 | `search_r1.py:45` `res = search_pipeline.search(query, qid=qid)` | PyTerrier `Transformer.search()` 便利方法，明文 query 进入检索管线 |
| 检索器 | `retrieval_utils.py:125` `pt.terrier.Retriever(lexical_index_path, wmodel=wmodel, metadata=["docno","text"])` | **本地索引**上的 PyTerrier Terrier Retriever |
| 索引构建 | `retrieval_utils.py:30-70` `index_lexical()` 用 `pt.terrier.IterDictIndexer(...).index(corpus_iter)` | 在本地路径 `calc_index_fpath()` = `{DATA_DIR}/index/<dataset>_bm25_index/` 建索引（第 16–27 行） |
| 返回 docid/rank | `search_r1.py:50-59` `for doc_item in retrieval_result.itertuples(): ... doc_item.docno ...` | docid 来自本地索引结果的 `docno` 列；rank 由 PyTerrier 结果给出，extractor 用 `cumcount()+1` 落盘（`extractor_df.py:89`） |
| 管线注入 | `tutorial_main.py:105-115` `pipeline = build_retrieval_pipeline(...)` → `agent = build_agent(args, pipeline)` | 检索器是**参数注入的本地 `pt.Transformer`** |

**逐问回答（任务包 1.1）**：

1. Agent 生成的 `query` 是否为自然语言明文？—— **是**（`search_r1.py:182`，`<search>` 内文本）。
2. 明文是否直接传入 `search_pipeline.search()`？—— **是**（第 184 行 → 第 45 行，无编码/加密/令牌化中间层）。
3. 默认 BM25/PyTerrier Retriever 是否用明文查询检索？—— **是**（`pt.terrier.Retriever` 在本地索引上执行 BM25，直接消费该字符串）。
4. Retriever 在本地进程、客户端控制环境，还是独立远程服务？—— **本地进程内**（PyTerrier/Terrier 以 Java 索引 + Python transformer 形式在同一机器运行；`tutorial_main.py:94` `pt.java.set_memory_limit()` 显示 Java 是本地 JVM）。
5. 是否存在真实 RPC、HTTP、网络调用边界？—— **未发现**。对全部源码做 `requests./urllib/http://socket/flask/fastapi/grpc/xmlrpc/localhost/port/serve/listen/httpx/aiohttp` 扫描，**除 import 行与注释中的项目 URL 外无任何网络边界代码**。检索调用是进程内方法调用。
6. 哪个组件实际能看到查询明文？—— **执行检索的本地 PyTerrier/Terrier 进程**（以及 LLM 生成器、extractor）。**不存在一个"外包检索服务"观察主体**——除非实验方自行把 retriever 换成远程服务，那属于改造，非上游默认行为。
7. 是否存在查询加密、令牌化、隐私保护 ANN 等机制？—— **不存在**。上游检索栈是纯本地 BM25（`pt.terrier.Retriever`）+ 可选本地 `ElectraScorer` 重排（`retrieval_utils.py:127`），无任何查询保护机制。
8. docid / rank / 数量 / 轮次从哪个执行边界产生？—— 全部从**本地索引检索结果**产生：`docno` 来自 Terrier 索引（`retrieval_utils.py:125` metadata）、rank 来自结果顺序（`extractor_df.py:89`）、数量来自每次返回行数、轮次来自 Agent 生成循环 `cnt`（`search_r1.py:154,199`）。**没有跨网络边界，因此也没有"服务端视角"的这些字段**。

> **关键裁定**：在 ASQ 默认配置下，"明文查询不写入审计日志"成立（extractor 只落 `llm_query` 到研究者侧 TSV），但"外包检索服务看不到明文"**不成立**——因为根本没有外包检索服务，检索在本地完成。把本地日志当作外包服务器观察是错误类比。

## Q2. 三种执行模型对照表（任务包 1.2）

| 模型 | 执行方式 | 查询明文可见性 | 是否符合当前核心威胁模型 |
|---|---|---|---|
| **A1** | Agent 与 Retriever 均在客户端/本地执行（ASQ 默认） | 外部服务端不存在或不可观察；本地检索进程可见 | **不构成外包服务端泄漏实验**。可用于验证 Agent 生成与 ACL 因果机制（对照 A 零点、后续轨迹差异），但不能冒充真实外包服务端结果 |
| **A2** | 客户端向外包服务发送明文查询，服务端执行 BM25 | 服务端可见明文 | **不符合**查询隐私假设。此时查询语义可直接读出，问题退化为普通语义分类；只能作 `QUERY-VISIBLE DIAGNOSTIC` 诊断任务语义影响，不得写成隐私条件下泄漏 |
| **A3** | 客户端提交受保护查询表示，外包服务执行具体隐私保护检索 | 取决于具体协议与实现 | **只有通过逐项审计后才可能符合**。不得仅凭"加密了查询"认定合格 |

**ASQ 默认落点 = A1**（本地进程，无外包服务端）。ASQ 源码不提供 A2/A3 的现成后端；把它改造成 A2 只需把 retriever 换成远程 HTTP BM25（但那是**降低**隐私，不符合需求）；改造成 A3 则需要引入本任务包之外的具体隐私保护检索系统。

## Q3. A3 合格条件核验（任务包 1.3）

按任务包要求逐项核验是否存在"已核验、符合查询隐私要求的外包检索接口"：

| 核验项 | 结论 |
|---|---|
| 论文或官方文档 | ASQ 仓库内**无**查询隐私保护检索方案；上游依赖是 PyTerrier 本地索引 |
| 代码仓库及固定 commit | ASQ `be49cce` 的检索栈为 `pt.terrier.Retriever` 本地实现，无远程受保护查询接口 |
| 客户端→服务端请求形式 | **不存在**（默认 A1，无网络请求） |
| 服务端能否恢复明文 | 不适用（无服务端） |
| 是否暴露可反演/可关联查询向量或令牌 | 不适用 |
| 是否暴露查询长度/频率/重复关系 | 不适用（无服务端观测面） |
| 是否暴露返回 ID/数量/rank/访问模式/时间 | 不适用（无服务端观测面） |
| 是否支持连续多轮 Agent 检索 | ASQ Agent 侧支持多轮（`search_r1.py:154` 循环），但检索是本地的 |
| 是否支持跨请求可关联 opaque docid | ASQ 本地索引用整数 docno；opaque 映射需实验方自建（见 §2.2 Int64 约束） |
| 普通 HTTPS / 哈希查询 / 删除日志 query 字段 | **均不算查询隐私机制**（任务包明令禁止） |

**结论：`NO VERIFIED QUERY-PRIVATE RETRIEVAL BACKEND`。**

含义严格限定为：**当前 ASQ 实验路线不具备符合查询隐私威胁模型的检索后端**——ASQ 默认是 A1（本地，无外包服务端），不是 A3。这不等于证明整个研究问题不存在；架构 A 的间接泄漏因果关系仍是可检验假设（见 `OBSERVABILITY_AUDIT.md` §1），只是缺少一个"服务端确实只看到受保护查询 + 可见轨迹"的合规实验后端。

## Q4. 对本审计其余部分的连带修正

- `AGENT_GENERATION_AUDIT.md` §0 总判定"PARTIAL-FEASIBLE"维持，但须补一句：该"可行"指 **A1 本地生成机制**可行，不表示满足查询隐私威胁模型；按本表，ASQ 默认 = A1，需 A3 合规后端才能做正式外包服务实验。
- 生成器组件（Agent 多步、extractor 记录顺序/docid）**可复用**；默认 BM25 检索器**不能直接作为查询隐私保护的外包服务**——两者必须拆开评价，不得因 Agent 部分可复用就顺带通过整个威胁模型。

## Q5. 本新增章节证据索引

| 结论 | 源码位置（固定 commit `be49cce`） | 核验方式 |
|---|---|---|
| query 为自然语言明文 | `search_r1.py:182` | 读取源码 |
| 明文直传 search() | `search_r1.py:184` → `:45` | 读取源码 |
| 本地索引 Retriever | `retrieval_utils.py:125,16-27,30-70` | 读取源码 |
| 无网络/RPC 边界 | 全源码 grep（requests/urllib/socket/grpc/flask/fastapi/httpx/port 等） | 仅在 import 与注释 URL 命中 |
| docid/rank/数量/轮次来源 | `search_r1.py:50-59`；`extractor_df.py:89`；`search_r1.py:154,199` | 读取源码 |
| 本地 JVM（非远程服务） | `tutorial_main.py:94` `pt.java.set_memory_limit()` | 读取源码 |
| 版本一致 7/7 SHA | 固定 commit 重新下载 vs 本地副本 | SHA256 逐文件比对 |
