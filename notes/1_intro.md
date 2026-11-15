# 第1讲：课程导论 (Introduction)

> 原英文标题：*Modern AI Systems: Agents and System Optimizations — Overview*（Lecture 1，讲师 Juncheng Yang，课程主页 https://cs2680.com）

## 本讲概览

这是 CS2680「Modern AI Systems: Agents and System Optimizations（现代 AI 系统：智能体与系统优化）」的第一讲，由讲师 Juncheng Yang 主讲。本讲分三块：课程概览（这门课是什么、你将学到什么）、政策与行政安排（五个作业、开放选题项目、评分细则、选课规模、使用 AI 的政策、计算资源），以及两个核心内容部分：Part I 讲 AI 系统与传统计算机系统有何不同（异构计算、prefill/decode 的不同瓶颈、浮点非确定性、巨大的状态、多 GPU 通信、可靠性与功耗），Part II 讲 agentic AI 系统——什么是 agent、为什么它是系统问题、agentic 技术栈、以及真正的优化目标（$/任务而非 tokens/s）。本讲同时明确了课程边界：不覆盖训练与模型架构设计，课程聚焦 LLM 系统与 agent 服务（serving）。

## 一、今日安排与讲师团队

### 今日计划

开场列出了本讲的三个议题：

- 课程概览（Course overview）
- 政策与行政安排（Policy and logistics）
- AI 系统与 agentic 系统（AI systems and agentic systems）

幻灯片页脚标注了课程归属：Harvard Madsys · course.agentic-system.org。

### 关于讲师

Juncheng Yang 是哈佛 SEAS（工程与应用科学学院）的助理教授（Assistant Professor），2024 年从 CMU（卡内基梅隆大学）毕业，此前曾在 AWS、Snowflake、Cloudflare、Twitter 工作。

### Harvard MaDSys 研究组

幻灯片介绍了 Harvard MaDSys（Measurement and Design of Computer Systems，计算机系统测量与设计）研究组的三个方向：

| 方向 | 覆盖领域 | 追求的目标 |
|---|---|---|
| Efficiency / Performance（效率与性能） | 存储系统、缓存、可持续存储 | 更少资源、更快；更高利用率、更可扩展 |
| Reliability / Sustainability（可靠性与可持续性） | Agent 服务系统、上下文管理（context management）、LLM serving 优化 | 更少停机时间；更稳健；更少碳排放 |

研究组的座右铭是：“People find solutions, we find problems; we measure, design, and operate real systems.”（人们找方案，我们找问题；我们测量、设计并运营真实的系统。）

图示：该幻灯片用三列排版呈现 MaDSys 组的三条主线（效率性能、可靠可持续，各带领域与目标标签），突出该组既研究存储等经典系统，也研究 LLM/agent serving 等新兴系统。

### 助教（TFs）与课堂约定

- 课程团队共三人：Juncheng Yang（讲师）、Yiyu Liu（TF）、Yunjia Zheng（TF）。三人的 Office hour（答疑时间）均为「by appointment」（需预约）。
- 课程 staff 邮箱：cs2680-staff@g.harvard.edu。
- 讲师表示会努力记住每个人的名字；请大家在提问或回答问题之前，先报一下自己的名字。
- 第一节课的破冰环节：每组（table）用 5 分钟向本组同学介绍自己，内容包括：姓名与来自哪里、所在项目/年级/背景、研究方向、以及为什么选这门课、希望学到什么；每桌选出一名代表，负责向全班介绍整桌同学。

## 二、课程定位与你将学到什么

### 这是一门什么课

本课程名为 **Agentic AI Systems**，是一门研究生级别的计算机**系统**课程。先修背景要求：

- 上过至少一门研究生级别的系统课程（操作系统 OS、计算机网络、数据库、计算机体系结构）；
- 有真实系统（real systems）的实践经验。

### 课程内容两大板块

| 板块 | 覆盖范围 | 内容 |
|---|---|---|
| Foundations（基础） | 前几节课 | LLM 与 agent 入门；如何使用 Claude Code；如何设计一个 coding agent；如何优化你的 coding agent |
| Systems for LLMs & agents（LLM 与 agent 的系统） | 大部分课程 | GPU 编程与 kernel；批处理（batching）、调度（scheduling）、内存管理；负载均衡与路由（load balancing and routing）；KV cache 与 prefix cache（前缀缓存）；agent 服务系统及其他优化 |

可以看出课程结构是「先 agent 后系统」：先用前几节课打好 LLM 与 coding agent 的基础，再用大部分课时深入 GPU 编程、调度、内存管理、路由、缓存等系统优化主题。

