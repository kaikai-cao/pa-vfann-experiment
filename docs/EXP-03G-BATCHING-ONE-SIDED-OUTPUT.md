# EXP-03G：Batching RAM-2PC 单方输出适配审计

> PA-VFANN-19。本轮只审计 Afshar et al., EUROCRYPT 2015 会议正式版 §3 batching protocol 的单方输出适配。
> 不搜索新文献，不设计新队列，不讨论索引初始化/承诺绑定，不做性能实验，不写代码。

## 0. 执行摘要与判决

**判决：HOLD —— 保留一个待证明命题（命题 3），不是 GO，也不是 NO-GO。**

- **确认成立**：用户提出的 `inst_ctrl`/`result` 接口拆分与 Afshar batching 的结构相容；§2.2 的 garbling 安全性质（部分解码 + 互补 label 不可预测）与 §3.1 的 authenticity 检查，为"P2 只拿活动结果 label、不拿结果线翻译信息"提供了原文级别的实现基础。EXP-03F 中 streaming w-key 风险**不**自动迁移到 batching。
- **确认必须修改**：§2.1 的 RAM 语义把最终输出编码在 `inst=(halt,z)` 中；§3.2 步骤 3(f) 对**所有** `i∈B_t` 开放 `τ(inst(D(i)))`；3(g) 中**双方**解码 `inst_t` 并在 `halt` 时双方都得到 `z`。沿用原始接口，O1 不可能成立。
- **仍缺一步证明**：把 `result` 从 `inst` 拆出后，P1 对返回结果 label 的检查不再是"共同解码后重编码"的 authenticity 检查，而必须改写为**位置/轮次/实例绑定的 label membership 检查**；同时恶意 P2 模拟器必须在不依赖 `z` 的前提下采样结果线活动 label 并维持与 garbled-circuit equivocation 的一致性。本轮给出构造路径与逐攻击面分析，但未完成形式化证明，因此不判 GO。
- **否定范围**：本轮没有否定 Afshar 适配路线；没有否定语义 A 的结构性论证；也没有声称索引初始化已解决（ Explicitly Out of Scope，见 §6）。

证据等级：会议正式版（LNCS 9056, DOI `10.1007/978-3-662-46800-5_27`）全文可从 Springer 官方 PDF 取得；ePrint `2014/759.pdf` 在本环境持续 403，full version Appendix D 未逐字核验。凡引 full version 之处均标注为受限。

## 1. 原文事实核对（只引用会议版可核验段落）

### 1.1 输出确实嵌在 `inst` 里（用户指出的遗漏成立）

- §2.1 RAM semantics：`st := x₁‖x₂‖0ⁿ; block := 0ⁿ; inst := ⊥; do until inst has the form (halt,z) ... output z`（提取文本第 109–111 行）。
- §2.1 ORAM security：`I(Π,M,x₁,x₂)` 定义为 `inst` 变量取值序列；要求存在模拟器 `S` 使 `S(1^λ,z)` 与 `I(Π,M,x₁,x₂)` 不可区分，其中 `z` 是 RAM 程序最终输出（第 122–124 行）。
- §2.2 wire-label conventions：输出 `W` 分为 `st(W), inst(W), block(W)`，其中 `inst(W)` 是 "output instruction (read/write/halt, and memory location)"（第 153–155 行）。注意此处**没有**独立的 `result(W)` 分区——结果只能经 `inst=(halt,z)` 传出。
- §3.2 步骤 3(g)：`P2 sends Ỹ = inst(Y_t) to P1. Both parties decode the output inst_t = lsb(Ỹ) ⊕ τ(inst(D(hd_t))). P1 aborts if ... Ỹ do not equal the expected wire labels inst(D(hd_t))|*inst_t. If inst_t = (halt,z), then both parties halt with output z.`（第 343 行）。

**结论（[原文事实]）**：在原始 batching 协议中，`z` 不是独立输出线，而是 `inst` 的一个域；3(f) 对 bucket 内所有电路开放 `τ(inst(D(i)))`，3(g) 双方解码并在 halt 时双方获得 `z`。因此"直接沿用 batching 协议即可得到单方输出"是错的；用户的接口拆分判断成立。

