# 第 9 讲:LLM 服务基础 I(认识 LLM)

> **LLM Serving Basics I: Introduction to LLM** · Harvard CS2680 · 讲师 Juncheng Yang
> 原始幻灯片:[9_llm_serving_basics_1.pdf](../9_llm_serving_basics_1.pdf)

## 本讲概览

本讲是 LLM Serving 系列的第一讲,目标是先"了解 LLM 本身"。主线一是一个请求的六阶段生命周期(Tokenize → Schedule → Prefill → Decode → Detokenize → Stream),点出 Prefill 是 compute-bound(算力受限,对应 time to first token)、Decode 是 bandwidth-bound(带宽受限,对应 tokens/second)这一根本区别。主线二是"Peeking into the model":以 Llama 3 70B 为例讲清 Transformer 结构、注意力的 O(n²) 代价、KV cache 大小,以及权重/算力/KV 三个量如何决定 prefill 时间、decode 时间与显存。最后简述 MoE 与一组高级架构变体如何压缩 KV cache。

## 课程安排(Logistics)

- Assignment 3 截止周二 11:59pm;**leaderboard 提交没有补交日(NO LATE DAY)**。
- 项目海报展示备选时段 12 月 2 日 1–3pm,仅限无法参加 12 月 7 日的人报名。

## LLM 请求的生命周期

六个阶段:Tokenize → Schedule → Prefill → Decode(每个输出 token 重复)→ Detokenize → Stream。

- **Tokenize**:
  - 文本按 **byte-level BPE**(从 256 字节出发反复合并最高频相邻对,无 unknown token)切成 token,约 3–4 字符/token
  - "Serving is hard" 是 4 个 token 而非 3 个单词
  - 不同模型 tokenizer 不同;token 数直接驱动成本与内存
- **Schedule**:
  - 请求独立到达、GPU 想要批
  - **连续批处理(continuous batching)** 让请求每步随时加入/离开,不必等满批
  - **准入受 KV cache 内存上限约束**(cache full → 抢占或排队)

| step t | step t+1 | step t+2 |
|---|---|---|
| R1 | R1 | R1 |
| R2 | free | R5 |
| R3 | R3 | R3 |
| free | R4 | R4 |

- **Prefill**:
  - 整个 prompt 一次前向传播、所有 token 并行 attention
  - **compute-bound → time to first token**
  - 生成 KV cache 并输出第 1 个 token
- **Decode**:每 token 一次前向传播,KV 每步增长一格,**bandwidth-bound → tokens/second,所以要批处理**。采样从 logits 选 token:
  - `temperature = 0` 恒取 top token(>1 更发散)
  - `top_k = 50` 取前 k 个
  - `top_p = 0.9` 取累计概率达 p 的最少集合
  - 同模型同 prompt,设置改变答案与运行时长
- **Detokenize / Stream**:token ID 即产即转文本,不完整字符缓冲;stop token、长度上限或断开连接结束流并释放 KV cache。

## Transformer 架构(Peeking into the Model)

符号约定,以 Llama 3 70B 为例(Meta, The Llama 3 Herd of Models, 2024):

| 符号 | 含义 | Llama 3 70B | 符号 | 含义 | Llama 3 70B |
|---|---|---|---|---|---|
| d | 模型宽度 | 8,192 | n | 序列 token 数 | e.g. 20,000 |
| L | 层数 | 80 | B | 并发请求数 | e.g. 16 |
| H | query 头数 | 64 | N | 参数量 | 70.6B |
| H_kv | KV 头数 | 8 | W | 权重(BF16) | 141 GB |
| d_k | 每头维度 d ÷ H | 128 | KV | 每 token KV 字节 | 320 KB |
| d_ff | FFN 隐层宽度 | 28,672 | KV 公式 | 2 × L × H_kv × d_k × 2 B | — |
| V | 词表大小 | 128,256 | Kᵀ | K 转置 | — |

- **结构**:
  - token IDs → Embedding(8,192 维向量)→ **80 个相同 Transformer block** → LM head(对 128,256 个词表 token 各出一个分数)→ Softmax
  - 每个 block:`h = x + Attn(RMSNorm(x))`,`y = h + FFN(RMSNorm(h))`
  - RMSNorm 按均方根缩放(每维一个学习增益 g),pre-norm + 残差流(residual stream)让 80 层深堆叠稳定训练