## 三、五个作业（Assignments）

### 作业 1–3：围绕 coding agent 的三步走

| 作业 | 标题 | 核心内容 |
|---|---|---|
| 1 | Build a web UI for Claude Code（为 Claude Code 构建 Web UI） | 解决一组简单问题；体验 coding agent 的「魔法」；为作业 3 的 leaderboard 创建新问题 |
| 2 | Build a simple coding agent（构建一个简单 coding agent） | 开放题（open-ended）：上下文（context）、记忆（memory）、test-time scaling（测试时扩展）、路由、sub-agent、工具调用（tool call）等方向自选；需要理解 coding agent 的生命周期（lifecycle） |
| 3 | Optimize your coding agent（优化你的 coding agent） | 以指标（metrics）为准：准确率（accuracy）、成本（cost）、延迟（latency） |

这一组作业的设计逻辑是递进的：先用现成的 Claude Code 体验 agent 能力并贡献评测题，再亲手实现一个 coding agent，最后进入性能优化——为作业 3 的排行榜（leaderboard）竞争做准备。

### 作业 4–5：走向系统与全栈优化

| 作业 | 标题 | 核心内容 |
|---|---|---|
| 4 | Serve your agent（为你的 agent 提供服务） | 从商业 API 走向自部署小模型（from a commercial API to a small model）；这是最难的作业；任务更难（harder tasks）；协同调优 agent 与 serving 引擎（co-tune your agent and the serving engine）以优化性能 |
| 5 | Optimize the full stack（优化全栈） | 开放题：量化（quantization）、路由（routing）、微调（fine-tuning）、引擎–agent 协同设计（engine–agent co-design） |

幻灯片上附了一张「选课警告」对照表：

| 会做的事（Scored on the leaderboard） | 如果你在乎 GPA，就别选这门课（Do NOT take this class if you care about） |
|---|---|
| 作业 3 与作业 5：按 leaderboard 排名 + 相对 baseline 的提升打分 | 每周预计要花 10 小时以上（Expect 10+ hours every week） |

也就是说，作业 3 和 5 不是「做完全给分」，而是看你在排行榜上的排名和相对基线的提升；而整门课每周至少 10 小时以上的投入是默认预期。

## 四、开放选题项目（Project）

- 形式：开放题（open-ended）、个人项目 + AI 辅助（individual project + AI）。
- 成果展示：在 reading period（阅读周，考试前的考试周）举行 poster + demo session（海报与演示会）。
- 评分：代码（code）+ 报告（report）+ 海报/演示的同侪评审（poster / demo peer review）。

项目有两种典型形态：

1. **Build a tool（造一个工具）**：找到一个真实的缺口（gap），做出一个你自己会实际使用的工具。
2. **Research（研究项目）**：做一个研究性质的课题——先和 TF 沟通（talk to the TFs first）。

## 五、评分、政策与行政安排

讲师特别提示：这一节「值得仔细读」（The parts worth reading carefully）。

### 评分构成（Grading）

| 项目 | 占比 | 说明 |
|---|---|---|
| 五个作业 | 70% | 作业 1、2、4 各占 10%；作业 3、5 各占 20% |
| 项目（Project） | 16% | 见上节 |
| 演讲（Presentation） | 10% | 一篇 paper + 作业 1 |
| 课堂参与（Participation） | 4% | 课程反馈（course feedback）+ 提出「AI 解决不了的问题」（problems that AI cannot solve） |
| 附加分（Bonus） | 10% | — |

两条附注：

- 作业 3 和 5 的分享会（sharing sessions）按 leaderboard 排名组织。
- **警告：本课程执行「20% A」评级政策（20% A grading policy enforced）——想拿到 A 甚至 A- 都很困难。**

### 迟交与 late days

- 全学期共 4 个 late day（可迟交的天数额度）。
- 迟交每天扣 20%（20% penalty per day）。

### 选课规模（Enrollment）

幻灯片给出的三组数字：

| 40 | 80 | 68 + 10 + 6 |
|---|---|---|
| 计划并预算的容量（planned and budgeted） | 今日已注册（enrolled today） | 预注册 / 交叉注册 / 候补（prospective, cross-registration and waiting list） |

补充说明：课程上限（cap）已提高到 80。旁听（auditing）仅在哈佛政策允许且有空位时才可。但要注意：计算资源（computing resources）可能不会随人数同比例增加，**你在作业截止日期当天很可能拿不到 GPU**。

### 政策：使用 AI（Using AI in this course）