### 1.2 garbling 安全性质：部分解码与 authenticity

- §2.2：`lsb(W[i,b])=b`；`W[i,2]` 为单比特 translation bit；`τ(W)=W[1,2]‖…‖W[m,2]`；`W|*x := W|x⊕τ(W)`；正确性 `Eval(Garble(f,E,D), E|*x) = D|*f(x)`（第 130–134 行）。
- §2.2：若只揭示掩码后的解码信息 `(μ, τ(D)∧μ)`，"allows the evaluator to learn only the output bits for which μ_i=1"；安全定义推出"the adversary's view is independent of `f(x)∧μ`"，且"view is independent of the complementary wire labels `D|*f(x)`"—除 lsb 外—"the other wire labels are hard to predict, and we achieve an authenticity property similar to that of [5]"（第 138–149 行）。
- 同页脚注 2：**"the evaluator can indeed decode the garbled output (using τ(D) and the select bits), yet cannot forge valid output wire labels in their entirety"**（第 161 行）。
- §3.1：`P1 opens the commitment to their translation values, so P2 can decode ... P2 sends these labels back to P1, who verifies them for authenticity. Knowing only the translation values and not the entire actual output wire labels, P2 cannot lie about the circuit's output except with negligible probability.`（第 242–244 行）。

**结论（[原文事实]）**：这四条共同给出 O1 的核心可行性：对 `result` 线取 `μ=0`（不开放 `τ`，也不开放 `(μ,τ∧μ)`），则 P2 视图独立于结果明文；P2 持有活动 label 却不能伪造/翻转。这是 batching 相对 streaming w-key 的结构性优势——batching 中每个电路独立选择 `E(i),D(i)`（§3.2 步骤 1(a)，第 306 行），没有跨线程共享的 authenticity key。

### 1.3 模拟器：原文为什么必须拿到 `z`

- §3.3 [When P2 is corrupted]：`S ... extracts P2's input x₂ from its select bits sent to F_ot. It sends x₂ to the ideal functionality and receives the output z. Then S generates a simulated ORAM memory-access sequence.` 随后 `S also equivocates on the decommitment to the decoding information τ(inst(D(i))), chosen so that the visible output wires will decode to the next simulated ORAM memory instruction. Instead of checking P2's claimed wire labels in step (3g), the simulator simply aborts if these wire labels are not the pre-determined visible output wire labels.`（第 374–380 行）。
- §3.3 [When P1 is corrupted]：`S can extract P1's input x₁ ... sends x₁ to the ideal functionality and receives the output z. Then S generates a simulated ORAM memory-access sequence.`（第 368–370 行）。

**结论（[原文事实]）**：原文两种腐败模拟器都把 `z` 作为生成 ORAM 访问序列的输入；这是 §2.1 ORAM 定义的直接后果。本轮目标中的 `S(1^λ, I, L_S)` 在原文中**不存在**，必须由"语义 A + 固定预算 + dummy access"的组合来替代（见 §4.3）。

## 2. Task 1：输出接口拆分

### 2.1 修改内容（[我们的协议修改]，非论文已有）

把 RAM 电路 `Π` 的输出分区由 `(st, inst, block)` 扩展为 `(st, inst_ctrl, block, result)`：

| 分区 | 内容 | `τ` 对 P2 | 解码方 |
|---|---|---|---|
| `st` | 内部状态（含队列、访问集、当前结果累加器） | 不开放；仅经 `Solder` 开放差值 `τ(A)⊕τ(A')` | P2 只见 label，不解码 |
| `inst_ctrl` | `read/write`、地址、必要控制状态；**不含 z** | **开放**（§3.2 3(f) 原样保留） | P2 解码，驱动 ORAM |
| `block` | 内存数据块 | 不开放 | P2 只见 label |
| `result` | 固定 `K` 条结果 + dummy 补齐；独立于 `inst` 编码 | **不开放**（不进入 3(f) 的 `τ(inst(D(i)))`） | 仅 P1 解码 |

