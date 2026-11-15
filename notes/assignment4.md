# 作业 4：MadsServe（自持推理引擎）

> 原幻灯标题：*Assignment 4: MadsServe: Own the Serving Engine*（讲师：Juncheng Yang，cs2680.com）

## 本讲概览

本作业把"使用别人家推理服务"升级为"自己拥有整个 serving 引擎"：你在 ATG 集群上分配一台 GPU 节点，搭建 SGLang serving 引擎，把之前作业里做好的 Agent 接上这个自持引擎运行，然后深入度量端到端延迟，找出真实 Agent 工作负载下的性能瓶颈，最后针对你亲自观测到的瓶颈做优化，并通过迭代提交冲击排行榜。与前几个作业不同，这一作允许你改两处代码：serving 引擎本身（配置与代码）以及 Agent 使用 server 的方式，但明确禁止更换模型——因为本作业的重点是系统层的调度与服务效率，而不是换个更强的模型。评分由排行榜上的端到端时间（end-to-end time）和解出任务数（solved tasks）决定，其余规则与作业 3 类似，且引擎加载时间不计入评分。最终交付包括一份展示你对瓶颈理解的 Writeup 和一个 3 分钟的真人出镜视频。

## 作业总览（Overview）

幻灯片给出的工作主线是五步循环，每一步都建立在上一步之上：

1. **Setup the basic SGLang serving engine（搭建基础 SGLang serving 引擎）**——先有一个能跑起来的自持推理后端，替代之前依赖的商业 API。
2. **Run agent with the self-hosted serving engine（用自持引擎跑你的 Agent）**——把之前作业练好的 Agent 完整接上自己的引擎，在真实任务上跑通。
3. **Observe the bottleneck（观察瓶颈）**——不是凭直觉猜哪里慢，而是实际观测时间都花在哪里。
4. **Optimize for the bottleneck you have observed（针对你观测到的瓶颈做优化）**——优化的对象必须是你自己测出来的那个瓶颈，而不是教科书上的"标准优化清单"。
5. **Submit and iterate（提交并迭代）**——把优化后的版本提交上去，然后回到测量环节继续循环。

图示：该页是一张简单的流程性要点列表，按顺序呈现上述五个步骤，整体构成一个"测量 → 优化 → 再测量"的闭环工作流。

值得注意的是这条主线的方法论含义：作业不预设你要优化什么（比如不指定"去做前缀缓存"或"去调批处理"），而是要求你先建立可测量的事实基础，再基于事实决策。这与课程后半段反复强调的"先度量、后优化"的系统工程方法论一致。

## 基础 SGLang 搭建（Basic SGLang Setup）

- **First time setup in the ATG cluster（在 ATG 集群上首次搭建）**——所有环境准备都发生在课程的 ATG 集群里，第一次使用需要完成集群侧的初始配置。
- **Allocate a RTX Pro 4500 Node（分配一台 RTX Pro 4500 节点）**——你需要申请一台配有 RTX Pro 4500 GPU 的节点来跑 SGLang。
- **Follow the instructions on the Assignment 4 page to set up a SGLang instance and connect to your agent（按照课程 Assignment 4 网页上的说明，搭建一个 SGLang 实例并把你的 Agent 接上）**——具体的安装命令与连接配置以 Assignment 4 的官方网页为准，幻灯片本身不重复这些细节。

这一部分的意义在于：从"调商业 API"切换到"自持开源 serving 引擎"，引擎的每个可调参数和每行代码从此都在你的控制范围内——这正是后面"Own the Serving Engine"这一标题的由来。

## 测量性能（Measure the Performance）

- **Run your agent with all 25 tasks distributed to you（把你被分到的全部 25 个任务都跑一遍）**——完整跑 25 个任务，而不是挑几个容易的。幻灯片特别注明：**The task set is different from the task set on the leaderboard（你本地的任务集与排行榜上的任务集不同）**，所以本地测量结果只是诊断工具，最终成绩由排行榜上的另一套任务决定。
- **Log your agent and serving engine——/metrics endpoint in SGLang is useful（为你的 Agent 和 serving 引擎都记录日志——SGLang 提供的 /metrics 端点很有用）**——建议同时记录 Agent 侧（每步耗时、token 用量等）与引擎侧指标；SGLang 暴露的 /metrics 端点是采集引擎侧数据的关键接口。
- **Dig deep into where the time goes（深入挖掘时间到底花在哪里）**——把端到端时间拆开，定位时间的大头究竟在请求排队、prefill、decode、工具调用，还是 Agent 自身的逻辑开销。
- **Also run the SGLang bench to see how different the real serving is different from benchmarks（同时运行 SGLang 自带的基准测试 bench，看真实 serving 与 benchmark 之间的差异）**——幻灯片追问：**Does the benchmark show the same trend or different trend due to some reason?（benchmark 呈现的趋势和真实负载是相同的还是不同的？如果不同，是因为什么原因？）** 也就是说，你要对比合成基准（synthetic benchmark）与你 Agent 产生的真实流量（real serving）之间的行为差异，并解释差异的来源——例如真实 Agent 请求的到达模式、请求长度分布与上下文复用特征与 bench 的均匀假设可能完全不同。

