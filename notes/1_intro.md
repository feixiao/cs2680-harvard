# 第 1 讲：课程导论

> **Modern AI Systems: Agents and System Optimizations — Overview** · Harvard CS2680 · 讲师 Juncheng Yang · 课程主页 https://cs2680.com · Harvard MaDSys 组
> 原始幻灯片:[1_intro.pdf](../1_intro.pdf)

## 本讲概览

CS2680 是一门研究生级别的计算机系统课程,聚焦 LLM 系统与 agent serving(智能体服务)系统。本讲分三块:课程定位与学习内容;五个作业、开放选题 project、评分细则、使用 AI 的政策与计算资源;以及两个内容部分——Part I 讲 AI 系统与传统计算机系统的本质差异,Part II 讲 agent 的定义、为什么它是系统问题、agentic 技术栈与真正的优化目标。

课程归属 Harvard MaDSys 组:

> "People find solutions, we find problems; we measure, design, and operate real systems."

TF 为 Yiyu Liu 与 Yunjia Zheng,office hour 均预约制,staff 邮箱 cs2680-staff@g.harvard.edu。

## 课程定位与学习内容

- **定位**:研究生级别系统课程
  - 先修要求一门研究生级别系统课(OS / 网络 / 数据库 / 体系结构)与真实系统经验
  - 课堂时间有限,大量学习发生在课后——提供指引,靠动手学(learn by doing)
- **基础部分**(前几节课):
  - LLM 与 agent 入门
  - 使用 Claude Code
  - 设计一个 coding agent
  - 优化你的 coding agent

### 系统部分(大部分课时)

- GPU 编程与 kernel
- 批处理(batching)/ 调度(scheduling)/ 内存管理
- 负载均衡与路由(load balancing and routing)
- KV-cache 与 prefix cache(前缀缓存)
- agent serving 系统及其他优化

## 五个作业(合计 70%)

| # | 作业 | 核心内容 | 占比 |
|---|------|---------|------|
| 1 | Build a web UI for Claude Code | 解决一组简单问题;体验 coding agent 的"魔法";为作业 3 的 leaderboard 贡献新题目 | 10% |
| 2 | Build a simple coding agent | 开放题:context、memory、test-time scaling、routing、subagent、tool call;理解 coding agent 生命周期 (lifecycle) | 10% |
| 3 | Optimize your coding agent | 指标:accuracy、cost、latency;leaderboard 竞争 | 20% |
| 4 | Serve your agent | 从商业 API 转向自部署小模型;全学期最难的作业,任务更难;协同调优 agent 与 serving 引擎 | 10% |
| 5 | Optimize the full stack | 开放题:quantization、routing、fine-tuning、engine–agent co-design | 20% |

- 作业 3 与 5:
  - 按 leaderboard 排名 + 相对 baseline 的提升打分
  - 其分享会(sharing session)也按 leaderboard 组织

> **幻灯片上的警告对照表**:「作业 3 与 5 按 leaderboard 打分」/「在乎 GPA 就别选这门课——预计每周 10 小时以上」。

## Project(16%)与 Presentation(10%)

- **Project**:开放题、个人项目 + AI 辅助
  - reading period 期间:poster + demo session
  - 评分 = code + report + poster/demo 同侪评审
- **两种典型形态**:
  - 造一个自己会真实使用的工具(先找到真实 gap)
  - 研究性项目(先与 TF 沟通)
- **Presentation** 10%:一篇 paper + 作业 1
- **参与** 4%:课程反馈 + 提出 AI 解决不了的问题

## 评分、政策与行政

- **评分构成**:
  - 五个作业 70%(作业 1/2/4 各 10%,作业 3/5 各 20%)
  - Project 16%
  - Presentation 10%
  - 参与 4%
  - bonus 10%
- 执行 20% A 政策(20% A grading policy enforced):
  - 拿 A 甚至 A- 都很难
  - 全学期共 4 个 late day,迟交每天扣 20%
- **注册**:
  - 计划容量 40 / 当日已注册 80 / 68+10+6(预注册 + 交叉注册 + 候补)
  - 上限已提到 80,但计算资源不会同比例增加——作业截止日很可能拿不到 GPU
  - 旁听(auditing)仅在政策允许且有空位时可行
- **使用 AI 政策**:
  - 鼓励使用 AI,但必须对 AI 生成的代码进行推理审视,并对提交的所有代码负责
  - 每次作业提交必须上传 AI 会话日志(session log)作披露,说明哪些做法有效、哪些无效