实现要点：
1. `result` 取自 `st` 中的结果累加器，在最后一轮 `t=E` 以独立输出线给出；中间轮次的 `result` 输出线可为全 dummy。
2. `result` 线必须与 `st`/`inst_ctrl`/`block` 一样参与 §3.2 的 `Solder`/`MkBucket`/`Adjust` 流程（第 250–285 行），以保证 bucket majority 在 head 描述下逐 label 可取。
3. `result` 线的 `D(i)` 分量按 §3.2 步骤 1(a) 一并由 `F_xcom` 承诺；cut-and-choose 阶段（步骤 2，第 306–308 行）随之覆盖。
4. 3(f) 的开放集合显式写为 `τ(inst_ctrl(D(i)))`，**不得**写成 `τ(inst(D(i)))`；否则结果明文回到 P2 视图。

### 2.2 固定预算与 halt（[我们的协议修改]）

- 程序按 `t=1..E` 固定执行 `E` 轮；每轮固定处理 `M` 个邻居，空队列/重复/未授权禁展开/桥接达上限均执行 dummy read（沿用 EXP-03E/F 的 7 项 dummy 规则）。
- `inst_ctrl` 中的 halt 指示在 `t<E` 恒为"非 halt"，`t=E` 恒为"halt"，与 `P`、结果数量、匹配位无关。因此 P2 从控制线看不到结果相关或策略相关的提前终止。
- 注意：这要求修改 §2.1 的 `do until (halt,z)` 循环语义为固定步数语义；这属于**对 RAM 程序的改写**，不是新密码学原语。1600 次 `E×M` 仍是逻辑邻居读，不是物理 ORAM 访问数（EXP-03F §5.4 结论保留）。

### 2.3 translation information 开放矩阵（[我们的协议修改]）

| 线组 | `τ` 是否给 P2 | `(μ,τ∧μ)` 是否给 P2 | 依据 |
|---|---|---|---|
| `inst_ctrl` | 是（3(f) 原样） | 是（μ=全 1） | P2 必须解码指令以执行 ORAM |
| `result` | **否** | **否**（μ=0） | §2.2 部分解码性质：视图独立于结果明文 |
| `st` / `block` | 否（仅 solder 差值） | 否 | 原文已如此；防止 P2 解码内存 |

## 3. Task 2：结果线认证——三个概念的严格区分

### 3.1 定义（本轮统一口径）

1. **label membership**：P1 检查 P2 返回的 label `L` 是否**精确等于**位置 `(t, hd_t, wire index i)` 上承诺描述 `D_result(hd_t)[i,0]` 或 `[i,1]` 之一。
2. **label authenticity**：P2 不能提交一个"看起来像输出但并非本轮真实活动 label"的值；即不能凭空伪造互补 label，也不能把别处的合法 label 冒充此处输出。
3. **output correctness**：P1 解码得到的 `z` 等于承诺索引 `I` 上指定检索状态机的输出。这依赖电路正确性（cut-and-choose）、输入一致性、ORAM 执行正确，以及 `x₂=I` 的承诺绑定（后者本轮范围外）。

**关键结论（[协议推导]）**：membership **不等于** authenticity，authenticity **不等于** correctness。EXP-03E 初稿"P1 能解码 ⇒ 可信"的错误正是把三者混同；本轮不复现该错误。

### 3.2 原文 3(g) 的检查到底检查了什么

§3.2 3(g) 的检查形式是：`P1 aborts if Ỹ ≠ inst(D(hd_t))|*inst_t`，其中 `inst_t = lsb(Ỹ) ⊕ τ(inst(D(hd_t)))`。在 point-permute 下 `lsb(D[i,b])=b`，故：

```
inst(D)|*inst_t = inst(D)[i, inst_t_i ⊕ τ_i] = inst(D)[i, lsb(Ỹ)_i]
```

