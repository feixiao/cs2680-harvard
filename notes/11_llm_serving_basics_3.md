# 第11讲：LLM 服务基础 III —— 调度、分页与并行

> 原始标题：*LLM Serving Basics III: Scheduling, Paging and Parallelism*
> 课程：Harvard CS2680 *Modern AI Systems: Agents and System Optimizations*（MaDSys），讲师 Juncheng Yang

## 本讲概览

本讲继续 LLM 推理服务（LLM serving）系列，覆盖三大主题：**推理性能评测（evaluation）**、**批处理/调度/内存管理/前缀缓存**（batching, scheduling, paging and caching）和**并行（parallelism）**。开篇先解释为什么值得用好几节课讲 LLM serving：计算量巨大、每个 token 都要付费、GPU 昂贵，效率直接决定成本与速度。随后系统梳理了评测指标（TTFT、TBT、TPOT、goodput）与四个常见评测陷阱，接着深入 Orca 式连续批处理与选择性批处理、FCFS/SJF 请求调度、chunked prefill、PD 分离（disaggregation）、PagedAttention 内存分页、前缀缓存（vLLM block hashing 与 SGLang RadixAttention），最后讲透数据/张量/流水线/专家/上下文五种并行、集合通信原语及其通信代价对比。下一讲将进入投机解码（speculative decoding）。

---

## 一、导言：为什么 LLM 服务值得用好几节课

### 1. 本课计划（Plan for today）

- LLM serving 性能评测
- 调度与资源管理
- 并行

### 2. 课程事务（Logistics）

- **Assignment 4 下周二午夜截止**，内容：阅读材料、调节引擎 flag（tune engine flags）、投机解码（speculative decoding）、agent-engine 协同设计（co-design）。
- 撰写报告（write-up）和视频要求：测量/观察 + 推理，回答四问——**你观察到了什么、做了什么、改变了什么以及为什么、权衡（trade-off）在哪里**。
- 测量时**要使用多于一个计数器（counter）和指标（metric）**。
- 项目提案（project proposal）上周三已截止。

### 3. 为什么要在 LLM serving 上花好几节课？

| 巨大算力（Huge compute） | 每个 token 都付费（Paid on every token） | GPU 昂贵（GPUs are costly） |
|---|---|---|
| LLM 需要 GPU 和其他加速器 | 每个用户请求都会重新跑一遍模型 | 服务效率决定了成本与速度 |

### 4. LLM serving 与以往计算（web 服务、批处理作业）不同

- **Web 请求**：在约 5–50 ms 内跑完（run to completion）。
- **LLM 请求**：prefill / decode 两阶段，**每生成一个 token 就要一次批式 forward pass**（one batched forward pass per token）。

**在单个请求内部：**

- Web 请求：一次短小的、无状态的调用。LLM 请求：**两个阶段、两个瓶颈**——Prefill：计算受限（compute-bound）；Decode：内存带宽受限（memory-bound）。
- 一次 forward pass 需要**多 GPU、多服务器的计算与通信**（GPU 1/2/3/4 协同）。
- 一次请求的 KV cache 存放在 GPU 1 上；如果路由（Router）把后续请求 checkpoint 到 GPU 2，**必须重建状态（rebuild state）**。
- **Token = 柔软的、不断增长的状态（Soft, growing state）**。

**跨许多请求：**

- **输出长度未知（Unknown output length）**：prompt 已知，output 在 stop token 出现前未知。
- **Token 是工作单元（Tokens as the unit of work）**：准入（admission）、调度（scheduling）、路由（routing）、自动扩缩（autoscaling）、限流（rate limits）、价格（prices）、SLO 全部按 token 计数；成本差距可达 **10⁴–10⁶×**。
- **瓶颈不断迁移（Shifting bottlenecks）**：batch size 有大有小、context length 有长有短、阶段组成在 prefill 与 decode 间变化。
- **Agent 与推理（reasoning）拉大所有差距**：Turn 1 全为新 prompt；Turn 2 约 **90% 前缀复用**（≈90% prefix reuse）；Turn 3 复用前缀 + 新 token——**KV cache 因此变成一个存储问题（storage problem）**。

---

## 二、LLM 推理指标与评测（LLM inference metrics and evaluation）

### 1. LLM 服务的两个阶段：prefill 与 decode

| | Prefill | Decode |
|---|---|---|
| 粒度（Granularity） | 一次性处理全部 S 个 prompt token | 每步 1 个 token |
| 主导算子（Dominant op） | 矩阵–矩阵 GEMM | GEMV / 瘦 GEMM（thin GEMM） |
| 瓶颈（Bottleneck） | 计算（FLOPs） | 内存带宽 |
| 延迟驱动（Latency driver） | TTFT | TPOT × 输出长度 |

**对服务的含义：** 一个请求同时混合了一个计算受限阶段和一个内存带宽受限阶段。

### 2. 单个请求时间线上的服务指标

时间线：queue（排队）→ prefill → decode，逐步产出 t1…t6。

- **TTFT**（time to first token）：排队 + prefill，到第一个 token。
- **TBT**（time between tokens）：decode 阶段每 token 一个间隔（t1→t2、t2→t3 …）。**TBT 是单个间隔，按 token 测量，所以其 P99 能捕捉到停顿（stall）**。
- **TPOT** = 5 个 TBT 间隔（t2…t6）的**平均**，即 (E2E − TTFT) ÷ (n − 1)。**少数长停顿几乎不影响它**。
- **E2E** = TTFT + TPOT × (n − 1)：从到达（arrival）到最后一个 token（t6）。
- **Throughput（吞吐）**：全部请求的每 GPU token/s，靠大 batch 最大化。
- **Goodput（有效吞吐）**：只统计满足其 TTFT 与 TPOT SLO 的请求的吞吐。

