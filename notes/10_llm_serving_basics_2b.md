# 第10讲：LLM 服务基础 IIb（LLM Serving Basics II: Intro to GPUs）

> 原课程：Harvard CS2680 *Modern AI Systems: Agents and System Optimizations*（Harvard MaDSys，course.agentic-system.org），讲师 Juncheng Yang，第 10 讲（PDF 页 1–44，幻灯片编号至 54）。

## 本讲概览

本讲的正式标题是 **LLM Serving Basics II: Intro to GPUs**：在讲解 LLM 服务系统之前，先补齐 GPU 这一底层硬件与编程模型的知识，为后续的性能分析打基础。课程明确说明不会深入细节（"We will not go into details"），目标是帮大家建立直觉（intuition）。全讲分三大部分：**GPU 编程**（异步执行、SIMT 线程层次、torch.compile 图编译器、Triton/TileLang/CuTe 等 tile 语言与抽象层次、编译到 SASS 的流程）、**GPU 效率与利用率**（MFU、MBU 两套效率指标，Nsight 剖析工具，计数器判读决策树）、**GPU kernel 优化的最新进展**（kernel 融合、FlashAttention 1→4、persistent kernels、split-KV、CUDA Graphs、PDL、megakernel、融合集合通信、MoE all-to-all、用 AI agent 写 kernel），最后还有一页 AI 硬件挑战（网络、可靠性、功耗、水耗）与一份"优化 GPU 代码"的选读材料。

## 课程安排（Logistics）与今日计划

### 作业与课程事务

- **Assignment 4 今天发布，两周半后截止**。目标（Goal）：学会对性能（performance）、瓶颈（bottlenecks）进行推理并迭代改进（improve iteratively），理解真实世界 workload 与合成 benchmark（synthetic benchmarks）有何不同。
- **写作报告（write-up）很重要**，代码只需要很少几行（a small number of lines of code）——强调分析能力而非编码量。
- 排行榜（leaderboard）提交**没有补交（late day）**；**不要一次占用超过一块 GPU**。
- 对系统编程（systems programming）经验有限的同学来说难度较高（Hard）。
- 项目提案（Proposal）下周三（**10 月 28 日**）截止；格式与页数不限；**不要上传 AI 生成的内容**。

### 今日计划（Plan for today）

1. Introduction to GPU for LLM serving（脚注[1]：不会深入细节，目标只是帮助大家建立直觉）
2. GPU basics（GPU 基础）
3. GPU architecture（GPU 架构）
4. GPU programming and recent kernel advances（GPU 编程与近期 kernel 进展）

## GPU 编程（GPU Programming）

### GPU 代码是异步执行的

这是理解 GPU 编程的第一条心智模型。整个系统分为两侧：

- **Host（宿主侧）**：CPU + DRAM，运行 `main()`；
- **Device（设备侧）**：GPU + HBM，运行 kernels（内核）。

两侧之间通过 **PCIe Gen5 x16** 互联，带宽约 **64 GB/s**，比 HBM 低 **75 倍**——因此跨 PCIe 的拷贝是昂贵操作，应尽量减少 H→D 传输、尽量让数据留在 GPU 上。

一次典型的 vector add 调用时序：CPU 线程依次执行 `cudaMalloc` → `memcpy H→D`（拷贝输入 a、b 到设备）→ `launch`（发射 kernel）→ 随后继续做其他 CPU 工作 → 最后 `memcpy back`（把结果 c 拷回，这里会等待）。与此同时，GPU 侧的 **Copy engine** 负责把 a、b 拷入、把 c 拷出，**SM**（流多处理器）负责运行 `vec_add` kernel。

图示：该页是一张 CPU 线程 / Copy engine / SM 三条泳道的时间线图，展示 `cudaMalloc`、`memcpy H→D`、`launch`、"other CPU work"、`memcpy back (waits)` 与 GPU 侧 `copy a, b in`、`vec_add kernel runs`、`copy c out` 的并行时间轴。

两个关键推论：

- **Launch 是异步的**：CPU 发射 kernel 后不会等待 GPU 完成，CPU 可以继续干别的事。
- **错误暴露得晚（errors surface late）**：一个 kernel 里的错误（fault）要到下一次同步调用（sync call）时才显现出来——这是 GPU 调试困难的根源之一。

（来源：NVIDIA, CUDA C++ Programming Guide, 2024；PCI-SIG, PCIe 5.0, 2019。）

### Kernel 按单线程编写（SIMT）

CUDA kernel 的编写单位是**一个线程**，采用 SIMT（Single Instruction, Multiple Threads，单指令多线程）模型。以向量加为例：

```cpp
__global__ void add(float* x, float* y, float* out, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;  // Global index
    if (i < n) out[i] = x[i] + y[i];
}
```

每个线程用 **block ID** 与 **thread ID** 算出自己的全局下标 `i = blockIdx.x * blockDim.x + threadIdx.x`，负责计算一个输出元素；边界检查 `i < n` 防止越界。发射（launch）参数示例：`n = 1M` 个元素，每 block **256** 线程，则 `blocks = (n + threads - 1) / threads = 4,096` 个 block（1M ÷ 256 = 4096），这 4,096 个 block 由 GPU 铺到 **132 个 SM** 上执行。

函数限定符（qualifiers）：

| 限定符 | 运行在 | 调用来自 |
|---|---|---|
| `__global__` | device（设备） | host（宿主） |
| `__device__` | device | device |
| `__host__ __device__` | 两者 | 两者 |

**经验法则：block 大小取 32 的倍数**，128–256 线程是典型选择——因为硬件的 warp 恰好是 32 个线程一组（warp 来自线性 tid）。

图示：该页把 4,096 个 block 画成网格（Block 0、Block 1、Block 2、…、Block 4,095，每块含线程 0…255）。以某个线程为例：`blockIdx.x = 2`（哪个 block）× `blockDim.x = 256`（block 大小）+ `threadIdx.x = 1`（block 内槽位）= 全局下标 `i = 513`，该线程随后写入自己对应的元素 `out[513]`；底部一行展示数组元素 0, 1, … 255, 256, 257, … 511, 512, 513, … 767, … 1,048,575 与 block/线程的一一对应。

### Grid / Block / Warp / Thread 层次：block 以 32 线程的 warp 运行在 SM 上

这张幻灯片把**软件概念**映射到**硬件**：