于是该检查等价于 `Ỹ_i == inst(D)[i, lsb(Ỹ)_i]`，即 **`Ỹ_i` 必须属于该位置的两个候选 label 之一**。它是一个 **membership 检查**，而不是"输出值正确"的检查。§3.1 所说 "verifies them for authenticity" 在机制层面就是 membership：P2 只知道 `τ`，不知道完整 label，因此无法通过检查除非返回真实活动 label。output correctness 由 cut-and-choose 独立保证。

**对我们的意义**：把接口改成 `inst_ctrl/result` 后，P1 的 `result` 检查也必须写成同样形式的 membership 检查，但比较对象从 `inst(D)` 换成 `D_result(hd_E)`（或对应轮次的 `D_result(hd_t)`），并且必须**逐位置**比较——这正是用户要求的"绑定到正确的输出位置和执行实例"。

### 3.3 恶意 P2 六类攻击逐项分析

以下均假设 `τ(result(D(i)))` 不开放、`D(i)` 每电路独立、P1 做逐位置 membership 检查。

| # | 攻击 | 结果 | 依据 |
|---|---|---|---|
| 1 | 伪造互补 label | **不成立**（可忽略概率）。§2.2：互补 label 除 lsb 外不可预测；footnote 2：evaluator 不能完整伪造输出 label。batching 每电路独立 `D(i)`，无全局 Δ 可推。 | §2.2 第 147–149、161 行；§3.2 1(a) |
| 2 | 使用其他线程的合法 label | **不成立**（前提是位置绑定）。其他线程的 `D(i)` 独立随机，其 label 不在 `D_result(hd_E)` 中；P1 逐位置 membership 拒绝。若 P1 只做"是某个合法 label"的粗检查则**会中招**——必须在报告中写死位置绑定。 | §3.2 1(a)、3(f)、3(g) |
| 3 | 使用其他 timestep / 其他输出线的 label | **不成立**，同上：比较按 `(t, hd_t, i)` 索引，跨轮/跨线 label 不属于该位置候选集。 | §3.2 2–3(a) |
| 4 | 拼接合法但错误的 label 序列 | **不成立**（在 membership 绑定下）：单独替换任一位置即被拒；整体替换需要知道目标位置的完整 label 集，P2 只有活动 label 与 `τ(inst_ctrl)`。 | §2.2、§3.2 3(g) |
| 5 | 选择性返回 / 延迟 / 中止 | **部分成立但受限**：拒绝服务不可阻止（与 EXP-03F 一致）；但 P2 看不到 `τ(result)`，无法按结果位做选择性中止；控制线 halt 固定，无法按策略中止。中止消息需固定长度，超出固定预算的中止视为网络失败而非协议泄露。 | §2.2 部分解码；§4.2(f)/(i) 对照见 §5 |
| 6 | 由消息长度/返回顺序/错误分支推断 | **不成立**（若按固定预算实现）：`K` 条结果 + dummy 补齐，label 数量、消息长度、顺序固定；result 不进入 P2 可解码的分支条件。 | §2.2；本轮 §2.2/2.3 |

**限制**：以上结论是[协议推导]，不是已证定理。特别是攻击 1 依赖 garbling 方案满足 §2.2 安全定义且 `D(i)` 每电路独立；攻击 2–4 依赖 P1 正确实现位置绑定 membership。形式化证明仍缺（见 §6.2）。

## 4. Task 3：完整模拟器审计

### 4.1 恶意 P2（服务端）模拟器目标

```
S(1^λ, I, L_S)   where  L_S = (R_I, ver, q, E, public parameters)
```

`I` 是腐败方自己的辅助输入（EXP-03E 修正审计已确立此写法）；`S` **不得**以 `z` 或 `P` 为输入。需要模拟的 transcript 分量：

