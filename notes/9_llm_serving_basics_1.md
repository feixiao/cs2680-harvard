# 第9讲：LLM 服务基础 I（LLM Serving Basics I: Introduction to LLM）

> 原幻灯片标题：Modern AI Systems: Agents and System Optimizations — LLM Serving Basics I: Introduction to LLM（Harvard CS2680，讲师 Juncheng Yang）

## 本讲概览

本讲是 LLM Serving 系列的第一讲，主题是"了解 LLM 本身"，为后续的服务与系统优化打基础。幻灯片共 36 页，主线有两条：第一部分从一个请求的生命周期出发，依次讲清 Tokenize（分词）→ Schedule（调度与连续批处理）→ Prefill（预填充）→ Decode（解码）→ Detokenize/Stream（反分词与流式输出）六个阶段，并指出 Prefill 是 compute-bound（算力受限）、Decode 是 bandwidth-bound（带宽受限）这一贯穿全系列的根本区别。第二部分"Peeking into the model"深入模型内部：以 Llama 3 70B 为例，讲 Transformer block 的堆叠结构、RMSNorm 与残差流、self-attention 的 QKV 计算与 O(n²) 复杂度、FlashAttention、多头注意力（MHA）与 KV 头共享（GQA/MQA）对 KV cache 的压缩，并用具体数字（141 GB 权重、320 KB/token 的 KV cache、141 GFLOPs/token）把权重、算力和 KV cache 三个量与 prefill 时间、decode 时间、显存需求对应起来。随后简要介绍 MoE（稠密 vs 专家混合）的内存/算力权衡，最后用"Advanced — skim"标记的一组幻灯片快速扫过滑动窗口注意力、MLA、线性注意力、状态空间模型（Mamba）、稀疏注意力、循环 Transformer 与扩散 LM 等前沿变体，重点强调它们对 KV cache 与服务吞吐的影响。

## 课程安排（Logistics）

- **Assignment 3** 截止时间为周二（Tuesday）23:59（11:59pm）。
- **排行榜（leaderboard）提交没有补交日（NO LATE DAY）**——错过截止就没有补交机会，这是硬性规定。
- 具体需要提交什么，查看课程网站。
- 项目海报展示（Project poster presentation）可选第二时段：**12 月 2 日下午 1–3 点**；仅当 12 月 7 日无法到场的人才能报名，报名截止为最后一个星期日，想改到 12 月 2 日展示的同学要尽快发邮件联系课程组。

## 今日计划（Plan for today）

本讲的议程包括：

- Introduction to LLM（LLM 介绍）：一个 LLM 请求的生命周期（lifecycle of an LLM request）、Transformer 架构¹、稠密模型（dense）、MoE 及高级变体。
- Introduction to GPU for LLM serving（面向 LLM 服务的 GPU 介绍）：GPU 基础、GPU 架构、GPU 编程与最近的 kernel 进展。

脚注 ¹ 说明本讲假设的是传统的 self-attention Transformer 架构；脚注 ² 说明 GPU 部分不会深入细节，目标是帮助建立直觉（build intuition）。

## LLM 请求的生命周期

幻灯片给出从 prompt（提示词）到流式文本的六个阶段，编号 1–6：

**1 Tokenize（分词）→ 2 Schedule（调度）→ 3 Prefill（预填充）→ 4 Decode（解码，每个输出 token 重复一次）→ 5 Detokenize（反分词）→ 6 Stream（流式输出）**

其中两个关键的性能指标在幻灯片中被特别强调：

- **Prefill → time to first token（首 token 延迟，TTFT）**：整个 prompt 在一次前向传播（one forward pass）中处理完。
- **Decode → tokens per second（每秒 token 数，吞吐/TPS）**：每生成一个输出 token 就要做一次前向传播，因此 decode 阶段对每个输出 token 重复执行。

### 阶段 1：分词（Tokenization）

幻灯片以 "Serving is hard" 为例说明分词的原理：

- **文本被切分成 token，而不是单词（word）**："Serving is hard" 这个短语有 3 个英文单词，但被切成了 **4 个 token**（token ID 为 1841、288、374、2653）——"Serving" 一词被拆成两个 token（1841 288）。
- **平均每 token 约 3–4 个字符**（about 3–4 characters per token）。
- **token 数量直接驱动成本（cost）和内存（memory）**：这是服务成本核算的基本单位，后面所有内存/算力估算都以 token 为单位。
- **不同模型的 tokenizer 各不相同**（Tokenizers differ across models）。
- 幻灯片给出 **Byte-level BPE（字节级字节对编码）** 的定义：从 256 个字节值（byte values）出发，然后反复把出现频率最高的相邻 token 对合并（merge）成一个新的 token。这样**不存在未知 token**（no unknown tokens），任何字节序列都能被编码。

图示：该页展示 "Serving is hard" 被切分为 1841 / 288 / 374 / 2653 四个 token ID 的示意图，直观说明"4 个 token —— 而不是 3 个单词"。

### 阶段 2：调度与批处理（Scheduling and batching）

幻灯片用一个表格展示连续批处理（continuous batching）下 GPU 每一步（step）实际运行的请求：