图示：单请求时间线图，横轴为时间，依次标出排队、prefill，然后 t1–t6 六个 token 时刻；TBT 是相邻 token 的间隔，TPOT 取这些间隔的平均。

**GPU 吞吐 vs 用户吞吐（GPU throughput vs user throughput）：**

图示：双轴图，横轴为 batch size 从 1 → 64。GPU 吞吐（TPS per GPU）随 batch 增大上升到 **6K TPS/GPU**（约 20 倍）；而用户感知的交互性（Interactivity, TPS per user）= 1 ÷ TPOT，从 batch 1 时的 **100 TPS/user** 下降——batch 增大 20 倍 GPU 吞吐，但**每个用户反而慢约 3 倍**。这正是"GPU 吞吐"与"用户吞吐"两个指标必须分开报告的原因。

### 3. 陷阱 1：短而瞬态的运行（Short, transient runs）

- 一次运行（one run）中吞吐为 K tokens/s。例：一次性发出 500 个请求。
- **早到的请求**要付出 kernel 编译、延迟加载（lazy loading）、GPU 频率爬升（GPU clock ramping）、冷前缀缓存（cold prefix caches）的代价；
- **晚到的请求**在收缩（shrinking）的 batch 里运行。整次运行的平均值把两者混在一起。

图示：单次运行的吞吐曲线随时间（秒）从 0 爬升到约 6K、中段约 5.0K 后回落，末端接近 0；曲线标注出 warmup（预热）、稳态（steady state，"Measure here"）、drain（排空）三段。

**应该做：** 只报告**稳态（steady state）**性能（剔除 warmup 与 drain 段）。

### 4. 陷阱 2：报告误导性或不透明的指标（Reporting misleading or opaque metrics）

- 请求在 prompt 长度、输出长度、延迟敏感性上各不相同，**一个平均值会掩盖用户真实体验**。
- 例子：两个响应，各 100 个 token，都在 5 s 内流式输出完毕：
  - **Smooth（平滑）**：Mean TPOT 50 ms，Max TBT 50 ms。
  - **Stalled（停顿）**：Mean TPOT 50 ms，Max TBT **4,500 ms**（中间 4.5 s 没有新 token）。
- **同样是 50 ms 的平均 TPOT，一个用户却在盯着冻结的流等了 4.5 s。**

**应该做：** (1) 展示完整分布（full distribution）；(2) 同时报告 TTFT、TPOT 和吞吐。

### 5. 陷阱 3：不真实的负载（Unrealistic workloads）

| Token 内容 | 长度分布 |
|---|---|
| Benchmark：`kq 7z ##vl 3x`（随机 gibberish） | Real：`Summarize this email` … 直到 **320K** token |
| （草稿 token 很少被接受） | 一个 320K 的 prompt 会卡住整个 batch |
| **突发（bursts）把 P99 TTFT 推得极高** | 共享 prompt 会跳过 prefill（前缀缓存命中） |

图示：请求到达曲线（突发到达）与前缀缓存命中率的示意对比。

**应该做：** 回放真实 trace（replay real traces），使用真实的长度和到达时间。

### 6. 陷阱 4：不公平的比较（Unfair comparison）

| 资源或调优不对等 | 基线没调优 | 未把算法本身分离出来 |
|---|---|---|
| 我们 8 GPU，基线 4 GPU：**双倍的 GPU 就能解释 2× 的"胜出"** | 只与 Default baseline（1.0×）比 | 调优后基线 1.6×，我们调优后 1.8× |
| | | **相对调优基线的真实增益：1.8 ÷ 1.6 ≈ 1.1×；速度提升的 70% 来自实现（implementation），只有 30% 来自算法（algorithm）** |

图示：条形图，Default baseline 1.0×、Tuned baseline 1.6×、Ours tuned 1.8×，并标注 speedup 中 implementation 与 algorithm 各占约 70% / 30%。

**修复：** 在同一硬件上调优每一个基线，然后逐一关闭（switch off）每项技术以测量其影响（impact）。

---

## 三、批处理、调度、分页与缓存（Batching, scheduling, paging and caching）

本节包含四部分：批处理（Batching）、请求调度（Request scheduling）、内存管理（Memory management）、前缀缓存（Prefix caching）。

### 1. 批处理：连续批处理与迭代级调度

| 静态批处理（Static batching） | 动态批处理（Dynamic batching） | 连续批处理（Continuous batching） |
|---|---|---|
| 客户端请求到达即发送；服务器等待凑成一个 batch；把序列拼在一起，**整个 batch 跑到完成** | 客户端到达即发送；**整个 batch 跑到完成** | **每生成一个 token（每个迭代 iteration）就等待并重新组 batch**：完成的请求离开、新请求加入 |

连续批处理（iteration-level scheduling，迭代级调度）让 GPU 不再有整批 idle 等待，是现代 LLM 服务（vLLM、SGLang 等）的调度基石。

图示：三个时间轴小图。Static：客户端发出请求后服务器等待凑批，期间 idle。Dynamic：整个 batch 一起跑完，先完成的序列也要干等。Continuous：每个 token 生成后重新组批，新请求随时进入（idle / wait / idle / new），GPU 持续满载。

### 2. 普通批处理在请求输入长度与 KV 历史不同时失效

例：把每个输入都 pad 到 128 token：

| 请求 | 阶段 | 本步 token 数 | KV cache 长度 |
|---|---|---|---|
| A | Prefill | 128 | 0 |
| B | Decode | 1 | 500 |
| C | Decode | 1 | 1,000 |

结果：A 有 128 个有效 token，B 要 pad 127 个、C 要 pad 127 个——大量算力浪费在填充上。

**Orca 的观察（Yu et al., OSDI 2022，Orca）：** 并非 Transformer 的每个算子都需要同一种批处理策略：

