# 第 10 讲：LLM 服务基础 II —— GPU 入门（LLM Serving Basics II: Intro to GPUs）

> 哈佛 CS2680《Modern AI Systems: Agents and System Optimizations》，讲师 Juncheng Yang，课程主页 course.agentic-system.org。本讲 PDF 共 41 页。

## 本讲概览

本讲是「LLM 服务基础」系列的第二讲，主题是 **GPU 入门（Intro to GPUs）**：课程说明本次不会深入细节，目标是帮学生建立对 GPU 的**直觉（intuition）**，为理解 LLM 服务（serving）的性能瓶颈打基础。内容分四部分：GPU 基础（throughput 机器、warp、SIMT、三大规格、roofline 模型）、GPU 架构（H200/SM/Tensor Core/内存层次/Little's law/TMA 与 Blackwell 新特性）、从单卡到 scale-up/scale-out 的层次结构，以及选读的各家加速器（AMD MI355X、Google TPU Ironwood、AWS Trainium3 等）。贯穿全讲的核心线索是：**decode 是带宽受限（bandwidth-bound）的 GEMV，batching 能把权重读取推向 roofline 的脊点（ridge point），而 KV cache 读取始终留在内存受限一侧**；新一代 GPU 不断降低精度、把脊点推向右边，使越来越多的 kernel 变成带宽受限。本讲还布置了 Assignment 4（目标：推理性能瓶颈并迭代改进、理解真实负载与合成基准的差异）并预告了下节课将进入 LLM Serving III（batching、paging、parallelism）。

---

## 一、课程事务（Logistics）

- **Assignment 4** 当天发出，两个半周后截止（due in two and half weeks）。
- 作业目标：**对性能、瓶颈进行推理（reason about performance, bottlenecks）并迭代改进**，理解真实世界负载（real-world workloads）与合成基准（synthetic benchmarks）的差别。
- 写报告（write-up）很重要，只需要写少量代码。
- 排行榜提交**不接受迟交（NO LATE DAY）**；**不要一次占用超过一块 GPU**。
- 如果对系统编程（systems programming）经验有限，这个作业会很难。
- 课题提案（Proposal）下周三（**10 月 28 日**）截止，格式和页数不限。
- **禁止上传 AI 生成的内容（DO NOT upload AI-generated content）**。

## 二、今天的计划（Plan for today）

1. 面向 LLM serving 的 GPU 导论（脚注说明：不会深入细节，目标是建立直觉）；
2. **GPU 基础（GPU basics）**；
3. **GPU 架构（GPU architecture）**；
4. **GPU 编程与近期的 kernel 进展（GPU programming and recent kernel advances）**。

---

## 三、GPU 基础（GPU Basics）

开场分隔页的口号是「**你必须知道的一切**（Everything you must know about GPUs）」。

### 3.1 GPU 的形态（Form Factors）

GPU 有两类典型形态：

- **消费级（Consumer）**：插在台式机里的 **PCIe 卡**；
- **数据中心（Data center）**：插在服务器里的 **8-GPU 板卡**。

图示：该页是一张数据中心机架（rack）的照片，机架从上到下依次标注：2 个管理/顶层以太网交换机（2 management top-of-rack Ethernet switches）、4 个电源架（power shelves）、10 个计算节点（compute nodes）、9 个 **NVLink 交换机（NVLink switches）**、8 个计算节点、4 个电源架，以及抗震支撑结构（seismic bracing）。可以看出 NVLink 交换机以独立机框的形式存在于机架中，为后面的 scale-up 一节埋下伏笔。

### 3.2 GPU 是一台吞吐机器（A GPU is a Throughput Machine）

- **CPU 为单个线程优化**：每颗核心配有控制逻辑、乱序执行（out-of-order, OoO）、分支预测（branch predict）、ALU 算术单元和 L1/L2 缓存；芯片上多颗核心共享 **L3 缓存**；内存是**少数几条 DDR 通道**，位宽有限。
- **GPU 为整块芯片优化**：芯片上有大量 **SM（Streaming Multiprocessor，流式多处理器）**，共享 **L2 缓存**和**内存控制器**；内存是 **HBM 堆栈，位宽达数千位（thousands of bits wide）**；把芯片面积划分成「控制与猜测」和「算术单元」两大类——算术单元占绝大部分。

幻灯片的比喻：**跑车（sports car）坐 2 个人，跑得最快**；**公交车队（bus fleet）较慢，但能运送数千人**。CPU 像跑车（单线程延迟低），GPU 像公交队（吞吐量高）。

图示：左侧是 CPU 示意（少数带 OoO/分支预测/L1/L2 的核心 + 共享 L3 + 几条 DDR 通道）；右侧是 GPU 示意（132 个 SM 中画出 32 个，配 L2 缓存与内存控制器，连接位宽极大的 HBM 堆栈）。

### 3.3 用少数快核心换数千个简单核心

一张 **64 核服务器 CPU 与 NVIDIA H200 SXM** 的对照表：

| 指标 | 64 核服务器 CPU | NVIDIA H200 SXM |
|---|---|---|
| 并行单元 | 64 个核心 | 132 个 SM，共 16,896 个 FP32 核心 |
| 同时在飞的线程数（threads in flight） | 128 | 270,336（每 SM 2,048 个） |
| 内存带宽 | 约 0.46 TB/s（DDR5） | 4.8 TB/s（HBM3e） |
| 峰值稠密算力 | 约 5 TFLOPs FP32 | 989 TFLOPs BF16 |
| 隐藏延迟的方式 | 缓存、乱序核心 | 切换到就绪的 warp |