| step t | step t+1 | step t+2 |
|---|---|---|
| R1 | R1 | R1 |
| R2 | free | R5 |
| R3 | R3 | R3 |
| free | R4 | R4 |

要点：

- 请求是**独立到达**的（requests arrive independently），而 GPU 希望处理**批**（batches）。
- **调度器（scheduler）负责决定每一步运行哪些请求**。
- **连续批处理（continuous batching）：请求可以中途加入或离开（join or leave mid-flight）**——上表中 R2 完成离开，R4、R5 随后加入，而不必等待凑满一整批。
- **准入（admission）受 KV cache 内存上限约束**（admission is capped by KV cache memory）：新请求能否进入批次，取决于 KV cache 是否还有余量。
- 幻灯片底部结论：**"完成的请求离开，新请求加入——不必等待满批"**（Finished requests leave, new ones join — no waiting for a full batch）。这是 LLM 服务区别于传统"静态批"（static batching）的核心机制，也是后面显存预算问题的入口。

图示：该页的表格展示了三个连续 step 中各槽位（slot）请求的进进出出：R2 在 t+1 完成后腾出槽位，R4 在 t+1 加入，R5 在 t+2 加入。

### 阶段 3：预填充（Prefill）

幻灯片要点：

- **整个 prompt 在一次前向传播中运行**（whole prompt runs in one pass）。
- **所有 prompt token 并行参与 attention**（all prompt tokens attend in parallel）。
- **Prefill 是 compute-bound（算力受限）**，其成本随 prompt 长度增长。
- Prefill 阶段**生成 KV cache**（generate the KV cache），并**输出第 1 个 token**（emits token 1，即首个输出 token）。
- 幻灯片标注：compute-bound → 对应指标是 **time to first token（首 token 延迟）**。

图示：该页展示 prompt 的 6 个 token（t1–t6）被打包成"对全部 token 的一次前向传播"（one forward pass over all tokens），随后产出"第一个输出 token"，并引出逐渐变长的 KV cache。

### 阶段 4：解码与采样（Decode generates logits; sampling picks the next token）

这一页把 decode 与采样（sampling）并排展示，要点：

- **每个新 token 对应一次前向传播**（one forward pass per new token），KV cache 每步增长一个 token（cache grows by one token per step）。
- Decode 是 **bandwidth-bound（带宽受限）**，所以幻灯片建议"batch it"（用批处理把它摊开）。
- **KV cache 满了 → 抢占（preempt）或排队（queue）**（Cache full → preempt or queue）。
- 采样参数（同一模型、同一 prompt，这些设置会改变答案以及运行时长）：
  - **Temperature（温度）**：`temperature = 0` 时总是取概率最高的 token（always the top token）；>1 时更多 token 成为可能（more tokens are possible）。
  - **Top-k**：`top_k = 50` 表示从最可能的 k 个（概率最高的 50 个）token 中采样，k 是固定值。
  - **Top-p（nucleus，核采样）**：`top_p = 0.9` 取"累计概率和达到 p（0.9）的最少 token 集合"（fewest tokens summing to p），集合大小随分布置信度自适应（adapts to confidence）。

图示：该页分两栏。左栏"STAGE 4 · DECODE"画了 4 个 step，每一步的 KV 块都比上一步多一格，标注"每个新 token 一次前向传播""缓存每步增长一个 token""带宽受限，所以要批处理""缓存满了就抢占或排队"。右栏"STAGE 5 · SAMPLING"把 logits 经过温度、top-k、top-p 三种采样策略选出下一 token 的过程可视化。

### 阶段 5：反分词与流式输出（Detokenize and stream）

幻灯片要点：

- **token ID 在产生的同时就变成文本**（token IDs become text as produced）。
- **不完整的字符会被缓冲**（partial characters are buffered）——因为一个 token 可能只覆盖一个 UTF-8 字符的一部分，要等下一个 token 才能拼出完整字符。
- **流式输出（streaming）带来交互感**（streaming makes it interactive）。
- **提前停止会释放 KV cache 内存**（stopping early frees cache memory）。
- **停止 token（stop token）、长度上限（length limit）或客户端断开（disconnect）都会结束流**（Stop token, length limit or disconnect ends the stream）。

图示：该页用一个逐 token 累积的表格展示用户看到的内容如何一步步增长：t1 → "The"，t2 → "The model"，t3 → "The model streams"，t4 → "The model streams tokens"。

### 生命周期要点回顾（Lifecycle: what to take away）

幻灯片把六个阶段浓缩成五条：

1. **Tokenize**：把文本转成 token ID；**词表（vocabulary）越大 → token 数越少，但 embedding 表（embedding table）越大**。
2. **Schedule**：连续批处理允许每个 step 都有请求加入和离开；**KV cache 内存约束准入**。
3. **Prefill**：整个 prompt 在一次 compute-bound 的前向传播中完成，**生成 KV cache 和第 1 个 token**。
4. **Decode and sample**：每个 token 一次 memory-bound（内存受限）的前向传播；采样从 logits 中选出每个 token。
5. **Detokenize and stream**：把每个 token ID 转成文本，产出即发送。

## 深入模型内部（Peeking into the model）

### 符号约定（Notation）

