# PA-VFANN-28S / EXP-05B 补充：Primitive 门展开、只读 RAM 与归纳不变量

> 用户独立核查 GitHub 报告（Blob `272c48566a1f1b319cb8c7e4e6267015d9c545bc`）后提出的三处窄范围补充：① 把 `g_Q/g_V/g_addr` 展开到可检查内部 MUX/比较器/条件控制；② 明确只读 RAM 假设或纳入写入状态转换；③ 明确初始状态约束并用归纳不变量替代两轮展开。本补充**只做这三项**，不改 EXP-05B 原文、不搜新文献、不写代码/数据文件、不扩 L3。

## 0. 边界、基线与来源

| 项目 | 值 |
| --- | --- |
| 基线 | `ae552580b5b13e85574dbad9c8a8c1ab43e5a6f6`（EXP-05B，用户已核查版本） |
| 分支 | `exp05b-supplement-gate-level` |
| 目标 | 把 EXP-05B §3.3 的 16 项模块接口规范细化到 primitive 门级，使"完整门级非干扰"可逐门复算 |
| 禁止 | 改 EXP-05B 原文、新增代码/数据文件、扩 L3、扩协议设计 |

核查对象一致性：本地 `git rev-parse HEAD:docs/EXP-05B-CIRCUIT-ADDRESS-NONINTERFERENCE.md` = `272c48566a1f1b319cb8c7e4e6267015d9c545bc`，与用户从 GitHub 读取的 Blob SHA 相同。

---

## 1. 结论先行：三项缺口闭合，判断维持但力度上移一级

| 项 | EXP-05B 原判 | 本补充后 |
| --- | --- | --- |
| \(\Pi_A\) 地址/停止非干扰 | 模块接口层 ACCEPT | **primitive 门级 ACCEPT**（含展开后的 MUX/比较器/条件写/解码器/只读 RAM） |
| 任意轮数成立 | 仅展开 2 轮 | **单步归纳不变量 ACCEPT**（不再依赖展开轮数） |
| \(\Pi_B\) 对照 | 2 条泄露路径 | 4 轮展开重现，含 MUX 内部门 `mux_a`；REJECT 维持 |

仍保留的边界（用户已认可，不重复论证）：ACCEPT 对象是**门级规范 \(\Pi_A\)**，不是物理网表；规范 (N-r) 是本场景额外设计要求，非 Afshar 原文定理；L3 完整视图联合模拟仍 UNKNOWN。本补充不改变这三点。

---

## 2. 缺口 ①：把 \(g_Q,g_V,g_{addr}\) 展开到 primitive 门级

EXP-05B §3.3 的 16 项是把整模块封装成一个表项的**接口规范**。下表逐模块展开到基本门（NOT / AND / OR / MUX / 比较器 / 解码器 / 条件写），并标注每个内部门的输入闭包是否含 \(P\) 派生 wire。

### 2.1 \(g_{addr}\) 展开：地址选择 MUX

原表项：`addr_t ← {addr_sel, Q_head, dummy_const}`。展开为（逐位，记 \(b\) 为地址位索引）：

| primitive 门 | 输出 wire | 输入 wires | \(P\) 依赖 |
| --- | --- | --- | --- |
| \(g_{\neg}\) | `nsel` | `addr_sel` | 无 |
| \(g_{\land}^{a}\) | `mux_a[b]` | `nsel`, `Q_head_key[b]` | 无 |
| \(g_{\land}^{b}\) | `mux_b[b]` | `addr_sel`, `dummy_const[b]` | 无 |
| \(g_{\lor}\) | `addr_t[b]` | `mux_a[b]`, `mux_b[b]` | 无 |

选择信号 `addr_sel ← {ptr, Q_empty}` 的上游是 `ptr, t, Q_reg`（均策略无关，见 §2.4）。MUX 的**选择信号本身**是控制依赖的关键——展开后确认它不含 `match / P_reg / R_reg`。

### 2.2 \(g_Q\) 展开：优先队列条件更新