- **Linear 层**：所有 token 都乘以同一个 W，所以一次 batched GEMM 就能服务所有请求（共享 W，token 数 40 / 120 / 300 各不相同）。
- **Attention**：不能共享一个 GEMM——每个请求读**自己**的 KV cache，且长度参差不齐（ragged lengths），所以每个请求要各自跑自己的 attention。

图示：左侧"Linear layer: batched"展示 token A(×40)、B(×120)、C(×300) 与共享 W 相乘，输出 A(=40)、B(=120)、C(=300)；右侧"Attention: per request"展示每个请求用各自的 Query 读自己的 KV cache。

### 3. 选择性批处理（Selective batching）：所有线性层都批处理，只有 attention 按请求拆分

流水线（每请求 A/B/C 各有一条线）：

1. 所有请求的输入 token 按 token-major **展平（Flatten）**合并；
2. **MLP + QKV 投影**：一个 GEMM 对全部 token 批处理；
3. **LayerNorm + 残差**：按请求分别计算；
4. **Attention**：按请求逐个执行，每个读自己的 KV cache；
5. **输出投影（output projection）**：又一个 GEMM 对全部 token 批处理。

**为什么成立：** 线性层对每个 token 一视同仁，一个 GEMM 服务所有请求；只有 attention 需要各请求自己的 KV cache。（来源：Yu et al., OSDI 2022, Orca）

图示：三条请求流（A、B、C）在 MLP/QKV 投影和输出投影处合并为两个大 GEMM 块，在 attention 处拆成各自持有 KV cache 的独立计算块。

### 4. 请求调度：先到先服务（FCFS）

- **vLLM 和 SGLang 默认 FCFS**：当 KV cache 空间释放时，按到达顺序接纳等待中的请求。
- 优点：简单、无饥饿（starvation-free）。
- 缺点：**队首一个长请求会延迟它后面所有请求**（head-of-line blocking）。
- 关键问题：新请求的 prefill 与进行中的 decode 如何混合？
  - **立即 prefill**：batch 更大，但阻塞所有正在 decode 的请求；
  - **等到 decode 结束再做**：TPOT 受影响较小，但新请求排队时间长。

图示：时间轴上 decode（D）流被新请求的 prefill 打断——"Prefill：Decodes stall here（decode 在此停顿）"，之后 "New request waits（新请求等待）"。

### 5. Prefill-first 保护 TTFT；Decode-first 保护 TPOT

| Prefill-first（SGLang） | Decode-first（FasterTransformer） |
|---|---|
| **+ TTFT**：新 prompt 立即开始 | **+ TPOT**：稳定的 token 流 |
| **+ 吞吐**：每个 step 都会补满 batch | **− TTFT**：新 prompt 要等 batch 排空（drain） |
| **− TPOT**：每次到达都停顿所有 decode | **− 吞吐**：请求结束使 batch 收缩 |

图示：两条 prefill 时间轴。Prefill-first 时间线上 decode（D）之间反复插入 prefill 块；decode-first 时间线先连续 decode、再集中 prefill。

**打破该权衡的两种方式：** **chunked prefill**（把小的 prompt 块混进 decode batch）与 **disaggregation**（把 prefill 与 decode 放到不同 GPU 上）。框架引自 Agrawal et al., Sarathi-Serve, OSDI 2024。

### 6. Chunked prefill 旨在取得平衡

图示（方框宽度 = step 时间，D = 4 个在跑请求的纯 decode step）：

- **不切块**：D → Prefill（2,048 token）+ 4 个 decode · **92 ms** → D。在跑请求要等 **92 ms** 才拿到下一个 token。
- **切成 4 个 512-token 块（Chunk 1–4）**：每步 = 512 个 prompt token + 4 个 decode，token 间隔降到 **约 23 ms**。
- **每步 token 预算（per-step token budget）界定了迭代延迟**。
- 前提：混合 batch 的 kernel 效率要接近纯 prefill / 纯 decode kernel。
- **SGLang**：prefill 优先（用 `--prefill-decode-interval N` 保护 decode）；**vLLM**：decode 优先（配 chunked prefill，`enable_chunked_prefill`）。

**Chunked prefill 的代价：更多内存读取。**

图示（2,048-token prompt，chunk 512，4 次迭代）：Iter 1 计算 chunk 1；Iter 2 计算 chunk 2、从缓存读 chunk 1 的 KV；Iter 3 计算 chunk 3、读前 2 个块；Iter 4 计算 chunk 4、读前 3 个块。**第 k 个 chunk 要重读 (k − 1) × 512 个 token 的 KV**——总 prefill FLOPs 相同，只是摊到 4 个更短的 step 上；**chunk size 在 decode 延迟与 prefill 效率之间做权衡**。（Agrawal et al., Sarathi (2023) 与 Sarathi-Serve (OSDI 2024)）

### 7. PD 分离（Disaggregation）：把 prefill 与 decode 分开

**一个请求的路径：** 请求到达 **Prefill 池**（prefill pool，计算受限；为 TTFT 配置并行度）→ 跑完 prompt、发出 token 1 → **KV 传输**：prompt 的 KV 经 **NVLink 或 RDMA 逐层（layer by layer）发送** → **Decode 池**（decode pool，内存带宽受限；大批量；为 TPOT 配置）加载 KV 后以大批量 decode 发出 token 2…n。

参考工作：DistServe（Zhong et al., OSDI 2024）、Splitwise（Patel et al., ISCA 2024）、Mooncake（Qin et al., FAST 2025）。

**每个池各自独立配置，按各自 SLO 调优：**

| | Prefill 池 | Decode 池 |
|---|---|---|
| 目标 | TTFT SLO | TPOT SLO |
| Batch | 一个或少数几个 prompt | 上百条序列（100s of sequences） |
| 并行 | 更多 TP（低延迟） | 更多副本（replicas） |
| 最佳 GPU | 高 FLOPS | 高 HBM 带宽 |

