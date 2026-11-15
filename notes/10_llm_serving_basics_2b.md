# 第 10 讲(下):LLM 服务基础 II(GPU 入门)

> **LLM Serving Basics II: Intro to GPUs** · Harvard CS2680 · 讲师 Juncheng Yang
> 原始幻灯片:[10_llm_serving_basics_2b.pdf](../10_llm_serving_basics_2b.pdf)
> 原课程:Harvard CS2680 *Modern AI Systems: Agents and System Optimizations*(Harvard MaDSys, course.agentic-system.org)

## 本讲概览

本讲正式标题是 LLM Serving Basics II,实际内容是 **GPU 基础**:GPU 编程模型、效率指标(MFU/MBU)与剖析方法、kernel 优化的最新进展。课程明确不深入细节,目标是建立 LLM serving 性能分析的直觉(intuition)。全讲分三部分:GPU 编程、GPU 效率与利用率、kernel 优化最新进展,另加一页 AI 硬件挑战与四页选读(GPU 代码优化技巧系统化)。

## 课程事务(Logistics)

- **Assignment 4** 今天发布,两周半后截止。目标:对性能(performance)、瓶颈(bottlenecks)进行推理并迭代改进,理解真实 workload 与合成 benchmark 有何不同。
- 写作报告(write-up)比代码重要:只需很少几行代码。
- 排行榜提交**没有补交(late day)**:
  - 不要一次占用超过一块 GPU
  - 对系统编程经验少的同学难度较高
- 项目 Proposal 下周三(10 月 28 日)截止,格式与页数不限;**不要上传 AI 生成的内容**。

## GPU 编程基础(GPU Programming)

- **异步执行(asynchronous)**:
  - Host(CPU + DRAM)与 Device(GPU + HBM)经 **PCIe Gen5 x16(~64 GB/s,比 HBM 低 75 倍)** 互联
  - CPU 发射(launch)kernel 后不等待,GPU 侧由 Copy engine 与 SM 并行干活
  - kernel 错误要到下一次同步调用才暴露(errors surface late)

> **图示** CPU 线程 / Copy engine / SM 三条泳道的时间线,展示 `cudaMalloc`、`memcpy H→D`、`launch`、其他 CPU 工作与 GPU 侧拷贝、kernel 执行的并行关系。

- **SIMT 按单线程编写**:kernel 为"一个线程"而写,每线程用 `i = blockIdx.x * blockDim.x + threadIdx.x` 算全局下标、负责一个输出元素。
  - 例:n = 1M、每 block 256 线程 → 4,096 个 block 铺到 132 个 SM
  - 限定符:`__global__`(host 调用、device 运行)、`__device__`(device 调用、device 运行)、`__host__ __device__`(两者)
  - 经验法则:block 大小取 32 的倍数,128–256 线程典型
- **软件/硬件层次**:
  - **Grid** = 整个 GPU(一次发射的全部 block)
  - **Block** = 一个 SM(≤1,024 线程,共享内存驻留至 block 结束)
  - **Warp** = 一个分区(32 线程锁步,调度器每周期发射)
  - **Thread** = 一条 lane(自己的寄存器与下标)
- **torch.compile(图编译器)**:
  - 你只写数学(普通 PyTorch/JAX,不碰线程、tile、内存)
  - 编译器决定哪些算子融合(fuse)、tile 大小、生成 Triton 或 XLA kernel
  - 控制流打断图、或慢算子无法融合时失效
  - JAX 对应 `jax.jit` → XLA
- **Tile 语言**:描述"一个数据 tile 的工作"而非"一个线程的工作"(`program_id` + tile 范围;staging、同步、Tensor Core 点积交给编译器)。在用的:
  - **Triton**(Python,NVIDIA/AMD)
  - **Pallas**(JAX,TPU/GPU)
  - **TileLang**(基于 TVM 的 Python DSL)
  - **ThunderKittens**(C++ tile 模板)
  - **cuTile**(NVIDIA CUDA)
  - 【进阶】Triton:一个 program = 一个 block,拥有 BLOCK 个元素;`tl.load/tl.dot/tl.store`,`@triton.autotune` 按形状搜索 tile 大小与 warp 数。
  - 【进阶】TileLang:你放 tile 形状、共享内存 vs 寄存器存储、pipelined stages;编译器决定线程映射、拷贝、swizzle、MMA;用于需要显式 staging 的 GEMM/attention。
  - 【进阶】CuTe/CUTLASS/ThunderKittens:你选 layout(坐标→偏移代数)、TMA 异步流水、warp 角色;库提供经过测试的构建块;用于 GEMM/attention 冲峰值的"最后一段路"。