关键解释：CPU 线程遇到缓存未命中（cache miss）时，会**超前执行直到乱序窗口填满，然后停住（stall）**；GPU 则直接**切换到另一个就绪的 warp（warp switching）**。这正是 warp 切换隐藏延迟的硬件基础。

**为什么契合 LLM**：每个 token 都在相同的权重上跑同样的矩阵乘法（matmul），天然可以并行——这正是 GPU 擅长的负载形态。

### 3.4 Warp 切换隐藏内存延迟（Switching Warps Hides Memory Latency）

图示：一条时间轴上画出 Warp 0/1/2/3 的行为——某个 warp 发出指令（issues instructions）后要等内存（waiting on memory），此时下方「Math units（数学单元）」正在执行别的 warp（W0→W1→W2→W3 轮转）。**原理：一个 warp 在等内存时，另一个 warp 发出指令，于是数学单元始终保持忙碌**。

关键数字：在 **A100 / H200 / B200** 上，每个 SM 有 **4 个 warp 调度器（warp scheduler）**，每个调度器最多管理 **16 个 warp**，因此每个 SM 有 **64 个常驻（resident）warp**（64 × 32 = 2,048 线程/SM）。

### 3.5 SIMT：单指令多线程（Single Instruction, Multiple Threads）

一个线程的标量程序（scalar code, written once），例如：

```
i = threadIdx.x
y[i] = a*x[i] + b
```

在一个 block 内，**一个 warp = 该 block 的线程 0–31（32 个线程）**，32 个 lane 各有自己的寄存器。执行时 **1 次取指（fetch）、1 次译码（decode）、1 次调度决策**就让整条 warp 指令在 32 个执行 lane 上同时运行。

**为什么高效**：一条 warp 指令完成了 32 条标量指令的工作；控制开销只付一次、由 32 个 lane 分摊——类似 CPU 上的 SIMD 向量指令。

### 3.6 分支发散（Branch Divergence）

同一 warp 内执行含分支的指令：

```
int i = threadIdx.x;
bool p = (i % 4 == 0);
if (p) a = f(x[i]);
else  a = g(x[i]);
y[i] = a;
```

warp 有一个 **active mask（活动掩码）**：

| 阶段 | active mask（lane 0 → lane 31） | 含义 |
|---|---|---|
| 分支前 | 0xFFFFFFFF | 32 个 lane 全部活跃 |
| 发散（diverged）后走 f 路径 | 0x11111111 | 只有 i%4==0 的 8 个 lane 在跑 f，其余被掩掉（masked off, idle） |
| 再走 g 路径 | 0xEEEEEEEE | 其余 24 个 lane 在跑 g |
| 重新汇合（reconverged） | 0xFFFFFFFF | 32 个 lane 全部活跃 |

**代价（The cost）**：warp 必须**依次跑完两条路径**；本例中 f 只用 8/32 个 lane、g 用 24 个，也就是说 8 个 lane 在跑 g 时空闲、24 个 lane 在跑 f 时空闲——分支发散浪费吞吐。

### 3.7 GPU 背后的权衡（The Trade-offs Behind the GPU）

幻灯片用「GPU 放弃了什么 / 换来了什么」两栏总结：

| GPU 放弃（gives up） | 换来（gets） |
|---|---|
| **单线程速度**：主频不高、没有推测执行，串行代码跑得慢得多 | 面积和功耗花在**数千个算术单元**上 |
| **并行性必须显式提供**：约 27 万线程才能填满 132 个 SM，小任务会让芯片闲置 | 延迟靠**切换 warp** 隐藏，而不靠缓存和推测 |
| **控制流共享**：线程以 32 个一组运行，分支发散损失吞吐 | 一次取指译码就能驱动 **32 个核心** |
| **每线程片上内存小**：满占用时约 **240 字节/线程** | 每个线程的状态常驻，**warp 切换是免费的**（switches are free） |

### 3.8 三个规格决定每块 GPU 的上限（Three Specs Set the Limits）

每个 GPU 由三个规格限定，分别对应三种瓶颈：

| | A100 | H200 | B200 | Rubin | 限定了什么 |
|---|---|---|---|---|---|
| **峰值 BF16 算力** | 312 TFLOP/s | 989 TFLOP/s | 2,250 TFLOP/s | ≈ 4,000 TFLOP/s | 数学跑得多快 |
| **内存带宽** | 2.0 TB/s | 4.8 TB/s | 8 TB/s | ≈ 22 TB/s | 权重和 KV cache 读得多快 |
| **内存容量** | 80 GB HBM2e | 141 GB HBM3e | 180 GB HBM3e | 288 GB HBM4 | 能装下多少权重和 KV cache 条目 |

直觉：**算力是发动机，带宽是输油管，容量是油箱**（compute is the engine, bandwidth the fuel line, capacity the tank）。

### 3.9 只有每个读出的字节喂足足够 FLOPs，算力才能到峰值

用具体数字说明 decode 与 prefill 的本质区别（以 H200、8B 级模型、BF16 为例）：

- **Decode，batch 1**：每 token **3.3 ms**；HBM 要读 **16 GB 权重**（16 GB ÷ 4.8 TB/s ≈ 3.3 ms）；而数学本身只需 **0.016 ms**——**0.016 ms 的数学在等 3.3 ms 的读取**；Tensor Core **99.5% 的时间在闲置**。结论：**decode 时计算在等（compute waits）**：每个权重只用一次。
- **Prefill，2,048 tokens**：每条 prompt **33 ms**；每个权重喂给 2,048 个 token，权重加载完后读取提前结束，**数学设定节奏**；Tensor Core 以约 **33 TFLOP** 工作、**接近峰值地忙碌**。