- **出勤**:
  - 要求线下到场,课程不录像、不允许录制
  - 允许带笔记本,若打算整堂开着请坐后排
  - 客座讲座报名(sign-up)提前一周开放
- **计算资源**:
  - Claude Code API 统一走 api.cs2680.com
  - GitHub 私有仓库(与 staff 共享)
  - 课程 HPC 为 SLURM + RTX 6000 PRO Blackwell(仅限课程用途)
  - AWS:有 Canvas 访问权限即已入系统,周五前完成报名并填 Google Form,不用时必须关停实例

> **本课程首次开设,expect a bumpy ride**——课表(Week 1 → 14)与评分(如 paper reading)都可能调整。

## 课前背景问卷

- 调查系统课背景(OS / 分布式 / 数据库 / 网络 / 架构)与主题熟悉度:
  - Transformer 架构
  - TP / PP / DP / EP 并行
  - pagedAttention
  - iteration-level 调度
  - GPU
  - linear attention
  - Linux 内核编程
- **AI 使用层次**:
  - chat
  - coding agent
  - customized agent(MCP、Skills / Plugins、subagent、parallel agent)
- **Agentic coding 等级**:
  - 0 手写代码
  - 1 AI 自动补全(Assist)
  - 2 AI 写函数、你审查(Supervised)
  - 3 交付整个任务、你审查代码(Scoped)
  - 4 AI 写全部、测试验证(Goal-driven)
  - 另有 parallel agents(subagent 分工)

## Part I:AI 系统与传统系统的差异

- **两个视角**:
  - AI/ML 问"用哪个模型 / 如何设计模型"(优化 accuracy 与 capability)
  - AI systems 问"如何大规模训练并服务"(优化 GPU 利用率 / 资源浪费 / 停机时间 / 碳足迹)
  - 这是"能力变成产品"的地方,是关键的数字基础设施,且比 AI 本身更难
- **计算**:
  - 异构:CPU 做 tokenization、kernel launch、数据搬移、tool call;GPU 做 matmul;不同代 GPU 与 xPU 混布
  - prefill 是 compute-bound、decode 是 memory-bandwidth-bound,同一部署在 compute / bandwidth / capacity 三类瓶颈间切换
  - 执行时长依赖输出长度,不可预测,使调度复杂化
- **非确定性计算**:
  - 浮点加法不满足结合律,matmul 第 7 位小数的偏差会翻转下一个 token
  - 来源:runtime(warp/block 调度、内存顺序、异步流、batch size)、软件(FMA 与两条指令、autotuning、次正规数)、硬件(CUDA 与 tensor core 路径不同、Hopper FP8 与 Blackwell micro-scaling)
  - 分配律与传递性同样失效,近似计算(approximate computing)可以接受
- **巨大状态**:
  - 模型权重 GB 到 TB;KV-cache 每 token 10s–100s KB;prefix cache 跨请求复用 KV
  - 多 GPU 通信:pipeline / tensor / expert / context 并行,NCCL / UCCL,NVLink / Ethernet / InfiniBand,RDMA 绕开 CPU 与内核
  - 数据搬移是瓶颈
- **快速演进**:
  - 架构:MHA、GQA、MLA、NSA、linear attention
  - 负载:多轮聊天延迟敏感、problem solving 长输出、RAG 长上下文、agent 长上下文 + routing + 负载均衡
  - 都在快速变化;对策是模型适配硬件与为模型设计硬件双向进行
- **可靠性与功耗**:
  - GPU AFR 约 9%、MTBF 约 50,000 小时——16K-GPU 集群平均每 3 小时坏一块 GPU
  - CPU 100–300W 对 GPU 700–1000W(每服务器 4–8 块)
  - 整机功耗 800W → 6,000W(8 倍),功率波动是工程问题

## Part II:Agentic AI 系统

- **定义**:agent 是自主软件系统,用 AI 模型对目标推理、使用外部工具、执行多步动作直至任务完成
  - 循环:plan → act(调用 API / 数据库)→ observe → adapt → deliver
  - 由 LLM(推理与规划)+ Memory 构成,经 Action / Observation 与环境交互
- **为什么需要 agent**:LLM 是"奇怪的计算机"
  - 超群于:海量事实回忆、语言、模式匹配、代码生成、跨域作业
  - 出奇地弱于:持久记忆、可靠理解上下文、避免幻觉、知道自己不知道、安全与对抗输入
  - 因此需要工具 + 记忆 + 校验的外围框架