- **抽象层次与代价**(越低掌控越强、代价越高):

| 层次 | 何时用 | 代价 |
|---|---|---|
| 图编译器 torch.compile、XLA | 整个模型的默认 | 对慢算子几乎没有掌控 |
| Tile 语言 Helion、Triton、Pallas | 某算子没被融合或缺失 | 数小时;可跨 GPU 移植 |
| 显式 tile:TileLang | 需要控制 staging | 数天 |
| 布局、warp 角色:CuTe、CUTLASS、ThunderKittens | GEMM/attention 必须达峰值 | 数周;每代 GPU 重做 |
| 线程:CUDA C++ | 不规则工作:排序、稀疏、图 | 一切都在你自己身上 |

- **编译流程**:所有语言最终都编译到 **SASS**:
  - NVCC 设备码走 NVVM→PTX→ptxas
  - Triton 走 Triton IR→LLVM→PTX
  - cuTile 走 cuTile IR→tileiras
  - 驱动加载时优先运行匹配当前 GPU 的 SASS,否则 JIT 编译 PTX 并缓存

> **图示** 四条编译流水线(device/host、Triton、CUDA Tile)在加载期的汇聚。

## GPU 效率与利用率(GPU Efficiency and Utilization)

- **MFU (Model FLOPs Utilization) = 实际模型 FLOP/s ÷ 峰值**(dense Tensor Core 速率):
  - 例:Llama 2 70B 在 8×H100:每 token 约 2N ≈ **140 GFLOP**,3,040 tok/s × 140 GFLOP ≈ 426 TFLOP/s,MFU ≈ 426 ÷ 1,979 ≈ **22%**
  - 经验值:训练 35–45%,推理 prefill 40–60%、decode 10–40%
- **MFU 低的四个原因**:
  - 内存受限 kernel(norms、softmax、优化器步按带宽而非 Tensor Core 峰值跑)
  - 通信(张量/流水/数据并行传输藏在计算后)
  - 流水线气泡(batch 填充/排空时 stage 空闲)
  - 重计算(训练的 activation checkpointing 重跑前向,MFU 不计入)

> MFU 把硬件能力与软件成熟度区分开。

- **MBU (Model Bandwidth Utilization) = 实际 bytes/s ÷ 峰值 HBM**:
  - decode 每步读全部权重 + KV cache,瓶颈是带宽而非 FLOPs
  - 例:Llama 3 8B、BF16、batch 1、H200:每 token 读 **16 GB**,200 tok/s → 3.2 ÷ 4.8 TB/s ≈ **67%**
- **其他 serving 指标**:
  - 每 GPU tokens/s
  - 给定延迟目标(如 p50)下的吞吐
  - 每输出 token 时间
  - 每 token 能耗(平均整板功耗 ÷ tokens/s)
  - 每百万 token 成本($/GPU-hour ÷ (tokens/s × 3,600) × 10⁶)
- **剖析顺序:先时间线,后 kernel**
  - `nsys profile -o run ./app`(Nsight Systems):CPU 线程、CUDA API、拷贝、kernel、stream 的统一时间线;找空闲间隙、串行 stream、launch 开销。
  - `ncu --set full -k vec_add ./app`(Nsight Compute):重放单个 kernel 收集计数器(speed of light、内存流量、warp stalls、热行);解释一个 kernel 为什么慢(replay 计时仅供对比)。
  - 工作流:`nsys` 找慢区段 → `ncu` 解释单个 kernel → 改一件事 → 再测。
- **利用率计数器**:
  - `nvidia-smi` utilization(至少一个 kernel 在跑的时间占比)
  - SM active(有 warp 驻留的 SM 周期占比)
  - SM occupancy(驻留 warp ÷ 最大)
  - Tensor pipe active(Tensor Core 忙碌占比)
  - DRAM active(HBM 忙碌占比)
  - `dcgmi dmon -e 203,1002,1003,1004,1005` 一行全观测