- **鼓励使用 AI**（Using AI is encouraged）。
- 但是：你必须对 AI 生成的代码进行推理与审视（reason about AI-generated code），并且**对你提交的每一行代码负责**（you are responsible for all code you submit）。
- **必须披露（Disclosure required）**：每次作业提交时都要上传你的 AI 会话日志（session log），说明哪些做法有效、哪些无效（What worked and did not work）。
- 要求查看课程网站上各作业的提交页面（assignment submission page）。

### 政策：出勤与笔记本电脑（Attendance and laptops）

- **必须出勤**：要求线下到场（In-person attendance is expected）；**课程不做录像**（Class is not recorded），也不允许视频录制。
- **允许使用笔记本**：如果你打算在课堂上一直开着电脑用，请坐到教室最后一排（If you plan to keep yours open, please sit at the back）。
- **客座讲师**：客座讲座的报名（Meeting sign-up）会提前一周开放。
- 完整政策见课程网站。

### 其他行政安排：计算资源（Computing）

| 资源 | 说明 |
|---|---|
| Claude Code API 访问 | 统一入口 api.cs2680.com |
| GitHub | 私有仓库（Private repo），与 staff 共享 |
| 课程 HPC | 基于 SLURM 调度；配备 RTX 6000 PRO Blackwell；仅限课程用途（Course work only） |
| AWS | 所有能访问 Canvas 的学生已在系统内；**必须在周五之前**完成注册并填写 Google Form；**不使用时务必终止或关闭实例**（Terminate or turn off your instance when not in use） |

同样要求阅读课程网站上的 computing 页面。

### 课表可能变动

这是本课程**第一次开设**（The first time offering this course）：“expect a bumpy ride ahead!”（预期会有一段颠簸期）；评分方式也可能调整（例如 paper reading 的阅读报告）。学期共 14 周（Week 1 → Week 14）。

## 六、课前背景调查

讲师在正式进入内容之前，先用几张幻灯片了解大家的背景（“To help me understand everyone’s background”）：

- **你上过多少门计算机体系结构/系统类课程？** 选项包括：操作系统（Operating systems）、分布式系统（Distributed systems）、数据库（Databases）、计算机网络（Computer networking）、计算机架构（Computer architecture），以及……其他任何。
- **你对以下这些主题熟悉多少？** Transformer 架构（Transformer architecture）、TP / PP / DP / EP（张量/流水线/数据/专家并行）、pagedAttention、迭代级调度（iteration-level scheduling）、GPU、线性注意力（Linear attention）、Linux 内核编程（Linux kernel programming）。
- **你如何使用 AI？** 三个层次：1 Chat（聊天）；2 Coding agent（编码智能体）；3 Customized agent（定制化 agent，如 MCP、Skills / Plugins、subagent、parallel agent）。
- **Agentic Coding Levels（agentic 编码等级）**，从低到高：
  - 0：No AI——手写代码；
  - 1：Assist——AI 自动补全；
  - 2：Supervised——AI 写函数，你来审查；
  - 3：Scoped——把一个任务整体交给 AI，你审查代码；
  - 4：Goal-driven——AI 写全部代码，用测试来验证；
  - 以及一个并行形态：Parallel agents——由 sub-agent 分工协作。

这组问卷实际上勾勒出了本课程的隐含假设：学生至少处在 1–3 级的日常 AI 使用水平，而课程要带大家走向 4 级与并行 agent 的系统化实践。

## 七、Part I —— AI 系统：它们与传统计算机系统有何不同

本节标题即「How they differ from traditional computer systems」（它们如何区别于传统计算机系统）。

### 7.1 什么是 AI 系统（What is an AI System?）

讲师先点出 AI 系统「有很多活动部件」（Many moving parts）：调度与编排（scheduling & orchestration）、状态管理（state management）、通信（communication）、缓存（caching）、容错（fault-tolerance）、安全（security）、可观测性（observability）……

随后用一张对照图区分了两个学科视角：

| AI / ML（模型视角） | AI Systems（系统视角） |
|---|---|
| 核心问题：“我们应该用哪个模型？”/“模型该如何设计？” | 核心问题：“我们如何在大规模下训练并服务它？”（How do we train and serve it at scale?） |
| 做法：选一个模型、写一个 Python 脚本来解决任务 | 做法：面向部署与服务的系统工作 |
| 优化目标：准确率（accuracy）与能力（capability） | 优化目标：最大化 GPU 利用率（性能 performance）；最小化资源浪费（效率 efficiency）；最小化停机时间（可靠性 reliability）；更低的碳足迹（可持续性 sustainability） |

图示：左右两栏对比——左侧是「AI/ML」气泡，右侧是「AI Systems」气泡，各自列出核心问题、典型做法与优化目标。