| 分量 | 模拟策略 | 难点 |
|---|---|---|
| OT / `GetInput2` | 原文 §3.3：模拟 `F_ot` 输出为随机 label；从 P2 的 select bits 抽取 `x₂=I`（第 374 行） | 无；与原论文相同 |
| garbled circuits / cut-and-choose | 原文：收到 `S_c` 后把 check circuits 等化为诚实电路；eval 电路用 visible labels 生成 simulated GC（第 372–379 行） | 需扩展以覆盖新增 `result` 输出线 |
| `τ(inst_ctrl(D(i)))` | 等化为使 visible control label 解码为模拟指令（原文做法，第 378–380 行） | 模拟指令序列必须只依赖 `(I, L_S)` |
| `result` 活动 labels | **本轮新构造**：simulator 代表诚实 P1，本就控制所有 `D(i)` 与承诺；因 P2 视图独立于 `(τ(result(D)), z)`，可选任意满足 `lsb` 一致性、属于承诺 `D_result(hd_t)` 的 label 序列 | 必须与 garbled-circuit equivocation 一致；需混合论证 |
| label authenticity checks | 原文：simulator 在 3(g) 处"若返回 label 不是预定 visible label 则中止"（第 380 行） | 改为 result 线的位置绑定 membership |
| ORAM 逻辑/物理访问 | 语义 A：逻辑地址序列只依赖 `(I, q, E)`；物理轨迹由选定 ORAM 实例在给定逻辑序列下采样 | 见 §4.3 |
| abort / 消息长度 | 固定预算、固定消息长度；中止只在预定 visible label 不匹配时触发 | 中止概率须与 `P` 无关 |

### 4.2 结果线活动 label 能否在不知 `z` 时采样 —— 可以，但有条件

论证链（[协议推导]，基于 §2.2 原文性质）：

1. 对 `result` 线取 `μ=0`：P2 只拿到活动 label 与 `lsb`；§2.2 明确此视图独立于结果明文 `f(x)∧μ`（此处 `f` 为扩展后的电路，μ 屏蔽结果位）。
2. batching 中 `D(i)` 每电路独立（§3.2 1(a)），不存在 streaming 那种跨线程共享 authenticity key 的耦合（§5）。
3. 因此 simulator 可以在不知 `z` 的情况下，为 `result` 线选取"某个合法的 label 序列"作为 visible output labels，并用 §3.3 的 equivocation 技术使承诺、GC 与这些 label 自洽。
4. P2 无法区分"模拟 label 序列"与"真实活动 label 序列"，因为二者的可见部分（label 值 + `lsb`）分布相同，而 `τ(result(D))` 从未进入 P2 视图。
5. 理想世界中 `z` 只交给 P1；P1 的输出由 ideal functionality 给出，不要求 simulator 知道 `z`。这是**单方输出带来的模拟便利**，正是用户指出的突破口。

**条件**：(a) `result` 线必须以 `μ=0` 处理，任何对结果线的 `τ` 或 `(μ,τ∧μ)` 开放都会破坏第 3 步；(b) `result` 线不得参与任何依赖明文的控制分支；(c) 必须证明上述替换与 ORAM 访问序列的模拟**联合可区分性**——单独可模拟不等于联合可模拟。这是命题 3 的核心。

### 4.3 ORAM 轨迹：能否去掉对 `z` 的依赖

- 原文 §2.1 的模拟器输入是 `z`，因为一般 RAM 程序的 `inst` 序列依赖输出。
- 本方案的语义 A + 固定 `E` 轮 + dummy read 使逻辑访问序列成为 `(R_I, ver, q, E, I)` 的确定函数，与 `P` 和 `z` 无关（EXP-03E 修正审计 §4.3；EXP-03F §5.4）。
- 因此模拟器在已知 `I`（腐败方辅助输入）和公开参数时，可独立生成逻辑序列，再按选定 ORAM 实例采样物理轨迹；不需要 `z`。
- **证据等级**：这是针对本方案的**结构性论证**，不是 Afshar 原文定理。ORAM 物理访问数未实例化；`1600` 只是逻辑邻居读。语义 B（谓词影响队列优先级）下此论证**不成立**，仍沿用 EXP-03E 的否定结论。

### 4.4 恶意 P1（客户端）模拟器——必须单独讨论