**代价：** 每个请求一次 KV 传输、一个要调的 P:D（prefill:decode）比例、两个以上实例。

### 8. PD 分离需要在节点之间移动 KV cache

**KV 大小：Llama-3.1-70B（GQA），FP16**

- 2 (K, V) × 80 层 × 8 个 KV 头 × 128 维 × 2 字节 = **每 token 320 KB**
- × 65,536 token = **20 GB**

**移动 20 GB 所需时间：**

| 链路 | 带宽 | 时间 |
|---|---|---|
| NVLink, H100 | 450 GB/s | 44 ms |
| NVLink, A100 | 300 GB/s | 67 ms |
| InfiniBand 400 Gb/s | 50 GB/s | 400 ms |
| PCIe 4.0 x16 | 32 GB/s | 625 ms |
| Ethernet 100 Gb/s | 12.5 GB/s | 1.6 s |

- 该 prompt 的 prefill ≈ 2 × 70B × 65,536 ÷ (4 × 200 TFLOPS) ≈ **11.5 s**；即使 400 ms 的 InfiniBand 传输也只占 prefill 的 **不到 4%**。
- **逐层流式传输可掩盖大部分传输**：第 i 层的 KV 在发送时，第 i+1 层正在计算。

### 9. 从 FCFS 到 SJF：短请求不应排在长请求后面

**队头阻塞（head-of-line blocking）：** 一个满 batch 按到达顺序服务：

- GPU 上 R0（长答案，**1,000 个输出 token**）与 R1–R4（各 **20 token**）在同一个 batch；队列头在左侧，到达顺序 R0 → R4；**R1–R4 要等 R0 的全部 token 产出**。
- **FCFS**：按到达顺序服务，vLLM 与 SGLang 默认；一个长作业延迟后面所有请求。
- **SJF**：先服务最短作业；最小化平均等待时间，但**需要事先知道每个作业的大小**。
- 对 LLM 来说，作业大小取决于输出长度，而**输出长度在 decode 结束前未知**。

图示（进阶）：三个请求同时到达，GPU 每秒产出 1 个 token：FCFS 下按 R0(10 token)、R1(2)、R2 顺序，平均等待 6.7 s/token；SJF 重排后 R2(0 s)、R1(2)、R0(10)，平均仅 1.3 s/token，约 13 s 内完成。

**进阶内容（ADVANCED，可略读或自学）——排名而非回归（Rank instead of regress）：**

- 难点：输出长度在 decode 结束前未知，必须**预测**。
- 用**排序损失（ranking loss）**训练——只关心相对顺序，不关心精确数值。
- 一个 **OPT-125M ranker** 为每个 prompt 打排名分。
- **饥饿防护（starvation guard）**：等待过久的请求被提升（promoted）。
- 队列按预测排名排序；vLLM 每步从队列顶部取 batch。

来源：Fu et al., *Efficient LLM Scheduling by Learning to Rank*, NeurIPS 2024。

### 10. FastServe：token 级抢占 + skip-join 多层队列

图示（条形长度 = 每轮时间片/quantum）：

- **按 prompt 长度 skip-join**：新作业进入**其 quantum 能覆盖 prefill 时间的最高队列**——短 prompt（prefill ≤ q）进 Q1；prefill > 2q 的长 prompt 直接进 Q3（4q）。
- **降级（Demotion）**：用尽自己 quantum 的作业下移一层队列（Q1 → Q2 → Q3 → Q4）。
- **升级（Promotion）**：等待过久的作业被提升回上层，防止饥饿。
- **Q1 优先级最高，Q4（8q）最低。**

**为什么有效：** 长作业下沉、短作业先完成，从而在**不知道作业大小的情况下近似 SRPT**（shortest remaining processing time first，最短剩余处理时间优先）。

来源：Wu et al., FastServe, NSDI 2026（arXiv 2305.05920）。

### 11. 检查理解：请求调度（Check your understanding）

- **Q1. 每当长 prompt 到达，P99 TBT 就会尖刺。哪些技术能修复？**
  答：**Chunked prefill** 限制每步的 prompt token 数；**PD 分离**把 prefill 移出 decode 步骤。
- **Q2. 什么时候 PD 分离不值得部署？**
  答：**短 prompt 或小规模集群**：KV 传输、P:D 调优和额外实例的代价超过了它省下的停顿。
- **Q3. SJF 需要作业大小。对 agentic 工作负载还有别的办法绕开吗？**
  答：用**未被缓存的 prefill token 数**作为作业大小。

---

## 四、内存管理：PagedAttention

### 1. Orca 式连续分配器以三种方式浪费内存

例：**Llama-3.1-70B 跑在两块 H200 上，共 282 GB 内存**：权重（Weights）141 GB（50%）、KV cache 约 130 GB（45%）。在 Orca 式连续分配器中，**KV 内存里只有 20–38% 持有真实 token**。

三种浪费：

| 浪费方式 | 说明 |
|---|---|
| 未知输出长度（Unknown output length） | 迫使**每请求按 128K-token 上限预留 KV**。Request A：为其 128K-token 上限预留（每 token 320 KB，约 40 GB）——这些槽位之后要用，但在那之前一直空闲（idle） |
| 内部碎片（Internal fragmentation） | 持有尚未生成 token 的槽位（slots held for tokens not yet generated） |
| 外部碎片（External fragmentation） | 真实结尾之后的槽位；回复在到达其最大长度之前就命中 EOS |

（Request B 为对照：实际只用了很小一部分。）

来源：Kwon et al., SOSP 2023, Fig. 2–3；Meta Llama 3.1 70B 配置（2024）；NVIDIA H200 数据手册。