原表项：`Q_next ← {Q_reg, key_new, node_id}`。展开为：

| primitive 门 | 输出 wire | 输入 wires | \(P\) 依赖 |
| --- | --- | --- | --- |
| \(g_{\text{cmp}}\) | `cmp_lt` | `key_new`, `Q_head_key` | 无（比较 (dist,node_id) 键） |
| \(g_{\text{ins}}\) | `ins` | `cmp_lt`, `Q_empty`, `addr_sel` | 无（条件写使能 = 比较结果 ∧ 队列状态） |
| \(g_{\text{slot}}\) | `slot_new` | `ins`, `key_new`, `Q_reg` | 无（MUX：插入 or 保留） |
| \(g_{\text{Qout}}\) | `Q_next` | `slot_new`, `Q_reg` | 无 |

关键点：比较器输入 `key_new ← {dist_new, node_id}`，而 `dist_new ← {q, block}`、`node_id ← block`；在只读 RAM 下 `block = I[addr_t]`，\(I\) 是公开索引、\(q\) 公开，故整条键计算链策略无关（见 §3）。**插入位置 `ins` 由比较结果与队列空标志决定，不由任何授权匹配位决定**——这正是语义 A 与语义 B 的分界：语义 B 会让 `match` 驱动堆键（§4.2）。

### 2.3 \(g_V\) 展开：访问位图解码置位

原表项：`V_next ← {V_reg, node_id}`。展开为：

| primitive 门 | 输出 wire | 输入 wires | \(P\) 依赖 |
| --- | --- | --- | --- |
| \(g_{\text{dec}}\) | `onehot` | `node_id` | 无（地址解码器） |
| \(g_{\lor}^{V}\) | `V_next` | `onehot`, `V_reg` | 无（按位或置位） |

`node_id` 来自 `block`（只读 RAM 读回），策略无关。

### 2.4 展开后的完整单步依赖闭包（验算）

以所有策略无关源 \(\{Q_{reg},V_{reg},ptr,t,q,E,I,\text{dummy\_const}\}\) 出发做传递闭包：覆盖 33 根 wire，包含全部状态汇点 `{Q_next, V_next, ptr_next, addr_t, halt_t, op_t, block, key_new, node_id, dist_new}`——即**每个状态汇点都只由策略无关输入驱动**。逐一检查策略派生源 `{P_reg, match, R_reg, result}` 到这些汇点的路径：**0 条**。

---

## 3. 缺口 ②：只读 RAM 假设（显式纳入电路对象）

用户指出：EXP-05B 定义了 `block` 来自索引 \(I\)，但未在门表中定义 RAM 读写状态转换。本补充明确固定：

> **假设 (RO-RAM)**：\(\Pi_A\) 检索阶段为只读 RAM——\(\forall t:\ M_t = I\)（常量索引），`block_t = I[addr_t]`，**无写端口**，即电路中不存在 `M_next / write_addr / write_data` wire。

**依据**：PA-VFANN 目标是过滤 ANN 检索（`F_retrieve` 只读查询），EXP-01/02 的搜索实现不含索引写入；原文 §2.1 的 RAM 过程虽含 `(write,·)` 分支（提取文本 54–58 行），但本场景的 \(\Pi\) 规范只启用 read。这是一条**本场景的规范选择**，与 (N-r) 同类，不冒充原文定理。

**纳入门表**：新增一行 `block ← {addr_t}`（地址是唯一选择器，\(I\) 为公开常量输入）。验算确认：展开图中 `block` 只由 `addr_t` 驱动，无 `M_next`/`write_data` 节点——写回路径在 \(\Pi_A\) 中不存在，因此不存在"写地址/写数据引入 \(P\) 依赖"的通道。

**若将来放开写**：必须新增 \(M_{t+1}[\,wa_t\,]\leftarrow wd_t\) 变压器并证明 \(wa_t,wd_t\) 策略无关、且下一轮 `block` 不受 \(P\) 污染；这超出本补充范围，明确标记为新工作，不在 \(\Pi_A\) ACCEPT 之内。