| 软件概念 | 硬件对应 | 说明 |
|---|---|---|
| **Grid**（网格） | 整个 GPU | 一次 kernel 发射的全部 block，散布在 132 个 SM 上 |
| **Block**（块） | 一个 SM | 最多 **1,024** 线程；共享内存（shared memory）在该 block 结束前一直保留在那里 |
| **Warp**（束） | 一个 partition（分区） | **32 个线程锁步（in lockstep）**执行；调度器（scheduler）每个周期发射它 |
| **Thread**（线程） | 一个 core（也叫 **lane**） | 拥有自己的寄存器（registers）、自己的下标；是 warp 中 32 条 SIMT 车道之一 |

要点：GPU 并不像 CPU 那样给每个线程一个独立核心；而是把 32 个线程捆成一个 warp、在 SIMT 分区上锁步执行。这解释了为什么"block 取 32 的倍数"重要——不满 32 的尾部线程会被浪费。

（来源：NVIDIA, CUDA C++ Programming Guide, 2024。）

### 图编译器：torch.compile——你写模型，编译器写 kernel

PyTorch 2 的 `torch.compile` 代表的思路是：**你只写数学，编译器决定怎么落到硬件上**。

- **你决定（You decide）**：用普通 PyTorch（或 JAX）写数学。不碰线程、tile 或内存管理：

```python
import torch

def block(x, w, b):
    h = x @ w + b
    return gelu(h) * 0.5

fast = torch.compile(block, mode="max-autotune")
y = fast(x, w, b)   # 第一次调用时编译
```

- **编译器决定（The compiler decides）**：哪些算子做融合（fuse）、tile 大小（tile sizes）、以及生成哪种 kernel（Triton 或 XLA kernel）。JAX 中对应 `jax.jit(block)`，降低（lower）为 XLA。

- **何时失效（Stops working when）**：控制流（control flow）把图（graph）打断，或者慢的那个算子（slow op）无法被融合。

（来源：Ansel et al., PyTorch 2, ASPLOS 2024；OpenXLA documentation, 2026。）

### Tile 语言：描述"一个 block 的工作"，而不是"一个线程的工作"

| | CUDA C++ | Tile 语言 |
|---|---|---|
| 你写的 | 一个线程的工作（the work of one thread） | 一个数据 tile 的工作（the work of one tile of data） |
| 索引 | `blockIdx × blockDim + threadIdx` | `program_id` + 对 tile 的一个范围 |
| 内存 staging 与同步 | 你自己 stage tile、调用 `__syncthreads()` | 编译器负责 stage 与同步 |
| Tensor Cores | warp 级 MMA 指令 | 对整个 tile 的一次点积 |

**在用的 tile 语言（Tile languages in use）**：

| 语言 | 定位 |
|---|---|
| **Triton** | Python；支持 NVIDIA 与 AMD GPU |
| **Pallas** | JAX kernel，面向 TPU 与 GPU |
| **TileLang** | 构建在 TVM 之上的 Python DSL |
| **ThunderKittens** | C++ tile 模板 |
| **cuTile** | NVIDIA 在 CUDA 中的 tile 模型 |

tile 语言把编程抽象从"逐线程"提升到"逐 tile"：coalescing、共享内存 staging、Tensor Core 调用都交给编译器，大幅降低写出高性能 kernel 的门槛。

（来源：Tillet et al., MAPL 2019；Spector et al., ThunderKittens, 2024；NVIDIA CUDA 13.1, 2025。）

### 【进阶】Triton：每个 program 处理一个数据 tile

> 幻灯片标注 ADVANCED——可略读，或自行深入。

核心抽象：**一个 program = 一个 CUDA 线程 block；它拥有 BLOCK 个元素**。

```python
@triton.jit
def add(x, y, out, n, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offs < n
    a = tl.load(x + offs, mask=mask)
    b = tl.load(y + offs, mask=mask)
    tl.store(out + offs, a + b, mask=mask)
```

- **编译器做剩下的事**：内存合并（coalescing）、共享内存 staging，以及通过 `tl.dot` 调用 Tensor Core 的 MMA。
- **自动调优（Autotuning）挑选 tile**：`@triton.autotune` 会为每种形状（per shape）尝试不同的 BLOCK 大小与 warp 数。

发射方式：

```python
grid = (triton.cdiv(n, 1024),)   # 每个 tile 一个 program
add[grid](x, y, out, n, BLOCK=1024)
```

（来源：Tillet, Kung & Cox, Triton, MAPL 2019。）

### 【进阶】TileLang：你放 tile，编译器映射线程

TileLang 比 Triton 更"显式"：程序员亲自决定 tile 的存储位置与流水级数。

- **你决定**：tile 形状、共享内存 vs 寄存器存储、以及 stages（提前加载多少级 tile）。

```python
@T.prim_func
def mm(A, B, C):
    with T.Kernel(N // bn, M // bm, threads=128) as (bx, by):
        As = T.alloc_shared((bm, bk), "float16")
        Bs = T.alloc_shared((bk, bn), "float16")
        Cl = T.alloc_fragment((bm, bn), "float")
        T.clear(Cl)
        for k in T.Pipelined(K // bk, num_stages=3):
            T.copy(A[by * bm, k * bk], As)
            T.copy(B[k * bk, bx * bn], Bs)
            T.gemm(As, Bs, Cl)
        T.copy(Cl, C[by * bm, bx * bn])
```

- **TileLang 决定**：线程映射（thread mapping）、拷贝指令、swizzle（共享内存布局交错）以及 MMA 调用。
- **适用场景**：GEMM 和需要显式 staging 控制的 attention 变体。

（来源：Wang et al., TileLang, arXiv 2025。）

### 【进阶】CuTe、CUTLASS 与 ThunderKittens：你选 layout、异步拷贝与 warp 角色

这是最底层的"布局/流水"级控制，用于榨取最后一点性能。

- **你决定**：布局（layouts）、TMA 与异步流水（async pipelines）、以及哪些 warp 负责 load、哪些 warp 负责 compute。

CuTe layout 的代数：一个 layout 把坐标（coordinate）映射为偏移（offset）：

```python
row = cute.make_layout((8, 4), stride=(4, 1))
col = cute.make_layout((8, 4), stride=(1, 8))
# (i, j) -> i*4 + j   versus   i + j*8
```

