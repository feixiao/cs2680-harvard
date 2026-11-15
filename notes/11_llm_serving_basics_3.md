# 第 11 讲：LLM 服务基础 III(调度、分页与并行)

> **LLM Serving Basics III: Scheduling, Paging and Parallelism** · Harvard CS2680 · 讲师 Juncheng Yang
> 原始幻灯片:[11_llm_serving_basics_3.pdf](../11_llm_serving_basics_3.pdf)

## 本讲概览

本讲继续 LLM serving 系列，覆盖三大主题：推理性能评测（指标与四个评测陷阱）、批处理/调度/内存管理/前缀缓存（连续批处理、Orca 选择性批处理、chunked prefill、PD 分离、PagedAttention、前缀缓存）、以及数据/张量/流水线/专家/上下文五种并行与其通信代价。下讲进入投机解码（speculative decoding）。

## LLM 推理指标与评测

### 为什么 LLM serving 值得专讲

- Web 请求 5–50 ms 跑完；LLM 请求分 prefill + decode 两阶段、**每生成一个 token 一次批式 forward pass**：prefill 计算受限 (compute-bound)、decode 内存带宽受限 (memory-bound)。
- Token = 柔软增长的状态 (soft, growing state)；KV cache 在别的 GPU 上路由时须重建。
- 跨请求：输出长度未知（stop token 前未知）；token 是工作单元（admission、scheduling、autoscaling、SLO 全按 token 计，成本差 **10⁴–10⁶×**）；瓶颈不断迁移（batch size / context 长度 / prefill-decode 占比）；agent 与 reasoning 拉大所有差距（turn 2 约 90% 前缀复用，KV cache 变成存储问题）。

### 指标与四个陷阱

- 两阶段对比：

| | Prefill | Decode |
|---|---|---|
| Granularity | 全部 S 个 prompt token 一次 | 1 token / step |
| Dominant op | 矩阵–矩阵 GEMM | GEMV / thin GEMM |
| Bottleneck | 计算 (FLOPs) | 内存带宽 |
| Latency driver | TTFT | TPOT × 输出长度 |

- **TTFT**：排队 + prefill 到第一个 token；**TBT** 是单个 token 间隔，P99 能捕捉停顿 (stall)；**TPOT** = (E2E − TTFT) ÷ (n−1)，是平均，少数长停顿几乎不影响它；**E2E** = TTFT + TPOT × (n−1)。**Goodput**：只统计满足 TTFT/TPOT SLO 的吞吐。
- GPU 吞吐与用户吞吐须分开：batch 1→64 使 GPU 吞吐升约 20×（6K TPS/GPU），但单用户 100 TPS/user 反而慢约 3×。
- 陷阱 1 短瞬态运行：早期请求付 kernel 编译/冷缓存/时钟爬坡，晚期在收缩 batch 里跑 → 只报**稳态 (steady state)**。
- 陷阱 2 误导性平均：两条 5 s、100 token 的流，TPOT 都是 50 ms，但 Max TBT 是 50 ms 还是 4,500 ms 差天共地 → 展示完整分布 + TTFT/TPOT/吞吐。
- 陷阱 3 不真实负载：benchmark 的随机 gibberish、无突发的到达、无共享 prompt 都失真（真实突发推高 P99 TTFT，320K prompt 卡住整个 batch）→ 回放真实 trace。
- 陷阱 4 不公平比较：8 GPU 对 4 GPU 就能解释 2× 的"胜出"；同硬件调优后基线 1.6×、我们 1.8× → **真实算法增益 1.8÷1.6 ≈ 1.1×，70% 来自实现、30% 来自算法**；修复：同硬件调优每个基线并逐项关闭技术。

## 批处理、调度、分页与缓存

### 批处理：连续批处理与选择性批处理