---

## 4. 缺口 ③：初始状态约束与归纳不变量

用户指出：仅展开两轮不足以声称任意轮数成立。本补充用单步归纳不变量替代。

### 4.1 初始化规则（显式）

\[
Q_0=\text{empty},\quad V_0=0^{|V|},\quad ptr_0=0,\quad t_0=0,\quad R_0=0^{K\times w}
\]

全部为**公开常量**，由常量输入线 `const_empty / const_zero / const_0 / I` 置入；`P_reg` 不出现在任何初始化来源的闭包中（验算 CHECK 3：False）。这把 EXP-05B 状态表中"依赖 \(P\)？否"的断言落实为具体初始化连线。

### 4.2 归纳不变量

\[
\mathcal I(t):\quad Q_t,\ V_t,\ ptr_t,\ t \text{ 均为 } (I,q,E) \text{ 与允许随机性的函数，与 } P \text{ 无关。}
\]

**基例**：\(t=0\)，由 §4.1 初始化规则，\(\mathcal I(0)\) 成立。

**归纳步**：设 \(\mathcal I(t)\) 成立。由 EXP-05B §3.3 门表 + 本补充 §2 展开：

1. `Q_empty, Q_head_key ← Q_reg`；`op_sel ← {t,ptr}`；`addr_sel ← {ptr,Q_empty}` —— 由 \(\mathcal I(t)\) 全部策略无关。
2. `nsel, mux_a, mux_b, addr_t ← addr_sel/Q_head_key/dummy_const` —— MUX 内部逐门策略无关，故 `addr_t` 策略无关。
3. `block ← addr_t`（RO-RAM，§3），\(I\) 公开 —— `block` 策略无关；继而 `dist_new ← {q,block}`、`node_id ← block`、`key_new ← {dist_new,node_id}` 策略无关。
4. `cmp_lt, ins, slot_new, Q_next`（§2.2）与 `onehot, V_next`（§2.3）的输入闭包全在上列策略无关量内 —— \(Q_{t+1},V_{t+1}\) 策略无关。
5. `ptr_next ← {ptr,t}`、`halt_t ← {t,E}` —— \(ptr_{t+1}, halt_t\) 策略无关。
6. 唯一 \(P\) 派生链 `match ← {P_reg,block} → R_next → result` 只写入 \(R_{t+1}\) 与 result 线；\(R_{reg}\) 的下游与状态/控制汇点交集为 **NONE**（验算 CHECK 1c）。

故 \(\mathcal I(t+1)\) 成立。由归纳法，\(\forall t\ \mathcal I(t)\)。

**推论（目标等式）**：因 `addr_t`、`halt_t` 在每步都是策略无关输入的确定函数，故对任意 \(P_0,P_1\)（固定 \(I,q,E\) 与允许随机性）：

\[
\mathrm{AddrTrace}(I,q,E;P_0)=\mathrm{AddrTrace}(I,q,E;P_1),\qquad
\mathrm{StopTrace}(I,q,E;P_0)=\mathrm{StopTrace}(I,q,E;P_1).
\]

**验算对应**：CHECK 1a/1b/1c 验证单步归纳步（任意轮数的充分条件）；4 轮显式展开（含跨轮寄存器边 `X_next@r→X_reg@(r+1)`、`t@r→t@(r+1)`、`E@r→E@(r+1)`）验证 \(\Pi_A\) 中 \(P@0\) 到任何 `addr_t@r/halt_t@r` 零路径，两种力度一致。

### 4.3 \(\Pi_B\) 对照（展开门级重现）

同一 4 轮展开图中加入语义 B 两条边 `match→hop_next→key_new`、`match→legal_cnt→halt_t`，找到 7 条泄露路径，例如：

```
P_reg@0 → match@0 → hop_next@0 → key_new@0 → slot_new@0 → Q_next@0
        → Q_reg@1 → Q_head_key@1 → mux_a@1 → addr_t@1
P_reg@0 → match@0 → legal_cnt@0 → halt_t@0
```