- **库提供的**：拷贝、swizzled 共享内存 tile、TMA box、MMA fragment 这些经过充分测试的构建块（tested building blocks）；同一套代数可以描述每种 GPU 上的 MMA 与 pipeline。
- **适用场景**：让 GEMM 与 attention 冲峰值（peak）的"最后一段路"（the last stretch）。

### 【进阶】不同抽象层次：何时用哪一层

| 层次（Level） | 何时用它 | 代价（Cost） |
|---|---|---|
| 图编译器：`torch.compile`、XLA | 整个模型的默认选择 | 对慢算子几乎没有掌控力 |
| Tile 语言：Helion、Triton、Pallas | 某个算子没被融合或缺失 | 若干小时（Hours）；可跨 GPU 移植 |
| 显式 tile：TileLang | 需要控制 staging | 若干天（Days） |
| 布局、warp 角色：CuTe、CUTLASS、ThunderKittens | GEMM 或 attention 必须达到峰值 | 数周（Weeks）；每个 GPU 代都要重做 |
| 线程：CUDA C++ | 不规则工作：排序、稀疏、图 | 一切都在你自己身上 |

这张表是前面几页的综合（course synthesis）：**抽象越高越省事但掌控力越低；越往下越能冲峰值但工程代价越高且不可移植**。

### 【进阶】所有 GPU 程序最终都编译成 SASS

图示：该页给出四条编译流水线，全部终点是 SASS 机器码：

- **NVCC 设备代码**：device code → NVVM → PTX →（ptxas）→ SASS → fatbinary（fatbin = SASS + PTX）；
- **NVCC 宿主代码**：host code → GCC / Clang / MSVC → host object →（linker）→ executable + fatbin；
- **Triton**：`@triton.jit` → Triton IR → TritonGPU IR →（LLVM）→ LLVM IR → PTX →（ptxas）→ SASS（cubin）；
- **CUDA Tile**：source →（cuTile Python/C++）→ intermediate code（virtual ISA）→ CUDA Tile IR →（tileiras 工具）→ SASS。

**加载时（Load time）**：驱动（driver）优先运行与当前 GPU 匹配的 SASS；若没有匹配的 SASS，则对 PTX 做 JIT 编译并缓存起来。

要点：无论用 CUDA C++、Triton 还是 cuTile 写，中间表示各不相同，但都经由 PTX + ptxas 到达同一份 SASS；PTX 作为可移植的中间层保证了跨 GPU 代际的兼容（以性能损失为代价）。

## GPU 效率与利用率（GPU efficiency and utilization）

### 推理中的 MFU：模型 FLOPs 利用率

**MFU（Model FLOPs Utilization）= 实际达到的模型 FLOP/s ÷ 峰值**（peak）。注意分子只统计"模型前向"的浮点量，不含通信、冗余计算等开销。

幻灯片给出的例子：**Llama 2 70B 跑在 8 块 H100 上**：

- **每 token 的模型 FLOPs**：约 **2N**（仅前向，forward pass only）≈ **140 GFLOP** / 生成 token；
- **每 GPU 实际吞吐**：**3,040 tok/s × 140 GFLOP ≈ 426 TFLOP/s**；
- **峰值**：GPU 的 dense Tensor Core 速率（1,979 TFLOP/s）；
- **MFU = 426 ÷ 1,979 ≈ 22%**。

**经验法则（Rule of thumb）**：训练（training）MFU 约 **35–45%**；推理中 prefill 约 **40–60%**，decode 约 **10–40%**。decode 之所以低得多，是因为它带宽受限（见下节 MBU）。

### MFU 低的四个原因

1. **内存受限的 kernel（memory-bound kernels）**：norms、softmax 以及优化器步骤（optimizer step）是按带宽（bandwidth）而非 Tensor Core 峰值在跑；
2. **通信（Communication）**：张量并行、流水线并行、数据并行的传输（tensor-, pipeline- and data-parallel transfers）藏在计算背后，不产生模型 FLOPs；
3. **流水线气泡（Pipeline bubbles）**：每个 batch 填充与排空流水线（fills and drains）时，各 stage 空闲；
4. **重计算（Recomputation，训练特有）**：activation checkpointing（激活检查点）重新跑一遍前向，这部分工作量 MFU 根本不计入。

幻灯片总结：**MFU 把硬件能力（hardware capability）与软件成熟度（software maturity）区分开来**——MFU 低通常说明软件/系统还有优化空间，而不是硬件不行。

（来源：Chowdhery et al., PaLM, JMLR 2023；Korthikanti et al., Activation Recomputation, MLSys 2023。）

### MBU：decode 的效率看"每秒搬运多少字节"，不看 FLOPs

**MBU（Model Bandwidth Utilization）= 实际 bytes/s ÷ 峰值 HBM 带宽**。decode 阶段每生成一个 token 都要把全部权重读一遍（外加 KV cache），FLOPs 很少，瓶颈在内存带宽，所以用 MBU 评价 decode 更合适。

例子：**Llama 3 8B，BF16，batch 1，H200**：

- **每个 decode step 的字节数**：读取全部权重 + KV cache = **每 token 读 16 GB**；
- **200 tok/s 时**：200 × 16 GB = 3.2 TB/s，**3.2 ÷ 4.8（H200 峰值）≈ 67%** MBU。

**评价一个 serving 系统的其他指标**：

| 指标 | 说明 |
|---|---|
| Tokens/s per GPU | 每 GPU 吞吐 |
| Throughput at a stated latency target | 在给定延迟目标（如 p50）下的吞吐 |
| Time per output token | 每个输出 token 的时间（TPOT） |
| Energy per token | 焦耳 = 平均整板功耗（average board power）÷ tokens/s |
| Cost per million tokens | $ / GPU-hour ÷ (tokens/s × 3,600) × 10⁶ |

**经验法则：prefill 和训练报 MFU，decode 报 MBU。**

（来源：Databricks, LLM Inference Performance Engineering, 2023。）

### 剖析顺序：先看时间线，再看 kernel

- **Nsight Systems（nsys）**——看全局时间线：

```
nsys profile -o run ./app
```

  显示（Shows）：一条包含 CPU 线程、CUDA API 调用、拷贝（copies）、kernel 与 stream 的统一时间线。
  能发现（Finds）：空闲间隙（idle gaps）、被串行化的 stream、launch 开销。

- **Nsight Compute（ncu）**——钻到单个 kernel：