- 三种 batching：static（整批跑到完成）、dynamic、**连续批处理 (continuous batching)**：每生成一个 token 即重新组批，完成的退出、新的加入（iteration-level scheduling）——vLLM/SGLang 的调度基石。
- 普通 pad 式批处理在请求输入长度与 KV 历史不同时失效：pad 到 128 token，decode 请求（KV 500 / 1,000）各浪费 127 个填充 token。
- **Orca 的观察（Yu et al., OSDI 2022）：并非每个 Transformer 算子需要同一种批处理策略**——linear 层所有 token 共享同一个 W，一次 batched GEMM 服务所有请求；attention 每请求读自己的 KV cache 且长度不齐 (ragged)，须按请求拆分。
- **选择性批处理 (selective batching)**：token 展平 → QKV 投影/MLP 一个 GEMM → LayerNorm/残差按请求 → attention 按请求（各自 KV cache）→ 输出投影一个 GEMM。

### 请求调度：FCFS、chunked prefill、PD 分离

- **FCFS**（vLLM、SGLang 默认）：KV 空间释放即按到达顺序接纳；简单、无饥饿，但队首长请求阻塞其后所有请求（head-of-line blocking）。
- **Prefill-first（SGLang）保 TTFT**（新 prompt 立即开始、每步补满 batch，但每次到达停顿所有 decode）；**decode-first（FasterTransformer）保 TPOT**（稳定 token 流，但 TTFT 等 batch 排空、吞吐随请求结束收缩）。框架：Agrawal et al., Sarathi-Serve, OSDI 2024。
- **Chunked prefill**：用每步 token 预算 (per-step token budget) 界定迭代延迟，把 prompt 切块混入 decode batch。例：2,048-token prefill 不切块时 decode 每 token 等 92 ms；切 4×512 后每步 = 512 prompt token + 4 decode，token 间隔降到约 23 ms。代价：第 k 个 chunk 重读 (k−1)×512 token 的 KV，总 FLOPs 相同但摊到更多步。SGLang 用 `--prefill-decode-interval N` 保护 decode；vLLM 用 `enable_chunked_prefill`。
- **PD 分离 (disaggregation)**：prefill 与 decode 分池（不同 GPU），KV 经 NVLink/RDMA **逐层流式传输**、藏进计算后。DistServe (OSDI 2024)、Splitwise (ISCA 2024)、Mooncake (FAST 2025)。

| | Prefill 池 | Decode 池 |
|---|---|---|
| Target | TTFT SLO | TPOT SLO |
| Batch | 一个或少数 prompt | 100s of sequences |
| Parallelism | 更多 TP（低延迟） | 更多副本 |
| Best GPU | 高 FLOPS | 高 HBM 带宽 |

  - 代价：每请求一次 KV 传输、要调 P:D 比例、两套以上实例；短 prompt / 小规模集群不值得。
  - 传输量例（Llama-3.1-70B GQA FP16：320 KB/token，65,536 token = 20 GB）：

| Link | Bandwidth | Time |
|---|---|---|
| NVLink, H100 | 450 GB/s | 44 ms |
| NVLink, A100 | 300 GB/s | 67 ms |
| InfiniBand 400 Gb/s | 50 GB/s | 400 ms |
| PCIe 4.0 x16 | 32 GB/s | 625 ms |
| Ethernet 100 Gb/s | 12.5 GB/s | 1.6 s |

    该 prompt 的 prefill ≈ 11.5 s，即便 400 ms 也只占不到 4%。
- **SJF**：最小化平均等待，但作业大小 = 输出长度，decode 结束前未知 → 进阶做法：学排名 (ranking loss，OPT-125M ranker，配饥饿防护 promotion)，Fu et al., NeurIPS 2024；**FastServe**（NSDI 2026）：skip-join 多层队列 + token 级抢占（新作业按 prompt 长度进最高可覆盖队列，用尽 quantum 降级，等太久升级），无需作业大小即可近似 **SRPT**。
- 检查理解：P99 TBT 尖刺 → chunked prefill 或 PD 分离；PD 分离对短 prompt / 小集群不值得；SJF 的 size 可用**未缓存 prefill token 数**替代。

### 内存管理：PagedAttention