幻灯片给出两列符号表，并以 **Llama 3 70B**（引用 Meta, The Llama 3 Herd of Models, 2024）作为贯穿全讲的具体例子：

| 符号 | 含义 | Llama 3 70B | 符号 | 含义 | Llama 3 70B |
|---|---|---|---|---|---|
| d | 模型宽度（model width） | 8,192 | n | 序列中 token 数 | 例如 20,000 |
| L | 层数（layers） | 80 | B | 并发请求数 | 例如 16 |
| H | query 头数（query heads） | 64 | N | 参数量（parameters） | 70.6B |
| H_kv | key/value 头数 | 8 | W | 权重大小（字节，BF16） | 141 GB |
| d_k | 每头维度，d ÷ H | 128 | KV | 每 token 的 KV 字节数 | 320 KB |
| d_ff | MLP 隐层宽度 | 28,672 | KV | 2 × L × H_kv × d_k × 2 B | — |
| V | 词表大小 | 128,256 | Kᵀ | K 的转置 | — |

这些符号会在后面的计算中反复出现，其中 **KV = 2 × L × H_kv × d_k × 2 B** 是 KV cache 每 token 大小的核心公式（2 代表 K 和 V 两份，BF16 下每个值 2 字节）。

### 一个 LLM 就是相同 Transformer block 的堆叠

幻灯片以 Llama 3 70B 为例描述前向流程：

- **输入**：文本以整数 token ID 的形式到达（text arrives as integer token IDs）。
- **Embedding（嵌入层）**：每个 token ID 变成一个 8,192 维向量。
- **Transformer block × L**：Llama 3 70B 有 **L = 80 个 block**，每个 block 都带 norm + residual（归一化 + 残差）。每个 block 内：
  - **Self-attention（自注意力）**：在不同 token 之间混合信息（mixes information across tokens）。
  - **FFN（feed-forward，前馈网络）**：对每个 token 独立地做变换（transforms each token on its own）。
- **LM head（语言模型头）**：对词表中的**每个 token 输出一个分数**（one score per vocabulary token），表示下一 token 的概率。
- **Softmax**：把分数变成概率。

图示：该页是一张纵向流程图，从底部的 token IDs 出发，经 Embedding 变成 8,192 维向量，向上穿过 80 个 Transformer block（每个含 Self-attention 与 FFN），最后经 LM head 得到 128,256 个分数并 softmax 成概率。

### 每个 block：残差流上叠加 attention 与 MLP，各带 RMSNorm

幻灯片给出 block 内部公式：

- **h = x + Attn(RMSNorm(x))**
- **y = h + FFN(RMSNorm(h))**

三个关键概念：

- **RMSNorm**：按均方根（root-mean-square）对输入重新缩放，每个输入维度有一个**学习到的增益 g（learned gain g）**；公式上 RMSNorm(x) = x ⊙ g / sqrt( (1/d) Σ xᵢ² + ε )。
- **Pre-norm（前置归一化）**：每个子层（attention、FFN）先过 RMSNorm 再加回残差流。
- **残差流（residual stream）**：向量 x 流经全部 80 个 block；每个子层只是往残差流上"加"一个更新（only adds an update）。正是这种结构让深堆叠能够稳定训练（so deep stacks train stably）。

（引用：Zhang & Sennrich, RMSNorm, NeurIPS 2019；Xiong et al., ICML 2020；Meta, Llama 3, 2024）

### 自注意力（Self-attention）：每个 token 能读到其他 token

幻灯片解释 self-attention 的核心语义：

- 每个 token 产生三样东西：**value（值）、key（键）、query（查询）**。
- **Query · key 的打分决定从每个 token 读取多少**（query·key scores decide how much to read from each token）。
- **因果掩码（causal mask）**：n 个 token 产生 n² 个分数，掩码**隐藏未来 token**（hides future tokens）——token 只能看到自己之前的内容；代价是成本随 n² 增长。
- 计算形式：`softmax(QKᵀ/√d_k) · V`，即 masked softmax 在 QKᵀ/√d_k 上做 softmax 再乘 V。
- **为什么要除以 √d_k？** 因为 q·k 是 d_k 个乘积的和，其数值随 d_k 增长；缩放可以**防止 softmax 饱和**（scaling keeps softmax from saturating）。
- 幻灯片举例：某行的 attention 权重为 0.1、0.2、0.5、0.2，和为 1。

图示：该页用一个 5 个 token 的序列示意因果注意力矩阵：对角线以上被掩码（masked）置为 −∞，示例行 "The" 读到之前各 token 的权重为 0.1 / 0.2 / 0.5 / 0.2，行和为 1。

（引用：Vaswani et al., Attention Is All You Need, NeurIPS 2017）

### QKV 投影：每个 token 是 X 的一行，权重矩阵把它变成 Q、K、V

幻灯片给出变量定义与三个投影：

| 符号 | 形状 | 含义（Llama 3 70B 数值） |
|---|---|---|
| X | n × d | 目前的 n 个 token（prompt + 已输出部分） |
| d | — | 每个 token 向量 8,192 个数 |
| d_k | — | 每个 query 或 key 128 个数（每头） |
| W_Q, W_K, W_V | d × d_k | 学习到的权重，每头一份 |