```
ncu --set full -k vec_add ./app
```

  显示：把每个 kernel 重放（replayed）以收集计数器：speed of light（性能上界）、内存流量、warp stalls（停顿原因）、热行（hot lines）。
  能发现：**某一个 kernel 为什么慢**。注意：replay 得到的计时只用于对比，不代表真实端到端耗时。

**工作流口诀：`nsys` 找到慢的区段 → `ncu` 解释某一个 kernel → 改一件事（change one thing）→ 再测一遍（measure again）。**

直觉（Intuition）：先扫"整个身体"（timeline）找出时间花在哪，再放大（zoom in，kernel）看它为什么慢。

### GPU 利用率计数器

| 计数器（Counter） | 测量什么 |
|---|---|
| `nvidia-smi` utilization | 至少有一个 kernel 在运行的时间占比 |
| SM active | SM 有 warp 驻留（resident）的周期占比 |
| SM occupancy | 驻留 warp 数 ÷ 最大 warp 数（所有 SM） |
| Tensor pipe active | Tensor Core 忙碌的周期占比 |
| DRAM active | HBM 在搬数据的周期占比 |

用 DCGM 一行命令即可同时观测这 5 个计数器（每个计数器一列）：

```
dcgmi dmon -e 203,1002,1003,1004,1005
```

（来源：NVIDIA, DCGM User Guide: profiling metrics, 2026。）

### 读计数器：找出到底哪个单元在忙

幻灯片给出一棵三段式决策树：

1. **GPU 忙吗？** 看 `nvidia-smi` 是否 100%。
   - **否（No）**→ GPU 在 kernel 之间空闲（idle between kernels）→ 下一步：用 **Nsight Systems 时间线**排查；可用 **CUDA graphs** 消除间隙。
2. **SM 忙吗？** 看 `SM active` 是否高。
   - **否（No）**→ 线程 block 太少（too few thread blocks）：CPU launch 开销大，或工作量填不满所有 SM → 下一步：**加大 batch、每个 kernel 放更多 block**。
3. **哪个单元忙？** 对比 `DRAM active` 与 `Tensor pipe active`：
   - **DRAM active 高** → **内存受限（memory-bound）**→ 用 **MBU** 评判；
   - **Tensor pipe active 高** → **计算受限（compute-bound）**→ 用 **MFU** 评判；
   - **两者都低** → **延迟受限（latency-bound）**→ 用 **Nsight Compute** 深入。

核心提醒：`nvidia-smi` 显示 100% **只说明"有 kernel 在跑"**，并不代表 GPU 被有效利用——必须继续往下读 SM / Tensor / DRAM 计数器。

### GPU 效率小结

1. **MFU** = 实际模型 FLOP/s ÷ dense 峰值；用它评判 prefill 与训练。
2. **MFU 低的原因**：通信、流水线气泡、内存受限 kernel、重计算，这些都会吃掉峰值。
3. **MBU** = 实际 bytes/s ÷ 峰值 HBM 带宽；用它评判 decode。
4. **计数器**：`nvidia-smi` 100% 只意味着有 kernel 在跑；要读 SM、Tensor、DRAM 的活跃度才知道真相。

## GPU Kernel 优化的最新进展（Recent Advances in GPU Kernel Optimizations）

### kernel 在三个地方丢失 GPU 时间

| 位置 | 丢失时间（Lost time） | 进展（Advances） |
|---|---|---|
| **1. kernel 内部**（一个 SM 内：MMA、exp、load） | Tensor Cores 在等待 load、softmax 和 exp | FlashAttention、warp specialization、FlashAttention-4 |
| **2. 跨 SM** | SM 在不均衡的轮次（uneven rounds）和 kernel 之间闲置 | Persistent kernels、split-KV、CUDA Graphs、PDL、megakernels |
| **3. 跨 GPU** | GPU 之间互相等待对方的数据 | 融合集合通信（fused collectives）、MoE all-to-all overlap |

另外还有一个"人"的维度——**写 kernel 本身丢失工程师的时间（Lost engineer time）**：每代新 GPU 都需要重新手工调优（hand-tuned）kernel；进展方向是**会自己写 kernel 并测试的 AI agent**（write → test 循环）。

### Kernel 融合：纵向串步骤，横向并操作

**未融合（Unfused）的例子**：对 1 GB 的 FP32 数据做 scale、加 bias、ReLU 三步，写成三个 kernel：每一步都要往返 HBM（read x → write t → read t → write u → read u → write y），总耗时 **1.25 ms**。

**融合（Fused）后**：一个 kernel，每个中间结果都留在寄存器里（read x → write y），**0.42 ms，HBM 流量减少 3 倍**。

- **纵向融合（Vertical fusion）**：生产者把自己的输出直接喂给同一个 kernel 内的消费者。例：GEMM + bias → GELU 一个 kernel 完成。省掉 HBM 往返。典型例子：GEMM epilogue（后处理）、LayerNorm、带 mask 的 softmax。
- **横向融合（Horizontal fusion）**：共享同一输入的操作合并为一个 kernel：`x·W_q`、`x·W_k`、`x·W_v` 合并为一次 `x·[W_q W_k W_v]` GEMM——x 只读一次，只 launch 一次。省掉 launch 次数与对 x 的重复读取。典型例子：QKV projection、FFN 的 gate + up。
- **编译器两件事都干**：`torch.compile` 把纵向链融合进一个 Triton kernel；模型代码通常手工把 QKV、gate + up 的权重拼接（concatenating）起来做横向融合。

图示：左侧未融合的"read x / write t / read t / write u / read u / write y"六段 HBM 流量条与 1.25 ms；右侧融合后的"read x / write y"两段与 0.42 ms；中间是 GEMM+bias+GELU 纵向链和 x·W_q/k/v 合并为 x·[W_q W_k W_v] 的横向示意。

### FlashAttention：分 tile 计算 attention，让 S 永不落 HBM

- **问题**：标准 attention 会把 n × n 的分数矩阵 **S** 及其 softmax 结果 **P** 写进 HBM，再读回来。在 **8K token** 时，每一层每个头都有 **67M（6700 万）个分数**全部要穿过 HBM——这是巨大的、随序列长度平方增长的流量。
- **解决**：把 Q、K、V 切成 tile，放在芯片上（on chip）一个 block 的共享内存和寄存器里计算：`S tile = Q·Kᵀ`，做 softmax 时维护**运行最大值（running max）与运行和（running sum）**（online softmax），乘以 V 累加到 O tile；对每一个 K、V tile 重复这个过程——**S 和 P 永远不出芯片**（never leave the chip）。
- 结果：整个 kernel 只需**读一次 K、V，写一次 O**（read K, V once; write O once），把注意力从"内存受限"拉回到"计算受限"。