- Orca 式连续分配器三种浪费（Llama-3.1-70B 于 2×H200、282 GB：权重 141 GB/50%，KV ~130 GB/45%，**只有 20–38% 的 KV 内存持有真实 token**）：① 输出长度未知 → 每请求按 128K-token 上限预留（约 40 GB）；② 内部碎片（预留了尚未生成的槽位）；③ 外部碎片（EOS 提前，尾槽空闲）。
- 连续缓存无法共享：并行采样 (n=3) 把 prompt 存 3 遍；beam search 每次 fork 复制整个 slab；共享系统提示每请求重复。
- **PagedAttention（Kwon et al., SOSP 2023）像 OS 分页管理 KV**：一层间接 (indirection) 消除连续内存需求——token 入逻辑块（16 token/块）→ 块表 (block table) 映射到非连续物理块；支持**按需分页 (demand paging)**、**共享页/写时复制 (copy-on-write，引用计数)**、**换出到磁盘/ CPU 内存 (swap)**。

### 前缀缓存 (prefix cache)

- 复用服务器已算过的前缀 KV：共享前缀来自系统提示、多轮聊天（每轮重发历史）、agent（每步重发 tools + trace）。3 个 1,000+50 token 请求：无缓存 prefill 3,150 token → 有缓存 **1,150**。
- **只能精确匹配 (exact match)**：一个 token 的 KV 依赖之前所有 token（两个仅第 3 token 不同的 prompt 至多共享 2 token，16-token 块哈希下为零）。
- **vLLM 块哈希**：每块哈希折入父哈希（h₂ 覆盖整个前缀）；查找遇第一个 miss 停止；命中只增引用计数、不复制；无引用块按 LRU 驱逐；未填满的末块永不共享。
- **SGLang RadixAttention（Zheng et al., NeurIPS 2024）**：一棵 radix tree 存所有已缓存请求的 KV——到达时匹配最长前缀、只 prefill 剩余部分；完成后新分支入树、KV 留在 GPU；LRU 逐出无在跑请求的叶子；分支共享父节点 KV。token 粒度匹配（可复用半块）。
- 张力：最大化缓存命中（先服务缓存最热的客户端）与公平调度冲突。

## 并行：一个模型，多张 GPU

### 为什么单卡不够

- 70B bf16 权重 140 GB vs 单张 H200 141 GB，KV 还要与权重抢同一 HBM → 切到 4 卡、每卡 35 GB。
- decode 速度受单卡带宽封顶：**t ≥ 2N ÷ BW_HBM**；70B bf16 于 H200：140 GB ÷ 4.8 TB/s ≈ **29 ms/token**。

### 集合通信原语（图示：4 GPU 矩阵 Before/After 分布）

- send/recv（PP stage 跳板、SP 环）；broadcast（批输入分发到 TP rank）；all-gather（TP 输出、SP K/V，代价 0.75M）；reduce-scatter（0.75M，TP+SP）；**all-reduce** = reduce-scatter + all-gather（1.5M，TP row-parallel 层后）；**all-to-all**（EP 的 dispatch/combine，0.75M）。

### 五种并行

- **数据并行 (DP)**：每卡持有完整模型，router 切分流，每副本自带调度器与 KV；通信 0、吞吐 ≈ G×，但最大模型尺寸不变。
- **张量并行 (TP)**：层内矩阵切分，每 block 后 all-reduce，须 NVLink 级带宽（限节点内）。
  - 列并行：W 按列切，每卡持完整 X、无层内通信；行并行：W 按行切、每卡持部分和，一次 all-reduce（G=4 每 GPU 发 3bh）。来源：Megatron-LM（Shoeybi et al., 2019）。
  - **Megatron TP block**：列并行（QKV / up+gate）→ 本地计算（attention / 激活）→ 行并行（输出 / down 投影）→ 每 block 只一次 all-reduce。70B 于 G=4 → 每卡 35 GB；每 GPU 每层通信 2×1.5×2bh 字节。
- **流水线并行 (PP)**：层切连续 stage（80 层 → 4 stage），micro-batch 保持各 stage 忙碌；每跳板一次 2bh send；**bubble = (G−1) ÷ (m+G−1)**（G=4：m=4 → 43%，m=16 → 16%）；容忍慢链路、**可跨节点**。
- **专家并行 (EP)**：MoE experts 分布多卡（8 experts / 4 GPU），all-to-all 三步：dispatch → 本地计算 → combine；每卡负载 ≈ k·b÷G、每层通信 2×0.75×2kbh 字节；路由不均使部分卡空闲。
- **上下文并行 (SP)**：长 prompt 切 token（128K ÷ 4 = 32K/卡），ring attention 传 K/V 块（每层 G−1 次，与计算重叠，每 query 仍见全部 key）；**只帮 prefill，对 decode 无益**。