- 原文 §3.3 [P1 corrupted] 中 `S` 抽取 `x₁`、从 ideal functionality 取 `z`、生成模拟 ORAM 访问，并在 3(g) 发送选定 label（第 368–370 行）。
- 在单方输出下，恶意 P1 是**结果接收方**：它可以对任意结果宣称"我收到了 z'"，不影响诚实 P2（P2 无输出）。因此主要安全目标是 P2 的输入 `I` 隐私与执行完整性。
- P1 侧模拟器可抽取 `x₁=P`，并**仍需**从 ideal functionality 获得 `z` 以模拟 honest P2 对 P1 的响应——因为 P1 能解码结果，其视图包含 `z`。这不违反单方输出（P1 本就该看到 `z`）。
- **不能**默认原文证明自动适用：接口拆分后，P1 获得了 result 线的完整 `D(i)` 与 `τ`，这改变了它在 cut-and-choose 与输出阶段的可见信息结构；需要重写该情形的模拟器与混合论证。此点列入命题 3 的证明清单，不作为独立缺口。

## 5. Task 4：与 streaming w-key 路径的对照

| 维度 | batching §3（本轮路线） | streaming §4.2（EXP-03F 发现风险） |
|---|---|---|
| authenticity material | 每电路独立 `D(i)`，P1 持完整 label 描述；P2 仅知 `τ(inst_ctrl(D(i)))`（§3.2 1(a), 3(f)） | `w(t,j,0), w(t,j,1)` **跨线程共享**，且 `w(t,j,0)⊕w(t,j,1)=Δ_t`（§4.2(f)，第 480–482 行） |
| check 线程可见性 | 无 check 线程的 w-key 解密步骤；P1 在 3(g) 做 membership | §4.2(i)：check 线程向 P2 揭示**两个** w-key；P2 用活动 label 解密其一即可比对（第 507–509 行） |
| 扩展到结果线 | 结果线不开放 `τ`，P2 只见活动 label；membership 按位置检查 | 原样扩展会让 P2 由 w-key 比对恢复结果位，无需 `τ(result)` |
| 风险结论 | **可接受路径，但需证明**（本轮 §3、§4） | **条件性泄露**：仅针对"把同一 w-key 机制扩展到结果线" |

**必须明确的边界（回应用户要求）**：EXP-03F 发现的 w-key 风险**不是**"Afshar 原协议泄露它原本认证的结果"，因为原协议的该机制只覆盖 `inst-output`（§4.2(f) "for each inst-output bit j"），而 `inst` 本身包含 `z` 且 P2 本来就知道 `inst` 明文——w-key 比对在那里的泄露是平凡的。风险只在**我们把同一机制复用到新引入的、P2 本不应解码的 `result` 线**时才出现。这一点在报告中写死，避免误记为原协议漏洞。

选择：按用户指示，**优先 batching label-authenticity 路径**；不把 streaming w-key 路线带入下一步原型。

## 6. 判决与剩余命题

### 6.1 四项分水岭结论

| 分水岭 | 结论 | 等级 |
|---|---|---|
| 输出隐私：服务端完整视图能否在无 `z` 下模拟 | **有条件成立**：语义 A + 固定预算 + `result` 线 `μ=0` + batching 独立 `D(i)`；见 §4.2–4.3 | 结构性论证 |
| 输出完整性：客户端能否验证每一条结果线标签 | **机制可构造**：位置绑定 membership + §2.2 互补 label 不可预测；六类攻击逐项受阻 | 协议推导，未形式化 |
| 索引完整性：`R_I` 是否绑定到 RAM 内存 | **本轮不审计**（用户明确排除）；EXP-03F 缺口②保持未闭合 | Out of Scope |
| 执行隐私：固定逻辑访问能否隐藏物理 ORAM 访问 | **有条件成立**：仅语义 A；1600 是逻辑读；ORAM 实例未选 | 结构性论证 |

### 6.2 唯一待证明命题（命题 3）

