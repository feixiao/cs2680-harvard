# 第 10 讲（上）：LLM 服务基础 II —— GPU 入门 (LLM Serving Basics II: Intro to GPUs)

> 哈佛 CS2680 *Modern AI Systems: Agents and System Optimizations*，讲师 Juncheng Yang，课程主页 course.agentic-system.org。本讲 PDF 共 41 页。

## 本讲概览

本讲是「LLM 服务基础」系列第二讲，主题为 **GPU 入门（Intro to GPUs）**：不深入细节，目标是建立对 GPU 的**直觉（intuition）**，为理解 LLM serving 的性能瓶颈打基础。内容分四部分：GPU 基础（吞吐机器、warp/SIMT、三大规格、roofline）、GPU 架构（H200、Tensor Core、内存层次、Little's law、Hopper/Blackwell 数据通路）、scale-up/scale-out 层次，以及选读各家加速器（AMD MI355X、Google TPU Ironwood、AWS Trainium3 等）。贯穿主线：**decode 是强度 ≈ 1 FLOP/B 的带宽受限 GEMV，batching 把权重读取推向脊点（ridge point），但 KV cache 读取始终内存受限；新一代 GPU 降低精度把脊点推右，使 kernel 越来越带宽受限**。下节课进入 LLM Serving III（batching、paging、parallelism）。

## 课程事务

- **Assignment 4** 当天发出、两个半周后截止：目标是**对性能与瓶颈进行推理（reason about performance, bottlenecks）并迭代改进**，理解真实负载（real-world workloads）与合成基准（synthetic benchmarks）的差别；write-up 重要，代码量小；对系统编程（systems programming）经验不足者会很难。
- 排行榜提交**不接受迟交（NO LATE DAY）**；**一次不要占用超过一块 GPU**；课题提案（Proposal）下周三（**10 月 28 日**）截止，格式/页数不限；**禁止上传 AI 生成的内容（DO NOT upload AI-generated content）**。
- 下节课：学生分享（student sharing）；GPU 编程与性能优化（GPU programming and performance optimization）；**LLM Serving III: batching, paging, and parallelism**。

## GPU 基础 (GPU Basics)

### 形态与吞吐机器

- 两类形态：**消费级 = 台式机里的 PCIe 卡；数据中心 = 服务器里的 8-GPU 板卡**（图示：机架照片，含独立的 NVLink 交换机机框，为 scale-up 埋下伏笔）。**CPU 为单个线程优化**（少数带乱序执行 (OoO)、分支预测、L1/L2 的核心，共享 L3，少数几条 DDR 通道）；**GPU 为整块芯片优化**（大量 SM，共享 L2 与内存控制器，HBM 堆栈位宽达数千位，面积绝大部分是算术单元）。比喻：**CPU 像跑车，GPU 像公交队（慢，但运送数千人）**。

| | 64 核服务器 CPU | NVIDIA H200 SXM |
|---|---|---|
| Parallel units | 64 cores | 132 SMs, 16,896 FP32 cores |
| Threads in flight | 128 | 270,336 (2,048 per SM) |
| Memory bandwidth | ~0.46 TB/s (DDR5) | 4.8 TB/s (HBM3e) |
| Peak dense math | ~5 TFLOPs FP32 | 989 TFLOPs BF16 |
| Hides latency by | Caches, out-of-order cores | Switching to a ready warp |