页脚有一条重要限定：**“AI systems” 是一个宽泛的术语，而本课程只聚焦其中的 LLM 系统**（this course narrowly focuses on LLM systems）。

### 7.2 为什么你应该关心 AI 系统（Why should you care about AI systems?）

讲师给出论点：**“This is where capability becomes product”（这里是能力变成产品的地方）**——并且它比 AI 本身更难（it is harder than the AI itself）。AI 系统已经成为关键数字基础设施（Critical digital infrastructure）。学好它的三个直接收益：

- 理解模型设计（Understand model design）；
- 设计更好的产品（Design better products）；
- 获得更多工作机会（More job opportunities）。

### 7.3 计算（Compute）：异构、分阶段、时长不可预测

传统系统的计算是相对同质的，而 AI 系统的计算有三个根本性差异：

- **异构计算（Heterogeneous computation）**：CPU 负责 tokenization（分词）、kernel launch（内核启动）、数据移动（data movement）、工具调用（tool calls），GPU 负责 matmul（矩阵乘）；集群中还会混用不同代的 GPU 以及 xPU。
- **计算的不同阶段（Distinct phases of computation）**：**prefill（预填充）阶段是 compute-bound（受算力限制）**，**decode（解码）阶段是 memory-bandwidth-bound（受内存带宽限制）**；同一个部署会在 compute、bandwidth、capacity 三种瓶颈之间来回切换。这是全课程反复出现的核心张力：同一个服务在不同阶段需要不同的优化手段。
- **执行时间不可预测（Unpredictable execution time）**：执行时长依赖输出长度（output-length dependent），这使调度变得复杂——你无法像传统请求那样预估每个任务的时长。

### 7.4 非确定性计算（Non-deterministic compute）

传统系统假设同输入同输出，AI 系统不成立：

- **为什么会发生**：浮点加法**不满足结合律**——每次运算都有舍入（rounding）；由此产生「蝴蝶效应」：一个 matmul 中第 7 位小数的偏差，就能翻转下一个 token。
- **来源（Where it comes from）**，三个层次：
  - **Runtime（运行时）**：warp/block 调度、内存访问顺序（memory ordering）、异步流（async streams）、batch size；
  - **Software（软件）**：fused multiply-add（乘加融合）与两条独立指令的结果不同、autotuning（自动调优）、次正规数（subnormals）；
  - **Hardware（硬件）**：CUDA 核与 tensor core 的路径不同、Hopper 的 FP8 与 Blackwell 的微缩放块（micro-scaling tiles）。
- **近似计算是可接受的（Approximate computing is acceptable）**：分配律同样不成立：a × (b + c) ≠ a × b + a × c（但这种差异不常被利用）；传递性也不成立：a == b 且 b == c 并不能推出 a == c。

工程含义：基于 LLM 推理的测试与验证不能假设逐位可复现，评估必须容忍数值层面的抖动——这一点在后续作业（leaderboard 打分）中会直接影响设计。

### 7.5 内存、存储与通信（Memory, storage and communication）

- **巨大的状态（Huge state）**：
  - 模型权重（Model weights）：从 GB 级到 TB 级；
  - **KV cache**：每个 token 需要 10s–100s KB（几十到几百 KB）；
  - **前缀缓存（Prefix cache）**：跨请求复用 KV（KV reuse across requests）。
- **多 GPU 通信（Multi-GPU communication）**：
  - 并行方式：pipeline（流水线）/ tensor（张量）/ expert（专家）/ context（上下文）并行；
  - 集合通信库（Collectives）：NCCL、UCCL；
  - 拓扑：NVLink、Ethernet / InfiniBand；
  - **数据移动是瓶颈**（Data movement is the bottleneck）；
  - 绕过 CPU 与内核态：**RDMA**。

状态规模（权重 + 每 token 的 KV）决定了 LLM 系统的内存层级设计与缓存策略；跨 GPU 的数据搬运则决定了并行化方案的上下限。

### 7.6 快速演进的模型与负载（Fast-moving models and workloads）

- **模型架构快速演进（Rapidly-evolving model architecture）**：MHA、GQA、MLA、NSA、linear attention（线性注意力）……架构几乎每季都在变。
- **负载快速演进（Rapidly-evolving workloads）**，四类典型负载：
  - 多轮聊天（Multi-turn chat）：交互式，延迟敏感；
  - 问题求解（Problem solving）：需要长输出的推理；
  - RAG：回答前需检索文档，长上下文；
  - Agent：长上下文、prefix cache 至关重要、需要路由与负载均衡。