注意第一条路径现落实到 MUX 内部门 `mux_a`（EXP-05B 只到 `Q_head@1→addr@1` 的模块接口级），确认展开后 REJECT 仍成立，且跨轮反馈机制与源码 `filter_aware.py:64–81` 一致。

---

## 5. 判决表与力度边界

| 检查项 | 判决 | 依据 |
| --- | --- | --- |
| \(g_{addr}\) 内部 MUX 无 \(P\) 扇入 | ACCEPT | §2.1 逐门展开 + 闭包验算 |
| \(g_Q\) 内部比较器/条件写无 \(P\) 扇入 | ACCEPT | §2.2 + CHECK 1a（33 wire 闭包） |
| \(g_V\) 内部解码器无 \(P\) 扇入 | ACCEPT | §2.3 |
| 只读 RAM：无写端口、无 \(P\) 写数据通道 | ACCEPT（假设 RO-RAM） | §3，验算 CHECK 2 |
| 初始化 \(Q_0,V_0,ptr_0,t_0\) 为公开常量 | ACCEPT | §4.1，CHECK 3 |
| 归纳不变量 \(\mathcal I(t)\Rightarrow\forall t\) | ACCEPT | §4.2 六步归纳 + CHECK 1/4 轮展开 |
| \(\Pi_B\) 同性质 | REJECT | §4.3，含 `mux_a` 内部门的两类路径 |
| 物理网表忠实于展开后 \(\Pi_A\) | UNKNOWN（不在范围） | 无实现；cut-and-choose 只保证 garble 忠实于 \(\Pi\) |
| L3 完整视图联合模拟 | UNKNOWN（不变） | 物理 ORAM、abort、消息长度、控制/result 联合 |

**整体：L2 primitive 门级 ACCEPT（\(\Pi_A\)，条件 RO-RAM + 显式初始化 + (N-r)）；\(\Pi_B\) REJECT；物理与 L3 仍 UNKNOWN。** 三处缺口全部闭合，力度从"模块接口层"上移到"primitive 门级 + 任意轮数归纳"。

**力度边界照旧**：ACCEPT 对象是规范，不是物理实现；(N-r) 与 RO-RAM 是本场景规范选择而非原文定理；本结论不外推为完整协议安全，不复活已 NO-GO 的具体贡献。

---

## 6. 停止条件与下一步

用户要求："这次补充通过后，我们就不再回头审计 L2，直接进入 EXP-06。"

- 三项缺口已闭合：展开门级、只读 RAM、归纳不变量均有明确门表/规则/证明与验算。
- 未发现 \(P\) 到地址/停止的真实路径；\(\Pi_B\) 的 REJECT 属已否定的语义 B，不构成对 \(\Pi_A\) 路线否定。
- **不再回头审计 L2**。下一步直接进入 EXP-06（L3 完整视图模拟可行性审计）。

写门级网表时的验收清单（仍有效，现更细）：① \(R_t\) 写端口与 \(Q/V\) 分离；② 规范 (N-r) 排除随机带进控制闭包；③ (RO-RAM) 无写端口；④ 初始化 \(Q_0,V_0,ptr_0,t_0\) 为公开常量；⑤ 展开后 MUX/比较器/条件写/解码器逐门核对 §2 表。

## 附录 A：验算复现要点

内存脚本（不落盘）：(1) 单步展开图逐门 `out←inputs`，从策略无关源做 BFS 闭包，检查 9 个状态汇点全在闭包内；从 `P_reg/match/R_reg/result` 出发到这些汇点零路径；`R_reg` 下游与汇点交集为空。(2) 4 轮展开加跨轮寄存器边，`P_reg@0` 到 `addr_t@r/halt_t@r`（r=0..3）零路径。(3) \(\Pi_B\) 加两条边后重现 7 条路径。原始 EXP-05B 的两轮验算保留在其附录 A，本补充不覆盖它，只补充更细粒度与归纳层。