一般化公式：**kernel 时间 ≈ max( 字节 ÷ 带宽 , FLOPs ÷ 峰值算力 )**。

### 3.10 Roofline 模型：判断 kernel 是内存受限还是计算受限

- **算术强度（Arithmetic intensity）= 执行的 FLOPs ÷ 与 HBM 之间搬运的字节数**（FLOPs / byte）。
- Roofline 图中：**脊点（ridge point）= 峰值 FLOP/s ÷ 带宽**。H200 的脊点 **≈ 206 FLOP/B**（989 TFLOP/s ÷ 4.8 TB/s）。
- 脊点**左侧**是内存受限（memory-bound）：**可达速度 = 带宽 × 强度**；脊点**右侧**是计算受限（compute-bound）：**速度 = 峰值 FLOP/s**。
- 对应 LLM：**prefill 在脊点右侧（compute-bound）**，**decode 在左侧（memory-bound）**。

（模型出处：Williams, Waterman & Patterson, *Roofline*, CACM 2009。）

### 3.11 常见操作的算术强度（Common Arithmetic Intensity）

设每元素 b 字节，强度 = FLOPs ÷ 字节数：

| 操作 | 推导 | 强度 | 直觉 |
|---|---|---|---|
| 向量加（vector add），长 N | N ÷ 3Nb | **1/(3b)** | 每搬 3 个元素只做 1 次 FLOP |
| GEMV（decode 权重乘），N×N | 2N² ÷ (N² + 2N)b | **≈ 2/b** | 每个权重只用一次 |
| Decode attention，n×d | 4nd ÷ 2ndb | **= 2/b** | 每个 KV entry 每个头只用一次 |
| 方阵 GEMM，N×N | 2N³ ÷ 3N²b | **= 2N/(3b)** | 每个元素被重用约 N 次 |

要点：在 BF16（b = 2）下，decode 的两类操作强度都约为 1 FLOP/B，而大 GEMM 的强度随 N 线性增长——强度能否越过脊点 206，取决于矩阵有多大（或 batch 有多大）。

### 3.12 Batch 能不能帮 decode？（Does Batching Help Decode？）

图示：算术强度（FLOP/B，BF16）随 batch size n（1, 2, 4, 8, 16, 32, 64, 128, 256）的曲线，纵轴 0–300，脊点 206 画在图上。两条曲线：

- **权重 GEMV（W × x）**：强度随 batch 增大而上升——batch n 时每个权重喂给 n 个请求，强度从约 1 爬向脊点 206（256 时接近 256 以上）；
- **Attention 读 KV（Q × KV）**：**恒定停留在 2/b ≈ 1 FLOP/B**——batch 只是把「读多少 KV」等比例放大，强度不变。

结论（幻灯片原话）：**batching 把权重 GEMV 推向脊点，但 decode attention 始终停在 2/b**。也就是说 batch 只能缓解权重读取的瓶颈，**KV cache 读取的瓶颈必须靠别的手段**（量化、压缩 KV、减少 KV 流量等，见后续各讲）。

### 3.13 上下文长度能帮 decode 吗？（Does Context Length Help Decode?）

数据条件：**Llama 3 8B**（引用 Meta, *The Llama 3 Herd of Models*, 2024）、**batch 16**、**BF16**、H200（NVIDIA 数据手册, 2024）。每个 decode step 从 HBM 读的字节数随上下文长度 L 变化：

| 上下文 L | 1K | 4K | 8K | 16K | 32K |
|---|---|---|---|---|---|
| 每 step 读的总字节 | 18.2 GB | 24.7 GB | 33.3 GB | 50.5 GB | 84.8 GB |
| 其中权重（固定） | 16.1 GB | 16.1 GB | 16.1 GB | 16.1 GB | 16.1 GB |
| 每 step 时间（≈ 字节 ÷ 4.8 TB/s） | 3.8 ms | — | — | — | 17.7 ms |

- **权重：固定 16.1 GB**，任何 L 下每 step 都读一次；
- **KV cache：128 KiB/token**，随 batch × L 增长（batch 16 时从约 2 GB 涨到约 68 GB）。

结论：上下文越长，每个 decode step 越慢（1K 时 3.8 ms，32K 时 17.7 ms，约 4.7 倍），且增长几乎全来自 KV cache——**长上下文让 decode 的内存压力进一步恶化**。

### 3.14 H200 在 batch-1 decode 时有多忙？（课堂提问）

给你已知条件：峰值算力 989 TFLOP/s（BF16 dense）、HBM 带宽 4.8 TB/s、batch-1 decode 是「每读 1 字节权重约做 1 个 FLOP」的 GEMV。让你估计它用掉峰值算力的份额：

- A ≈ 50%
- B ≈ 10%
- C ≈ 2%
- D < 1%

然后追问：**接下来你会改什么来提升它？**

### 3.15 在 H200 roofline 上，batch-1 decode 只跑到峰值算力的 0.5%

图示：H200 roofline（对数坐标）：算力屋顶 989 TFLOP/s，内存屋顶 4.8 TB/s × 强度，脊点 ≈ 206 FLOP/B。图上标出五个工作点：**vector add、GEMV batch 1、GQA decode、GEMV batch 32、GEMM N = 8192**。

