# EXP-10B.1 Data Gate STOP — Hugging Face revision-pinned resolve 通道返回 502

日期：2026-11-25  
分支：`exp10-fiqa-hnswlib-external-validity`  
基线：`ccebb03e67c31ea1cc325c2837c92ccfc4323fd4`  
修订：`docs/EXP10B_DATA_SOURCE_AMENDMENT.md`  
裁决：`STOP_PRE_REGISTERED_DATA_GATE`（组件来源修订后第二次数据门失败）

---

## 1. 结论

EXP-10B.1 已按用户批准的条款修订数据源：不再依赖 UKP ZIP 服务器，改用 BEIR 官方 Hugging Face 组织在历史 revision 中保存的原始 `corpus.jsonl.gz`、`queries.jsonl.gz` 和 `test.tsv`。

但当前环境访问 Hugging Face revision-pinned resolve 端点时，本机代理返回 `502 Bad Gateway`。脚本在 `hf_hub_download` 的元数据 HEAD 阶段即失败，**没有取得任何组件字节**，因此无法执行 SHA-256、大小、gzip、JSON、qrels 结构和 ID 集合校验。

按任务包第 3.4 节：

- 数据门保持 STOP；
- 不启动 embedding；
- 不下载模型权重；
- 不构建 HNSW；
- 不运行 C++ trace runner；
- 不运行 prefix / Oracle / nDCG / bootstrap；
- 不寻找其他数据源。

这不是研究结论层面的 GO/NO_GO；它只表示修订后的数据固定条款在当前网络环境下无法执行。

---

## 2. 已完成的基线核验

| 项目 | 结果 |
| --- | --- |
| HEAD | `ccebb03e67c31ea1cc325c2837c92ccfc4323fd4` |
| 分支 | `exp10-fiqa-hnswlib-external-validity` |
| 工作区初始状态 | clean |
| `docs/EXP10B_PHASE0_STOP.md` | 存在，未修改 |
| EXP-10A patch / 插桩源码 / 报告 | 存在，未修改 |
| 原有测试 | `43 passed in 1.10s` |
| 测试命令 | `PYTHONPATH="src;tests" .venv/Scripts/python -m pytest -q --disable-warnings --capture=tee-sys` |

---

## 3. 新增的固定条款

在查看任何 Recall 数值之前，已经写入：

- `docs/EXP10B_DATA_SOURCE_AMENDMENT.md`
- `experiments/exp10_fiqa_hnswlib/experiment_config.json`

其中固定：

- 原 ZIP MD5 `17918ed23cd04fb15047f73e6c3bd9d9` 状态为 `NOT_VERIFIED`；
- 数据门通过词汇只能是 `PASS_COMPONENT_ARTIFACTS`；
- Recall 准入门按修订规则：**三个 efSearch 的 mean unfiltered exact Recall@10 全部低于 0.90 时才停止正式 Oracle 结论**；
- 所有模型、HNSW、mask、prefix、Oracle、bootstrap 参数保持原 EXP-10B 不变。

---

## 4. 数据门失败细节

### 4.1 目标端点

首先尝试下载：

`BeIR/fiqa@a90551af496e20ce7887c02f07f7ea5c86908fb9/corpus.jsonl.gz`

即 revision-pinned resolve 路径：

`https://huggingface.co/datasets/BeIR/fiqa/resolve/a90551af496e20ce7887c02f07f7ea5c86908fb9/corpus.jsonl.gz`

### 4.2 实际错误

执行命令：

` .venv/Scripts/python experiments/exp10_fiqa_hnswlib/restore_component_data.py`

两次均失败，核心异常相同：

```text
[download] corpus: BeIR/fiqa@a90551af496e20ce7887c02f07f7ea5c86908fb9/corpus.jsonl.gz
[data-gate] STOP: ProxyError: 502 Bad Gateway
httpcore2.ProxyError: 502 Bad Gateway
...
File ".../huggingface_hub/file_download.py", line 1670, in get_hf_file_metadata
    response = _httpx2_follow_hub_redirects_with_backoff(
...
```

失败发生在 `get_hf_file_metadata` 的 HEAD 请求阶段，尚未进入文件字节下载。

### 4.3 代理环境

当前环境使用本机代理：

```text
https_proxy=http://127.0.0.1:55194
HTTPS_PROXY=http://127.0.0.1:55194
http_proxy=http://127.0.0.1:55194
HTTP_PROXY=http://127.0.0.1:55194
NO_PROXY=127.0.0.1,localhost,::1
```

本次没有绕过代理，也没有改用 `main`、Parquet、第三方仓库或手工拼装文件。

### 4.4 未产生的产物

- `data/exp10_fiqa_manifest.json`：不存在；
- 原始组件文件：未取得；
- 解压 corpus/queries：未产生；
- embedding：未产生；
- trace：未产生；
- 任何 prefix / Oracle / nDCG 结果：未产生。

---

## 5. 冻结边界

本轮未修改：

- `docs/EXP10B_PHASE0_STOP.md` 原始内容；
- EXP-10A 全部文件；
- EXP-10 Faiss Phase 0 STOP；
- EXP-01 / EXP-08 / EXP-09 / EXP-09.1 历史文件；
- 原始共享工作区 `D:\Research\pa-vfann-experiment`。

本轮新增/修改仅限：

- `.gitignore`
- `docs/EXP10B_DATA_SOURCE_AMENDMENT.md`
- `docs/EXP10B1_DATA_GATE_STOP.md`
- `experiments/exp10_fiqa_hnswlib/experiment_config.json`
- `experiments/exp10_fiqa_hnswlib/restore_component_data.py`

没有提交原始语料、模型权重或 embedding 矩阵。

---

## 6. 恢复条件

恢复执行需要满足任一项：

1. 当前环境能够访问 revision-pinned `huggingface.co/datasets/.../resolve/<sha>/...` 端点，使 `hf_hub_download` 能完成 HEAD 和 GET；或
2. 用户明确允许把已下载并本地校验过的三个组件文件放入指定本地目录，再由本脚本只做 SHA-256 和结构门校验；该路径仍需满足任务包中的 revision 和 SHA 固定，不降低标准。

恢复后直接运行：

` .venv/Scripts/python experiments/exp10_fiqa_hnswlib/restore_component_data.py`

数据门通过后脚本会写出 `data/exp10_fiqa_manifest.json`，裁决为 `PASS_COMPONENT_ARTIFACTS`；原 ZIP MD5 继续保持 `NOT_VERIFIED`。

在任何恢复条件满足前，不启动 embedding、HNSW、Oracle 分析，也不自动进入 EXP-11。