- CPU 线程缓存未命中（cache miss）时会超前执行直到乱序窗口填满再停住（stall）；**GPU 直接切换到另一个就绪的 warp**——一个 warp 等内存时数学单元跑别的 warp，从而隐藏内存延迟。A100/H200/B200：**每 SM 4 个 warp 调度器（warp scheduler），各管最多 16 个 warp = 64 个常驻（resident）warp（2,048 线程）**。
- **SIMT (Single Instruction, Multiple Threads)**：1 warp = 一个 block 的线程 0–31，各 lane 有独立寄存器；**1 次取指 · 1 次译码 · 1 次调度决策**让整条 warp 指令在 32 个执行 lane 上运行——一条指令干 32 条标量指令的活，控制开销只付一次由 32 个 lane 分摊，类似 CPU 的 SIMD 向量指令。
- **分支发散（branch divergence）**：warp 靠 active mask 管理各 lane，发散后**依次跑完两条路径**——如 f 用 8/32 lane、g 用 24/32 lane，每轮都有大量 lane 被掩掉空闲，浪费吞吐。
- **GPU 的取舍**：放弃单线程速度（主频不高、无推测执行）、要求显式并行（约 27 万线程才能填满 132 SM，小任务芯片闲置）、控制流 32 个一组共享（发散损失）、每线程片上内存仅约 240 字节（满占用）；换来面积/功耗投向数千个算术单元、延迟靠切换 warp 隐藏（每线程状态常驻，**warp 切换是免费的**）、一次取指译码驱动 32 个核心。
- **为什么契合 LLM**：每个 token 在相同权重上跑同样的矩阵乘法（matmul），天然可并行——正是 GPU 擅长的负载形态。

### 三个规格与 Roofline

三个规格限定每块 GPU 的上限（直觉：**算力是发动机，带宽是输油管，容量是油箱**）：

| | A100 | H200 | B200 | Rubin | 限定什么 |
|---|---|---|---|---|---|
| Peak BF16 | 312 TFLOP/s | 989 TFLOP/s | 2,250 TFLOP/s | ≈ 4,000 TFLOP/s | 数学跑多快 |
| Memory bandwidth | 2.0 TB/s | 4.8 TB/s | 8 TB/s | ≈ 22 TB/s | 权重与 KV cache 读多快 |
| Memory capacity | 80 GB HBM2e | 141 GB HBM3e | 180 GB HBM3e | 288 GB HBM4 | 能装多少权重与 KV 条目 |

- **只有每个读出的字节喂足足够 FLOPs，算力才能到峰值**，一般化：**kernel 时间 ≈ max(字节 ÷ 带宽, FLOPs ÷ 峰值)**。以 H200 + 8B 模型 + BF16：**decode batch 1** 每 token 3.3 ms，HBM 读 16 GB 权重（÷4.8 TB/s ≈ 3.3 ms），数学本身只需 0.016 ms——**Tensor Core 99.5% 时间空闲，"计算在等"**（每个权重只用一次）；**prefill 2,048 tokens** 约 33 ms/prompt，每个权重喂 2,048 个 token，读取提前结束、**数学设定节奏**（Tensor Core 近峰值忙碌）。
- **Roofline 模型**：算术强度（arithmetic intensity）= FLOPs ÷ 与 HBM 之间搬运的字节；**脊点（ridge point）= 峰值 FLOP/s ÷ 带宽，H200 ≈ 206 FLOP/B**；脊点左侧内存受限（速度 = 带宽 × 强度），右侧计算受限（速度 = 峰值）——**prefill 在右侧，decode 在左侧**（Williams, Waterman & Patterson, *Roofline*, CACM 2009）。常见强度（b = 每元素字节）：向量加 = 1/(3b)；**decode GEMV ≈ 2/b**（每个权重用一次）；**decode attention = 2/b**（每个 KV entry 每头用一次）；N×N GEMM = 2N/(3b)（每元素重用约 N 次）；BF16 下 decode 两类操作都约 1 FLOP/B，GEMM 强度随 N 线性增长。
- **Batch 能帮 decode 吗**：batch n 时每个权重喂 n 个请求，权重 GEMV 强度从约 1 爬向脊点 206；但 **decode attention 恒停在 2/b**——batching 只缓解权重读取，KV cache 瓶颈必须靠别的手段（量化、压缩 KV 等）。
- **上下文长度能帮 decode 吗**：Llama 3 8B、batch 16、BF16，每 decode step 读 HBM 18.2 GB（1K）→ 84.8 GB（32K），时间 3.8 ms → 17.7 ms（step ≈ 字节 ÷ 4.8 TB/s）；**权重固定 16.1 GB**（任何 L 每 step 读一次），**KV cache 128 KiB/token** 随 batch × L 增长——上下文越长 decode 内存压力越大。课堂提问（H200 batch-1 decode 用到峰值的多少？≈50%/10%/2%/<1%？）：在 H200 roofline 上 batch-1 GEMV 强度 ≈ 1 FLOP/B，只跑到约 **5/989 TFLOP/s ≈ 峰值的 0.5%**（大 GEMM 坐在平坦算力屋顶上）；对策：**提高算术强度——加大 batch、量化、减少 KV 流量**。
- **趋势：低精度把脊点推向右边**（脊点 = 稠密峰值 ÷ HBM 带宽，FLOP/B）：