- **Decode 是带宽受限**：batch-1 GEMV 强度 ≈ 1 FLOP/B，只能达到约 **5 / 989 TFLOP/s**，即峰值的 **0.5%**（对应上面课堂提问的答案 D 附近）。
- **对策：提高算术强度**——**加大 batch、量化（quantize）、压缩 KV 流量**。
- **Prefill 是计算受限**：大 GEMM 坐在平坦的算力屋顶上，只有更快的数学或更少的 FLOPs 能帮上忙。

### 3.16 趋势：低精度把脊点推向右边（Lower Precision Pushes the Ridge Right）

脊点 = 稠密峰值 ÷ HBM 带宽（单位 FLOP/B），各精度下各 GPU 的脊点：

| GPU | HBM 带宽 | FP32 | BF16 | FP8 | FP4 |
|---|---|---|---|---|---|
| A100 SXM | 2.04 TB/s | 9.6 | 153 | – | – |
| H100 SXM5 | 3.35 TB/s | 20 | 295 | 591 | – |
| H200 | 4.8 TB/s | 14 | 206 | 412 | – |
| B200 HGX | 8 TB/s | 9.4 | 281 | 563 | 1,125 |
| MI355X | 8 TB/s | – | 315 | 629 | 1,259 |
| Rubin（初步） | 22 TB/s | – | 182 | 795 | 1,591 |

两个要点：

- **FP4 把脊点推右**：例如 Rubin 的 dense NVFP4 需要约 **1,600 FLOP/byte** 才能变成计算受限——decode 这种强度 ≈ 1 FLOP/B 的负载离脊点更远了。
- **算力增长快于带宽**：从 A100 到 Rubin，**BF16 算力增长约 13 倍，而带宽只增长约 9 倍**，所以 kernel 越来越倾向于带宽受限（increasingly bandwidth-bound）。

### 3.17 GPU 基础小结（What to Take Away）

1. **吞吐机器**：GPU 用快速的单线程换数千个并行核心；
2. **三个上限**：峰值算力、HBM 带宽、内存容量限定每个 kernel；
3. **Roofline**：脊点（H200 上 206 FLOP/B）分隔内存受限与计算受限的 kernel；
4. **Decode**：batching 把权重读取推向脊点；KV cache 读取始终内存受限；
5. **趋势**：新 GPU 把脊点右移，更多 kernel 变成带宽受限。

---

## 四、GPU 架构（GPU Architecture）

### 4.1 H200 一览（An Illustration of the H200）

图示：H200 芯片布局——**132 个 SM**（图中只画了 44 个）排列在 die 上，共享**一个 50 MB L2 缓存**；周围环绕 **6 个 HBM3e 堆栈，每个 24 GB**，可用 **141 GB**、带宽 **4.8 TB/s**；die 边缘有 **NVLink：900 GB/s 连到其它 GPU**。每个 SM 有自己的寄存器和 **256 KB SRAM**。

（出处：NVIDIA, *Hopper Architecture* whitepaper, 2022；H200 datasheet, 2024。）

### 4.2 SM 内部：四个分区

每个 SM 分成 **4 个分区（partition）**，每个分区包含：一个 **warp 调度器**（每周期发射一条 warp 指令）、**64 KB 寄存器文件**、**32 个 FP32 核心**、一个 **Tensor Core**；SM 还有一个 **256 KB 的 L1 / 共享内存池**。

三个要点：

- **Warp = 32 个线程**：一条指令同时作用在 32 个线程上（SIMT）；
- **最多 64 个 warp 常驻（2,048 线程）**，调度器每周期挑一个就绪的 warp 发射——这就是靠大量常驻线程隐藏延迟的机制；
- **Tensor Core**：每条指令完成一个小矩阵乘加（small matrix multiply-add）。

### 4.3 LLM 的数学基本是矩阵乘法，Tensor Core 让它加速

**一条 warp 指令：D = A × B + C**（H200 上的 mma 指令形状为 16×16 × 16×8，C/D 为 16×8）。

H200 SXM 的峰值稠密算力（TFLOP/s）按路径分档：

| 计算路径 | 峰值稠密 TFLOP/s | 说明 |
|---|---|---|
| FP32 标量 | 67 | |
| FP16 标量 | 134 | |
| TF32 Tensor | 495 | |
| BF16 Tensor | 989 | **一条 mma = 2,048 次乘加，是普通 FMA 每条指令工作量的 64 倍** |

要点：**矩阵乘法占 LLM FLOPs 的 99% 以上**；softmax 和归一化（norms）用的是 FP32 核心。

### 4.4 Tensor Core 为什么快（Why Tensor Cores Are Fast）

四个原因（NVIDIA, *Hopper Architecture* whitepaper, 2022）：

1. **专用算术单元**：专用的乘加数据通路并行处理整个矩阵 tile；
2. **每 FLOP 的指令更少**：一条 MMA 指令覆盖许多乘加，分摊（amortize）了译码、调度和操作数处理的开销；
3. **操作数高效复用**：A 中每个值喂给若干输出列，B 中每个值喂给若干输出行（一个操作数被多次使用，减少访存）；
4. **低精度算术**：FP16、BF16、FP8 提高吞吐并缩小操作数，通常配**更高精度的累加（accumulation）**以保数值质量。

### 4.5 内存层次（The Memory Hierarchy）

H200 的各层（出处：Luo et al., *Dissecting the NVIDIA Hopper Architecture*, 2024）：