（来源：Dao et al., FlashAttention, NeurIPS 2022；Dao, FlashAttention-2, ICLR 2024。）

### 【进阶】从 FlashAttention 到 FlashAttention-4

每一代 FlashAttention 都是针对新硬件上"下一个瓶颈"的修补：

| 版本（年份 · 硬件） | 瓶颈（Bottleneck） | 对策（Fix） | 效果 |
|---|---|---|---|
| **FlashAttention**（2022 · A100） | HBM 流量：n × n 分数矩阵被写出再读回 | Q、K、V tile 进共享内存；online softmax | attention 快 **2–4×**；内存随长度**线性**增长 |
| **FlashAttention-2**（2023 · A100） | 占用率低（low occupancy）：每个 head 一个 block，很多 warp 在 load 与算 softmax；非矩阵乘 FLOPs | 把工作在**序列维度**上切分（split work across the sequence）；减少 rescale 次数 | 约为 FA1 的 **2×**；最高达 A100 峰值的 **~70%** |
| **FlashAttention-3**（2024 · H100） | Tensor Cores 在等待，而 exp 单元却不缺活：softmax（exp）成为瓶颈 | **TMA + warp specialization**；把 softmax 与 GEMM 重叠（overlap）；FP8 | FP16 下约达 H100 峰值的 **75%** |
| **FlashAttention-4**（2025 · B200） | Tensor Cores 翻倍了，exp 单元没有翻倍 | **TMEM 累加器**；把部分 exp 放到 **FMA 单元**上 | 在 B200 上**比 cuDNN attention 更快** |

（来源：Dao et al. 2022；Dao 2023；Shah et al. 2024；Dao et al. 2025。）

### 【进阶】Persistent kernels：每个 SM 一个 block，循环处理很多 tile

- **问题**：一次矩阵乘被切成 **160 个输出 tile**，每个 tile 一个线程 block。GPU 有 **132 个 SM**，所以 block 要分两轮跑。第一轮 132 个 block 填满全部 SM；第二轮只剩 **28 个 block：104 个 SM 干等**。而且每个 block 只为一个 tile 服务，setup（初始化）开销被重复付出。
- **解决**：**persistent kernel**——发射 132 个 block（每 SM 一个），让它们**驻留不动、逐个领取 tile**（tile 0 math → write tile 0 → tile 1 math → write tile 1 → …）。没有空闲轮次，setup 只做一次。
- **Stream-K**（另一种思路）：把 tile 切成更小的片段，让所有 SM **同时完成**，避免轮次不均。
- 要点：`CUTLASS` 和 `DeepGEMM` 都这么干。

（来源：Osama et al., Stream-K, PPoPP 2023；NVIDIA CUTLASS 3.x, 2024。）

### 【进阶】Split-KV：让 decode 在所有 SM 间均衡

- **问题**：decode 每个请求只有一个 query token，只按 batch × heads 切分会留下大量 SM 空闲；而且各请求的 **KV 长度相差可达 100 倍**，它们的 KV 页（pages）又零散地散布在 HBM 中。
- **解决（图示：KV pages per request）**：把每个请求的 KV 页按 block-sparse 行切分（如 **每个 SM 分 4 页**，R1/R2/R3 的请求页分布在 SM0–SM3 上），各 SM 并行计算部分结果，再**按请求合并部分和 (m, ℓ, O)**——与 online softmax 相同的合并方式。网格（grid）固定不变，因此对 **CUDA Graph 安全（CUDA Graph-safe）**。
- 要点：**FlashInfer（MLSys 2025 最佳论文）**把 block-sparse KV 与 JIT 特化 kernel 及该调度器组合在一起；**vLLM 与 SGLang 都使用它**。

（来源：Dao et al., Flash-Decoding, 2023；Ye et al., FlashInfer, MLSys 2025。）

### 【进阶】CUDA Graphs：launch 只记录一次，一次调用重放全部

- **问题**：decode 一个 token 要跑**几十个（dozens of）小 kernel**；每次 launch 要花几微秒（few µs）的 CPU 与驱动时间，于是 GPU 在 kernel 之间只能等。
- **解决（图示：CPU/GPU 双泳道时间线）**：普通 stream 是"每个 kernel 一次 CPU launch"，GPU 之间有间隙；CUDA Graph 模式下 CPU **一次调用重放全部 kernel**——无间隙、更早完成。API 如下：

```cpp
cudaStreamBeginCapture(s, mode);   // 记录一步
    …launch the kernels…;
cudaStreamEndCapture(s, &g);
cudaGraphInstantiate(&e, g, 0);
cudaGraphLaunch(e, s);
```

- 要点：**把一个 decode step 捕获一次，之后每个 token 重放**；**vLLM 与 SGLang 都这么做**。

（来源：NVIDIA CUDA Programming Guide, CUDA Graphs, 2025。）

### 【进阶】PDL（Programmatic Dependent Launch）：提前启动下一个 kernel

- **问题**：在 stream 中，kernel B 要等 kernel A **完全排空并刷新内存**（drained and flushed）之后才会启动。decode 每个 token 跑很多 µs 级的小 kernel，launch 延迟、prologue（序言）以及每个 kernel 的尾部（tail）累积起来就很可观。
- **解决（图示）**：默认 stream 顺序是 Kernel A 完整执行 → 间隙（gap）→ Kernel B 的 prologue。启用 PDL 后，Kernel A 执行 `cudaTriggerProgrammaticLaunchCompletion()`（sync A）提前触发，**Kernel B 的 prologue 提前开始**（加载权重等准备工作与 A 的收尾重叠），随后 B 在 `cudaGridDependencySynchronize()`（wait）处等待 A 真正完成再进入计算。
- 要点：PDL 需要 **Hopper 或更新架构（SM 9.0）**；它削减 decode 中每个 kernel 之间的间隙，并且**可以与 CUDA Graphs 配合使用**。

（来源：NVIDIA CUDA Programming Guide §4.5, 2025。）

### 【进阶】Megakernel：一次 launch 跑完整模型