图示：该页为要点列表，核心信息是"双轨测量"：一路记录 Agent + 引擎的 /metrics 日志，一路跑 SGLang bench，再把两者放在一起对比。

## 让 Serving 更高效（Make Serving Efficient）

- **Think about the possible solutions to the problem you found in the measurement（基于测量中发现的问题，思考可能的解决方案）**——先列出候选方案清单，再做实验验证。
- **Try the solutions——One solution at a time（逐个尝试——一次只改一个方案）**——幻灯片明确要求一次只动一个变量，这样才能把性能变化归因到具体改动上，避免多变量混杂后说不清收益来自哪里。
- **Allowed changes（允许修改的范围）**：
  - **Serving engine changes: configuration and code（serving 引擎：可以改配置，也可以改代码）**——从调参（如批处理、缓存策略相关配置）到直接改引擎源码都可以。
  - **The agent: how it uses the server（Agent：可以改它使用 server 的方式）**——例如请求的组织方式、对引擎功能的利用方式。
- **Model change is not allowed in the assignment (not the focus of this assignment)（不允许更换模型——这不是本作业的重点）**——换模型会同时改变质量与速度，把"系统优化"的效果污染掉；本作业考察的是在固定模型前提下，把 serving 系统本身做快、做省。

## 排行榜（Leaderboard）

- **We will run the serving engine in a sandbox（排行榜由官方在沙箱中运行你的 serving 引擎）**——评测环境由课程方控制，保证公平。
- **Grading: end-to-end time, and solved tasks（评分依据：端到端时间与解出的任务数）**——两个指标共同决定你的名次，一个衡量快慢，一个衡量能力上限。
- **The others are similar to Assignment 3（其余规则与作业 3 类似）**——除上述差异外，其他评分细节沿用作业 3 的设定。
- **The serving engine loading time is not counted（serving 引擎的加载时间不计入评分）**——启动引擎、加载权重等一次性开销不计，只考核真正跑任务阶段的端到端表现。

## Writeup 与视频（Writeup & Video）

- **Show your understanding（展示你的理解）**——交付物不是为了展示"我做了一些优化"，而是展示"我理解了为什么这些优化有效/无效"。
- **Required content in Writeup（Writeup 必须包含的内容）**：
  1. **The bottleneck you found in the measurement（你在测量中发现的瓶颈）**；
  2. **The findings compared to the SGLang benchmark（与 SGLang benchmark 对比后的发现）**——即真实负载与合成基准的趋势异同及其原因；
  3. **Changes made with detailed observation and reasoning（所做的改动，附详细的观测数据与推理过程）**——每个改动都要有测量支撑的论证链；
  4. **Lessons learned（经验教训）**。
- **Video（视频）**：**3-minute video with your face and real human interaction（3 分钟视频，要求真人出镜并有真实的人机交互演示）**——需要展示你本人在真实环境中与系统/Agent 的交互，而非纯录屏或纯讲解。

## 公告（Notices）

- **Please be considerate. Use at most 1 GPU at a time!（请体谅他人——同时最多使用 1 块 GPU！）**——集群资源共享，硬性限制每人同时占用不超过 1 块 GPU；需要更多算力时请排队复用而非多开。

## 核心要点

- 本作业主题是 **"Own the Serving Engine"**：自己搭建 SGLang serving 引擎并把它作为 Agent 的推理后端，全面接管服务层。
- 工作主线是五步循环：搭引擎 → 跑 Agent → 观察瓶颈 → 针对观测到的瓶颈优化 → 提交并迭代。
- 环境：在 **ATG 集群**上首次搭建，分配一台 **RTX Pro 4500** 节点；SGLang 的具体安装与连接说明以课程 Assignment 4 网页为准。
- 本地测量要跑满分配的 **25 个任务**，且**本地任务集 ≠ 排行榜任务集**——本地结果只用于诊断，最终成绩由排行榜上不同的任务集决定。
- 日志记录要双轨并行：Agent 侧日志 + serving 引擎侧指标，其中 **SGLang 的 /metrics 端点**是引擎侧数据采集的关键。
- 必须 **"dig deep into where the time goes"**：把端到端时间拆解，找出时间真正的大头，而不是凭猜测优化。
- 必须同时跑 **SGLang bench** 并与真实 Agent 流量对比，判断两者的趋势相同还是不同，并解释差异原因。
- 优化实验纪律：**one solution at a time**——一次只改一个方案，保证性能变化可归因。
- 允许改动的范围只有两处：**serving 引擎（配置与代码）**和 **Agent 使用 server 的方式**。
- **模型更换被明确禁止**——本作业的重点是服务/调度系统优化，不是换模型。
- 排行榜由官方**沙箱**运行你的 serving 引擎；**引擎加载时间不计分**。
- 评分指标为 **end-to-end time（端到端时间）+ solved tasks（解出任务数）**，其余规则与作业 3 类似。
- Writeup 四项必写内容：测量发现的瓶颈、与 SGLang benchmark 对比的发现、改动及其详细观测与推理、经验教训。
- 视频要求：**3 分钟、真人出镜、有真实人机交互演示**。
- 资源纪律：集群共享，**同时最多使用 1 块 GPU**。
- 方法论主线：先建立可测量的事实（/metrics + bench 双轨对照），再基于事实单变量实验，最后用完整论证链写进 Writeup。