- 应对策略是双向的：**让模型适配硬件**（Adapt model to hardware）与**为模型架构设计硬件**（Design hardware for model architecture）同时进行。

### 7.7 可靠性、功耗与能耗（Reliability, power and energy）

- **可靠性**：GPU 的年故障率（AFR）约 **9%**，平均无故障时间（MTBF）约 **50,000 小时**；换算下来，在一个 **16K-GPU 集群中，平均每 3 小时就有一块 GPU 失败**。这意味着故障不是尾部事件而是常态，容错必须是设计的一等公民。
- **功耗与能耗**：CPU 单片 100–300W，而 GPU 为 700–1000W，一台服务器插 4–8 块 GPU；服务器整机功耗从 800W 涨到 6,000W，**增长了 8 倍**；由此引出工程问题：如何避免功率波动（power fluctuation）。

图示：幻灯片以两组数字卡片呈现可靠性指标（AFR / MTBF / 16K 集群每 3 小时一次故障）与功耗指标（CPU vs GPU 瓦数、800W → 6,000W 的 8 倍增长）。

## 八、Part II —— Agentic AI 系统：什么是 agent，为什么它是系统问题

### 8.1 什么是 AI agent（What is an AI agent?）

定义（逐字）：**An AI agent is an autonomous software system that uses an AI model to reason about a goal, use external tools, and execute multi-step actions until a task is finished**（AI agent 是一个自主软件系统，它使用 AI 模型对一个目标进行推理、使用外部工具，并执行多步动作，直到任务完成）。

其运行循环包含五个步骤：

1. **plan（计划）**——把任务拆解为子步骤；
2. **act（行动）**——调用外部工具（APIs、数据库）；
3. **observe（观察）**——解释这些工具返回的结果；
4. **adapt（适应）**——根据新信息修正计划；
5. **deliver（交付）**——返回最终结果。

图示：该图是一个 agent 闭环结构——Agent 框内含 LLM（负责 Reasoning & Planning，推理与规划）与 Memory（记忆），Agent 通过 Action（动作）作用于 Environment（环境），环境的 Observation（观察）反馈回 Agent，形成 plan → act → observe → adapt 的循环，直至 deliver。

### 8.2 为什么需要 AI agent（Why do we need an AI agent?）

讲师称 **LLM 是「奇怪的计算机」：同时在某些方面超群（superhuman）、在另一些方面无能（incompetent）**（superhuman and incompetent at the same time）：

| 超群（Superhuman at） | 出奇地弱（Surprisingly weak at） |
|---|---|
| 回忆海量事实知识（Recalling vast factual knowledge） | 持久记忆（Persistent memory） |
| 语言（Language） | 可靠地理解上下文（Reliably understanding context） |
| 模式匹配（Pattern matching） | 避免幻觉（Avoiding hallucinations） |
| 生成代码（Generating code） | 知道自己不知道什么（Knowing what they don't know） |
| 跨多个领域运作（Operating across many domains） | 安全与对抗性输入（Security and adversarial input） |

（幻灯片附带一个 YouTube 视频链接来演示这一论点。）正因为 LLM 缺乏持久记忆、上下文理解不可靠、会幻觉、且面对对抗输入不安全，才需要外围的 agent 框架（工具、记忆、校验）来弥补——这正是 agentic 系统存在的原因。

### 8.3 Agent 作为一种新的计算机（Agents as a new kind of computer）

幻灯片给出一组类比映射：

| Agent 世界的部件 | 对应传统计算机部件 |
|---|---|
| LLM | CPU |
| Context window（上下文窗口） | RAM / 工作内存（working memory） |
| Tools（工具） | 外设（Peripherals） |
| Agent harness（智能体框架） | 操作系统（OS） |
| Agent（智能体） | 应用程序（Application） |

并强调：**一个 LLM 远不止一块「更聪明的 CPU」——它是一类全新的可编程计算机，有着完全不同的编程模型与失效模型**（a new kind of programmable computer — with a completely different programming model and failure model）。这个类比是全课程的思维框架：既然 agent 是一台新计算机，那么操作系统、内存管理、调度、I/O 等一切系统问题都会以新的形式重新出现。

### 8.4 为什么 agent 是系统问题（Why are agents a systems problem?）

核心论点：**多轮交互（Many turns）使关键路径跨越 GPU、CPU、存储、网络与外部服务**。

图示：该幻灯片用两条时间线对比——上方的「Traditional LLM serving（传统 LLM 服务）」是单段式：request → inference → response；下方的「Agent serving（智能体服务）」是多段式：infer → tool → infer → tool → retrieval → infer …，每一段之间夹着工具调用与检索，轨迹在时间轴上不断延伸。