- **问题**：每个 op 一个 kernel，意味着**每个 launch 边界都有气泡**。Llama-3.2-1B 的 batch-1 decode 每层要跑约 **7 个 kernel**（Norm、QKV、Attn、O-proj、FFN），共 **16 层**。每个边界处 GPU 都要先把上一个 kernel 排空、下一个 kernel 再重新加载权重，只跑到 H100 带宽的 **~50%**。
- **解决**：**megakernel**——一个巨型 kernel 内部，**下一个 op 的权重在当前 op 计算期间就提前加载**（对每个 token 都是如此），launch 边界消失。内部机制包括：on-GPU interpreter（GPU 上的解释器）、每个 SM 一条指令队列（per-SM instruction queue）、用于权重的分页共享内存（paged SMEM for weights）、用于依赖关系的全局计数器（global counters for dependencies）。
- 要点：**Hazy Research 的 megakernel 在 batch 1 时达到 H100 带宽的 78%，每用户吞吐约为 SGLang 的 1.5 倍**；**Mirage MPK** 可以自动编译出这样的任务图。

（来源：Spector, Juravsky et al., *Look Ma, No Bubbles!*, Hazy Research 2025；Mirage MPK, 2025。）

### 【进阶】融合集合通信：把 TP 通信藏进 GEMM

- **问题**：张量并行（tensor parallelism）把每层切到 8 块 GPU 上，每个分片 GEMM 前面要一次 **AllGather**、后面要一次 **ReduceScatter**。若作为独立 kernel 运行，GEMM 要等整个集合通信完成才能开始/结束。
- **解决（图示：8 GPU 的 t0–t5 时间线）**：
  - 独立 kernel：先跑完整 GEMM（all tiles），再单独跑 ReduceScatter，通信完全暴露。
  - 融合后：**每个 tile 的 epilogue 直接写往它所属的那块 GPU**；AllGather + GEMM 时，**tile 在对应行到达后立即开始**（tiles start as their rows arrive）；peer 之间通过 **NVLink 或 NVSHMEM** 写数据，**不需要额外的 kernel**，计算与通信在 NVLink 上重叠。
- 要点：**Flux** 最高可隐藏 **96% 的通信**，在 8 GPU 上比 vLLM **prefill 快至多 1.66×、decode 快至多 1.30×**。

（来源：Chang et al., FLUX, arXiv:2406.06858, 2024。）

### 【进阶】MoE all-to-all：让 token 路由藏在计算后面

- **问题**：每个 MoE 层把每个 token 发给其他 GPU 上的 top-8 expert，再收回来（all-to-all）。若串行执行（dispatch → experts → combine → 下一层），dispatch 和 combine 期间 Tensor Cores 空闲，而 NCCL kernel 还会占用 SM，把 SM 从计算上抢走。
- **解决（图示：SMs / Network 双泳道）**：**DeepEP 用两个 micro-batch 重叠流水**——Attn A、Attn B 期间分别进行 Dispatch A / Dispatch B，Experts A / Experts B 与 Combine A / Combine B 交错，网络传输与专家计算完全重叠。基于 hook 的传输跑在 **NIC 上，不占用 SM**；**dispatch 用 FP8 压缩、combine 用 BF16**；并支持 **NVLink → RDMA 转发**（同节点 NVLink 收数后转发到远端）。
- 要点：**DeepEP 在同节点 NVLink 上维持约 153 GB/s 的 dispatch 带宽，跨节点 RDMA 约 43 GB/s，接近链路峰值**。

（来源：DeepSeek-AI, DeepEP, 2025；DeepSeek-V3, arXiv:2412.19437。）

### 【进阶】Agent 成为新的编译器

- **问题**：每一代新 GPU（TMA、TMEM、FP4）和每一种 attention 变体都需要新的手工调优 kernel，而会写这类 kernel 的工程师很少。
- **解决（图示：闭环流水线）**：agent **写 kernel**（CUDA、Triton、CuTe DSL）→ **编译**（nvcc、ptxas，把报错作为反馈）→ 形成**反馈循环**（feedback loop）→ **剖析**（Profile：在多种 shape 上测运行时间、跑 Nsight 计数器）→ **校验**（Check：与 PyTorch 参考实现对比；静态检查会拒绝有竞态（racy）的调度）。
- 两个告诫：**生成的 kernel 可能只是"看起来快"**——通过弱测试或钻测试框架（harness）的空子；因此用 **fast_p** 指标衡量：正确且比 PyTorch 快 p 倍以上的任务占比（share of tasks that are correct and more than p× faster than PyTorch）。

（来源：Ouyang et al., KernelBench, 2025；AutoMegaKernel, arXiv:2606.09682, 2026。）

### Kernel 优化进展小结

1. **kernel 内部：喂饱 Tensor Cores。** 融合 epilogue；FP8/FP4 按 block 做 scale；把 warp 拆成生产者/消费者；把工作从最慢的单元上挪走。
2. **跨 SM 与跨 launch：消灭空闲时间。** persistent CTA 与 split-KV 均衡 SM；PDL 与 megakernel 封住 kernel 之间的间隙。
3. **跨 GPU：隐藏通信。** 把张量并行集合通信融进 GEMM tile；让 MoE all-to-all 与专家计算重叠。
4. **写 kernel：自动化搜索。** 让 agent 写并剖析候选 kernel；用多种 shape 上的正确性检查决定谁留下来。

## AI 硬件挑战（Challenges in AI Hardware）

这一页从系统视角列出四组挑战（幻灯片编号 48）：

| 维度 | 关键数字 |
|---|---|
| **网络（Networking）** | 节点外（off-node）慢 **9 倍**：KV-cache 交接，32K token 的 Llama 3 70B prompt——NVLink（H100）上 **24 ms**，400G NIC 上 **215 ms** |
| **可靠性（Reliability）** | **每 3 小时 1 次故障**¹；Llama 3 训练 419 次中断的原因构成：HBM3 内存 **30%**、GPU 故障 **8%**、网络 **17%** |
| **功耗（Power）** | 每机架功耗²是普通机架的 **8 倍**：Conventional **15 kW**、HGX B200 **60 kW**、GB200 NVL72 **120 kW** |
| **冷却与水（Cooling and water）** | GB200 NVL72 机架需要液冷²；训练 GPT-3 耗淡水 **700,000 L**³；2027 年预计 AI 抽水量 **4.2–6.6B m³**³ |

脚注：¹ *The Llama 3 Herd of Models*；² *NVIDIA HGX Platform: Data Center Physical Requirements Guide*；³ *Making AI Less "Thirsty"*。