### 2. 连续缓存无法共享：n 个样本把同一个 prompt 存 n 遍

**并行采样（parallel sampling），n = 3，连续 slab：**

| 样本 | 内容 | 问题 |
|---|---|---|
| Sample 1 | Prompt KV 副本 1 + Output 1 | **并行采样**：对一个 prompt 的 n 个回复把 prompt 复制了 n 遍 |
| Sample 2 | Prompt KV 副本 2 + Output 2 | **Beam search**：各 beam 共享 prompt 和每步都在变化的前缀；一次分叉（fork）就要复制整个 slab |
| Sample 3 | Prompt KV 副本 3 + Output 3 | **共享系统提示（shared system prompt）**：每个用户请求重复同样的 instructions |

### 3. PagedAttention：像操作系统分页一样管理 KV cache

核心：**一层间接（one level of indirection）去除了对连续内存的需求。**

图示（请求 A："The cat sat on the mat and then it slept"）：

- **每 token 一个槽位**（类比 OS 的字节）；
- **逻辑块（logical blocks）**：每请求把 token 切成块（块存 16 个 token，图中画出 4 个：`The cat sat on` / `the mat and then` / `it slept` …）；
- **块表（block table）**：每行一个逻辑块，指向物理块编号（0→物理块 4、1→1、2→3…）；
- **GPU 上的物理 KV 块**非连续、按需分配：
  - **按需分页（Demand paging）**：上一个块填满时才分配新块；
  - **共享页、写时复制（Shared pages, copy-on-write）**：共享 prompt 块用引用计数（reference counts）；
  - **换出到磁盘（Swap to disk）**：把块换入/换出 CPU 内存。

来源：Kwon et al., *PagedAttention and vLLM*, SOSP 2023, Fig. 6。

---

## 五、前缀缓存（Prefix cache）

### 1. 前缀缓存：复用服务器已经计算过的前缀的 KV

**三个聊天请求共享同一个系统提示：**

| | 系统提示 | 问题 |
|---|---|---|
| Req 1 | **prefill**（首次计算） | Q1 |
| Req 2 | **cache hit** | Q2 |
| Req 3 | **cache hit** | Q3 |

**共享前缀从何而来：**

| 来源 | 说明 |
|---|---|
| 系统提示（System prompts） | 每个请求重复同样的 instructions |
| 多轮聊天（Multi-turn chat） | 每轮重发完整历史 |
| Agent | 每步重发 tools 和至今为止的 trace |

**Prefill 工作量（1,000-token prompt + 50-token 问题，共 3 个请求）：**

- **无缓存：** 3 × 1,050 = **3,150 token** 的 prefill；
- **有前缀缓存：** 1,050 + 50 + 50 = **1,150 token**。

**只能精确匹配（Exact match only）：** 一个 token 的 KV 依赖于它之前的**所有** token。

### 2. 块哈希（Block hashing）：用整个前缀的哈希查找已缓存的 KV 块

- 一个 prompt，**每块 4 个 token（vLLM 使用 16）**。例：prompt "You are a helpful assistant who answers in French."
- **查找（Lookup）**：对新 prompt 的每个完整块计算哈希，**遇到第一个 miss 即停止**。
  - h₀ = H(∅, B₀)、h₁ = H(h₀, B₁)、h₂ = H(h₁, B₂)——**每个哈希折入其父哈希，所以 h₂ 考虑了全部 12 个 token，而不只是最后 4 个**。
  - 示例结果：Hit: block 7 → Hit: block 2 → Miss: compute（未命中部分现场计算）。
- **共享（Sharing）**：命中时增加该块的引用计数；**不复制任何东西**。
- **驱逐（Eviction）**：无引用的块保留在缓存中，直到内存需要时按 **LRU** 顺序逐出。
- **粒度（Granularity）**：**未填满的最后一个块从不共享**。

**在 PagedAttention 之上加一张哈希表，就把共享块变成了一枚缓存。**（来源：vLLM 文档，Automatic Prefix Caching 设计，2024）

### 3. SGLang RadixAttention：用 radix tree 保存每个请求的 KV 并共享其前缀

**一棵树保存所有已缓存请求的 KV：**

- **到达（Arrive）**：在树中匹配最长前缀，**只 prefill 剩余部分**；
- **完成（Finish）**：把新 token 作为分支插入树中；KV 留在 GPU 上；
- **驱逐（Evict）**：丢掉的 LRU 叶子不被任何在跑请求使用。
- **分支共享其父节点的 KV**，所以公共前缀只存一份。

图示：radix 树以 root 为根，挂着 System prompt 分支、Chat A（turn 1 / turn 2）、Chat B（turn 1）、few-shot set 等分支，Query 1 / Query 2 / Query 3 分别命中不同深度，被 LRU 驱逐的叶子标为 "LRU evicted"。

来源：Zheng et al., *SGLang*, NeurIPS 2024, Sec. 3 与 Fig. 3。

### 4. 检查理解：前缀缓存

- **Q1. 两个 prompt 只在 1,000 个 token 中的第 3 个不同，能共享多少 KV？**
  答：至多 **2 个 token**；若用 16-token 块哈希，则是**零**——每个 token 的 KV 依赖于之前所有 token。
- **Q2. 为什么最大化前缀缓存命中率与公平调度相冲突？**
  答：优先服务缓存最热（hottest cache）的客户端会**饿死其他请求**。
- **Q3. 一个已缓存前缀在块中间结束。哪个索引仍能复用它：块哈希还是 radix 树？**
  答：**radix 树**，它以 token 为粒度匹配；块哈希只能复用完整的块。

---

## 六、并行：一个模型，多张 GPU（Parallelism）

五种并行方式：**数据并行（DP）、张量并行（TP）、流水线并行（PP）、专家并行（EP）、序列并行（SP）**。

### 1. 为什么一张 GPU 不够

