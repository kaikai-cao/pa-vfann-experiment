# PA-VFANN-28 / EXP-05B：电路级地址非干扰审计

> 用户批准：先固定 L2 的电路对象与状态边界，再在**具体门级对象**上证明或否定地址/停止非干扰，而不是靠抽象依赖图宣布通过。本轮不写实现代码、不改历史报告、不搜新文献、不把局部结论扩展为完整协议安全。目标是把 L2 的一个 UNKNOWN 推进为明确的 ACCEPT 或 REJECT。

## 0. 边界、基线与来源

| 项目 | 值 |
| --- | --- |
| 基线 | `334b352e869c6ee47455939ed10d3813e1d2d5fe`（EXP-05A） |
| 分支 | `exp05b-circuit-address-noninterference` |
| 目标等式 | \(\forall P_0,P_1:\ \mathrm{AddrTrace}(I,q,E;P_0)=\mathrm{AddrTrace}(I,q,E;P_1)\) 且 \(\mathrm{StopTrace}\) 相等，在相同公开输入 \((q,E,I)\) 与相同允许随机性条件下 |
| 允许 | 核对 Afshar 原文、核对 EXP-03C–05A 报告与 E2/E3 源码、定义具体门级电路对象、小规模符号可达性验算 |
| 禁止 | 改旧报告、新增代码/数据文件、把门级规范层结论写成物理实现已验证、扩展为完整协议安全、无边界文献搜索 |

来源：Afshar 2015 会议版（Springer PDF，SHA-256 `92ccf8ab…e73d50`）；本地提取文本行号见 §5。源码：`src/pa_vfann/search_common.py`、`fixed_trace.py`、`filter_aware.py`、`secret_filter.py`；测试 `tests/test_algorithms.py`。

---

## 1. 独立判断（结论先行）

**在明确固定的门级电路对象 \(\Pi_A\) 上，地址输出与停止状态对秘密策略 \(P\) 满足非干扰——ACCEPT。作为对照，语义 B 电路 \(\Pi_B\)（即当前 E2 源码的电路化）存在两条真实泄露路径——REJECT。**

但判决力度必须钉死，避免过度声称：

- 本轮 ACCEPT 的对象是**一个被明确定义到门与 wire 级别的电路规范 \(\Pi_A\)**，不是仓库中某个已存在的门级网表（仓库没有，也不允许本轮新增实现代码）。
- 该结论是**结构性的、可静态验证的**：非干扰是 \(\Pi_A\) 的连线属性（哪些门的输出连到地址/停止线），一旦固定 netlist，结论即确定，不依赖运行测试、不依赖参数取值。
- 它**不等于** L3 完整视图安全，也不等于"物理实现已验证"。它把 L2 从"抽象结构性论证"推进为"具体电路对象的可检验定理"，这正是本轮要求。

| 层 | 本轮判决 | 对象 |
| --- | --- | --- |
| \(\Pi_A\)（语义 A 门级对象）地址/停止非干扰 | **ACCEPT** | §3 定义的 netlist，§4 可达性验算 |
| \(\Pi_B\)（语义 B / E2 电路化）同性质 | **REJECT** | §4.2 两条具体泄露路径 |
| 物理门级实现忠实于 \(\Pi_A\) | **UNKNOWN（本轮明确不在范围）** | 需后续实现或网表核验 |
| L3 完整视图联合模拟 | **UNKNOWN（不变）** | B4/B1 缺口 3 |

---

## 2. 为什么要先固定电路对象（回应"不能画抽象图"）

用户指出：若状态机或电路尚未具体定义，不能靠画一张抽象依赖图宣布通过。这句话击中了 EXP-05A 的真实弱点——"地址线不扇入 \(P\) 派生 wire"此前只是一个**条件句**，没有指认任何具体的门或 wire。

本轮的做法：先给出一个**完整、有限、可枚举的门级 netlist**（§3），明确到"哪个门、输入哪些 wire、输出哪根 wire"；再在这个 netlist 上做**传递闭包可达性分析**（§4），判定 \(P\) 派生源能否到达地址/停止汇点。这样 ACCEPT/REJECT 都落到具体对象上，可被独立复算。