- **Q = X W_Q**：每个 token 在"找"什么（what each token looks for）。
- **K = X W_K**：每个 token "提供"什么（what each token offers）。
- **V = X W_V**：每个 token 往上下文中"传递"什么（what each token passes on）。
- **head（头）**：一个注意力单元；**64 个头并行运行**（one attention unit; 64 run in parallel）。

### 打分与输出：QKᵀ 给每一对 token 打分，softmax 后乘 V

幻灯片逐步骤给出矩阵形状：

- **Kᵀ**：把 key 转置，使每一列对应一个 token（keys turned so each column is one token）。
- **S = Q Kᵀ / √d_k**：形状 n × n。S 中第 i 行第 j 列 = query i · key j，即 token i 对 token j 的分数。
- **加掩码 M**：对角线上方（future tokens）为 −∞，隐藏未来 token。
- **A = softmax(S + M)**：形状 n × n，**每一行和为 1**（each row sums to 1）。示例："A 的第 4 行说明 token 4 从 token 1 到 token 4 各取多少，且整行加和为 1。"
- **O = A V**：输出，形状 n × d_v，**每行是 V 各行的一种加权混合**（each row is a weighted mix of V rows）；d_v 为 value 向量维度（128）。

### 自注意力的 O(n²) 计算复杂度

幻灯片用表格总结各步的形状：

| 步骤 | 公式 | 形状 |
|---|---|---|
| 输入 | X | n × d |
| 查询 | Q = X W_Q | n × d_k |
| 分数 | S = QKᵀ/√d_k | n × n |
| 权重 | A = softmax(S + M) | n × n |
| 输出 | O = A V | n × d_v |

- **每层 FLOPs**：QK 部分 2 n² d，AV 部分 2 n² d，**合计 ≈ 4 n² d**——注意力计算量随序列长度**平方**增长。
- **如果显式存储 S 需要多少内存**：n² × heads × layers × 2 B；代入 Llama 3 70B 的数值（示例中取 n = 8,192）= 8,192² × 64 × 80 × 2 B ≈ **690 GB**——这是完全不可行的。
- **FlashAttention** 的解法：**分块（tile by tile）计算 softmax，从不存储 S**（computes softmax tile by tile and never stores S）。这正是 prefill 阶段能在显存限制内处理长序列的关键 kernel 技术。

（引用：Vaswani et al., NeurIPS 2017；Dao et al., FlashAttention, NeurIPS 2022）

### 多头注意力（MHA）：64 个小注意力并行，再用 W_O 混合

幻灯片给出 MHA 的公式与流程：

- **head_i = softmax(Q_i K_iᵀ/√d_k + M) V_i**
- **MHA(X) = Concat(head₁, …, head_H) W_O**

流程分三步：

- **Split（拆分）**：Q、K、V 各拆成 H = 64 份，每头维度 d_k = 8,192 ÷ 64 = **128**。
- **Attend（注意力）**：每个头在自己 128 维空间上独立跑带掩码的 softmax 注意力。
- **Mix（混合）**：W_O 把 64 个头拼回一个 128 维（8,192 维）向量。
- **与单个宽头 FLOPs 相同**：64 × 128 = 8,192，所以**拆分改变的是"学到什么"，而不是成本**（splitting changes what is learned, not the cost）。

### 每个头用自己的 128 维做注意力，因此头们学到不同模式

图示：该页展示 64 个头并行的数据流——输入 X（n × 8,192）投影出每头 n × 128 的 Q_i、K_i、V_i，各头独立注意力后 concat 回 n × 8,192 再乘 W_O。幻灯片用斜体标注各头可能学到的模式：**head 1 关注"前一个 token"**（previous token）、**head 2 关注"第一个 token"**（first token）、**head 3 关注"邻近 token"**（nearby tokens）、**head 64 关注"整个上下文"**（whole context），中间省略 60 个头。这种"不同头学不同模式"是多头设计的直观解释。

### 共享 KV 头：GQA / MQA 缩小 KV cache

幻灯片对比三种方案（以 8 个 query 头为例）：

| 方案 | query 头 | KV 头 | KV cache 大小 |
|---|---|---|---|
| Multi-head（MHA） | 8 | 8 | 1× |
| Grouped-query（GQA，分组查询） | 8 | 2 | ¼× |
| Multi-query（MQA，多查询） | 8 | 1 | ⅛× |

- **每 token 的 KV cache = 2 × L × H_kv × d_k × 每个值的字节数**。
- **Llama 3 70B**：64 个 query 头共享 **8 个 KV 头**，因此其 KV cache 比 MHA **小 8 倍**：
  - = 2 × 80 × 8 × 128 × 2 B = **320 KB / token**；
  - 若用 MHA（H_kv = 64）则约 **2.5 MB / token**。
- 这正是前文"准入受 KV cache 内存上限约束"这一调度约束在模型侧的解法：模型架构（GQA）直接决定了每个并发请求占用的显存量，从而决定了 GPU 能同时服务多少请求。

（引用：Ainslie et al., GQA, EMNLP 2023；Shazeer, MQA, 2019）