- 光权重就装不进单卡；KV cache 还要与权重竞争同一块 HBM。
  - 例：**70B 模型 bf16**：权重 **140 GB**，一张 GPU 只有 141 GB；**切到 4 张 GPU → 每卡 35 GB**。
- 单卡带宽封顶了 decode 速度：
  - 估算：**t ≥ 2N ÷ BW_HBM**；70B bf16 在 H200 上：140 GB ÷ 4.8 TB/s ≈ **每 token 29 ms**。
- 并行带来容量（capacity）与速度（speed）。

图示：单 GPU 上 140 GB 权重几乎占满 141 GB；横向切分后 4 张 GPU 各持 35 GB，留出 KV cache 空间。

### 2. 集合通信原语（Collectives）

颜色 = 产生数据的 GPU；数字 = 片（slice）编号；M = A、W 或某个矩阵的尺寸。

| 原语 | 行为 | 每 GPU 代价 | 典型用途 |
|---|---|---|---|
| Send / recv | 一张 GPU 向一张对端发送缓冲 | — | PP stage 跳板、SP 环（ring） |
| Broadcast | 一张 GPU 把缓冲复制给所有 GPU | — | 批输入分发到各 TP rank |
| All-gather | 各自贡献一个片，全部 GPU 得到完整结果 | 0.75 M | TP 输出、SP 的 K/V |
| Reduce-scatter | 跨 GPU 求和，各保留一个片（Σ₀ Σ₁ Σ₂ Σ₃） | 0.75 M | TP + 序列并行 |
| All-reduce | 跨 GPU 求和，每个 GPU 保留全部（= reduce-scatter + all-gather） | 1.5 M | TP 中 row-parallel 层之后 |
| All-to-all | GPU i 把片 j 发给 GPU j | 0.75 M | EP 的 token dispatch 与 combine |

图示：6 幅矩阵示意（4 个 GPU，各持不同颜色片）分别画出六个原语在 "Before" 与 "After" 各 GPU 上的数据分布。

### 3. 数据并行（DP）：更多副本

- 每张 GPU 持有**完整模型**；
- 请求被**路由器（router）**切分到各副本；
- 每个副本保留**自己的调度器和 KV cache**；
- 扩展吞吐：**2× 吞吐，同样的最大模型尺寸**；
- 矩阵视角：每张 GPU 上同一个 W，批按行切分（X₀×W=Y₀ → GPU 0，X₁×W=Y₁ → GPU 1，…）；
- 估算：吞吐 ≈ G × Θ（G 个副本）；**每 GPU 内存保持 2N + KV**；
- **通信：0，副本之间从不通信**。

### 4. 张量并行（TP）：层内切分

- 每层的矩阵被切到各 GPU（shard 0–3）；
- 每个 GPU 计算**每一层**的一部分，每个 block 后一次 **all-reduce** 合并切片；
- 需要 NVLink 级带宽，所以**保持在同一节点内**；对所有 L 层重复。
- 估算：
  - 每 GPU 权重 = 2N ÷ G；70B 在 G = 4 时 → 每卡 **35 GB**；
  - GPU 越多通信越多；**每 GPU 每层通信：2 × 1.5 × 2bh 字节**。

图示：一个 transformer 层被切成 4 个 shard 分布在 GPU 0–3，每个 block 后 all-reduce，纵向重复 L 层。

#### 列并行线性层（Column-parallel）：按列切 W，每个 GPU 拥有完整的输出列

- 每个 GPU 持有 W 的一个**竖切片**（h × f/G）和 X 的完整副本（b × h），算出自己那部分输出列（b × f/G），**无需通信**：GPU 0: Y₀ = X·W₀ … GPU 3: Y₃ = X·W₃（b = token 数，h = hidden，f = 输出宽度）。
- **通信：** 层内零通信；仅当下一步需要完整 Y 时才加一次 all-gather。

来源：Shoeybi et al., *Megatron-LM*, arXiv 1909.08053, 2019。

#### 行并行线性层（Row-parallel）：按行切 W，每个 GPU 持部分和，再 all-reduce

- 每个 GPU 持有 W 的一个**横切片**（h/G × h）和 X 的对应列（b × h/G）；其乘积是**全尺寸但只是答案的一部分**：Z = Z₀ + Z₁ + Z₂ + Z₃ = Σ Zᵢ，GPU i 计算 Zᵢ = Xᵢ·Wᵢ。
- **通信：** 对 b × h 输出做一次 all-reduce（bf16 下 2bh 字节）；每个 GPU 发送 2(G − 1)/G × 2bh，**G = 4 时为 3bh**。

来源：Shoeybi et al., *Megatron-LM*, arXiv 1909.08053, 2019。

#### Megatron TP block：先列并行后行并行，每个 block 只一次 all-reduce

- 列并行层的输出切片**恰好**是行并行层所需的输入，所以 GPU 们**只在末端通信一次**。
- **MLP**：Up + gate 投影（列并行）→ 激活（本地，无通信）→ Down 投影（行并行，合并部分和）→ All-reduce。
- **Attention**：Q, K, V 投影（列并行，每 GPU 1/G 个头）→ 逐头本地 attention → 输出投影（行并行）→ All-reduce。

### 5. 流水线并行（PP）：切分层

- 层被切成**连续的 stage**；每个 GPU 拥有一段连续层块（例：**80 层切成 4 个 stage**：L1–20 / L21–40 / L41–60 / L61–80）；
- **micro-batch 让每个 stage 保持忙碌**；
- 能容忍较慢的链路，所以**可以跨节点**。
- 估算：
  - 通信：**每个 stage 跳板一次 2bh 字节的 send**；
  - **Bubble（气泡）= (G − 1) ÷ (m + G − 1)**，G = GPU 数（stage 数），m = micro-batch 数；G = 4 时：**m = 4 → 43%，m = 16 → 16%**。