Agent 负载由此带来六个系统特性：

- 步骤间存在依赖（Dependencies between steps）；
- 各步骤延迟高度可变（Highly variable step latency）；
- 会阻塞/等待工具（Blocking / waiting on tools）；
- 轨迹（trajectory）中任何位置都可能失败（Failures anywhere in trajectory）；
- 状态快速增长（Rapidly growing state）；
- 并发与投机（Concurrency & speculation）。

也就是说，传统 serving 只需优化「一次推理」，而 agent serving 优化的是「一段跨越多种硬件与外部服务的长轨迹」。

### 8.5 Agentic 系统技术栈（The agentic systems stack）

幻灯片把整个 agentic 系统画成分层栈：

| 层 | 组件 | 职责 |
|---|---|---|
| Application / User（应用/用户） | 最上层 | 最终用户与产品形态 |
| Agent / Harness（智能体/框架） | Agent、Model、External Environment | 规划（planning）· 上下文（context）· 记忆（memory）· 工具（tools）· subagents |
| Serving System（服务系统） | 与 Tools（web · files · APIs · humans）并排 | batching · scheduling · routing · caching |
| Runtime / Kernels（运行时/内核） | 与 Systems 并排 | CUDA · Triton · collectives（集合通信） |
| Systems（系统层） | — | scheduling · caching |
| Hardware（硬件） | GPU · CPU · memory · network · storage | 底部还有 Hardware co-design（硬件协同设计） |

图示：该图是一个自顶向下的堆叠层次图，从应用/用户到硬件，中间各层并排标注了关键子系统（如 harness 内部的规划/上下文/记忆/工具/subagent，serving 系统的 batching/调度/路由/缓存，以及 CUDA/Triton/集合通信的运行时层），传达「agentic 系统是全栈问题、每一层都要协同优化」的信息。

### 8.6 我们在优化什么？（What are we optimizing?）

首要论点：**吞吐量（throughput）对 agent 来说是错误的目标**（Throughput is the wrong objective for an agent）。真正的目标表述为：

> **maximize task success**（最大化任务成功），**subject to** 资源约束（resources）：latency（延迟）、cost（成本）、reliability（可靠性）、security（安全）。

幻灯片用两栏对比了「有用但不足」的指标与「我们真正优化的」指标：

| Useful, but insufficient（有用但不足） | What we actually optimize（我们真正优化） |
|---|---|
| TTFT / TPOT（首 token 延迟 / 每 token 延迟） | Task success / accuracy（任务成功率/准确率） |
| Tool-call latency（工具调用延迟） | End-to-end latency（端到端延迟） |
| GPU utilization（GPU 利用率） | Tokens / task（每任务 token 数） |
| Tokens / sec（每秒 token 数） | $ / successful task（每个成功任务的美元成本） |
| — | Energy / successful task（每个成功任务的能耗） |

并配有一句点睛之笔：**“More tokens/sec can still mean a slower, costlier agent.”**（更高的 tokens/s 仍然可能意味着一个更慢、更贵的 agent。）

### 8.7 Agentic 系统引出的新系统问题（Agentic systems introduce new systems problems）

讲师总结：**agentic 负载的每一个属性，都点名了本课程将研究的一个系统问题**（Every property of an agentic workload names a systems problem this course will study）。完整映射表：

| agentic 负载属性 | 对应的系统问题 |
|---|---|
| 长轨迹（Long trajectories） | 状态与上下文管理（state & context management） |
| 巨大的上下文（Huge context） | 内存层级与检索（memory hierarchy & retrieval） |
| 重复的前缀（Repeated prefixes） | 前缀缓存（prefix caching） |
| 分支推理（Branching reasoning） | 投机执行（speculative execution） |
| 工具依赖（Tool dependencies） | 依赖感知调度（dependency-aware scheduling） |
| 不同模型（Different models） | 路由（routing） |
| 工具延迟可变（Variable tool latency） | 异步执行（asynchronous execution） |
| 外部副作用（External side effects） | 安全与隔离（security & isolation） |
| 多个 agent（Multiple agents） | 编排与通信（orchestration & communication） |
| 长时运行任务（Long-running tasks） | 检查点与容错（checkpointing & fault tolerance） |

这张表基本就是后续所有课程的「目录」：每一行都会展开成一到几节课。

### 8.8 可观测性是一等问题（Observability is a first-class problem）