### Llama 3 70B 结构总览（示例图）

图示：该页用 Llama 3 70B 作为例子展示一个 block 的宽度变化——d = 8,192（token 向量宽度，一个 token = 8,192 个数），64 个 Q 头 × 128 维 = 8,192；共享 **h_kv = 8** 个 KV 头（图中画了 KV 1 … KV 8）；FFN 隐层宽度 **d_ff = 28,672 = 3.5 × d**（8,192 → 28,672 → 8,192）；L = 80 个 Transformer block 串接（图中示意第 1、第 2、…、第 80 层）；V = 128,256，即 LM head 对词表中 128,256 个 token 各输出一个分数。

### Llama 3 70B：参数分布在哪里

幻灯片给出参数量的计算公式与数值：

| 组件 | 公式 | 参数量 |
|---|---|---|
| Attention / 层 | 2d · H · d_k + 2d · H_kv · d_k | 151M |
| FFN / 层 | 3 · d · d_ff | 705M |
| 所有层 | 80 × 856M | 68.5B |
| Embed + LM head | 2 · V · d | 2.1B |
| **总计** | — | **70.6B** |

要点：FFN 占每层参数的大头（705M，约占 856M 中的 82%），这是后文讨论 MoE（只替换 FFN）为什么能大幅改变内存/算力特征的背景。（引用：Meta, The Llama 3 Herd of Models, 2024）

### 系统直觉：权重、算力、KV cache 分别决定了 prefill、decode 与内存

幻灯片以 **Llama 3 70B、BF16、部署在 2× H200**（1,978 TFLOP/s、9.6 TB/s 带宽、282 GB 显存；引用 NVIDIA, H200 datasheet, 2024）为例，设 **n = 80,000 tokens**、B 个请求，给出三个基本估算量：

- **Weights（权重）= 2 B × params = 141 GB**——决定模型能不能装进显存。
- **Compute ≈ 2 × params = 141 GFLOPs/token**——每个 token 约 2×参数量 FLOPs（矩阵乘法的标准估算）。
- **KV cache = 2 × L × H_kv × d_k × 2 B = 320 KB/token**——决定能同时容纳多少 token 的上下文。

由此推导出两个关键表格（B = 1 与 B = 64，n = 80,000）：

| 量 | 公式 | 1 个请求 | 64 个请求 |
|---|---|---|---|
| Prefill 时间 | B · (2N·n + 2L·d·n²) ÷ FLOP/s | **9.95 s** | **637 s** |
| 所需 VRAM | W + B·n·KV | **167 GB** | **1,779 GB** |

要点解读（依据幻灯片内容）：

- Prefill 时间随并发数 B 线性放大（80K 长 prompt 单请求就要约 10 秒）。
- 显存 = 权重 + KV cache：**单请求 80K 上下文需要 167 GB**（141 GB 权重 + 80,000 × 320 KB ≈ 25 GB KV）；而 **64 个请求就需要 1,779 GB**，远超 2× H200 的 282 GB。
- 幻灯片提出的问题是：**"你如何支持更长的序列？"（How do you support longer sequences?）**——这正是后续各讲（KV cache 量化/压缩、前缀缓存、MoE、架构变体等）要回答的问题。

（引用：Meta, The Llama 3 Herd of Models, 2024；NVIDIA, H200 datasheet, 2024）

## MoE：用路由器和专家 FFN 替换每层的 FFN

### MoE 块结构

幻灯片对比 Dense block 与 MoE block：

- **Dense block**：Attention + **一个大的 FFN（单个大 MLP）**，"全部计算对每个 token 都执行"（all of it runs for every token）。
- **MoE block**：Attention 不变，**用 Router + 一组更小的专家 FFN 替换 FFN**（replace FFN with router + experts）：图中有 **E0–E7 共 8 个更小的 FFN，Router 选 top-2，每个 token 只运行其中 2 个**（8 smaller FFNs; only 2 run per token）。

（引用：Shazeer et al., MoE, ICLR 2017；Jiang et al., Mixtral of Experts, 2024）

### Dense vs MoE：内存随总参数增长，算力随激活参数增长

幻灯片给出对比表（**GFLOPs ≈ 2 × 激活参数量**）：

| 模型 | 专家（experts） | 总参数量 | 每 token 激活 | 权重（BF16） | GFLOPs / token |
|---|---|---|---|---|---|
| Llama 2 70B | 全部（稠密） | 69B | 69B | 138 GB | 138 |
| Mixtral 8x7B | 2 / 8 | 46.7B | 12.9B | 93 GB | 26 |
| Llama 3.1 405B | 全部（稠密） | 405B | 405B | 810 GB | 810 |
| DeepSeek-V3 | 9 / 257 | 671B | 37B | 1,342 GB | 74 |

- **同样的质量，更少的算力**（same quality, less compute）：
  - **Mixtral 8x7B 在约 1/5 的 FLOPs 下匹配 Llama 2 70B**（26 vs 138 GFLOPs/token）。
  - **DeepSeek-V3 在约 1/11 的 FLOPs 下比肩 Llama 3.1 405B**（74 vs 810 GFLOPs/token），**但需要 1.7× 的内存**（1,342 GB vs 810 GB）。