---

## 3. 固定电路对象：\(\Pi_A\) 的门级规范

### 3.1 原文 RAM 边界（必须先对齐）

原文 §2.1（提取文本 105–111 行）：

```
st := x1 || x2 || 0^n ;  block := 0^n ;  inst := ⊥
do until inst has the form (halt,z):
    block := [ if inst=(read,·) then M[·] else 0^n ]
    r ← {0,1}^n ;  (st, inst, block) := Π(st, block, r)
    if inst=(write,·) then M[·] := block
output z
```

映射到本场景（沿用 EXP-03E/F 角色）：

- \(x_1 = P\)（客户端秘密策略/授权位），\(x_2 = I\)（服务端索引）；
- \(r\)：原文 §3.2（提取文本 248 行）明确首轮由双方提供 \(x_1,x_2\)，后续轮由随机带份额 \(r_1,r_2\) 提供，故 \(r\) 是**允许随机性**（双方份额，非 \(P\) 单独函数）；
- \(st\) 是跨轮 wire-label 传递的**内部状态**，不走 ORAM；只有 `block`（内存读回值）走 ORAM；
- `inst` 含读/写操作码与地址，P2 每轮经 step 3(f) 开 \(\tau(inst(D(i)))\) 解码。

### 3.2 状态分区：\(Q_t,V_t,R_t\) 的字段、所有权、更新规则

把内部状态 \(S_t\) 拆成三个**不共享写端口**的寄存器组（这是非干扰的结构基础）：

| 字段 | 位宽 / 内容 | 依赖 \(P\)？ | 写端口拥有者 | 是否被地址/停止逻辑读 |
| --- | --- | --- | --- | --- |
| \(Q_t\) | 固定容量优先队列：条目 \((\text{dist},\text{node\_id})\)，键序由比较器定 | 否 | `QueueUpdate` 子电路 | **是**（队头 → 地址） |
| \(V_t\) | 已访问位图（去重） | 否 | `QueueUpdate` 子电路 | **是**（去重/dummy 判定） |
| \(R_t\) | 固定 \(K\) 槽结果累加器 \((\text{id},\text{dist},\text{valid})\) | **是**（ \(P\to R_t\) 允许） | `ResultAccum` 子电路 | **否**（关键隔离） |
| \(ptr_t,t\) | 队列指针、轮计数 | 否 | `Control` 子电路 | 是 |

**分区不变量**：\(Q_t,V_t,ptr_t,t\) 的写端口输入集合中**不含** `ResultAccum` 的输出，也不含任何由 \(P\) 标记的门输出；\(R_t\) 的写端口不被 \(Q/V\) 逻辑读取。这是要审计的核心，不是假设。

### 3.3 门级 netlist（每轮，\(\Pi_A\)）

下表是本轮固定的具体门级对象。记号 \(g:\ \text{out}\leftarrow\{\text{in}\}\)。

| 门 \(g\) | 输出 wire | 输入 wires | 注释 |
| --- | --- | --- | --- |
| \(g_{\text{dist}}\) | `dist_new` | `q`, `block` | 距离 = 查询到读回向量的平方 L2；`q` 公开、`block` 来自 \(I\) |
| \(g_{\text{id}}\) | `node_id` | `block` | 节点 ID 来自内存块（\(I\)） |
| \(g_{\text{qempty}}\) | `Q_empty` | `Q_reg` | 队列空标志 |
| \(g_{\text{qhead}}\) | `Q_head` | `Q_reg` | 队头条目 |
| \(g_{\text{opsel}}\) | `op_sel` | `t`, `ptr` | 读/写操作码选择 |
| \(g_{\text{addsel}}\) | `addr_sel` | `ptr`, `Q_empty` | 地址来源 MUX 选择（正常/dummy） |
| \(g_{\text{op}}\) | `op_t` | `op_sel` | 操作码输出 |
| \(g_{\text{addr}}\) | **`addr_t`** | `addr_sel`, `Q_head`, `dummy_const` | **地址输出线** |
| \(g_{\text{ptr}}\) | `ptr_next` | `ptr`, `t` | 指针递增 |
| \(g_{\text{key}}\) | `key_new` | `dist_new`, `node_id` | 队列键 = (距离, 节点 ID)，**无策略位** |
| \(g_{\text{Q}}\) | `Q_next` | `Q_reg`, `key_new`, `node_id` | 队列更新 |
| \(g_{\text{V}}\) | `V_next` | `V_reg`, `node_id` | 访问位图更新 |
| \(g_{\text{stop}}\) | **`halt_t`** | `t`, `E` | **停止线：强制 \(t=E\)，无提前终止** |
| \(g_{\text{match}}\) | `match` | `P_reg`, `block` | 授权匹配位（\(P\) 派生） |
| \(g_{\text{R}}\) | `R_next` | `R_reg`, `match`, `node_id`, `dist_new` | 结果累加（\(P\) 派生，只写 \(R\)） |
| \(g_{\text{res}}\) | `result` | `R_next` | result 输出线（\(\mu=0\)，仅客户端解码） |