- **Self-attention**:
  - 每个 token 产生 Q(找什么)、K(提供什么)、V(传递什么),`Q = XW_Q`、`K = XW_K`、`V = XW_V`
  - 打分 `S = QKᵀ/√d_k`,加因果掩码 M(对角线以上 −∞ 隐藏未来 token)后 softmax(每行和为 1)再乘 V
  - 除以 √d_k 是因为 q·k 随 d_k 增长,缩放防止 softmax 饱和
- **O(n²) 代价**:每层 FLOPs ≈ 4 n² d
  - 若显式存 S 需 8,192² × 64 × 80 × 2 B ≈ **690 GB**,不可行
  - **FlashAttention 分块(tile by tile)计算 softmax,从不存储 S**
- **多头(MHA)**:
  - Q/K/V 拆成 64 个头、每头 128 维(64 × 128 = 8,192)独立做带掩码注意力,concat 后乘 W_O 混合
  - 与单个宽头 FLOPs 相同——拆分改变学到什么(各头关注前一个 token、第一个 token、邻近 token 或整个上下文),而非成本
- **共享 KV 头缩小 KV cache**:

| 方案 | query 头 | KV 头 | KV cache |
|---|---|---|---|
| MHA | 8 | 8 | 1× |
| Grouped-query(GQA) | 8 | 2 | ¼× |
| Multi-query(MQA) | 8 | 1 | ⅛× |

  每 token KV = 2 × L × H_kv × d_k × 2 B。Llama 3 70B 的 64 个 query 头共享 8 个 KV 头,KV 比 MHA 小 8 倍:**2 × 80 × 8 × 128 × 2 B = 320 KB/token**(MHA 约 2.5 MB/token)。

## Llama 3 70B:参数分布与系统估算

| 组件 | 公式 | 参数量 |
|---|---|---|
| Attention / 层 | 2d·H·d_k + 2d·H_kv·d_k | 151M |
| FFN / 层 | 3·d·d_ff | 705M |
| 所有层 | 80 × 856M | 68.5B |
| Embed + LM head | 2·V·d | 2.1B |
| 总计 | — | 70.6B |

FFN 占每层参数约 82%,是参数大头(MoE 只替换 FFN 正是因此有效)。三个系统估算量:

- **权重 = 2 B × N = 141 GB**(装得下吗)
- **算力 ≈ 2N = 141 GFLOPs/token**
- **KV cache = 320 KB/token**

在 2× H200(1,978 TFLOP/s、9.6 TB/s、282 GB)上,n = 80,000:

| 量 | 公式 | 1 请求 | 64 请求 |
|---|---|---|---|
| Prefill 时间 | B·(2N·n + 2L·d·n²) ÷ FLOP/s | 9.95 s | 637 s |
| 所需 VRAM | W + B·n·KV | 167 GB | 1,779 GB |

单请求 80K 上下文约 10 s prefill、167 GB 显存尚可容纳;64 请求就要 1,779 GB,远超 282 GB。

> **"如何支持更长序列/更多并发"是本系列的驱动问题**。

## MoE:内存随总参数,算力随激活参数

MoE block 保留 Attention,用 **Router + 一组小专家 FFN 替换单个大 FFN**(如 8 个专家,每 token 只跑 Router 选出的 top-2)。

| 模型 | 专家 | 总参数 | 每 token 激活 | 权重(BF16) | GFLOPs/token |
|---|---|---|---|---|---|
| Llama 2 70B | 全部(稠密) | 69B | 69B | 138 GB | 138 |
| Mixtral 8x7B | 2 of 8 | 46.7B | 12.9B | 93 GB | 26 |
| Llama 3.1 405B | 全部(稠密) | 405B | 405B | 810 GB | 810 |
| DeepSeek-V3 | 9 of 257 | 671B | 37B | 1,342 GB | 74 |

(GFLOPs ≈ 2 × 激活参数)同等质量、更少算力:

- Mixtral 约 **1/5 FLOPs** 匹配 Llama 2 70B
- DeepSeek-V3 约 **1/11 FLOPs** 比肩 Llama 3.1 405B,但需要 1.7× 内存

> **MoE 把权重内存(总参数)与计算量(激活参数)解耦**。

## 高级架构变体(Advanced — skim)

幻灯片以 "ADVANCED — skim, or read more on your own" 标记,覆盖滑动窗口、稀疏注意力、MLA、循环 Transformer、线性注意力、多 token 预测、状态空间模型、扩散 LM 等,共同主题是用额外计算换取更小的 KV cache 或更低的 O(n²) 代价。

- **滑动窗口(Sliding window)**:局部层只读最近 w 个 token,KV 上限 w
  - Mistral 7B 每层局部(w = 4,096)
  - Gemma 2 为 1 局部 : 1 全局交替
  - Gemma 3 为 5 局部(w = 1,024):1 全局——128K 上下文下 KV 比全全局少约 **6 倍**