- 核心权衡：**MoE 把"权重内存"和"计算量"解耦**——总参数（决定内存/存储）可以很大，而每 token 激活参数（决定算力）可以很小。

（引用：Jiang et al. 2024；DeepSeek-AI 2024；Touvron et al. 2023；Llama Team 2024）

## 高级 LLM 变体（Advanced LLMs）

幻灯片用 "ADVANCED — skim, or read more on your own"（进阶——快速扫过，或自行深入）标记了这一组内容，涵盖：滑动窗口（Sliding window）、稀疏注意力（Sparse attention）、MLA（Multi-Latent attention）、循环 Transformer（Looped transformers）、线性注意力（Linear attention）、多 token 预测（Multi-token prediction）、状态空间模型（State-space models）、扩散 LM（Diffusion LMs）。以下按幻灯片内容逐一记录。

### 滑动窗口注意力（Sliding window）：限制 KV cache，少量全局层保留长程记忆

幻灯片对比三种方案，并给出代表模型的层模式：

| 模型 | 层模式 | 行为 | KV 行为 |
|---|---|---|---|
| 全因果（Full causal） | 每层全局（图中 L L L L L G 模式） | 每个 token 读所有前文 | **KV 随 n 增长** |
| Gemma 3 | **5 个局部层（w = 1,024）: 1 个全局层**，循环重复（sliding window, w = 3 的图示标注） | 局部层窗口 w 内 | **KV 上限为 w 个 token** |
| Mistral 7B | **每层都是局部层，w = 4,096** | 只读最近 4,096 个 token | KV 上限 4,096 |
| Gemma 2 | **1 局部（w = 4,096）: 1 全局交替** | 交替模式 | 混合 |

- 幻灯片对比"last token reads all（最后一个 token 读所有前文）"与"last token reads 3（只读窗口内的 3 个）"两种情形，说明全局层与局部层的记忆差异。
- **服务效果**：在 128K 上下文下，**Gemma 3 存储的 KV 比全全局层少约 6 倍**（about 6× less KV than all-global layers）。

（引用：Gemma Team, Gemma 3 Technical Report, 2025）

### MLA（Multi-Latent attention）：每个 token 只存一个压缩 latent

图示：该页对比 MHA 与 MLA 的缓存方式——MHA 为每个头缓存 K 和 V（图中蓝色 = K、黄色 = V，展示了 128 个头中的 8 个）；**MLA 每个 token 只缓存一个压缩 latent c**（compressed latent per token），虚线表示的 K、V **从 c 重建（rebuilt from c），从不存储**（rebuilt from c, never stored）。流程为：token h → 压缩（compress）出 latent c 缓存起来；attention 需要时再**展开（expand）回 K、V**。

- 幻灯片说明这是"存摘要、重建细节"（store the summary, rebuild the details），代价是 decode 时**在 decode 时间把升维投影折进 query 和 output 权重中做额外计算**（the up-projection is folded into the query and output weights at decode time）——**多些计算，省些内存**（extra math, less memory）。
- **服务效果**：**与 DeepSeek 67B 相比，DeepSeek-V2 将 KV cache 减少 93%（cuts KV cache 93%），并把生成吞吐提升 5.8×（lifts generation throughput 5.8×）**。

（引用：DeepSeek-AI, DeepSeek-V2, 2024；DeepSeek-AI, DeepSeek-V3, 2024）

### 线性注意力（Linear attention）与 Gated DeltaNet：固定大小状态替代增长的 KV cache

图示：该页对比 softmax attention 与线性注意力层的状态——softmax attention 的 **KV cache 永远每 token 追加一条记录**（one more entry per token, forever）；**线性注意力层保持固定大小的状态 S_t：d_k × d_v 矩阵**（fixed-size state），**每步大小相同、原地更新**（same size at every step, updated in place）。普通线性注意力"读取状态"；**Gated DeltaNet** 则"指向状态"：每个 token 把自己的 key × value 加进状态，查询先**淡出旧状态（fade the old state）再覆写新 key 所指的内容**（overwrite what the new key points to），由两个门控制：

- **α_t（decay gate，衰减门）**：决定忘记多少（how much to forget）。
- **β_t（write gate，写入门）**：决定覆写力度（how hard to overwrite）。

- **Qwen3-Next：48 层 = 36 层 GDN + 12 层 Attention，采用 3:1 配方**（only the 12 attention 层保留 KV cache）；同样的 3:1 配方也用于 **Kimi Linear、Qwen3.5**。
- **服务效果**：**4 层中有 3 层保持常量大小的每请求状态，无论上下文多长**（3 of 4 layers hold a constant-size state per request, at any context length）。

（引用：Yang et al., Gated Delta Networks, ICLR 2025；Qwen Team, Qwen3-Next, 2025）

### 状态空间模型（State-space models，Mamba）：同样保持固定大小状态

幻灯片用表格对比"门控线性注意力"与"状态空间（Mamba）"的更新规则：