- **读计数器的决策树**:
  - ① GPU 忙吗(`nvidia-smi` 100%?;否 → kernel 间空闲,看 Nsight Systems 时间线,可用 CUDA Graphs)
  - ② SM 忙吗(SM active 高?;否 → block 太少,加大 batch / 每 kernel 更多 block)
  - ③ 哪个单元忙:DRAM active 高 → 内存受限,用 MBU 评判;Tensor pipe active 高 → 计算受限,用 MFU 评判;两者都低 → 延迟受限,用 Nsight Compute 深入

> **关键** `nvidia-smi` 100% 只说明"有 kernel 在跑",不代表有效利用。

## GPU Kernel 优化的最新进展(Recent Advances)

- **时间丢在三个地方 + 一个"人"的维度**:
  - ① kernel 内部(Tensor Cores 等 load、softmax、exp)
  - ② 跨 SM(轮次不均、kernel 间闲置)
  - ③ 跨 GPU(互相等对方数据)
  - ④ 写 kernel 丢失工程师时间(每代新 GPU 都要重调 → 会自己写 kernel 的 agent)

### Kernel 融合与 FlashAttention

- **Fusion**:对 1 GB FP32 做 scale + bias + ReLU,三个 kernel 需 6 次 HBM 往返共 1.25 ms;融合后中间结果留在寄存器,0.42 ms,**HBM 流量减 3 倍**。
  - 纵向融合:生产者把输出直接喂给同 kernel 内的消费者(GEMM epilogue、LayerNorm、带 mask 的 softmax;torch.compile 干这件事)
  - 横向融合:共享输入合并(QKV projection、FFN gate+up 拼成一个 GEMM,x 只读一次、只 launch 一次;模型代码通常手工拼权重)
- **FlashAttention**:
  - 标准 attention 把 n×n 的 S 与 softmax P 写进 HBM 再读回(8K token 时每层每头 67M 个分数)
  - 解决:Q/K/V 切 tile 在片上(共享内存+寄存器)计算,维护运行 max/sum(online softmax)

> **S、P 永不落 HBM,K/V 只读一次、O 只写一次**。

- **FA1→FA4 的演进**(每代针对新硬件的下一个瓶颈;进阶):
  - FA1(2022·A100)HBM 流量 → tile + online softmax,attention 快 2–4×、内存随长度线性
  - FA2(2023·A100)占用率低 → 沿序列切分工作,~70% A100 峰值
  - FA3(2024·H100)exp 单元成为瓶颈 → TMA + warp specialization、softmax 与 GEMM 重叠、FP8,~75% H100 峰值
  - FA4(2025·B200)Tensor Cores 翻倍而 exp 没有 → TMEM 累加器、部分 exp 上 FMA 单元,B200 上比 cuDNN attention 更快

### 跨 SM 与跨 launch(进阶)

- **Persistent kernels**:
  - matmul 160 个 tile ÷ 132 SM 要跑两轮,第二轮 28 个 block、104 个 SM 空等且 setup 重复
  - 改为 132 个常驻 block 逐个领取 tile,无空闲轮、setup 只做一次(CUTLASS、DeepGEMM 这么做)
  - Stream-K:把 tile 切细让所有 SM 同时完成
- **Split-KV**:
  - decode 每请求只有一个 query token,只按 batch × heads 切分留下 SM 空闲,且各请求 KV 长度相差可达 100×
  - 按 KV 页切分(如每 SM 4 页)并行,按请求以 online softmax 方式合并部分和(m, ℓ, O),网格固定、CUDA Graph 安全
  - FlashInfer(MLSys 2025 最佳论文)将 block-sparse KV 与 JIT 特化 kernel 结合,**vLLM 与 SGLang 使用**
- **CUDA Graphs**:
  - decode 一个 token 要跑几十个 µs 级小 kernel,每次 launch 几 µs CPU/驱动时间
  - 把 decode step 捕获一次、一次调用重放全部 kernel,无间隙(vLLM/SGLang)
- **PDL(Programmatic Dependent Launch)**:
  - 让下一个 kernel 的 prologue 在上一个 kernel 完全排空前提前开始(`cudaTriggerProgrammaticLaunchCompletion` 提前触发、`cudaGridDependencySynchronize` 处等待),压缩 decode 中 kernel 间隙
  - 需 Hopper+(SM 9.0),可与 CUDA Graphs 配合