| 层次（H200 容量） | 延迟（Hopper） | 带宽 |
|---|---|---|
| 寄存器（256 KB/SM，流水线内） | 每条指令都读 | 每核心每时钟 3 个操作数 |
| 共享内存 / L1（每 SM 256 KB 池） | ≈ 30 周期（L1 命中 40） | 每 SM 128 B/clk，132 个 SM 合计 ≈ 33 TB/s |
| L2 缓存（50 MB） | ≈ 250 周期 | ≈ 6 KB/clk，Hopper 上 ≈ 12 TB/s |
| HBM3e（141 GB，6 个堆栈，H200 SXM） | ≈ 500 周期 | 4.8 TB/s |
| 主机内存与对端 GPU（CPU DRAM、经 NVLink 的其它 GPU） | 微秒级（经 NVLink 或 PCIe） | 每方向 450 GB/s（NVLink 4）；PCIe 5.0 ≈ 64 GB/s |

直觉：越靠近 SM 延迟越低但容量越小；HBM 容量大、带宽高，但延迟已是数百周期。

### 4.6 内存是一根 250 ns 的管道（Memory Is a 250 ns Pipe）

**Little's law：带宽 = 在飞字节数 ÷ 延迟（bandwidth = bytes in flight ÷ latency）**。（脚注引用：队列论公式的证明 L = λW；NVIDIA H200。）

- 管道长度 = 延迟：**从 load 发射到数据到达约 250 ns**。
- **朴素 kernel**：每 SM 在飞 4 KB（= 32 warps × 32 threads × 一个 4 B load）——但实际只有 8 个 512 B 的在飞块（每块 512 B），每 SM 仅 512 B 级别的在飞量 → 只能跑 **2.2 TB/s，峰值的 45%**。
- **满管**：每 SM 在飞 **9 KB = 4.8 TB/s × 250 ns ÷ 132 SMs** → **4.8 TB/s，峰值的 100%**。

图示：两条 SM 内存管道——朴素 kernel 的管道里只有稀疏的几个在飞块（2.2 TB/s，灰色），满管时管道被在飞字节塞满（4.8 TB/s，红色）。

**关键推论**：硬件把管道长度（延迟）定死了，所以**提高带宽的唯一办法是让管道里装更多字节**（keep more bytes in flight）。

**增加在飞字节的手段**：

1. 使用 **16 字节向量 load**（vector loads）；
2. 每线程发射 **4 个独立的 load**；
3. 使用**大块异步拷贝（TMA, bulk asynchronous copies）**。

### 4.7 在飞字节：每一代 GPU 需要更多才能达到峰值带宽

| | H200 · Hopper | B200 · Blackwell | Rubin |
|---|---|---|---|
| SM 数 | 132 | 148 | 224 |
| HBM | 141 GB HBM3e | 180 GB HBM3e | 288 GB HBM4 |
| HBM 带宽 | 4.8 TB/s | 8 TB/s | 22 TB/s |
| 整 GPU 在飞字节 | 1.2 MB | 2.0 MB | 5.5 MB |
| 每 SM 在飞字节 | 9 KB | 14 KB | 25 KB |
| 新数据通路特性 | TMA、clusters | TMEM、2-SM MMA | 内联 TMA 描述符（inline TMA descriptors） |

（出处：NVIDIA Hopper 与 Blackwell whitepapers；Vera Rubin, GTC 2025。）

含义：带宽每代提升，而延迟改善有限，于是**要填满内存管道需要越来越多的在飞字节**——这正是每一代引入更强异步拷贝/张量内存机制的原因（下一节展开）。

### 4.8 高级选读：Hopper 让每条指令携带更多在飞字节（Hopper Enables More Bytes in Flight per Instruction）

| 特性 | 做什么 | 效果 |
|---|---|---|
| **Coalescing（合并访存）** | 32 个线程读连续的 4 字节字，合并为**一个 128 B 请求** | 更少、更满的内存请求 |
| **16 字节向量 load** | 一条 warp 指令搬 **512 B** 而不是 128 B | 每指令字节数 4 倍 |
| **cp.async（Ampere+）** | 把全局内存直接拷进共享内存，**不经过寄存器暂存** | 寄存器空出来加载更多 load |
| **TMA（Hopper）** | **一个线程**发起整块 tile 拷贝，**硬件生成地址** | 一条指令带来千字节级在飞量 |
| **TMA multicast** | 一次 L2 读取落到 cluster 内**每个 SM 的共享内存** | 每 SM 的 L2 流量下降 |

### 4.9 高级选读：Hopper 的 TMA 用一条指令拷整块 tile

图示左（TMA：one thread, one tile）：全局内存（HBM）→ **TMA 引擎** → 共享内存中的一整块 tile（例如 **128 × 64**）——**一个线程**启动整个拷贝，寄存器保持空闲，**一条指令就能让几十 KB（tens of KB）处于在飞状态**。

图示右（Cluster multicast：one read, many SMs）：**L2 只读一次**，副本分别送入 **SM 0/1/2/3** 的共享内存——cluster 中最多 **8 个线程块（thread blocks）**共享一次 L2 读取，**L2 流量下降**。

### 4.10 高级选读：Blackwell 把结果放进张量内存，并让两个 SM 合做一次乘法

（出处：NVIDIA, *Blackwell Architecture* whitepaper, 2024。）两个变化：