| | 门控线性注意力 | 状态空间（Mamba） |
|---|---|---|
| 更新 | S ← α S + β v kᵀ | h ← Ā h + B̄ x |
| 状态 | d_k × d_v 矩阵 S（key–value 对） | 每通道一个小的向量 h |
| 每个 token | 把自己的 value × key 按 β 缩放后加进 S | 先按 Ā 衰减 h，再加上 B̄ × 当前 token x |
| 遗忘机制 | 门 α：token 决定 S 衰减多少 | Ā：token 决定 h 衰减多少 |
| 学术根源 | 去掉 softmax 的注意力 | 信号处理与 RNN |

三个关键词（Selective / Fixed state / Hardware-aware scan）：

- **Selective（选择性）**：Ā 和 B̄ 依赖每个 token，因此层可以选择保留什么（so the layer chooses what to keep）。
- **Fixed state（固定状态）**：每通道只保持一个小的状态 h，**decode 内存不随 n 增长而保持平坦**（decode memory stays flat as n grows）。
- **Hardware-aware scan（硬件感知扫描）**：并行 scan 把状态保持在 SRAM 中；**Mamba-2 把它变成 matmul（矩阵乘法）**。

- **服务效果**：**没有增长的 KV cache；Mamba 报告生成吞吐最高可达 Transformer 的 5 倍**（Mamba reports up to 5× a Transformer's generation throughput）。

（引用：Gu & Dao, Mamba, COLM 2024；Dao & Gu, Mamba-2, ICML 2024）

### 稀疏注意力（Sparse attention）：每个 query 只读前文中最相关的 top 2,048 个 token

图示：该页用一个 16 个 token 的序列示意（深红色 = 被选中的 top-k；示例取 k = 4，实际 **DeepSeek-V3.2 保留 k = 2,048**）。

三步流程：

1. **Score（打分）**：`I_{t,s} = Σ_j w_{t,j} · ReLU(q_{t,j} · k_s)`。其中 **Indexer（索引器）** 用少数头（few heads）、FP8 精度、每个 token 一个 128 维 key，对每个历史 token 打分。
2. **Select（选择）**：`S_t = top-k of I_{t,s}`——取分数最高的 2,048 个历史 token。
3. **Attend（注意力）**：`o_t = Attn(q_t, {c_s : s ∈ S_t})`——**主注意力只对 2,048 个 token 做，而不是全部 n 个**（2,048 tokens instead of all n）。

- **服务效果**：**每 token 的工作量被限制在 2,048 次读取以内**（work per token is capped at 2,048 reads），**但所有 token 的 KV 仍然全部存储**（all tokens' KV stays stored）——注意这与滑动窗口/MLA 不同：稀疏注意力只省算力，不省 KV cache 存储。

（引用：DeepSeek-AI, DeepSeek-V3.2-Exp, 2025）

### 循环 Transformer（Looped transformers）：重复使用同一个 block，深度花的是算力而非权重

图示：该页展示 "Input → Prelude P → Block R × K 个循环 → Coda C → Output" 的结构，强调"每个循环使用相同的权重"（same weights every loop）。

- **共享权重（Shared weights）**：block R 被应用 K 次，因此**增加深度不增加任何参数**（extra depth adds no parameters）。
- **测试时深度（Depth at test time）**：一个 **3.5B 的循环深度模型，随 K（循环次数）增大在推理任务上表现更好**（a 3.5B recurrent-depth model gets better on reasoning tasks as K grows）。
- **系统权衡（System tradeoffs）**：权重保持很小，**但每个循环是顺序执行的：延迟随 K 增长**（each loop is sequential: latency grows with K）；更深的模型意味着更多循环，"更多循环增加的是算力和延迟，而不是参数"（more loops add compute and latency, not parameters）。
- **无参数的算力（Compute without parameters）**：K 个循环花费 K 倍该 block 的 FLOPs，且**不增加额外权重内存**（K loops cost K× the block's FLOPs and no extra weight memory）。

（引用：Dehghani et al., Universal Transformers, ICLR 2019；Geiping et al., 2025）

### 扩散 LM（Diffusion LMs）：若干并行步骤填充实体 token

图示：该页用 4 个步骤展示扩散 LM 的生成方式——**Step 0** 全为掩码 `[M][M][M][M][M][M]`；**Step 1** 填入 "read"；**Step 2** 填入 "GPUs"；**Step 3** 完成为 "GPUs read every weight step"（深红框 = 本步新填入的 token），即**通过若干并行细化步骤（parallel refinement steps）逐步填入被掩码的 token**。

两个代表模型：

- **LLaDA（2025）**：8B 的掩码扩散模型，**从 2.3T token 从头训练**（trained from scratch on 2.3T tokens）；**与 Llama 3 8B 竞争力相当**（competitive with Llama 3 8B）。
- **Dream 7B（2025）**：**从 Qwen2.5 7B 权重出发**（starts from Qwen2.5 7B weights）；**网络本身仍然是 Transformer**（the network is still a Transformer）。

- **服务效果**：**每一遍（pass）可以填入许多 token，但减少步数会损失质量**（each one pass fills many tokens, but fewer steps cost quality）——与自回归"每步一个 token"形成对比，对延迟/吞吐结构有本质影响。

（引用：Nie et al., LLaDA, 2025；Ye et al., Dream 7B, 2025）

## 下一讲（Next class）