- **Megakernel**:
  - 一次 launch 跑完整模型,下一个 op 的权重在当前 op 计算期间预取,launch 边界消失(内部:on-GPU 解释器、per-SM 指令队列、分页共享内存权重、依赖用全局计数器)
  - Hazy Research 的 megakernel batch-1 达 **78% H100 带宽**、约 1.5× SGLang 每用户吞吐
  - Mirage MPK 可自动编译此类任务图

### 跨 GPU(进阶)

- **Fused collectives(Flux)**:
  - TP 把每层切到 8 GPU,每个 GEMM 前后各一次 AllGather/ReduceScatter
  - 融合后每个 tile 的 epilogue 直接写往所属 GPU、行到达即开始计算,peer 经 NVLink/NVSHMEM 写数据、无额外 kernel
  - 最多隐藏 **96%** 通信,8 GPU 上比 vLLM prefill 快至多 1.66×、decode 快至多 1.30×
- **MoE all-to-all(DeepEP)**:
  - 每个 MoE 层把 token 发给其他 GPU 的 top-8 expert 再收回
  - 两个 micro-batch 重叠流水让 dispatch/combine 与专家 GEMM 交叠,传输跑在 NIC 上不占 SM,dispatch FP8 / combine BF16,并支持 NVLink→RDMA 转发
  - NVLink ~153 GB/s、RDMA ~43 GB/s,接近链路峰值

### Agent 成为新的编译器(进阶)

- 问题:每代新 GPU(TMA、TMEM、FP4)与每种 attention 变体都需要新的手工调优 kernel,会写的工程师很少。
- 解决:agent 写 → 编译 → 剖析 → 校验的闭环:
  - 写 kernel(CUDA/Triton/CuTe)
  - 编译(nvcc/ptxas 报错反馈)
  - 剖析(多 shape 上的运行时间、Nsight 计数器)
  - 校验(对照 PyTorch 参考;静态检查拒绝有竞态的调度)

> 警惕"看起来快":生成的 kernel 可能靠通过弱测试或钻测试框架(harness)空子;用 **fast_p** 指标:正确且比 PyTorch 快 p 倍以上任务的占比。

## AI 硬件挑战(Challenges in AI Hardware)

| 维度 | 关键数字 |
|---|---|
| 网络 | KV-cache 交接,32K token 的 Llama 3 70B prompt:NVLink (H100) 24 ms vs 400G NIC 215 ms,**节点外慢 9 倍** |
| 可靠性 | 平均每 3 小时 1 次故障;Llama 3 训练 419 次中断构成:HBM3 内存 30%、网络 17%、GPU 故障 8% |
| 功耗 | 每机架:Conventional 15 kW、HGX B200 60 kW、GB200 NVL72 120 kW(普通机架的 8 倍) |
| 冷却与水 | GB200 NVL72 机架需液冷;训练 GPT-3 耗淡水 70 万 L;2027 年预计 AI 抽水量 42–66 亿 m³ |

## 选读:优化 GPU 代码(Optimize GPU Code)

- **四个可叠加的目标**:
  - ① 少搬数据(move less data:coalescing、tiling、fusion)
  - ② 隐藏等待(hide waiting:async copies、warp specialization)
  - ③ 暴露更多并行(expose more parallelism:Split-K、独立累加器)
  - ④ 用更快指令(faster instructions:Tensor Cores、更低精度)
  - 例:一个快的 GEMM 同时合并加载、双缓冲 tile、用 Tensor Cores。
- **内存流量**:
  - coalescing(相邻线程读连续地址:读 `x[i]` 而非 `x[32·i]`)
  - 共享内存/寄存器 tiling(加载一次、反复复用)
  - fusion(跳过 HBM 往返)
  - padding/swizzling(转置 tile 32×32 → 32×33 避免 bank conflict)
  - 缓存感知排序(读相同输入的 tile 分组调度)
- **隐藏等待/暴露并行**:
  - 异步拷贝 + 双缓冲(算当前 tile 时加载下一个)
  - 指令级并行(多个累加器而非一条依赖链)
  - warp specialization(生产者 load / 消费者 MMA)
  - Split-K(长 KV 切给多个 block 再合并)
  - warp 内 shuffle 通信
  - 代价:split-K 多一个合并步骤,流水化多缓冲与同步