| GPU | HBM | FP32 | BF16 | FP8 | FP4 |
|---|---|---|---|---|---|
| A100 SXM | 2.04 TB/s | 9.6 | 153 | – | – |
| H100 SXM5 | 3.35 TB/s | 20 | 295 | 591 | – |
| H200 | 4.8 TB/s | 14 | 206 | 412 | – |
| B200 HGX | 8 TB/s | 9.4 | 281 | 563 | 1,125 |
| MI355X | 8 TB/s | – | 315 | 629 | 1,259 |
| Rubin (prelim.) | 22 TB/s | – | 182 | 795 | 1,591 |

- Rubin 的 dense NVFP4 需 ≈ 1,600 FLOP/B 才算计算受限；从 A100 到 Rubin，**BF16 算力增长约 13 倍而带宽仅约 9 倍**——kernel 越来越倾向于带宽受限。小结：① 吞吐机器；② 三个上限（算力/带宽/容量）；③ roofline 脊点（H200 206 FLOP/B）分隔两类受限；④ decode：batching 推权重读取向脊点，KV 读取始终内存受限；⑤ 新 GPU 把脊点推右，更多 kernel 变带宽受限。

## GPU 架构 (GPU Architecture)

### H200 与 SM 内部

- 图示：H200 die 上 **132 个 SM** 共享**一个 50 MB L2 缓存**，环绕 **6 个 24 GB HBM3e 堆栈（141 GB @ 4.8 TB/s）**，die 边缘 **NVLink 900 GB/s** 连其它 GPU。（NVIDIA, *Hopper Architecture* whitepaper, 2022；H200 datasheet, 2024）**每个 SM 分 4 个分区（partition）**：各含一个 warp 调度器（每周期发射一条 warp 指令）、64 KB 寄存器、32 个 FP32 核心、一个 Tensor Core，另有 256 KB L1/共享内存池（每 SM 自己的寄存器与 256 KB SRAM）；最多 64 个 warp（2,048 线程）常驻，调度器每周期挑一个就绪 warp 发射。
- **Tensor Core**：一条 warp 指令完成小矩阵乘加 **D = A × B + C**（H200 上 mma 形状 16×16 × 16×8）；**一条 mma = 2,048 次乘加 = 普通 FMA 每指令工作量的 64 倍**。H200 SXM 峰值稠密算力：

| 计算路径 | 峰值 TFLOP/s |
|---|---|
| FP32 scalar | 67 |
| FP16 scalar | 134 |
| TF32 Tensor | 495 |
| BF16 Tensor | 989 |

- **矩阵乘法占 LLM FLOPs 的 99%+**（softmax、norms 走 FP32 核心），Tensor Core 让它加速。快的四个原因：① 专用乘加数据通路，并行处理整个矩阵 tile；② 每 FLOP 指令更少，分摊译码/调度/操作数处理开销；③ 操作数高效复用（A 中每个值喂若干输出列、B 中每个值喂若干行，减少访存）；④ 低精度算术（FP16/BF16/FP8）通常配更高精度累加（accumulation）以保数值质量。

### 内存层次与在飞字节

| 层次（H200 容量） | 延迟（Hopper） | 带宽 |
|---|---|---|
| 寄存器（256 KB/SM，流水线内） | 每条指令都读 | 每核心每时钟 3 个操作数 |
| 共享内存 / L1（每 SM 256 KB 池） | ≈ 30 周期（L1 命中 40） | 每 SM 128 B/clk，132 个 SM 合计 ≈ 33 TB/s |
| L2 缓存（50 MB） | ≈ 250 周期 | ≈ 6 KB/clk，≈ 12 TB/s |
| HBM3e（141 GB，6 堆栈） | ≈ 500 周期 | 4.8 TB/s |
| 主机 DRAM / 对端 GPU | 微秒级（NVLink 或 PCIe） | NVLink 每方向 450 GB/s；PCIe 5.0 ≈ 64 GB/s |