图示：该页以四象限版式呈现上述四组指标，含 KV-cache 交接在 NVLink 与 400G NIC 上的时间条、中断原因饼图（30%/8%/17%）、三档机架功耗柱状图（15/60/120 kW）与液冷机架照片。

## 下一讲（Next class）与选读

- **Next class**（幻灯片 49）：预告下一讲的过场页，正文为图像，无文本内容。
- **Optional reading：Optimize GPU code**（幻灯片 50）：以下为四页选读材料，把 GPU 代码优化的技巧系统化。

### 优化 GPU 代码：四个可叠加的目标

| 目标 | 含义 | 例子 |
|---|---|---|
| **Move less data**（少搬数据） | 每个结果对应的字节数更少 | coalescing（合并访问）、tiling（分块）、fusion（融合） |
| **Hide waiting time**（隐藏等待） | 加载还在飞行的时候让单元继续干活 | async copies（异步拷贝）、warp specialization |
| **Expose more parallelism**（暴露更多并行） | 给每个 SM 足够的独立工作 | Split-K、独立累加器 |
| **Use faster instructions**（用更快的指令） | 同一数学走更便宜的硬件路径 | Tensor Cores、更低精度 |

**它们可以叠加（They stack）**：一个快的 GEMM 会同时合并加载（coalesces loads）、对 tile 做双缓冲（double-buffers tiles）、并使用 Tensor Cores。

（来源：NVIDIA, CUDA C++ Best Practices Guide；NVIDIA, CUTLASS documentation。）

### 优化内存流量：搬更少的字节，让每个字节被复用更多

| 技术 | 核心思想（Core idea） | 例子（Example） |
|---|---|---|
| Memory coalescing（内存合并） | 相邻线程读连续地址 | 线程 i 读 `x[i]`，而不是 `x[32·i]` |
| Shared-memory tiling（共享内存分块） | 一个 block 加载一次，合作线程反复复用 | 矩阵 tile 被多个输出复用 |
| Register tiling（寄存器分块） | 每个线程从寄存器算出多个输出 | 每线程多个累加器 |
| Kernel fusion（kernel 融合） | 中间结果就地消费，跳过 HBM 往返 | matmul + bias + activation 一个 kernel |
| Padding / swizzling（填充/交错） | 改共享内存布局以避免 bank conflict | 转置 tile 32×32 → 32×33 |
| Cache-aware ordering（缓存感知排序） | 让相邻 block 调度到一起以复用已缓存数据 | 把读相同输入的输 tile 分组 |

（来源：NVIDIA, CUDA C++ Best Practices Guide；NVIDIA, CUDA C++ Programming Guide。）

### 隐藏等待、暴露并行：让每个 SM 持续发射工作

| 技术 | 核心思想 | 例子 |
|---|---|---|
| Async copies + double buffering（异步拷贝 + 双缓冲） | 计算当前 tile 的同时加载下一个 tile | GEMM 中交替使用两块共享内存缓冲 |
| Instruction-level parallelism（指令级并行） | 独立指令在前序指令等待时继续发射 | 多个累加器，而不是一条依赖链 |
| Warp specialization（warp 特化） | 不同 warp 承担流水线的不同角色 | 生产者 warp 负责 load；消费者 warp 跑 MMA |
| Split-K / split reductions（切分归约） | 把长归约摊到更多 worker 上，最后合并 | decode 时把长 KV 序列切给多个 block |
| Warp-level communication（warp 级通信） | warp 内寄存器到寄存器交换数值 | 基于 shuffle 的 warp sum 或 max |

**代价（The cost）**：split-K 多出一个合并（merge）步骤；流水化（pipelining）要多缓冲区和更多同步。

（来源：NVIDIA, CUTLASS documentation；NVIDIA, CUDA C++ Programming Guide。）

### 更便宜的计算：同一数学跑在更快的指令上

| 技术 | 核心思想 | 例子 |
|---|---|---|
| Tensor Core mapping（Tensor Core 映射） | 把矩阵运算整形为硬件支持的 tile 与布局 | 用 MMA 指令替代标量 FMA |
| Lower precision（降低精度） | 存储与搬运的字节更少；硬件支持处算得更快 | FP16/BF16 输入 + FP32 累加 |
| Unrolling + specialization（展开 + 特化） | 结构在编译期固定，去掉运行时工作 | 为某个 head dim 或某种 mask 类型专门构建 kernel |
| Less branch divergence（减少分支发散） | 让 warp 内的线程走同一条路径 | 把控制流相似的任务分组 |
| Autotuning（自动调优） | 对每种 workload 形状实测各种变体 | 搜索 tile 大小、warp 数、流水深度 |

幻灯片特别指出这是**两个独立的选择维度（Two separate choices）**：Tensor Cores 需要"合身"（fitting）的形状，而精度必须在准确的前提下降低。

（来源：NVIDIA, CUDA C++ Programming Guide；NVIDIA, CUTLASS documentation。）

## 核心要点

