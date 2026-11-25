# hnswlib v0.9.0 固定源码快照

## 上游固定

- Repository: `https://github.com/nmslib/hnswlib`
- Tag: `v0.9.0`（稳定标签；未使用 `master`，未使用 `v0.10.0-rc.*`）
- 完整 commit SHA: `d9b3608c83d83b46c96e25088cb1d729b29dcfe9`
- Tag 对象类型：`commit`；tree SHA: `1b59aaa0fa12b1ea6faec19c9f0fc387db5d935d`
- 许可：Apache-2.0，原文见 `hnswlib-v0.9.0/LICENSE`

## 参与编译文件的 SHA-256

两类哈希均给出，避免 Windows `core.autocrlf=true` 造成的行尾差异被误读：

| 文件 | 上游 blob 规范化 SHA-256 | 本工作区快照 SHA-256（实际参与编译） |
| --- | --- | --- |
| `hnswlib/hnswalg.h` | `483d3b3193969ef4c35239849b6385dd1086434a7bae1d8181acf287e46666fc` | `7e5eb7f353c71ed71b3900eff9a47c7a478ed7ca92264f5a6bce4a700614bc43` |
| `hnswlib/hnswlib.h` | `54403db81f55fd28246114c5c9f683e663a2a55ad64903b56578c73e6db5ad2c` | `200633c5fb1e85c2ba3847b0c78f256f941597be3dc08c0ac287edb4f96eb173` |
| `hnswlib/space_ip.h` | `6a89b5275527fe3592a9b02ea4fc50293fdc68cbd9f7c1ec13683581e1ebbaf7` | `80f96b23f04733dabcc96465228a20f9ba4b18da98a1e78a412503d7dd1d401b` |
| `hnswlib/space_l2.h` | `c599d024657896412250b4fde1a95e39f8bc55cccd263f36c8948fa35779edf1` | `79dbb957fff2d63498347f870a2d2d0e9c975e8d05f2d615ce677689bc009f51` |
| `hnswlib/stop_condition.h` | `930da73eead77dff0c8c9f3281c5d12250051c90ef98fcfbab8f5f307bdae8d9` | `25b4678f109aebd6c8d730f76cd2d50316da46fb95e31e2cc2ce7b2873c2edaf` |
| `hnswlib/visited_list_pool.h` | `8e5bab8d12b5ef26e3b603b656b8a1acba6738498d1d98f44c9fdb1cb0e25110` | `c6ffa99370594693b0b7c1aa998731334feaef8df42772923d88654d9f58ca8d` |
| `hnswlib/bruteforce.h` | `a6af7730da60ec23ac532b9bff3c5fa8b4fc5f0b7e5b824249766710004d9e93` | `7ebaaf3dd8adaa7c987abc5db07df1fc3d5869ee5cdcf749113e5001cfdc0c78` |
| `LICENSE` | `b40930bbcf80744c86c46a12bc9da056641d722716c378f5659b9e555ef833e1` | `e03ba41d7fab20700769fe4118bab50d800cb74f990353a05d2f5fff1c228363` |

说明：上游 blob 列为 `git show v0.9.0:<path> | sha256sum`；工作区快照列为磁盘实际字节（CRLF 行尾）。两者内容语义一致，仅行尾不同。本轮所有编译均使用工作区快照。

## 插桩版来源

- Patch：`patches/hnswlib-v0.9.0-query-trace.patch`
- 应用方式（在使用 CRLF 快照的工作区）：`patch --binary -p1 < patches/hnswlib-v0.9.0-query-trace.patch`
- 已实测对 pristine 快照 dry-run 与应用均成功，产物逐字节等于 `third_party/hnswlib-v0.9.0-instrumented/`。
- 插桩后 `hnswalg.h` SHA-256：`f232688dee3f5c91d9f3edfc829f814827f120f7b37b1a123616a1505f6a843c`
- 新增 `hnsw_trace_sink.h` SHA-256：`5e3102a9030ea17cc5c5108039dc244cb1137f3da1b888ab3ee49a876bb0c54d`
- 插桩未触及 `hnswlib.h`、`space_ip.h`、`space_l2.h`、`stop_condition.h`、`visited_list_pool.h`、`bruteforce.h`。