- **TMEM（Tensor Memory）**：Hopper 上 Tensor Core 的结果存放在**寄存器**里；Blackwell 把结果放进 **256 KB 的 TMEM**，**寄存器被释放出来去保持更多 load 在飞**（把「在飞字节」和「结果暂存」解耦）。
- **2-SM MMA**：一次矩阵乘法由**两个 SM 的 Tensor Core 协同**完成，**tile 扩大一倍**：SM 0 加载共享 tile 的一半、SM 1 加载另一半，**每个 SM 只需取回两个 SM 都需要的半个 tile**——进一步减少访存。

### 4.11 从一张 GPU 到多张：scale-up 与 scale-out

图示对比两种规模：

- **8-GPU 节点（HGX H200）**：8 个 GPU 通过 **NVSwitch** 全互联，配 **8 个 400 Gb/s 网卡**接入 scale-out 网络。
- **NVL72 机架（GB200）**：每行是若干「4 GPU + 2 CPU」单元（4 GPUs + 2 CPUs），行内经 NVLink switch 互连，机架内**9 行**（共 72 个 GPU）。

三种互连带宽的层次：

| 链路 | HGX H200 8-GPU 节点 | GB200 NVL72 机架 |
|---|---|---|
| HBM（片上） | 4.8 TB/s | 8 TB/s |
| NVLink（scale-up 域） | 900 GB/s | 1.8 TB/s |
| RDMA（scale-out 网络） | 50 GB/s | 100 GB/s |

含义：**HBM ≫ NVLink ≫ RDMA** 三个数量级的落差，决定了 LLM 并行策略——张量并行（TP）等需要频繁交换激活的并行应尽量留在 NVLink scale-up 域内，跨机架的 RDMA 只适合低频通信（如流水线并行）。（出处：NVIDIA, HGX H200 and GB200 NVL72 specifications, 2024。）

### 4.12 高级选读：NVIDIA GPU 的二十年（Two Decades of NVIDIA GPUs）

幻灯片把 GPU 史分成两段：**2006–17：图形 → 通用计算**；**2018–26：计算 → 低精度 AI 引擎**。

| 架构（年代 · 代表产品） | 对程序员意味着什么 |
|---|---|
| **Tesla**（2006 · G80） | 统一着色器；CUDA、线程块、共享内存 |
| **Fermi**（2010 · C2050） | 真正的 L1/L2 缓存、ECC、统一地址空间、快速 FP64 |
| **Kepler**（2012 · K20X） | Warp shuffle、动态并行、Hyper-Q 工作队列 |
| **Maxwell**（2014 · M40） | SM 分成四个分区；每瓦性能大幅提升 |
| **Pascal**（2016 · P100） | HBM2、NVLink、支持缺页的统一内存、2× FP16 |
| **Volta**（2017 · V100） | Tensor Core、独立线程调度、统一 L1/共享内存 |
| **Turing**（2018 · T4） | INT8 与 INT4 Tensor Core、光线追踪核心 |
| **Ampere**（2020 · A100） | TF32、BF16、2:4 结构化稀疏、cp.async、MIG、40 MB L2 |
| **Hopper**（2022 · H100） | FP8、TMA、clusters 与 DSMEM、wgmma、机密计算 |
| **Blackwell**（2024 · B200） | 两个 die、FP6/FP4 与 block scaling、TMEM、tcgen05、NVL72 |
| **Blackwell Ultra**（2025 · B300） | 288 GB HBM3e、15 PF dense NVFP4、更快的 exp、大幅削减 FP64 |
| **Rubin**（2026 · NVL72） | HBM4、NVLink 6、更大的 TMEM 与共享内存（初步） |

总结（幻灯片原话）：**算力跑赢了内存，G80 → B300：峰值算力约 43,000 倍，带宽约 90 倍**——与 3.16 节「算力增长快于带宽」的 roofline 趋势呼应。（链接引用：GeForce 8 series；Blackwell Ultra。）

---

## 五、下节课预告（Next Class）

- 学生分享（Student sharing）；
- **GPU 编程与性能优化（GPU programming and performance optimization）**；
- **LLM Serving III：batching、paging 与 parallelism**。

（即前面反复铺垫的「提高算术强度」的手段——连续批处理、PagedAttention 式内存管理、各类并行——将在后续各展开。）

---

## 六、选读（Optional Reading）：各家加速器

### 6.1 AMD Instinct MI355X：chiplet 封装、每封装更多 HBM 的 GPU

（出处：AMD, Instinct MI355X datasheet and CDNA 4 whitepaper, 2025。）

与 NVIDIA GPU 的不同：

- **一个封装上 8 个计算 die**（chiplet），软件看来是一整块 GPU；
- **256 MB Infinity Cache** 位于 HBM 前面（类似一个大 L2）；
- 用 **64 线程 wavefront** 而不是 32 线程 warp。

编程方式：

- **ROCm 和 HIP**：CUDA 风格的 C++；用 **hipify** 转换 CUDA 源码；
- PyTorch、**vLLM 和 SGLang** 都跑在 ROCm 上；
- 自定义 kernel 用 **Triton** 或 **Composable Kernel**。

关键规格（对比 B200 标注）：

| 规格 | MI355X | 对比 B200 |
|---|---|---|
| Dense FP8 | **5.0 PF** | B200: 4.5 PF |
| HBM3E | **288 GB** | B200: 180 GB |
| HBM 带宽 | **8 TB/s** | B200: 8 TB/s |
| Scale-up 域 | **8 GPU** | GB200 NVL72: 72 |

### 6.2 Google TPU Ironwood：组成立方体阵列（systolic array）、以 3D 环面互连