- **内存是一根 250 ns 的管道**（从 load 发射到数据到达约 250 ns）：**Little's law：带宽 = 在飞字节数 ÷ 延迟（bandwidth = bytes in flight ÷ latency）**。硬件把管道长度（延迟）定死，**提高带宽的唯一办法是让管道里装更多字节**：朴素 kernel（每线程只发一个 4 B load）仅 **2.2 TB/s（峰值的 45%）**；满管需**每 SM 9 KB 在飞 = 4.8 TB/s × 250 ns ÷ 132 SMs → 4.8 TB/s（100%）**。手段：**16 字节向量 load、每线程 4 个独立 load、大块异步拷贝（TMA）**（内存层次数据来源：Luo et al., *Dissecting the NVIDIA Hopper Architecture*, 2024）。
- 每代 GPU 需要更多在飞字节才能跑满峰值带宽（带宽每代提升、延迟改善有限）：

| | H200 · Hopper | B200 · Blackwell | Rubin |
|---|---|---|---|
| SMs | 132 | 148 | 224 |
| HBM | 141 GB HBM3e | 180 GB HBM3e | 288 GB HBM4 |
| HBM 带宽 | 4.8 TB/s | 8 TB/s | 22 TB/s |
| Bytes in flight, GPU | 1.2 MB | 2.0 MB | 5.5 MB |
| Bytes in flight, per SM | 9 KB | 14 KB | 25 KB |
| 新数据通路特性 | TMA, clusters | TMEM, 2-SM MMA | Inline TMA descriptors |

### Hopper / Blackwell 数据通路（高级选读）

- **Hopper 让每条指令携带更多在飞字节**：coalescing（32 线程读连续 4 B 合并为一个 128 B 请求）；16 字节向量 load（一条 warp 指令搬 512 B 而非 128 B，4×）；cp.async（Ampere+，全局→共享内存不经过寄存器，寄存器空出加载更多）；**TMA**（一个线程发起整块 tile 拷贝，如 128×64，硬件生成地址，一条指令即有几十 KB 在飞）；**TMA multicast**（cluster 中最多 8 个线程块共享一次 L2 读取，落到各 SM 共享内存，L2 流量下降）。
- **Blackwell 两个变化**：① **TMEM（256 KB 张量内存）**承接 Tensor Core 结果，寄存器被释放去保持更多 load 在飞（把「在飞字节」与「结果暂存」解耦）；② **2-SM MMA**：两个 SM 的 Tensor Core 协同完成一次矩阵乘法、tile 翻倍，每个 SM 只取回两个 SM 都需要的半个 tile，进一步减少访存。

## 从一张 GPU 到多张：Scale-up 与 Scale-out

- 图示：**8-GPU 节点（HGX H200）**——8 个 GPU 经 NVSwitch 互连，配 8 个 400 Gb/s 网卡接入 scale-out 网络；**NVL72 机架（GB200）**——9 行「4 GPU + 2 CPU」单元，行内经 NVLink switch 互连（共 72 GPU）。
- 三级互连带宽（HGX H200 节点 / GB200 NVL72 机架）：**HBM 4.8 / 8 TB/s ≫ NVLink 900 GB/s / 1.8 TB/s ≫ RDMA 50 / 100 GB/s**——数量级落差决定 LLM 并行策略：需频繁交换激活的并行（如张量并行）应留在 NVLink scale-up 域内，跨机架 RDMA 只适合低频通信（如流水线并行）。
- （高级选读）NVIDIA GPU 二十年分两段：**2006–17 图形→通用计算**（Tesla 统一着色器+CUDA、Fermi 真 L1/L2、Pascal HBM2+NVLink、Volta 首代 Tensor Core），**2018–26 计算→低精度 AI 引擎**（Ampere TF32/BF16/2:4 稀疏/cp.async、Hopper FP8/TMA/clusters、Blackwell 双 die FP4/TMEM/NVL72、B300 288 GB+15 PF dense NVFP4、Rubin HBM4/NVLink 6）。**算力跑赢内存：G80 → B300 峰值算力约 43,000 倍，带宽约 90 倍**。

