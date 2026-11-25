# EXP-10 Phase 0 停止报告：Faiss HNSW 有序访问轨迹不可可靠采集

- 基线：`exp09-oracle-prefix-diagnostic` @ `8b6b49841027c56cdce91d441d178811905048ce`（远端 `git ls-remote` 核验一致）；独立克隆至 `D:\Research\pa-vfann-exp10-fiqa-hnsw-workspace`，新分支 `exp10-fiqa-hnsw-external-validity`。原仓库与原工作区未写入。
- **裁决：Phase 0 硬门槛失败，正式停止 EXP-10 正式实验。** 不进入 FiQA 下载、编码、HNSW 全量建索引、Oracle 前缀分析；不移植 E1/E2；不设计新算法。
- 证据等级：`[实测]` 为本轮实际执行/检查；`[原文]` 为固定 wheel 的目录/导出符号与 Python API。

## 1. 已完成的固定版本与环境核验 `[实测]`

| 项目 | 结果 |
|---|---|
| Python | 3.14（系统安装） |
| Faiss wheel | `faiss_cpu-1.12.0-cp314-cp314-win_amd64.whl`，SHA-256 `11670337f9f5ee9ff3490e30683eea80add060c300cf6f6cb0e8faf3155fd20e` |
| 安装位置 | 仅工作区 `.deps/`（已加入 `.gitignore`，不提交、不改系统环境） |
| 导入验证 | `faiss.__file__` 指向 `.deps/faiss/__init__.py`；`importlib.metadata.version('faiss-cpu') = 1.12.0` |
| HNSW 可用性 | `faiss.IndexHNSWFlat(8,16)` 可建索引与 `add()`，标准 `search()` 返回 top-k |
| 编译器 | MinGW-W64 g++ 16.2.0、CMake 4.4.2 |
| 缺失构建依赖 | `swig` 未安装；MinGW 库目录无 `libopenblas*`/`libblas*` |

小规模合成集（200×8、单线程、M=16、efSearch=32）标准搜索可复现：重复 `search()` 的返回 ID 完全一致；query 0 返回 `[0, 95, 167, 106, 82, 191, 183, 182, 77, 197]` `[实测]`。但**这只验证标准搜索可用，不构成访问轨迹采集验证**。

## 2. 为什么硬门槛失败

1. **wheel 只提供聚合统计与最终 top-k** `[实测]`：`HNSWStats` 有 `n1, n2, ndis, nhops`，但 Python 侧既没有可访问的 `searchStats` 实例，也没有 `faiss.hnsw_stats` 对象；搜索接口只返回 `(D, I)`。`index` 与 `index.hnsw` 上不存在 `trace / visit / event / callback` 相关钩子。这正好是任务书禁止的"用 `ndis`/`nhops`/top-k 冒充轨迹"。
2. **没有可挂载的 DistanceComputer 装饰器** `[原文]`：Python API 虽暴露 `DistanceComputer`、`IndexHNSWFlat`、`PyCallbackIDSelector`，但没有 `PyCallbackDistanceComputer` 或任何把自定义 DistanceComputer 注入 `IndexHNSWFlat.search` 的接口；`SearchParametersHNSW` 仅有 `efSearch / sel / bounded_queue / check_relative_distance` 等，`sel` 是结果过滤选择器，不能提供距离值、搜索层或完整距离计算事件。
3. **无法对已安装二进制做最小 C++ 插桩** `[实测]`：wheel 不含 C++ 头文件与导入库；`_swigfaiss.cp314-win_amd64.pyd` 的 784 个导出符号中，唯一与 HNSW 相关的是全局 `?hnsw_stats@faiss@@3UHNSWStats@1@A`，未导出 `IndexHNSWFlat` 搜索或 `DistanceComputer` 相关符号，无法编写对其链接的装饰器扩展。
4. **源码构建属于被禁止的大规模改动** `[实测]`：要从固定源码重建带回调的 Faiss，需补装 SWIG 与 BLAS/LAPACK、完整编译 Faiss 并修改 HNSW 搜索热路径；这超出"最小 instrumentation、不大规模修改 Faiss"的边界，也违反 Phase 0 的即时停止要求。

## 3. 未执行的内容（防止误读）

- 未下载 FiQA 语料、qrels 或 `all-MiniLM-L6-v2` 模型；未生成任何 embedding 或授权掩码。
- 未构建真实 HNSW 索引，未运行任何 FiQA query，未产出 prefix/recall/轨迹结果。
- 未声称任何关于 FiQA / 真实 ACL / 真实 Agent-RAG 的外部有效性结论。
- 未修改 EXP-01 / EXP-08 / EXP-09 / EXP-09.1 的实验文件；本分支仅新增本报告并给 `.gitignore` 增加 `.deps/` 一行。

## 4. 解除停止需要什么

要在不违反本轮边界的前提下重开 EXP-10，至少需要：

1. 一个固定版本 Faiss 构建，同时提供 C++ 头文件、可链接库，以及可注入 HNSW 搜索的 DistanceComputer 回调点；或
2. 允许从固定 commit 构建 Faiss 源码并加入最小事件回调（需明确授权安装 SWIG/BLAS 与源码构建）。

随后必须先通过原任务书的五项小规模验证：事件数与 `HNSWStats.ndis` 一致、单线程轨迹可复现、开关插桩输出一致、覆盖上层与 level-0、区分唯一访问与重复距离计算。任一项不满足仍须停止。

## 5. 对主线的意义

这是一条**工具可行性边界**，不是 PA-VFANN 研究结论的否定：EXP-09 与 EXP-09.1 的合成图结果仍然成立，其边界（100 查询、合成 exact-kNN 图、Oracle 为事后上界）不变。当前不能把"真实 HNSW 外部有效性"写进成果清单，也不能用标准搜索耗时或 `ndis` 替代访问轨迹实验。