**跨轮连线**：`X_next@t → X_reg@(t+1)`，\(X\in\{Q,V,R,ptr\}\)。这是跨轮反馈的具体对象。

### 3.4 随机带 \(r\) 的边界处理

用户特别要求检查"随机带的使用"。原文中 \(r\) 进入 \(\Pi(st,block,r)\)。必须固定一条规范：

> **规范 (N-r)**：随机带 \(r_t\) 只允许进入与 result/Solder 随机化相关的门，**不得进入** \(g_{\text{addr}}\)、\(g_{\text{stop}}\)、\(g_{\text{key}}\)、\(g_{\text{Q}}\)、\(g_{\text{V}}\) 的输入闭包。

理由：E3 的 best-first 是确定性遍历（tie-break by node id，见 `search_common.py:63`），不需要随机化地址；因此可合法地把 \(r\) 完全排除在控制路径外。若某实现让 \(r\) 参与地址（例如随机化探测顺序），则 (N-r) 被违反，需重新审计——本轮固定的 \(\Pi_A\) 明确采用 (N-r)。原文 §3.2（248 行）的 \(r_1,r_2\) 份额机制为 (N-r) 提供了接口，但**原文不强制** (N-r)，它是本场景的规范选择，须写明。

---

## 4. 可达性验算（把 netlist 变成判决）

对 §3.3 的 netlist 做传递闭包：从 \(P\) 派生源出发，沿门依赖边 + 跨轮寄存器边做 BFS，检查能否到达汇点集 \(\{addr_t@0,addr_t@1,halt_t@0,halt_t@1\}\)。展开 2 轮以覆盖跨轮反馈。（验算为内存中小规模符号脚本，未落盘、未新增代码文件；§6 给出复现指令。）

### 4.1 \(\Pi_A\)：非干扰成立（ACCEPT）

结果：`P_reg@0 cannot reach any addr_t/halt_t`；`R_next@0 -> addr_t: NONE`。

逐项对应四项检查：

1. **状态分区**：\(R_t\) 与 \(Q_t/V_t\) 无共享写端口；\(g_R\) 的输出只进 \(R\_next\) 与 `result`，不进 \(g_Q/g_V/g_addr/g_stop\)。✓
2. **地址扇入**：\(g_{\text{addr}}\) 的输入闭包 = \(\{addr\_sel,Q\_head,dummy\_const\}\)，其上游只到 \(ptr,t,Q\_reg,Q\_empty\)，与 `match`/`P_reg`/`R_reg` 无交。✓
3. **控制依赖**：条件分支/MUX/比较器的选择信号分别是 `op_sel`（\(t,ptr\)）、`addr_sel`（\(ptr,Q\_empty\)）、`key` 比较（距离、ID）——全部策略无关；无 \(P\) 驱动的分支进入地址或停止。✓
4. **跨轮反馈**：即使展开两轮，\(R\_next@0\to R\_reg@1\) 后仍只进 \(g_R@1\)，不到 \(g_{\text{addr}}@1/g_{\text{stop}}@1\)。✓