## 选读：各家加速器

- **AMD Instinct MI355X**（chiplet 封装）：一个封装上 **8 个计算 die**（软件视为一块 GPU）、HBM 前 **256 MB Infinity Cache**、**64 线程 wavefront**（而非 32 线程 warp）。编程：**ROCm/HIP**（hipify 转换 CUDA 源码），PyTorch/vLLM/SGLang 均跑在 ROCm，自定义 kernel 用 Triton 或 Composable Kernel。规格 vs B200：**5.0 PF dense FP8**（B200 4.5）、**288 GB HBM3E**（B200 180）、8 TB/s（与 B200 同）、scale-up 域 8 GPU（GB200 NVL72 为 72）。
- **Google TPU Ironwood**：**weight-stationary 脉动阵列（systolic array）**——每个权重留在自己单元里，激活从左进入、部分和向下流动从底部流出，数据阵列内复用，访存远少于 SIMT（后者每条指令都要从寄存器文件读写）；3D torus 互连。编程：**JAX 或 PyTorch/XLA**（XLA 把 matmul tile 化铺到阵列），**Pallas** 写自定义 kernel。规格 vs B200：**4.6 PF dense FP8**（B200 4.5）、**192 GB HBM3E**（B200 180）、7.4 TB/s（B200 8）、3D torus **9,216 芯片**（NVL72 72）。
- **AWS Trainium3**：**8 个 NeuronCore**，各含独立的 **Tensor（systolic）/ Vector / Scalar** 引擎；**每核 32 MB SRAM** 由 DMA 引擎填充、**无硬件缓存**（缓存行为由软件管理）；性能增益主要来自 MXFP8/MXFP4，每核 BF16 与 Trainium2 相比不变。编程：Neuron SDK 编译 PyTorch/JAX 图，**NKI（Neuron Kernel Interface）**用 Python 写 kernel、**显式在 HBM 与 SRAM 间搬 tile**；没有 CUDA，kernel 面向「引擎」而非「线程」。规格 vs B200：**2.5 PF dense MXFP8**（B200 4.5 PF FP8）、**144 GB**（B200 180）、4.9 TB/s（B200 8）、scale-up 域 144 芯片。
- 其它加速器（用片上 SRAM 替代 HBM 的一极，与 NVIDIA「大 HBM + 缓存层次 + 软件管理在飞字节」形成对照——既然 HBM 带宽是瓶颈，干脆把数据尽量留在片上）：

| 芯片 | 片上 SRAM | 片外内存 | 权衡 |
|---|---|---|---|
| Cerebras WSE-3 | 44 GB | 无 | 整片晶圆即一颗芯片，更大的模型把权重流式传入 |
| Groq LPU | 230 MB | 无 | 70B 模型 8-bit 化约需 300 颗芯片 |
| Microsoft Maia 200 | 272 MB | 216 GB HBM3e | SRAM 放热点数据，仅 Azure 内部可用 |

## 核心要点