图示：4 个 GPU（G0–G3）× 7 个时间步的流水线甘特图，micro-batch 1–4 逐 stage 推进，灰色为气泡：28 个槽位中 12 个空闲 = 3/7 ≈ 43%。

### 6. 专家并行（EP）：切分 experts

- 一个 MoE 层包含很多 expert，每个 token 只用其中少数几个（如 top-2）；
- experts 分布在多 GPU 上（例：**8 个 experts 分到 4 张 GPU**：E0 E1 / E2 E3 / E4 E5 / E6 E7）；
- **all-to-all 把 token 送到它们的 expert**：1 Dispatch（把 t 发给它的 k 个 expert）→ 2 Compute（各 expert 本地计算）→ 3 Combine（把结果发回并求和）；所有 GPU 同时做这件事：all-to-all。例：token t → E3 和 E7（k = 2）。
- **路由不均会让部分 GPU 空闲。**
- 估算：每 GPU 负载 ≈ k × b ÷ G（top-2、1,024 个 token、4 卡 → 每卡 512）；**每 GPU 每层通信：2 × 0.75 × 2kbh 字节**。

### 7. 上下文并行（Context parallelism）：切分 token

- 长 prompt 超出单卡容量；
- 每个 GPU 持有一块 token；
- **ring attention 传递 K/V 块**；
- **帮助 prefill，对 decode 无益**。
- 估算：每 GPU token 数 = s ÷ G；**128K-token prompt，G = 4 → 每卡 32K token**；通信：每层 G − 1 次 K/V 块传递。

图示：128K-token prompt 在 4 张 GPU 上切成 0–32K / 32–64K / 64–96K / 96–128K 四段，GPU 间环形传递 K/V 块；**每个 query 依然能看到所有 key**；**传输与 attention 计算重叠**。

### 8. TP 与 EP 每 token 移动的字节数是 PP 的 240×

（70B 形状模型：h = 8,192、80 层、bf16、decode 一个 token；ring all-reduce 搬运 2(G − 1)/G 的数据；每层都有 MoE，3/4 的 expert 在远端。）

| 策略 | 集合通信 | 频率 | 每 token 每 GPU 字节 |
|---|---|---|---|
| Data | 无 | 从不 | 0 |
| Tensor (G = 4) | all-reduce | 每层 2 次 | **3.9 MB** |
| Pipeline (G = 4) | send / recv | 每次 stage 跳板 1 次 | **16 KB** |
| Expert (G = 4, top-2) | all-to-all | 每个 MoE 层 2 次 | ≈ 3.9 MB |

### 9. TP 与 EP 需要 NVLink

- 每 GPU 链路带宽（GB/s，单向）：**NVLink 4 = 450 GB/s；PCIe Gen5 x16 = 64 GB/s；InfiniBand NDR = 50 GB/s**（H100 SXM：NVLink 4 双向 900 GB/s、PCIe Gen5 x16、InfiniBand NDR 400 Gb/s）。
- 一次传输代价 **t = 字节 ÷ 带宽 + hop 数 × 延迟**；对 TP 的张量流量（3.9 MB/token/GPU）：**NVLink ≈ 9 µs；InfiniBand ≈ 78 µs**（还有额外开销）。
- **经验法则：TP 放节点内；PP 跨节点。**

### 10. 检查理解：并行

- **Q1. 70B bf16 模型放在一个 4 × H200（各 140 GB）的节点上。先切什么，为什么？**
  答：**NVLink 上的 TP = 4**；或 **DP2 + TP2**，取决于 context 大小。
- **Q2. 你加了第二个节点。用什么并行？**
  答：**跨节点用 PP**：每 token 一次 2h 字节的跳板传输，而 TP 每层都 all-reduce，流量大约多 **240×**。
- **Q3. 为什么 DP attention + EP 在长 context 上能胜过 TP，短 context 上却更差？**
  答：长 context：当 KV 头数 < rank 数时 TP 会**复制 KV**，而 DP 支持更大 batch。短 context：all-to-all 的开销占主导。

### 11. 并行：要点总结

| 并行方式 | 收益 | 代价 |
|---|---|---|
| **数据并行（DP）扩展吞吐** | G 个副本服务 G× 的请求 | 每个副本都必须持有完整模型 |
| **流水线与序列并行增加容量** | 流水线可跨节点且流量轻 | 引入气泡（bubble）；序列并行切分超长 prompt |
| **张量并行降低每 token 延迟** | 每个 GPU 只读 1/G 的权重 | 每层都要 all-reduce；保持在 NVLink 节点内 |
| **专家并行服务 MoE 模型** | experts 分布在多 GPU | all-to-all 流量 + expert 负载不均 |

---

## 七、总结与选读

### 下节课：投机解码（speculative decoding）

**本讲回顾（Today in brief）：**

- 测量（Measurement）：TTFT 与 TBT 百分位、goodput
- 批处理（Batching）：连续批处理、选择性批处理
- 调度（Scheduling）：请求调度、chunked prefill、disaggregation
- 内存管理（Memory management）：分页（paged）、共享 KV cache
- 并行（Parallelism）：DP、TP、PP、EP、SP

### 选读：各节背后的论文

| 章节 | 论文 |
|---|---|
| Evaluation | Agrawal et al., *On Evaluating Performance of LLM Inference Systems*, arXiv 2025 |
| Batching and scheduling | Yu et al., *Orca*, OSDI 2022；Agrawal et al., *Sarathi-Serve*, OSDI 2024；Sheng et al., *Fairness in Serving LLMs*, OSDI 2024 |
| KV-cache memory | Kwon et al., *PagedAttention and vLLM*, SOSP 2023；Zheng et al., *SGLang*, NeurIPS 2024 |
| PD disaggregation | Zhong et al., *DistServe*, OSDI 2024 |
| Parallelism | Shoeybi et al., *Megatron-LM*, arXiv 2019；Korthikanti et al., *Reducing Activation Recomputation*, MLSys 2023；Thakur, Rabenseifner and Gropp, *Collective Operations in MPICH*, IJHPCA 2005 |