因此：\(\forall P_0,P_1\)，只要固定 \((I,q,E)\) 与允许随机性，\(\mathrm{AddrTrace}\) 与 \(\mathrm{StopTrace}\) 逐轮相同。**目标等式在 \(\Pi_A\) 上成立。**

### 4.2 \(\Pi_B\)（语义 B / E2 电路化）：两条真实泄露路径（REJECT）

当前 E2 源码 `filter_aware.py:64–81` 把 `bits[node]`（即 \(P\)）用于 `next_hop`，并把 `next_hop` 作为堆键元组第三项；`:69` 用 `len(legal)>=top_k` 提前终止。电路化后增加两条门边（\(g_{\text{hop}}:\ match\to hop\_next\to key\_new\)，\(g_{\text{early}}:\ match\to legal\_cnt\to halt\_t\)）。验算找到两条路径：

- **跨轮地址泄露**：\(P\_reg@0\to match@0\to hop\_next@0\to key\_new@0\to Q\_next@0\to Q\_reg@1\to Q\_head@1\to addr\_t@1\)。这正是用户第 4 项担心的跨轮反馈：策略经队列键在下一轮变成地址。
- **停止泄露**：\(P\_reg@0\to match@0\to legal\_cnt@0\to halt\_t@0\)。合法计数驱动提前终止，停止位置依赖 \(P\)。

结论：语义 B 电路**违反**目标等式，REJECT 不是抽象的，而是这两条具体门路径。它与 EXP-03E §7.4 的否定结论一致，本轮把它落实到了门级。

### 4.3 直接依赖之外的检查（回应"不能只看数据依赖"）

| 依赖类型 | \(\Pi_A\) 中是否检查 | 结果 |
| --- | --- | --- |
| 直接数据依赖 | 是（\(g_{\text{addr}}\) 输入闭包） | 无 \(P\) |
| 控制依赖（分支条件） | 是（`op_sel`/`addr_sel` 上游） | 无 \(P\) |
| 条件选择 / MUX | 是（`addr_sel`、`key` 比较器） | 无 \(P\) |
| 状态反馈（跨轮） | 是（2 轮展开 + \(R/Q\) 写端口分离） | 无 \(P\) |
| 随机带使用 | 是（规范 N-r） | \(r\) 被排除出控制闭包 |
| 提前终止 | 是（\(g_{\text{stop}}\) 只有 \(t,E\)） | 无 \(P\) |

全部检查项在 \(\Pi_A\) 上通过；在 \(\Pi_B\) 上，控制/反馈/终止三项被 §4.2 路径击穿。

---

## 5. 原文与源码依据

| 依据 | 定位 | 用途 |
| --- | --- | --- |
| RAM 确定性电路、\(st=x_1‖x_2‖0^n\)、随机带 \(r\) | Afshar §2.1，提取文本 105–111 行 | \(\Pi\) 是固定电路 ⇒ 非干扰是静态连线属性 |
| 后续轮 \(r_1,r_2\) 份额提供随机带 | Afshar §3.2，248 行 | (N-r) 的接口依据 |
| `inst` 含地址、3(f) 开 \(\tau(inst)\) | 提取文本 343 行 | 地址线是 P2 可见汇点 |
| \(st\) 首轮 solder 跨步传递 | 提取文本 316、318、331 行 | 状态跨轮连线对象 |
| `plan_fixed_trace` 无策略参数 | `search_common.py:87–97` | \(Q/V\) 更新的算法层对应 |
| E3 确定性 tie-break by node id | `search_common.py:63` | (N-r) 的可行性依据 |
| E3 在完整轨迹后过滤、结果不回填 | `fixed_trace.py:62–64`、`secret_filter.py:27–28` | \(P\to R_t\) 但不回灌 \(Q/V\) |
| E2 策略进 hop 键与提前终止 | `filter_aware.py:64–69,78–81` | \(\Pi_B\) 两条泄露路径的源码根 |

---

## 6. 判决表与力度边界