> 在 batching §3 协议上，将电路输出接口改为 `(inst_ctrl, result)`、`τ` 仅对 `inst_ctrl` 开放、固定 `E` 轮 dummy execution、`result` 线参与 `Solder`/bucket majority 且 P1 按 `(t,hd_t,i)` 做逐位置 membership 检查的条件下：存在恶意 `P2` 模拟器 `S(1^λ, I, L_S)`，使 P2 的完整视图（OT、GC、`τ(inst_ctrl)`、结果活动 labels、membership 分支、ORAM 逻辑与物理访问、abort、消息长度）与 `P` 及 `z` 无关；并且恶意 `P1` 模拟器可相应重写，诚实 P1 解码的 `z` 满足相对于承诺索引的 G3-alg 完整性（`x₂=I` 的绑定假设另行处理，不在本命题内）。

完成此命题所需的证明清单（一次性列全，不再扩张）：
1. 扩展 garbling 安全定义到四分区输出 `(st, inst_ctrl, block, result)`，证明 `result` 取 `μ=0` 时 §2.2 部分解码性质仍成立。
2. 证明位置绑定 membership 检查在 point-permute + `Solder/Adjust` 下等价于 label membership（含 lsb 在 `Adjust` 后的正确转换）。
3. 证明结果活动 label 的无 `z` 采样与 §3.3 garbled-circuit/承诺 equivocation 的**联合**不可区分性。
4. 证明语义 A 下逻辑访问序列只依赖 `(I,L_S)`，且给定 ORAM 实例后物理轨迹可独立采样。
5. 重写恶意 `P2` 与恶意 `P1` 模拟器，给出中止概率与 `P` 无关的混合论证（§3.3 的 n-wise sharing 与 selective-abort 处理按新接口重证）。
6. 证明单方输出混合：理想世界只给 P1 输出 `z`，P2 视图可模拟，且 P1 的 membership 接受/拒绝不泄露额外信息。

### 6.3 停止规则

- 命题 3 成立 → 才回到索引初始化与承诺绑定（EXP-03F 缺口②），进入最小原型评估；本轮不预判其结果。
- 命题 3 失败，且失败原因是接口拆分本身与 §2.2/garbling authenticity 的结构性冲突 → 针对 Afshar batching 适配路线作 NO-GO；不等于 PA-VFANN 整体 NO-GO。
- 不再增加队列方案、算法参数或新文献搜索；索引绑定、队列优化、成本估算均留待命题 3 闭合后再处理。

## 7. 版本与交付核验

| 项 | 值 |
|---|---|
| 分支 | `exp03g-batching-one-sided-output` |
| 基线 commit | `ea09cd3aaf2f58a5516a678f8a7f5c916b233d3a`（EXP-03F 最终 HEAD） |
| 报告正文 commit | `d5c3d8d4b6c1b3608f8c9e71bfecc72b1f364c78` |
| 最终 HEAD | 本报告最后一次提交（元数据记录）；报告正文提交的远端引用已由 GitHub API 核验为上述 SHA |
| 工作区状态 | 元信息提交与推送后 `git status --short` 为空；除本报告外无改动 |
| 改动范围 | 仅新增 `docs/EXP-03G-BATCHING-ONE-SIDED-OUTPUT.md` |
| 不修改 | 代码、数据、EXP-01/02/02A/03A/03B/03C/03D/03E/03F 及任何历史结论 |

### 论文引用索引（会议正式版，Springer LNCS 9056）

- §2.1 RAM/ORAM 定义与模拟器：提取文本第 105–124 行
- §2.2 Garbling Schemes（部分解码、authenticity、分区约定）：第 126–161 行
- §3.1 High-Level Overview（P1 验证 authenticity）：第 180–244 行
- §3.2 Detailed Protocol（1(a) 承诺、2 cut-and-choose、3(a) head、3(f)–(g) 输出）：第 246–344 行
- §3.3 Security Proof（两种腐败模拟器）：第 345–380 行
- §4.2(f)/(i)/(j) streaming w-key（仅作对照）：第 478–509 行
- 全文 PDF：`https://link.springer.com/content/pdf/10.1007/978-3-662-46800-5_27.pdf`
- ePrint `2014/759.pdf`：本环境 403，full version Appendix D 未逐字核验；本轮所有引用均来自会议正式版。