- **类比**:
  - LLM ≈ CPU
  - context window ≈ RAM / 工作内存
  - tools ≈ 外设
  - agent harness ≈ OS
  - agent ≈ 应用
  - 一种新的可编程计算机,有完全不同的编程模型与失效模型
- **为什么 agent 是系统问题**:
  - 传统 serving:request → inference → response
  - agent serving:多轮 infer / tool / retrieval 交替,关键路径跨 GPU、CPU、存储、网络与外部服务
  - 面临:步骤间依赖、高度可变的步骤延迟、阻塞等待工具、轨迹中任何位置失效、快速膨胀的状态、并发与投机执行

### Agentic 技术栈(自顶向下)

- 应用 / 用户
- agent / harness(planning、context、memory、tools、subagents)
- model serving(batching、scheduling、routing、caching)+ 外部环境(web、files、API、人)
- runtime / kernels(CUDA、Triton、collectives、scheduling、caching)
- 硬件(GPU、CPU、memory、network、storage)
- serving 与硬件做协同设计

- **优化目标**:
  - 吞吐量(tokens/sec)对 agent 是错误目标
  - 真正优化的:task success / accuracy、端到端延迟、tokens / task、$/successful task、energy / successful task(受资源约束)
  - TTFT / TPOT、tool-call 延迟、GPU 利用率"有用但不够"——更多 tokens/sec 仍可能是更慢更贵的 agent

### Agentic 负载属性与系统问题的一一对应

- 长轨迹 → 状态与上下文管理
- 巨大 context → 内存层级与检索
- 重复前缀 → prefix caching
- 分支推理 → speculative execution
- 工具依赖 → 依赖感知调度
- 不同模型 → routing
- 可变工具延迟 → 异步执行
- 外部副作用 → 安全与隔离
- 多 agent → 编排与通信
- 长时任务 → checkpoint 与容错

- **可观测性是一等问题**:agent 的分布式 trace 变成嵌套轨迹(Session → Turn → agent step → model request → tool call / result → subagent)

> "you cannot optimize what you cannot observe"

### 课程要回答的代表性问题

- batching 为何提升吞吐却伤害 agent 延迟?
- 何时该用更大的模型?
- KV / prefix 状态应放在哪里?
- 同一 agent 的请求如何调度?
- tool call 能否与推理重叠?
- 何时该 spawn subagent?
- 如何跨异构 GPU 与模型路由?
- 30 分钟的 agent 如何恢复?
- 如何优化 $/successful task 而非 tokens/s——结课时应能定量回答。

- **课程边界**:
  - 明确不覆盖训练(数据管道、checkpoint、预训练 / 微调 / 后训练、RL rollout、集群管理)与模型架构设计
  - 下节课进入 LLM basics
- **附:agent / assistant / bot 的区分**(引 Google):
  - agent:自主、主动执行复杂多步任务,并借助 ML 学习适应
  - assistant:响应用户请求,由用户做决定
  - bot:遵循预定义规则,对触发器响应,几乎不学习

## 核心要点

- 这是一门研究生系统课,主线是"从 coding agent 到 serving 系统再到全栈优化",先修一门研究生系统课。
- 五个作业递进:用 Claude Code → 自建 coding agent → 优化(leaderboard)→ 自部署 serving → 全栈优化;作业 3、5 按 leaderboard 排名 + baseline 提升打分。
- 评分:作业 70%、project 16%、presentation 10%、参与 4%、bonus 10%;20% A 政策,拿 A 很难;每周 10+ 小时投入是默认预期。
- 鼓励用 AI 但须对代码负责,每次作业提交必须附会话日志披露。
- prefill 是 compute-bound、decode 是 memory-bandwidth-bound——同一部署的瓶颈会切换,这是全课程的核心张力。
- 浮点非确定性使输出不可逐位复现;近似计算可接受,评估与 leaderboard 设计必须容忍数值抖动。
- 可靠性是常态而非尾部事件:16K-GPU 集群平均每 3 小时坏一块 GPU(AFR 9%、MTBF 50,000 小时)。
- agent 是"新的计算机":LLM≈CPU、context window≈RAM、tools≈外设、harness≈OS;其多轮、跨组件的执行轨迹是本质难点。
- 对 agent,throughput 是错误目标:真正优化 $/successful task、task success、端到端延迟。
- 十类 agentic 负载属性(长轨迹、大 context、重复前缀、分支推理、工具依赖等)一一对应本课程的系统主题。
- 可观测性是一等问题:trace 变成嵌套轨迹,看不见就不能优化。
- 课程不覆盖训练与模型架构设计,聚焦 LLM 推理 serving 与 agent 系统。