### 通信代价对比与部署规则

| Strategy | Collective | How often | Bytes / token / GPU |
|---|---|---|---|
| Data | none | never | 0 |
| Tensor (G = 4) | all-reduce | 2 per layer | 3.9 MB |
| Pipeline (G = 4) | send / recv | 1 per stage hop | 16 KB |
| Expert (G = 4, top-2) | all-to-all | 2 per MoE layer | ≈ 3.9 MB |

- **TP 与 EP 每 token 移动的字节是 PP 的 240×**（70B 形状、h=8,192、80 层、bf16）。
- 链路带宽（GB/s 单向）：NVLink 4 = 450、PCIe Gen5 x16 = 64、InfiniBand NDR = 50；一次 TP 传输 NVLink ≈ 9 µs vs InfiniBand ≈ 78 µs → 经验法则：**TP 节点内、PP 跨节点**。
- 70B 于 4×H200 节点先 TP=4（或按 context 用 DP2+TP2）；当 KV 头数 < rank 数时 TP 会复制 KV，长 context 下 DP attention + EP 可反超，短 context 下 all-to-all 开销占主导。
- 一句话：DP 扩吞吐；PP/SP 加容量；TP 降每 token 延迟；EP 服务 MoE。

## 核心要点

- LLM serving：单请求两阶段两瓶颈（prefill 计算受限、decode 带宽受限），token 是柔软增长状态，跨请求成本差 10⁴–10⁶×，效率直接决定成本与速度。
- 指标：TTFT / TBT（P99 抓停顿）/ TPOT（平均，掩盖停顿）/ E2E = TTFT + TPOT×(n−1) / goodput；GPU 吞吐与用户吞吐须分开（20× batch 使单用户慢约 3×）。
- 评测四陷阱：只报稳态；报分布而非平均（50 ms TPOT 可藏 4.5 s 冻结）；回放真实 trace；同硬件调优基线、逐项关技术（真实算法增益仅 1.1×）。
- 连续批处理：每 token 重新组批；Orca 选择性批处理——线性层共享 W 一个 GEMM、attention 按请求拆分。
- 调度权衡：prefill-first 保 TTFT 伤 TPOT，decode-first 反之；chunked prefill 用每步 token 预算打破困境（92 ms → ~23 ms，代价 KV 重读）。
- PD 分离：两池各按 SLO 独立配置（TTFT 池少 prompt、多 TP、高 FLOPS 卡；TPOT 池百级序列、多副本、高 HBM 卡）；20 GB KV 传输 44 ms（NVLink H100）~1.6 s（Ethernet），一般 < 4% 的 11.5 s prefill。
- SJF 需预测输出长度（learning to rank）；FastServe 用 skip-join 多层队列 + token 级抢占在不知作业大小下近似 SRPT。
- PagedAttention 借鉴 OS 分页：16-token 块 + 块表的一层间接，把连续分配器 20–38% 的 KV 有效率问题变成引用计数共享 / 写时复制 / 换出。
- 前缀缓存只能精确匹配；vLLM 块哈希（父哈希折入、首 miss 停止、LRU 逐出、半块不共享）vs SGLang radix tree（token 粒度）；共享系统提示使 3 请求 prefill 从 3,150 降到 1,150 token。
- 单卡装不下 70B（140 GB 权重 + KV 抢 HBM）；decode 下界 t ≥ 2N÷BW_HBM ≈ 29 ms/token（H200）。
- Megatron TP block = 列并行 + 行并行，每 block 一次 all-reduce（G=4 每 GPU 3bh），每卡权重 2N÷G。
- PP 气泡 = (G−1)÷(m+G−1)（m=16 → 16%）可跨节点；EP 付 all-to-all 与负载不均；上下文并行 ring attention 只帮 prefill。
- 每 token 通信量：TP/EP ≈ 3.9 MB vs PP 16 KB（240×）→ 规则：TP 放 NVLink 节点内、PP 跨节点。