---

## 核心要点

- LLM serving 值得专门研究：计算巨大（需 GPU）、每 token 都付费（每请求重跑模型）、GPU 昂贵（效率决定成本与速度）；单请求有两阶段两瓶颈（prefill 计算受限、decode 带宽受限），且 token 是柔软增长的状态、跨请求存在 10⁴–10⁶× 的成本差距。
- 评测四指标：TTFT、TBT（P99 能捕捉停顿）、TPOT（平均间隔，掩盖停顿）、E2E = TTFT + TPOT × (n−1)；goodput 只统计满足 SLO 的吞吐。
- GPU 吞吐与用户吞吐要分开看：batch 1→64 带来约 20× GPU 吞吐（6K TPS/GPU），但单用户从 100 TPS/user 慢约 3 倍。
- 评测四陷阱：短瞬态运行（只报稳态）、误导性平均（展示分布 + TTFT/TPOT/吞吐）、不真实负载（回放真实 trace）、不公平比较（同硬件调优基线，真实算法增益 1.8÷1.6 ≈ 1.1×，70% 来自实现）。
- Orca 核心观察：线性层共享同一个 W，一次 GEMM 服务所有请求；attention 每请求各自执行——即选择性批处理；普通 pad 式批处理在 128-token 例中让 500/1,000 KV 的请求白算 127 个填充 token。
- FCFS 是 vLLM/SGLang 默认：简单无饥饿，但队首长请求阻塞所有后续请求；prefill-first（SGLang）保 TTFT 伤 TPOT，decode-first（FasterTransformer）保 TPOT 伤 TTFT。
- Chunked prefill 用每步 token 预算限制迭代延迟：2,048-token prefill 从 92 ms 步降到约 23 ms 步，代价是第 k 个 chunk 重读 (k−1)×512 token 的 KV；SGLang prefill 优先（--prefill-decode-interval），vLLM decode 优先（enable_chunked_prefill）。
- PD 分离把 prefill 池（TTFT、少 prompt、多 TP、高 FLOPS GPU）与 decode 池（TPOT、上百序列、多副本、高 HBM 带宽 GPU）分开；KV 逐层经 NVLink/RDMA 流式传输。Llama-3.1-70B 65,536-token 的 KV = 20 GB：NVLink(H100) 44 ms、InfiniBand 400 ms（< 4% 的 11.5 s prefill）；代价是每请求一次 KV 传输、P:D 比例与额外实例。
- SJF 需要作业大小（=输出长度），而输出长度 decode 结束前未知：可用 OPT-125M ranker 学排名（ranking loss、饥饿防护）；FastServe 用 skip-join 多层队列 + token 级抢占，无需作业大小即可近似 SRPT；agentic 负载可用未缓存 prefill token 数代替作业大小。
- Orca 式连续分配器在 2× H200（282 GB）上跑 70B 时只有 20–38% 的 KV 内存持有真实 token：未知输出长度预留（128K 上限 ≈ 40 GB）、内部碎片、外部碎片三种浪费。
- PagedAttention 借鉴 OS 分页：一层间接消除连续性需求，块（16 token）经块表映射到物理块，支持按需分页、引用计数共享/写时复制、换出到 CPU 内存。
- 前缀缓存：系统提示/多轮历史/agent trace 都是共享前缀来源；1,000+50 的三请求 prefill 从 3,150 降到 1,150 token；只能精确匹配（token 的 KV 依赖之前所有 token）。
- vLLM 用块哈希（16-token 块，父哈希折入）：首个 miss 停止、命中只增引用计数、未引用块 LRU 逐出、半满末块不共享；SGLang RadixAttention 用 radix 树以 token 粒度匹配最长前缀。
- 单卡装不下 70B（bf16 140 GB vs 141 GB，且 KV 抢 HBM）；decode 每 token 下界 t ≥ 2N ÷ BW_HBM（H200 ≈ 29 ms）。
- 集合通信六原语各有用途：send/recv（PP 跳板、SP 环）、broadcast（批分发）、all-gather（TP 输出、SP K/V，0.75M）、reduce-scatter（0.75M）、all-reduce（TP row-parallel 后，1.5M）、all-to-all（EP dispatch/combine，0.75M）。
- DP 零通信、G× 吞吐但每副本持有完整模型；TP 每卡 2N÷G 权重、每层 all-reduce（G=4 每层 2×1.5×2bh 字节），Megatron block 列并行+行并行使每 block 只通信一次（G=4 每 GPU 3bh）。
- PP 每跳板一次 2bh 字节、气泡 = (G−1)÷(m+G−1)（G=4: m=4→43%，m=16→16%），可跨节点；EP 用 all-to-all 分发 token，代价是负载不均；上下文并行把 128K prompt 切成 4×32K，ring attention 传 K/V 块（每层 G−1 次），只帮 prefill。
- 每 token 通信量对比：TP 与 EP 各约 3.9 MB，PP 仅 16 KB——**TP/EP 是 PP 的 240×**；NVLink 4 单向 450 GB/s 下 TP 传输约 9 µs，InfiniBand 约 78 µs，故经验法则：TP 节点内、PP 跨节点。
- 部署直觉：节点内先 TP=4（或按 context 用 DP2+TP2）；加节点用 PP；KV 头数 < rank 数时 TP 会复制 KV，长 context 下 DP attention + EP 可反超，短 context 下 all-to-all 开销占主导。
- 下讲预告：投机解码（speculative decoding）。