**对 agent 而言，分布式追踪（distributed trace）变成了一棵嵌套的轨迹树（nested trajectory）**，层级为：Session（会话）→ Turn（轮次）→ Agent step（智能体步骤）→ Model request（模型请求）→ Tool call（工具调用）→ Tool result（工具结果）→ Agent step → …，还可以嵌套 Subagent（子智能体）。

配套金句：**“You cannot optimize what you cannot observe.”**（你无法优化你无法观测的东西。）

图示：该图以缩进的树形/嵌套结构展示 trace 的层级——一个 Session 内含多个 Turn，每个 Turn 展开为若干 Agent step，每个 step 又展开为模型请求与工具调用/结果，且可进一步展开出 Subagent，强调 agent 的可观测性层级远深于传统请求追踪。

### 8.9 你在本课程中会思考的问题（Questions you will think about in this course）

幻灯片列出九个贯穿全课程的问题：

1. 为什么 batching（批处理）能提升吞吐量，却会损害 agent 延迟？
2. 什么时候 agent 应该换用更大的模型？
3. KV / prefix 状态应该放在哪里？
4. 来自同一个 agent 的请求应该怎样调度？
5. 工具调用能否与推理重叠（overlap with inference）？
6. 什么时候应该派生一个 subagent？
7. 如何在异构 GPU 与不同模型之间做路由？
8. 当一个运行 30 分钟的 agent 中途失败时，我们如何恢复？
9. 如何优化「$/成功任务」而不是「tokens/s」？

结语：**“By the end of CS2680, you should answer these quantitatively.”**（学完 CS2680，你应该能定量地回答这些问题。）

### 8.10 本课程不覆盖的内容（What we will not cover）

- **训练（Training）**（括号注明原因：inference dominates compute demand，推理主导算力需求），包括：数据管道（data pipeline）、检查点（checkpoint）、预训练/微调/后训练（pre-training, fine-tuning, post-training）、RL rollout（强化学习 rollout）、集群管理（cluster management）；
- **模型架构设计**（Model architecture design）；
- **与推理相关的其他主题**（Other topics related to inference）：通信（Communication）、功耗与能耗（Power and energy）、新硬件设计（New hardware design）。

即课程边界明确：推理侧的系统（尤其 serving 与 agent 系统），不做训练系统、不做模型设计、不做通信与功耗深水区。

### 8.11 下节课与选读

下节课（Next class）：**LLM basics（LLM 基础）**。另有一页 Optional reading（选读材料），但文字层为空，未给出具体书目。

### 8.12 附录：AI agent 与 AI assistant、bot 的区别

幻灯片附两张对比表（来源标注为 Google Cloud 的文章）。第一张按三个维度区分三者：

| 维度 | AI agent | AI assistant | Bot |
|---|---|---|---|
| Purpose（目的） | 自主地、主动地执行任务（Autonomously and proactively performs tasks） | 辅助用户完成任务（Assists users with tasks） | 自动化简单任务或对话（Automates simple tasks or conversations） |
| Capabilities（能力） | 复杂的多步动作；能学习并适应；独立决策 | 响应提示；可以推荐行动，但由用户决定 | 遵循预定义规则；学习能力有限；基础交互 |
| Interaction（交互方式） | 主动；目标导向（Proactive; goal-oriented） | 被动；响应用户请求 | 被动；响应触发或指令 |

第二张给出三条关键差异：

- **自主性（Autonomy）**：agent 独立运作与决策以达成目标；assistant 需要用户的输入与指引；bot 遵循预先编程的规则。
- **复杂度（Complexity）**：agent 处理复杂任务与多步工作流；assistant 和 bot 适合较简单的任务与交互。
- **学习（Learning）**：agent 用机器学习随时间适应；assistant 可能学到一点；bot 几乎不学习。

## 核心要点

