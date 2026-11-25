# EXP-10B Phase 0 STOP — FiQA 官方数据包无法获取，MD5 门未通过

日期：2026-11-25  
分支：`exp10-fiqa-hnswlib-external-validity`  
基线：`68ed142a234428bafc85be5cbad8de12371688f2`（远端 `kaikai-cao/pa-vfann-experiment` 精确 SHA）  
裁决：`STOP_PRE_REGISTERED_DATA_GATE`

---

## 1. 结论

EXP-10B 在 Phase 0 数据门停止。原因是 **BEIR 官方 FiQA-2018 数据包无法从官方 URL 下载，因此无法核对预注册 MD5 `17918ed23cd04fb15047f73e6c3bd9d9`**。

这不是研究结论层面的 GO/NO-GO，也不是 PA-VFANN 方法的负面证据；它只表示本轮任务包的第 3.1 节数据固定要求与第 14 节停止标准未被满足。没有用 Hugging Face parquet、第三方镜像、重建 zip 或其他数据替代官方包，也没有降低轨迹采集或数据完整性标准。

---

## 2. 已完成的 Phase 0 核验

| 项目 | 结果 |
| --- | --- |
| 新工作区 | `D:\Research\pa-vfann-exp10-fiqa-hnswlib-workspace` |
| 创建方式 | 从远端仓库 clone，checkout 精确 SHA 后创建本地分支 |
| `git rev-parse HEAD` | `68ed142a234428bafc85be5cbad8de12371688f2` |
| 当前分支 | `exp10-fiqa-hnswlib-external-validity` |
| 工作区初始状态 | clean |
| `third_party/hnswlib-v0.9.0/` | 存在 |
| `third_party/hnswlib-v0.9.0-instrumented/` | 存在 |
| `patches/hnswlib-v0.9.0-query-trace.patch` | 存在 |
| `docs/EXP10A_PHASE0_REPORT.md` | 存在 |
| 原有测试 | `43 passed in 9.95s` |
| 测试命令 | `PYTHONPATH="src;tests" .venv/Scripts/python -m pytest -q --disable-warnings --capture=tee-sys` |

环境已建立本地 `.venv`，未提交。依赖版本已冻结在：
`experiments/exp10_fiqa_hnswlib/requirements.lock`。

---

## 3. 数据门失败证据

### 3.1 固定目标

任务包指定：

- 数据集：BEIR FiQA-2018，`test` split；
- 官方数据包 URL（由 BEIR 官方 `examples/dataset/download_dataset.py` 确认）：
  `https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip`
- 官方 MD5（`examples/dataset/md5.csv` 亦一致）：
  `17918ed23cd04fb15047f73e6c3bd9d9`
- 预期 test queries：648；
- 预期 corpus：约 57K。

### 3.2 实际下载尝试

均未得到可用文件；目标路径下未留下可校验的 zip。

1. `curl -L --fail --retry 3 --retry-delay 2 ...`  
   失败：`curl: (35) schannel: failed to receive handshake, SSL/TLS connection failed`

2. `curl -L --fail --http1.1 --ssl-no-revoke --retry 3 --retry-delay 2 ...`  
   失败：同上，`schannel: failed to receive handshake`

3. PowerShell `Invoke-WebRequest -UseBasicParsing ...`  
   失败：远程连接被关闭（底层 `WebException`，连接中断）

4. Python `urllib.request`，默认证书上下文  
   失败：`URLError <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1032)>`

5. Python `urllib.request`，不校验证书上下文、浏览器 User-Agent  
   失败：同上，`SSL: UNEXPECTED_EOF_WHILE_READING`

6. `curl --noproxy '*'` 直连测试  
   失败：`Connection timed out after 10004 milliseconds`

当前环境的 HTTPS 代理能访问 GitHub / Hugging Face API，但对上述官方 UKP 主机未完成 TLS 握手；绕过代理则连接超时。

### 3.3 未采取的替代路径

以下替代路径被明确拒绝，避免违反任务包：

- 不把 Hugging Face `BeIR/fiqa` parquet 当作官方 zip；
- 不把 Hugging Face `BeIR/fiqa-qrels/test.tsv` 与 parquet 拼装成“等价数据”后继续；
- 不使用第三方仓库中的 `fiqa.zip` 或任何未获得官方 MD5 匹配的镜像；
- 不重新打包本地文件以试图制造相同 MD5；
- 不把 6,648 个跨 split query 误当成 648 个 test query。

---

## 4. 模型固定状态（仅诊断，未使用）

在 Hugging Face API 上取得模型固定信息：

- model：`sentence-transformers/all-MiniLM-L6-v2`
- commit SHA：`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
- license tag：`apache-2.0`
- pipeline tags：API 中同时存在 `sentence-similarity` 与 `feature-extraction`，按原文记录，不自行合并。

由于数据门先失败，本轮 **没有下载模型权重、没有生成 embedding、没有运行 C++ trace runner**。

---

## 5. 任务包内部矛盾记录

任务包第八章规定：

> 主 prefix 结论的准入条件：至少一个 efSearch 的 mean unfiltered exact Recall@10 达到 0.90。三个 efSearch 都未达到时才停止正式 Oracle Prefix 结论。

任务包第十四章停止标准第 8 条写的是：

> 至少一个 efSearch 未达到 0.90 unfiltered mean Recall@10。

两者在“至少一个”的触发逻辑上相反。此前已决定：若实验到达基线门，按第八章详细预注册口径执行，并在最终报告中显式记录该矛盾。

本轮未到达该门，因此该矛盾尚未影响任何实验裁决。

---

## 6. 冻结边界与工作区变更

本轮未修改：

- EXP-10A 已冻结探针代码、patch、原始数据；
- EXP-10 Faiss Phase 0 STOP 报告；
- EXP-01 / EXP-08 / EXP-09 / EXP-09.1 历史实验文件；
- 原始共享工作区 `D:\Research\pa-vfann-experiment`。

本轮新增/修改仅限：

- `.gitignore`（忽略本地数据、embedding 二进制与环境目录）；
- `docs/EXP10B_PHASE0_STOP.md`；
- `experiments/exp10_fiqa_hnswlib/requirements.lock`。

没有提交原始语料、模型权重或 embedding 矩阵。

---

## 7. 恢复条件

若要继续 EXP-10B，需要先解决以下任一项并由用户重新下达任务：

1. 使当前环境能够从官方 URL 下载 `fiqa.zip` 并核对 MD5 `17918ed23cd04fb15047f73e6c3bd9d9`；或
2. 用户明确修改任务包的数据固定条款，允许使用可核验来源的等价 FiQA test split，并重新定义完整性证据。

在此之前不启动 embedding、不构建 HNSW、不运行 prefix/Oracle/nDCG 分析，不自动进入 EXP-11。