（出处：Google Cloud, TPU7x (Ironwood) documentation, 2026；Jouppi et al., ISCA 2023。）

图示对比两种计算模型：

- **SIMT lanes（NVIDIA 风格）**：寄存器文件（register file）向一排 FMA 单元供数，**每条指令都要从寄存器文件读操作数（灰色箭头）并把结果（蓝色箭头）写回**——操作数流量大。
- **Systolic array（weight-stationary）**：3×3 的单元格（w00…w22）中**每个权重留在自己的单元里**；**激活值从左进入，部分和向下流动、从底部流出**——数据在阵列内流动复用，访存远少于 SIMT。

编程方式：用 **JAX 或 PyTorch/XLA**；**XLA 把矩阵乘法 tile 化铺到阵列上**；**Pallas** 用于自定义 kernel。

关键规格（对比 B200 标注）：

| 规格 | TPU Ironwood | 对比 B200 |
|---|---|---|
| Dense FP8 | **4.6 PF** | B200: 4.5 PF |
| HBM3E | **192 GB** | B200: 180 GB |
| HBM 带宽 | **7.4 TB/s** | B200: 8 TB/s |
| 互连规模 | **9,216 芯片**（3D torus） | GB200 NVL72: 72 |

### 6.3 Amazon Trainium3：带软件管理 SRAM 的脉动引擎

（出处：AWS, Trainium3 Architecture Guide for NKI, 2025；AWS Trainium product page, 2025。）

与 NVIDIA GPU 的不同：

- **8 个 NeuronCore**，每个内含独立的 **Tensor（脉动/systolic）、Vector、Scalar** 三种引擎；
- **每核 32 MB SRAM**，由 DMA 引擎填充，**没有硬件缓存**（缓存行为完全由软件管理）；
- 性能提升主要来自 **MXFP8 和 MXFP4**；每核的 BF16 性能与 Trainium2 相比没有变化。

编程方式：

- **Neuron SDK** 编译 PyTorch 和 JAX 计算图；
- **NKI（Neuron Kernel Interface）**：用 Python 写 kernel，**显式地在 HBM 与 SRAM 之间搬运 tile**；
- **没有 CUDA**；kernel 面向「引擎」而不是「线程」。

关键规格（对比 B200 标注）：

| 规格 | Trainium3 | 对比 B200 |
|---|---|---|
| Dense MXFP8 | **2.5 PF** | B200: 4.5 PF（FP8） |
| HBM3E | **144 GB** | B200: 180 GB |
| HBM 带宽 | **4.9 TB/s** | B200: 8 TB/s |
| Scale-up 域 | **144 芯片** | GB200 NVL72: 72 |

### 6.4 其它加速器：用片上 SRAM 代替 HBM

（出处：Cerebras, WSE-3 datasheet, 2024；Groq, LPU architecture, 2024；Microsoft, Maia 200, 2026。）

| 芯片 | 片上 SRAM | 片外内存 | 权衡（Trade-off） |
|---|---|---|---|
| **Cerebras WSE-3** | 44 GB | 无 | 整片晶圆就是一颗芯片；更大的模型需要把权重流式传入（stream weights in） |
| **Groq LPU** | 230 MB | 无 | 一个 70B 模型 8-bit 化后大约需要 **300 颗芯片** |
| **Microsoft Maia 200** | 272 MB | 216 GB HBM3e | SRAM 放热点数据；仅在 Azure 内部可用 |

这三者展示了「反 roofline 思路」的一极：既然 HBM 带宽是瓶颈，就干脆**把数据尽量留在片上 SRAM**（Cerebras 用超大 SRAM 取消片外内存，Groq 用确定性流式调度，Maia 用 SRAM+HBM 混合）——与 NVIDIA「大 HBM + 缓存层次 + 软件在飞管理」形成对照。

---

## 核心要点