1. CS2680 是研究生级计算机**系统**课程（Agentic AI Systems），先修要求一门研究生系统课（OS/网络/数据库/体系结构）+ 真实系统经验；课程归属 Harvard MaDSys 研究组，讲师 Juncheng Yang（SEAS 助理教授，CMU 2024 毕业，曾任职 AWS、Snowflake、Cloudflare、Twitter），TF 为 Yiyu Liu 与 Yunjia Zheng，答疑均需预约。
2. 课程结构分两块：前几节 Foundations（LLM/agent 入门、Claude Code、设计与优化 coding agent），大部分课时是 Systems for LLMs & agents（GPU 编程与 kernel、batching/scheduling/内存管理、负载均衡与路由、KV cache 与 prefix cache、agent 服务系统）。
3. 五个作业递进：A1 给 Claude Code 做 Web UI（并为 A3 leaderboard 出题）→ A2 自建 coding agent（开放题：context、memory、test-time scaling、routing、subagent、tool call）→ A3 优化 coding agent（accuracy/cost/latency）→ A4 自部署小模型来 serve 自己的 agent（最难的作业，agent 与 serving 引擎协同调优）→ A5 全栈优化（量化、路由、微调、engine–agent co-design）。
4. 作业 3 与 5 按 leaderboard 排名 + 相对 baseline 提升打分；全学期每周 10+ 小时投入是预期；课程执行 20% A 政策，拿 A 甚至 A- 都很难。
5. 评分：作业 70%（A1/2/4 各 10%，A3/5 各 20%）+ 项目 16% + 演讲 10% + 参与 4%（含提出 AI 解决不了的问题）+ 附加分 10%；全学期 4 个 late day，迟交每天扣 20%。
6. 选课：预算 40、当日注册 80（cap 已提到 80）、另有 68 预注册 + 10 交叉注册 + 6 候补；GPU 资源不随人数同比例增长，截止日可能拿不到 GPU。
7. 使用 AI 被明确鼓励，但必须对 AI 生成的代码负全责，且每次作业都要上传 AI 会话日志（说明什么有效、什么无效）。
8. 计算资源：统一 Claude Code API（api.cs2680.com）、与 staff 共享的私有 GitHub 仓库、SLURM 的课程 HPC（RTX 6000 PRO Blackwell）、AWS（周五前填 Google Form，不用就关机）。
9. AI 系统与 AI/ML 的分工：AI/ML 问「用什么模型、怎么设计模型」，优化准确率与能力；AI Systems 问「如何大规模训练与服务」，优化 GPU 利用率、资源浪费、停机时间、碳足迹；本课程只聚焦 LLM 系统。
10. AI 系统计算的根本差异：CPU/GPU 异构分工（tokenization、kernel launch、数据移动、工具调用在 CPU，matmul 在 GPU）、**prefill compute-bound 而 decode memory-bandwidth-bound**、执行时间依赖输出长度因而不可预测。
11. 非确定性计算源于浮点非结合性（第 7 位小数就能翻转下一个 token），来自 Runtime（warp/block 调度、内存顺序、异步流、batch size）、软件（FMA、autotuning、次正规数）、硬件（CUDA vs tensor core、Hopper FP8 vs Blackwell 微缩放）三层；近似计算可接受，传递性也不成立。
12. 状态巨大：权重 GB–TB 级，KV cache 每 token 几十到几百 KB，prefix cache 跨请求复用 KV；多 GPU 通信涉及 pipeline/tensor/expert/context 并行、NCCL/UCCL、NVLink/Ethernet/InfiniBand，数据移动是瓶颈，RDMA 用于绕开 CPU/内核。
13. 模型与负载都在快速演进（MHA/GQA/MLA/NSA/线性注意力；多轮聊天、问题求解、RAG、agent 四类负载），策略是模型适配硬件与为模型设计硬件双向推进。
14. 可靠性数字：GPU 年故障率约 9%、MTBF 约 50,000 小时，16K-GPU 集群平均每 3 小时坏一块卡；GPU 700–1000W、每服务器 4–8 块，服务器功耗 800W → 6,000W（8 倍）。
15. Agent 定义：自主软件系统，用 AI 模型对目标推理、调用外部工具、执行多步动作直至任务完成；循环为 plan → act → observe → adapt → deliver。
16. LLM 是「奇怪的计算机」：超群于知识回忆、语言、模式匹配、代码生成、跨域运作，但弱于持久记忆、可靠的上下文理解、避免幻觉、知道自己不知道、安全与对抗输入——所以才需要 agent。
17. Agent = 一种新计算机：LLM↔CPU、上下文窗口↔RAM、工具↔外设、harness↔OS、agent↔应用；它有全新的编程模型与失效模型。
18. Agent 是系统问题：多轮使关键路径横跨 GPU/CPU/存储/网络/外部服务，具有步骤依赖、延迟高度可变、阻塞等待工具、轨迹任意点失败、状态快速增长、并发与投机六大特性。
19. 优化目标要换：throughput 是错误目标；应最大化 task success，在 latency/cost/reliability/security 约束下优化；真正看的是任务成功率、端到端延迟、tokens/任务、$/成功任务、能耗/成功任务——更高的 tokens/s 可能意味着更慢更贵的 agent。
20. 课程边界：不覆盖训练（数据管道、checkpoint、预训练/微调/后训练/RL rollout、集群管理）、模型架构设计，以及通信、功耗、新硬件设计等推理相关深水区；下节课进入 LLM basics。