- **MLA(Multi-Latent attention)**:每 token 只缓存一个压缩 latent c,需要时再展开重建 K/V(升维投影折进 query/output 权重,decode 多算少存)。DeepSeek-V2 对比 DeepSeek 67B:**KV 减 93%、生成吞吐 5.8×**。
- **线性注意力 / Gated DeltaNet**:用固定大小 d_k × d_v 矩阵状态替代增长的 KV cache,每步原地更新
  - Gated DeltaNet 加衰减门 α(忘记多少)与写入门 β(覆写力度)
  - Qwen3-Next 48 层 = 36 层 GDN + 12 层 Attention(3:1 配方,同 Kimi Linear、Qwen3.5):3/4 层状态大小与上下文长度无关
- **状态空间模型(Mamba)**:`h ← Āh + B̄x`,Ā、B̄ 依赖每个 token(选择性遗忘)
  - 每通道固定小状态,decode 内存不随 n 增长
  - 硬件感知并行 scan,Mamba-2 化为 matmul
  - 无增长 KV cache,报告生成吞吐最高可达 Transformer 的 **5×**
- **稀疏注意力(DeepSeek-V3.2)**:轻量 indexer(少数头、FP8、128 维 key)对每个历史 token 打分,主注意力只读 **top 2,048** 个 token——每 token 算力封顶,但**全部 KV 仍存储**(与滑动窗口/MLA 不同,只省算力不省存储)。
- **循环 Transformer(Looped)**:同一 block 循环 K 次,共享权重——加深度不增参数,K 循环 = K× FLOPs 且延迟随 K 增长(3.5B 模型随 K 增大推理能力更好)。
- **扩散 LM(Diffusion LMs)**:若干并行步骤填充被掩码的 token,每遍可填许多 token,但减少步数损失质量
  - LLaDA 8B 从 2.3T token 从头训练、与 Llama 3 8B 竞争力相当
  - Dream 7B 从 Qwen2.5 7B 权重出发,网络仍是 Transformer

## 下一讲(Next class)

> **图示** 结尾页仅预告下一讲(GPU 部分),无文字内容。

## 核心要点

- 请求六阶段:Tokenize → Schedule → Prefill → Decode(每 token 重复)→ Detokenize → Stream。
- **Prefill = compute-bound → TTFT;Decode = bandwidth-bound → tokens/second**,所以 decode 要批处理。
- Byte-level BPE 分词:约 3–4 字符/token,token 数驱动成本与内存;tokenizer 因模型而异。
- 连续批处理每步进出,不等满批;准入由 KV cache 内存封顶,满了则抢占/排队。
- 采样参数 temperature / top-k / top-p 改变同一 prompt 的答案与运行时长。
- Llama 3 70B 关键量:d = 8,192、L = 80、H = 64、H_kv = 8、d_k = 128、d_ff = 28,672、V = 128,256、N = 70.6B、权重 141 GB(BF16)。
- Block = pre-norm + 残差:`y = h + FFN(RMSNorm(h))`,`h = x + Attn(RMSNorm(x))`。
- 注意力 `O = softmax(QKᵀ/√d_k + M)V`:因果掩码防看未来,√d_k 防 softmax 饱和;每层 ≈ 4 n² d FLOPs,O(n²)。
- 存 S 需约 690 GB,FlashAttention 分块计算、从不存 S。
- MHA 64 × 128 头:FLOPs 与单宽头相同,各头学不同模式;GQA 共享 KV 头使 KV 缩小 H/H_kv 倍(Llama 3 70B = 320 KB/token vs MHA 2.5 MB)。
- FFN 占每层参数约 82%(705M/856M)——MoE 替换 FFN 即可改算力/内存特征。
- 三估算式:权重 2N = 141 GB、算力 ≈ 2N = 141 GFLOPs/token、KV 320 KB/token;2× H200 上 80K 序列:1 请求 9.95 s / 167 GB,64 请求 637 s / 1,779 GB(超 282 GB)→ 长序列支持是驱动问题。
- MoE:内存随总参数、算力随激活参数;Mixtral 1/5 FLOPs、DeepSeek-V3 1/11 FLOPs,代价是更多权重内存。
- 高级变体(滑动窗口、MLA、线性注意力/DeltaNet、Mamba、稀疏注意力、循环、扩散 LM)核心是压缩 KV cache 或 O(n²) 注意力代价,用额外计算换内存。