1. **GPU 是吞吐机器**：CPU 像跑车（少数核心、乱序、分支预测，单线程快），GPU 像公交队（132 SM、16,896 FP32 核心、27 万在飞线程）；H200 对 64 核 CPU：4.8 TB/s vs 0.46 TB/s 带宽、989 vs 5 TFLOPs 峰值算力、warp 切换 vs 缓存+乱序来隐藏延迟。
2. **每 SM 内部**：4 个分区，各含 warp 调度器、64 KB 寄存器、32 个 FP32 核心、Tensor Core，外加 256 KB L1/共享内存；每 SM 4 个调度器各管 16 个 warp = 64 个常驻 warp（2,048 线程）。
3. **SIMT 高效**：一条 warp 指令 = 32 条标量指令的工作量，控制开销只付一次；但**分支发散**让不同 lane 跑不同路径时相互等待（8/24 lane 各空闲一轮）。
4. **GPU 的取舍**：放弃单线程速度、强制显式并行、控制流 32 个一组共享、每线程约 240 B 片上内存；换来海量算术单元和零成本 warp 切换。
5. **三个规格**：峰值算力（H200 989 TFLOP/s BF16）、HBM 带宽（4.8 TB/s）、容量（141 GB）分别限定数学速度、权重/KV 读取速度、可装下的权重与 KV 条目——「发动机/输油管/油箱」。
6. **Decode（batch 1）极度浪费算力**：每 token 3.3 ms 中数学只需 0.016 ms，Tensor Core 99.5% 空闲；在 H200 roofline 上约 5 TFLOP/s，即峰值的 **0.5%**——kernel 时间 ≈ max(字节÷带宽, FLOPs÷峰值)。
7. **Prefill 计算受限**：2,048 token 的 prompt 约 33 ms，每个权重喂 2,048 个 token，Tensor Core 以约 33 TFLOP 近峰值忙碌；大 GEMM 坐在算力屋顶上，只有更快的数学或更少的 FLOPs 有用。
8. **Roofline 脊点 = 峰值÷带宽**（H200 ≈ 206 FLOP/B）：脊点左侧内存受限（速度=带宽×强度）、右侧计算受限。
9. **常见强度**：向量加 1/(3b)、decode GEMV ≈ 2/b、decode attention = 2/b、N×N GEMM = 2N/(3b)；BF16 下前两者都是 1 FLOP/B 量级。
10. **Batching 只救权重、救不了 KV**：batch 把权重 GEMV 强度推向脊点，但 decode attention 恒在 2/b；长上下文更糟——Llama 3 8B、batch 16 时每 step 读 18.2 GB（1K）到 84.8 GB（32K），时间 3.8 ms → 17.7 ms，权重固定 16.1 GB，KV 128 KiB/token 随 batch×L 增长。
11. **低精度把脊点推右**：H200 BF16 脊点 206、FP8 412；B200 FP4 1,125、MI355X FP4 1,259、Rubin FP4 1,591（约 1,600 FLOP/B）——从 A100 到 Rubin BF16 算力涨约 13 倍而带宽只涨约 9 倍，decode 越来越带宽受限。
12. **Tensor Core 快在**：专用矩阵乘加通路、一条 mma = 2,048 乘加（64× FMA）、操作数跨行列复用、低精度+高精度累加；矩阵乘法占 LLM FLOPs 99%+，softmax/norm 走 FP32 核心。H200 峰值：FP32 标量 67、FP16 标量 134、TF32 495、BF16 989 TFLOP/s。
13. **内存层次**（H200）：寄存器（3 操作数/核/clk）→ 共享内存/L1 256 KB（约 30–40 周期，128 B/clk/SM，全片约 33 TB/s）→ L2 50 MB（约 250 周期，约 12 TB/s）→ HBM3e 141 GB（约 500 周期，4.8 TB/s）→ 主机/对端 GPU（微秒级，NVLink 450 GB/s 每方向，PCIe 5.0 约 64 GB/s）。
14. **Little's law：带宽 = 在飞字节 ÷ 延迟**：H200 的内存管道长 250 ns，每 SM 需约 9 KB 在飞才能跑满 4.8 TB/s（4.8 TB/s × 250 ns ÷ 132 SM）；朴素 4 B load 只有 45%（2.2 TB/s）。手段：16 B 向量 load、每线程 4 个独立 load、TMA。每代需要更多在飞字节：H200 1.2 MB/9 KB → B200 2.0 MB/14 KB → Rubin 5.5 MB/25 KB（每 SM）。
15. **Hopper 新武器**：合并访存（32×4B → 1 个 128 B 请求）、16 B 向量 load（512 B/指令）、cp.async（不经寄存器）、**TMA**（一个线程发起整块 128×64 tile 拷贝，硬件生成地址，一条指令几十 KB 在飞）、**TMA multicast**（cluster 最多 8 个 block 共享一次 L2 读取）。
16. **Blackwell**：**TMEM 256 KB** 承接 Tensor Core 结果，腾出寄存器维持更多 load 在飞；**2-SM MMA** 两个 SM 合做一次乘法、tile 翻倍、每 SM 只取半块。
17. **互连三级**：HBM 4.8/8 TB/s ≫ NVLink 900 GB/s/1.8 TB/s ≫ RDMA 50/100 GB/s（HGX H200 8-GPU 节点 vs GB200 NVL72 机架，9 行 ×（4 GPU + 2 CPU））；HGX 配 8 个 400 Gb/s 网卡。
18. **GPU 二十年**：2006–17 图形→通用计算（Tesla/CUDA 起步，Fermi 缓存，Pascal HBM2+NVLink，Volta 首代 Tensor Core），2018–26 计算→低精度 AI 引擎（Ampere TF32/BF16/稀疏，Hopper FP8/TMA/cluster，Blackwell FP4/TMEM/NVL72，B300 288 GB + 15 PF NVFP4，Rubin HBM4/NVLink 6）；G80→B300 峰值算力约 43,000 倍而带宽约 90 倍。
19. **非 NVIDIA 阵营**：AMD MI355X（8 die chiplet、256 MB Infinity Cache、64 线程 wavefront、5.0 PF FP8、288 GB、ROCm/HIP/hipify）；Google TPU Ironwood（weight-stationary 脉动阵列，3D torus 9,216 芯片，4.6 PF FP8、192 GB、7.4 TB/s，JAX/XLA/Pallas）；AWS Trainium3（8 NeuronCore、32 MB 软件管理 SRAM、无硬件缓存、2.5 PF MXFP8、Neuron SDK/NKI）；以及 Cerebras WSE-3（44 GB SRAM、整晶圆一芯片）、Groq LPU（230 MB SRAM、70B 8-bit 约需 300 片）、Microsoft Maia 200（272 MB SRAM + 216 GB HBM3e、仅限 Azure）。
20. **一句话主线**：LLM 的 decode 是强度 ≈ 1 FLOP/B 的带宽受限 GEMV，在 H200 上只跑峰值算力的 0.5%；一切优化（batching、量化、压缩 KV、提高在飞字节、NVLink 域内的并行）都是在提高算术强度或减少必须移动的字节——这正是后续「LLM Serving III: batching, paging, and parallelism」的出发点。