- **更便宜的计算**:
  - Tensor Core 映射(MMA 替代标量 FMA)
  - 低精度(FP16/BF16 输入 + FP32 累加)
  - 展开 + 编译期特化
  - 减少分支发散(同 warp 同路径)
  - autotuning(按 workload 形状搜 tile 大小/warp 数/流水深度)
  - 注意这是两个独立选择:Tensor Cores 需要"合身"的形状,精度降低必须保住准确性

## 核心要点

- 本讲目标是为 LLM serving 建立 GPU 直觉;Assignment 4 两周半后截止,重点是对性能与瓶颈的推理分析和 write-up,代码量很少。
- GPU 编程第一心智模型是**异步**:launch 后 CPU 不等待、错误延迟到下次同步才暴露;PCIe Gen5 x16 ~64 GB/s 比 HBM 低 75 倍,跨 PCIe 拷贝昂贵。
- SIMT 层次:Grid = 整个 GPU、Block = 一个 SM(≤1,024 线程)、Warp = 32 线程锁步、Thread = 一条 lane;kernel 按单线程编写,block 大小取 32 的倍数(典型 128–256)。
- 编程抽象从低到高:CUDA C++(一切自己来)→ CuTe/CUTLASS 布局与 warp 角色(数周、每代 GPU 重做)→ TileLang(数天)→ tile 语言 Triton/Pallas(数小时、可移植)→ torch.compile(默认);都最终编译为 SASS。
- **MFU = 实际模型 FLOP/s ÷ dense 峰值**:Llama 2 70B 在 8×H100 约 22%;经验值训练 35–45%、prefill 40–60%、decode 10–40%;低的四大来源:内存受限 kernel、通信、流水线气泡、重计算。
- **MBU = 实际 bytes/s ÷ 峰值 HBM**:decode 每 token 读全部权重 + KV(Llama 3 8B BF16 batch 1 为 16 GB),H200 上 200 tok/s 约 67%;经验法则 **prefill/训练报 MFU,decode 报 MBU**。
- 剖析:nsys 时间线找慢区段 → ncu 解释单个 kernel → 改一件事 → 再测;计数器决策树(nvidia-smi → SM active → DRAM vs Tensor pipe)区分 kernel 间空闲 / 并行不足 / 内存受限 / 计算受限 / 延迟受限。
- kernel 时间丢在三层(kernel 内部、跨 SM、跨 GPU)加"写 kernel 的工程师时间";融合是最常见手段:1.25 ms → 0.42 ms,HBM 流量减 3 倍。
- FlashAttention 让 S/P 永不落 HBM,K/V 读一次、O 写一次;FA1–4 依次针对 HBM 流量、占用率、exp 瓶颈、Tensor Core 翻倍,FA3 达 ~75% H100 峰值,FA4 在 B200 上超 cuDNN。
- 跨 SM/launch 技术:persistent kernels(消灭空闲轮)、Split-KV(FlashInfer,vLLM/SGLang)、CUDA Graphs(捕获重放、无间隙)、PDL(Hopper+、下个 kernel prologue 提前)、megakernel(一次 launch 跑全模型,78% H100 带宽、1.5× SGLang)。
- 跨 GPU 技术:Flux 把 TP 集合通信融进 GEMM tile(隐藏至多 96% 通信,1.66× prefill);DeepEP 用 micro-batch 重叠 MoE all-to-all 与专家计算(NVLink ~153 GB/s、RDMA ~43 GB/s)。
- Agent 写 kernel 是新方向:写→编译→剖析→多 shape 校验闭环,用 fast_p(正确且快 p 倍以上的任务占比)判断,警惕钻测试空子的"假快"。
- AI 硬件挑战:节点外网络慢 9 倍、平均每 3 小时一次故障、GB200 NVL72 机架 120 kW 需液冷、AI 行业水耗问题。
- 选读的四目标(少搬数据/隐藏等待/暴露并行/更快指令)可自由组合,对应 coalescing、swizzle、双缓冲、warp 特化、Split-K、MMA、低精度、autotuning 等全套技巧。