1. 本讲（LLM Serving Basics II: Intro to GPUs）的目标是为 LLM serving 建立 GPU 直觉，不深入细节；Assignment 4 今天发布、两周半后截止，重点是**推理性能与瓶颈的写作分析**，代码量很少。
2. GPU 编程基础：第一心智模型是**异步**（launch 后 CPU 不等、错误在下次同步才暴露；两侧经 **PCIe Gen5 x16 ~64 GB/s，比 HBM 低 75 倍**）；kernel 按单线程编写（SIMT，`i = blockIdx.x * blockDim.x + threadIdx.x`，1M 元素 × 256 线程/block → 4,096 block 铺在 132 SM 上，block 取 32 的倍数）；软件/硬件映射为 Grid=整个 GPU、Block=一个 SM（≤1,024 线程，共享内存驻留至结束）、Warp=一个分区（32 线程锁步）、Thread=一个 lane（独立寄存器）。
3. **torch.compile** 代表"你写数学、编译器写 kernel"：编译器决定算子融合、tile 大小、生成 Triton/XLA kernel；控制流打断图或慢算子无法融合时失效；JAX 对应 `jax.jit` → XLA。
4. **tile 语言**（Triton、Pallas、TileLang、ThunderKittens、cuTile）把编程单位从"一个线程"提升到"一个数据 tile"：`program_id` + tile 范围，staging、同步、Tensor Core 点积交给编译器。
5. 抽象层次与代价成反比：图编译器（掌控力最低、默认用）→ tile 语言（数小时、可移植）→ 显式 tile TileLang（数天）→ CuTe/CUTLASS 布局与 warp 角色（数周、每代 GPU 重来）→ 原始 CUDA C++（不规则工作，全靠自己）。
6. 所有 GPU 程序最终编译为 **SASS**：NVVM/PTX、Triton IR、CUDA Tile IR 殊途同归；驱动加载时优先匹配 SASS，否则 JIT 编译 PTX 并缓存。
7. **MFU = 实际模型 FLOP/s ÷ dense 峰值**：Llama 2 70B 在 8×H100 上 3,040 tok/s × 140 GFLOP ≈ 426 TFLOP/s，MFU ≈ 426/1,979 ≈ **22%**；经验值：训练 35–45%、prefill 40–60%、decode 10–40%。
8. MFU 低的四大来源：内存受限 kernel（norm/softmax/optimizer step）、通信（张量/流水/数据并行）、流水线气泡、训练重计算（activation checkpointing）——MFU 分离了硬件能力与软件成熟度。
9. **MBU = 实际 bytes/s ÷ 峰值 HBM**：Llama 3 8B BF16 batch 1 在 H200 上每 token 读 16 GB，200 tok/s 时 3.2/4.8 TB/s ≈ **67%**；经验法则 **prefill/训练报 MFU，decode 报 MBU**；其他指标：每 GPU tokens/s、给定延迟目标（p50）下的吞吐、TPOT、每 token 能耗、每百万 token 成本。
10. 剖析顺序：**nsys 看时间线**（找空闲间隙、串行 stream、launch 开销）→ **ncu 钻单 kernel**（speed of light、内存流量、warp stalls；replay 计时仅供对比）→ 改一件事 → 再测。
11. 计数器判读树：`nvidia-smi` 100% 只说明有 kernel 在跑 → 看 SM active（低则 block 太少：加 batch/加 block）→ 对比 DRAM vs Tensor pipe active（DRAM 高=内存限用 MBU 判；Tensor 高=计算限用 MFU 判；都低=延迟限用 Nsight Compute）；`dcgmi dmon -e 203,1002,1003,1004,1005` 一行观测全部。
12. kernel 丢时间在三层：kernel 内部（Tensor Cores 等 load/softmax/exp）、跨 SM（轮次不均、launch 间隙）、跨 GPU（互相等数据）——加上"写 kernel 丢失工程师时间"这一层。
13. **Kernel 融合**：1 GB FP32 上 scale+bias+ReLU 三 kernel 1.25 ms → 融合后 0.42 ms（HBM 流量减 3 倍）；纵向融合 GEMM epilogue/LayerNorm/softmax，横向融合 QKV、gate+up。
14. **FlashAttention** 分 tile 计算使 S/P 永不落 HBM（8K token 时每层每头 67M 分数），K/V 只读一次、O 只写一次；FA1（2022，HBM 流量→2–4× 提速）→ FA2（2023，序列切分提占用率，~70% A100 峰值）→ FA3（2024，TMA+warp 特化+softmax 与 GEMM 重叠，~75% H100 峰值）→ FA4（2025，TMEM 累加器+部分 exp 上 FMA，B200 上超 cuDNN）。
15. 跨 SM 技术：**persistent kernels**（132 个常驻 block 循环领 tile，160 tile 不再出现 104 SM 空等的第二轮；CUTLASS、DeepGEMM 采用；Stream-K 切细 tile 让所有 SM 齐步完成）、**split-KV**（decode 按 KV 页切分，每 SM 4 页，online softmax 式合并 (m, ℓ, O)，固定网格 CUDA Graph 安全；FlashInfer MLSys 2025 最佳论文，vLLM/SGLang 使用）。
16. 跨 launch 技术：**CUDA Graphs**（一次捕获 decode step、每 token 重放，消除每 kernel 几 µs 的 launch 间隙；`cudaStreamBeginCapture` → `cudaGraphLaunch`）与 **PDL**（Hopper/SM 9.0+，`cudaTriggerProgrammaticLaunchCompletion` / `cudaGridDependencySynchronize` 让下个 kernel 的 prologue 提前启动，可与 CUDA Graphs 配合）。
17. **Megakernel**：一次 launch 跑完整模型，下一 op 的权重在当前 op 计算期间预取，batch-1 达 H100 带宽 78%、约 1.5× SGLang 每用户吞吐（Hazy Research；Mirage MPK 自动编译）。
18. 跨 GPU 技术：**Flux** 把 TP 集合通信融进 GEMM tile（epilogue 直写所属 GPU、NVLink/NVSHMEM peer write），隐藏至多 96% 通信，prefill 1.66×、decode 1.30× 于 vLLM（8 GPU）；**DeepEP** 用两个 micro-batch 重叠 MoE all-to-all（NIC 上传输不占 SM，dispatch FP8 / combine BF16，NVLink→RDMA 转发），NVLink ~153 GB/s、RDMA ~43 GB/s 近链路峰值。
19. **AI agent 写 kernel**：针对"每代新 GPU 都要手工重调 kernel、会写的人少"——agent 写（CUDA/Triton/CuTe）→ 编译（nvcc/ptxas 报错反馈）→ 多 shape 剖析（Nsight）→ 对照 PyTorch 参考校验（fast_p：正确且比 PyTorch 快 p 倍以上的任务占比）；警惕"通过弱测试/钻框架空子"的假快。AI 硬件挑战：KV-cache 交接 32K Llama 3 70B prompt 节点外慢 9×（NVLink 24 ms vs 400G NIC 215 ms）；Llama 3 训练每 3 小时 1 次故障（419 次中断：HBM3 30%、GPU 8%、网络 17%）；GB200 NVL72 机架 120 kW（普通机架 8 倍）需液冷；GPT-3 训练耗淡水 70 万 L，2027 年 AI 预计抽水 42–66 亿 m³。
20. 选读要点——优化 GPU 代码的四个可叠加目标：少搬数据（coalescing/tiling/fusion）、隐藏等待（async copy/warp 特化）、暴露并行（Split-K/独立累加器）、更快指令（Tensor Cores/低精度）；配套技巧表：合并访问、共享/寄存器 tile、swizzle 32×32→32×33、双缓冲、shuffle 通信、MMA 映射、FP16/BF16+FP32 累加、编译期特化、减少分支发散、autotuning；代价：split-K 多合并步骤、流水化多缓冲与同步。