幻灯片最后一页预告了下一讲（仅给出 "Next class" 标题及配图，无更多文字内容）。

## 核心要点

1. 一个 LLM 请求经历六个阶段：Tokenize → Schedule → Prefill → Decode（每个输出 token 重复）→ Detokenize → Stream。
2. Prefill 是 **compute-bound**，对应指标是**首 token 延迟（TTFT）**；Decode 是 **bandwidth/memory-bound**，对应指标是 **tokens/second**，所以"要批处理"。
3. 分词按 **byte-level BPE** 切分：约 3–4 字符/token，"Serving is hard" 是 4 个 token 而非 3 个单词；token 数直接驱动成本与内存；不同模型 tokenizer 不同。
4. **连续批处理（continuous batching）**让请求在每一步随时加入/离开，不必等满批；**准入上限由 KV cache 内存决定**；缓存满了就抢占或排队。
5. 采样参数 temperature=0 / top_k=50 / top_p=0.9 会改变答案与运行时长：0 温度恒取 top token，top-k 固定取前 k 个，top-p 取累计概率达到 p 的最少集合。
6. Llama 3 70B 的关键参数：d=8,192、L=80 层、H=64 query 头、H_kv=8、d_k=128、d_ff=28,672、V=128,256、N=70.6B、权重 141 GB（BF16）。
7. Transformer block = x → h = x + Attn(RMSNorm(x)) → y = h + FFN(RMSNorm(h))；RMSNorm 用每维度学习增益 g 归一化，pre-norm + 残差流让 80 层深堆叠稳定训练。
8. 自注意力 O = softmax(QKᵀ/√d_k + M)V：因果掩码隐藏未来 token；除以 √d_k 防止 softmax 饱和；每行注意力权重和为 1。
9. 注意力计算 **≈ 4 n² d FLOPs/层**，O(n²) 复杂度；若显存存储 S 矩阵需约 **690 GB**（8,192² × 64 × 80 × 2 B），不可行；**FlashAttention 分块计算 softmax、从不存储 S**。
10. MHA 把 d 拆成 64 个 128 维头并行注意力再 concat + W_O；总 FLOPs 与单宽头相同，拆分改变学到什么而非成本；不同头学会关注不同模式（前一个 token / 第一个 token / 邻近 / 全上下文）。
11. **KV cache 每 token = 2 × L × H_kv × d_k × 2 B**；GQA/MQA 共享 KV 头：8 KV 头 vs 8 query 头 → 8× 缩小；Llama 3 70B 用 64 query 头共享 8 KV 头 = **320 KB/token**（MHA 则约 2.5 MB/token）。
12. 参数分布：每层 Attention 151M + FFN 705M ≈ 856M，80 层共 68.5B，Embed+LM head 2.1B，合计 70.6B——**FFN 是参数大头**。
13. 系统估算三式：**权重 = 2 B × N**（141 GB）、**算力 ≈ 2 N = 141 GFLOPs/token**、**KV = 320 KB/token**。2× H200（1,978 TFLOP/s、9.6 TB/s、282 GB）上，80K token：单请求 prefill 约 9.95 s、需 167 GB VRAM；64 请求要 637 s 与 1,779 GB VRAM——"如何支持更长序列"是本系列的驱动问题。
14. MoE 用 Router 从 8 个小专家 FFN 中选 top-2：**内存随总参数、算力随激活参数**；Mixtral 8x7B 约 1/5 FLOPs 匹配 Llama 2 70B；DeepSeek-V3（671B 总参、37B 激活）约 1/11 FLOPs 比肩 Llama 3.1 405B，但内存 1.7×。
15. 滑动窗口限制 KV 为 w 个 token：Mistral 7B 全层局部（w=4,096）、Gemma 2 为 1 局部:1 全局、Gemma 3 为 5 局部（w=1,024）:1 全局；**128K 上下文下 KV 约省 6 倍**。
16. **MLA 每 token 只存一个压缩 latent c**，K/V 用时重建（升维投影折进 query/output 权重，decode 多算少存）；**DeepSeek-V2 vs DeepSeek 67B：KV 减 93%、吞吐 5.8×**。
17. 线性注意力 / **Gated DeltaNet** 用固定大小 d_k × d_v 状态 + 衰减门 α / 写入门 β 替代增长的 KV cache；Qwen3-Next 48 层 = 36 GDN + 12 Attention（3:1 配方，同 Kimi Linear、Qwen3.5），3/4 层状态大小与上下文长度无关。
18. 状态空间模型（Mamba）：h ← Ā h + B̄ x，选择性状态、固定大小、硬件感知并行 scan（Mamba-2 化为 matmul）；无增长 KV cache，**生成吞吐最高可达 Transformer 的 5×**。
19. 稀疏注意力（DeepSeek-V3.2）：轻量 indexer（少头、FP8、128 维 key）对历史 token 打分，主注意力只取 **top 2,048**——算力封顶但**全部 KV 仍存储**。
20. 循环 Transformer 把同一 block 循环 K 次：深度增加算力/延迟但不增参数（K 循环 = K× FLOPs）；扩散 LM（LLaDA 8B、Dream 7B）每步并行填入多个 token，减少步数会损失质量。