| 检查项 | 判决 | 论证 / 反例 |
| --- | --- | --- |
| \(\Pi_A\) 地址非干扰 \(\mathrm{AddrTrace}(P_0)=\mathrm{AddrTrace}(P_1)\) | **ACCEPT** | §4.1：\(g_{\text{addr}}\) 输入闭包与 \(P\) 源无交，含跨轮展开 |
| \(\Pi_A\) 停止非干扰 \(\mathrm{StopTrace}(P_0)=\mathrm{StopTrace}(P_1)\) | **ACCEPT** | \(g_{\text{stop}}\) 仅 \(t,E\)，强制 \(t=E\) |
| 状态分区（\(Q,V\) 与 \(R\) 写端口分离） | **ACCEPT（规范层）** | §3.2 分区不变量 + §4.1 第 1 项 |
| 控制依赖 / MUX / 跨轮反馈 / 随机带（四类） | **ACCEPT（在 \(\Pi_A\) + 规范 N-r 下）** | §4.3 全通过 |
| \(\Pi_B\) 同性质（语义 B / E2） | **REJECT** | §4.2 两条具体门路径（跨轮地址 + 停止） |
| 物理实现忠实于 \(\Pi_A\) 网表 | **UNKNOWN（本轮不在范围）** | 无门级网表；cut-and-choose 保证"garble 忠实于 \(\Pi\)"，不保证"已实现的 \(\Pi\) = \(\Pi_A\)" |
| L3 完整视图联合模拟 | **UNKNOWN（不变）** | 物理 ORAM、abort、消息长度、控制/result 联合分布 |

**整体：L2 电路对象层 ACCEPT（\(\Pi_A\)）/ 对照 REJECT（\(\Pi_B\)）；物理实现与 L3 仍 UNKNOWN。** 本轮把一个 L2 的 UNKNOWN 变成了带具体对象与复算指令的 ACCEPT，没有新增 UNKNOWN 来稀释结论。

---

## 7. 停止条件与下一步

用户三边界对照：

- "证明成立 → 进完整联合模拟器"：本轮 L2 规范层成立，但物理实现与 L3 未闭合，**不足以进完整联合模拟器**。
- "发现 \(P\) 不可避免影响服务器视图 → 有限修改"：\(\Pi_A\) 未发现；\(\Pi_B\) 发现但属已否定的语义 B，不构成对 \(\Pi_A\) 路线的否定。
- "必须改变检索语义或引入不可接受成本 → 停止"：**不触发**——\(\Pi_A\) 采用语义 A 的 post-filter，无需改变检索语义；本轮未暴露新的通用 MPC/ORAM 成本。

关键剩余风险（必须诚实）：ACCEPT 的成立前提是**实现严格采用 \(\Pi_A\) 的 netlist**，尤其两条硬约束：① \(R_t\) 写端口与 \(Q/V\) 分离；② 规范 (N-r) 把随机带排除出控制闭包。任何实现若改用语义 B 队列键或让 \(r\) 进地址，立即落入 \(\Pi_B\) 的 REJECT。因此下一步最有价值的是：在真正写门级网表时，把 §3.3 的表作为**验收清单**逐门核对，而不是重新论证。

项目级口径不变：原始 Afshar 直接单方输出仍 REJECT（EXP-04 §2.2）；PA-VFANN 核心研究问题继续 HOLD。本轮 L2 ACCEPT 不外推为完整协议安全，也不复活已 NO-GO 的具体贡献。

---

## 附录 A：可达性验算复现指令

内存脚本（不落盘）：为每轮定义 §3.3 的门依赖边 `wire -> set(wires it influences)`；展开 2 轮；加跨轮寄存器边 `X_next@t -> X_reg@(t+1)`，`X∈{Q,V,R,ptr}`；从 `P_reg@0` 沿边 BFS，检查是否到达 `addr_t@r` / `halt_t@r`（`r=0,1`）。\(\Pi_B\) 在此基础上加两条边：`match -> hop_next -> key_new` 与 `match -> legal_cnt -> halt_t`，复现 §4.2 路径。本轮输出：`Pi_A NONINTERFERENCE HOLDS: True`；`Pi_B` 两条 LEAK PATH 如 §4.2 所列。