1. **GPU 是吞吐机器**：132 SM / 16,896 FP32 核心 / 270,336 在飞线程；对 64 核 CPU：4.8 vs 0.46 TB/s 带宽、989 vs 5 TFLOPs 峰值算力，延迟靠 warp 切换（每 SM 64 个常驻 warp）而非缓存+乱序隐藏。
2. **SIMT**：一条 warp 指令 = 32 条标量指令的工作量、控制开销只付一次；但分支发散（两路径依次执行、被掩 lane 空闲）浪费吞吐。GPU 放弃单线程速度、显式并行（约 27 万线程填满芯片）、共享控制流（32 一组）、约 240 B/线程片上内存，换得海量算术单元与零成本 warp 切换。
3. **三个规格**：峰值算力（H200 989 TFLOP/s BF16）、HBM 带宽（4.8 TB/s）、容量（141 GB）= 发动机/输油管/油箱。
4. **Decode batch 1 极度浪费算力**：每 token 3.3 ms 中数学只需 0.016 ms，Tensor Core 99.5% 空闲；在 H200 roofline 上约 5/989 TFLOP/s ≈ **峰值的 0.5%**（kernel 时间 ≈ max(字节÷带宽, FLOPs÷峰值)）。
5. **Prefill 计算受限**：2,048 token 约 33 ms，每个权重喂 2,048 个 token，Tensor Core 近峰值忙碌；大 GEMM 坐在算力屋顶上，只有更快的数学或更少的 FLOPs 有用。
6. **Roofline 脊点 = 峰值÷带宽（H200 ≈ 206 FLOP/B）**：左侧内存受限（带宽×强度）、右侧计算受限（峰值）。典型强度：向量加 1/(3b)、decode GEMV ≈ 2/b、decode attention = 2/b、GEMM = 2N/(3b)；BF16 下 decode 操作都约 1 FLOP/B。
7. **Batching 只救权重、救不了 KV**：batch 把权重 GEMV 推向脊点，decode attention 恒在 2/b；上下文越长越糟——Llama 3 8B、batch 16 时每 step 读 18.2 GB（1K）→ 84.8 GB（32K），时间 3.8 → 17.7 ms（权重固定 16.1 GB，KV 128 KiB/token）。
8. **低精度把脊点推右**：H200 BF16 206 → FP8 412；B200 FP4 1,125、MI355X 1,259、Rubin 1,591（NVFP4 dense 需 ≈1,600 FLOP/B 才计算受限）；A100→Rubin BF16 算力 ×13 而带宽仅 ×9，kernel 越来越带宽受限。
9. **Tensor Core 快在**：专用 tile 乘加通路、一条 mma = 2,048 乘加（64× FMA）、操作数跨行列复用、低精度+高精度累加；矩阵乘法占 LLM FLOPs 99%+，H200 峰值：FP32 标量 67 / FP16 134 / TF32 495 / BF16 Tensor 989 TFLOP/s。
10. **Little's law：带宽 = 在飞字节 ÷ 延迟**：H200 内存管道长 250 ns，每 SM 需 9 KB 在飞才跑满 4.8 TB/s（朴素 4 B load 仅 45%）；手段：16 B 向量 load、每线程 4 个独立 load、TMA。H200 → B200 → Rubin 整 GPU 在飞字节 1.2 → 2.0 → 5.5 MB（每 SM 9 → 14 → 25 KB）。
11. **Hopper/Blackwell 数据通路**：coalescing（32×4B→1 个 128 B 请求）、cp.async（不经寄存器）、**TMA**（一个线程拷整块 tile、一条指令几十 KB 在飞）、TMA multicast（cluster 8 块共享一次 L2 读）；Blackwell **TMEM 256 KB** 承接结果腾出寄存器、**2-SM MMA** 两个 SM 合做乘法 tile 翻倍。
12. **互连三级**：HBM ≫ NVLink（900 GB/s / 1.8 TB/s）≫ RDMA（50 / 100 GB/s），高频并行（如 TP）应留在 NVLink scale-up 域；NVL72 = 9 行 ×（4 GPU + 2 CPU）。
13. **非 NVIDIA 阵营**：AMD MI355X（8-die chiplet、256 MB Infinity Cache、64 线程 wavefront、5.0 PF FP8/288 GB、ROCm/HIP）；TPU Ironwood（weight-stationary 脉动阵列、3D torus 9,216 芯片、4.6 PF/192 GB、JAX/XLA/Pallas）；Trainium3（8 NeuronCore、32 MB 软件管理 SRAM、无硬件缓存、2.5 PF MXFP8、NKI）；Cerebras WSE-3（44 GB SRAM、无片外内存）、Groq LPU（230 MB SRAM、70B 8-bit ≈ 300 片）、Maia 200（SRAM+HBM、仅 Azure）。
14. **一句话主线**：LLM decode 是强度 ≈ 1 FLOP/B 的带宽受限 GEMV，在 H200 上只跑峰值算力的 0.5%；一切优化（batching、量化、压缩 KV、提高在飞字节、NVLink 域内并行）都是在提高算术强度或减少必须移动的字节——这正是后续「LLM Serving III: batching, paging, and parallelism」的出发点。
