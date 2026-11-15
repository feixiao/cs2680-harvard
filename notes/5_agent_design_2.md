# 第5讲：智能体设计 II（多智能体系统）

> 原讲次：*Agent Design II: Multi-Agent Systems*，Harvard CS2680《Modern AI Systems: Agents and System Optimizations》（Juncheng Yang，cs2680.com）

## 本讲概览

本讲是智能体设计的第二讲，主题从「一个智能体」转向「多个智能体」：何时该把工作拆给多个 agent，怎么拆，怎么通信，以及由此继承自分布式系统的种种难题。全讲围绕三条线索展开——架构（Architecture）、协调（Coordination，重点是任务分解 task decomposition）、通信（Communication）。课程先给出「每个多智能体架构背后都对应三张图」的分析框架：控制图（谁协调）、任务图（工作如何分解）、通信图（如何传递信息），再用它统一解读八种经典架构（supervisor–worker、层次化、pipeline/DAG、blackboard、委员会/辩论、市场/拍卖、swarm、动态拓扑），并强调真实系统几乎都是混合体。随后讨论任务分解的切分维度、粒度权衡、静态与动态分解、常见失败模式，以及消息的格式与语义设计；进一步指出多智能体系统本质上是分布式系统，要面对超时重试、幂等性、部分失败等经典问题，且 LLM 黑盒（上下文丢失、污染、过期信息、冲突信念）会让这些问题更难。最后引入两个协议：A2A（agent 对 agent 的通信协议：agent card、task 及其生命周期）与 MCP（agent 对能力/服务的能力协议），并给出核心设计原则：**很多时候单个 agent 就够了**。

## 课程信息（Logistics）

- Claude Code Premium 席位（seat）已配置；Assignment 1 相关事项在 Canvas 上。
- 课程 repo url、mini product 等事项见 Canvas。
- **Assignment 2 正在等你，截止约在两周后**；pre-proposal（预提案）需要提交。
- 下次 Office hour：下周四 3:30–5pm，地点 SEC 4.308。

## 今日计划（Plan for today）

- Multi-agent design（多智能体设计）
  - Architecture（架构）
  - Coordination: task decomposition（协调：任务分解）
  - Communication（通信）
- Agent memory（智能体记忆）

## 从一个 agent 到多个 agent

多智能体（multi-agent）并不是新事物——它有数十年的研究历史，本讲不展开这段历史，而是聚焦于把多智能体当作**系统工程问题**来设计。从单一 agent 到多智能体系统，需要回答三个层面的问题：

1. **Architecture（架构）**：agent 之间如何组织？
2. **Coordination（协调）**：工作如何在 agent 之间分解与协调？
3. **Communication（通信）**：agent 之间如何传递信息？

### 何时、为何把工作拆分给多个 agent？

幻灯片给出两大动机（并举手提问「when and why split work across agents?」）：

- **Specialization & isolation（专业化与隔离）**：让不同的 agent 使用不同的模型（models）、不同的提示词（prompts），并赋予不同的工具权限（tools/privileges）——例如只给某个 agent 暴露危险工具，隔离风险。
- **Parallelism & context management（并行与上下文管理）**：让相互独立的子任务并发执行（independent subtasks execute concurrently），并且**不要**把整条轨迹（entire trajectory）塞给每个 agent，从而控制每个 agent 的上下文长度。

## 每个架构背后的三张图（Three questions / graphs behind every architecture）

这是本讲的核心分析框架。设计任何多智能体系统时，先回答三个问题：

1. **Control graph（控制图）：Who coordinates?（谁协调？）**
   是一个 supervisor（监督者）、一套层次结构（hierarchy），还是根本没有人协调？协调关系是否在运行时变化（例如 handoff 交接）？
2. **Task graph（任务图）：How is work decomposed?（工作如何分解？）**
   由 planner 在执行前预先规划（up front）、由竞价（bidding）决定，还是从局部规则中涌现（emergently from local rules）？
3. **Communication graph（通信图）：How do they communicate?（如何通信？）**
   直接消息（direct messages）、广播（broadcast），还是共享工作区（shared workspace）？

后面每一种架构都可以用这三张图来刻画（控制、任务分解、通信分别落在什么形状上）。

## 八种多智能体架构（Multi-agent architecture）

幻灯片列出八种：**1. Supervisor–worker，2. Hierarchical，3. Pipeline/DAG，4. Blackboard，5. Committee，6. Market，7. Swarm，8. Dynamic topology**。下面逐一展开。

### 1. Supervisor–Worker（监督者–工作者）

- **结构**：一个 agent 负责计划（plan）、分派（delegate）和整合（integrate）；worker 只看到自己的子任务。
- **适用场景**：子任务相互独立、可以并行执行时最好。
- **弱点**：supervisor 会成为瓶颈（bottleneck）——它要重新读取每一个 worker 的结果，因此它的上下文增长得最快。
- 图示：一个 Supervisor 位于中心，下挂 Researcher、Coder、Reviewer 三个 worker。
- 三图刻画：**Task**：supervisor 预先拆分（splits up front）；**Control**：单一 supervisor；**Comms**：星型（star），一切经由 supervisor。

### 2. Hierarchical Agents（层次化智能体）

- **结构**：把 supervisor–worker 递归套用：supervisor 管理 sub-supervisor（supervisors of supervisors）。
- **适用场景**：任务本身已经呈层次化分解的结构——例如存储系统、查询引擎、测试体系这类天然分层的工程任务。
- **挑战**：分解发生在哪一层？多少上下文需要跨越每一层边界（how much context crosses each boundary）？
- 图示（示例：feature build 功能开发）：Feature manager（功能经理）之下是 Backend lead 与 Frontend lead 两个组长，再往下分别是 API、Database（后端）与 UI、E2E tests（前端）四个执行 agent。
- 三图刻画：**Task**：每一层再次拆分；**Control**：嵌套的 supervisor 链；**Comms**：树型（tree），只与父/子通信。

### 3. Pipeline / DAG（流水线 / 有向无环图）

- **结构**：固定的阶段（fixed stages），每个边界处有类型化契约（typed contract）。
- **优点**：是最便宜的（cheapest）拓扑，易于调试——错误可以定位到具体某个阶段（errors localize to a stage）。
- **弱点**：没有向后的路径（no path backwards）——第四阶段无法回头向第一阶段要更好的输入源（stage four cannot ask stage one for a better source）。
- 图示（示例：invoice processing 发票处理）：OCR → Extract fields（字段抽取）→ Match to PO（匹配采购订单）→ Approve（审批）→ Post to ledger（过账）。
- 一条重要经验：「one retry edge beats one more agent」——**加一条重试边（retry edge）往往比多加一个 agent 更划算**。
- 三图刻画：**Task**：阶段在设计时就固定；**Control**：顺序本身就是控制（the order is the control）；**Comms**：阶段到阶段（stage to stage）。

### 4. Blackboard and Shared Memory（黑板与共享内存）

- **结构**：agent 通过共享状态（shared state）协调，而不是直接互发消息。这个 workspace（工作区）可以是数据库、向量库（vector store）、文件系统、Git 仓库或任务图。
- **优点**：agent 可以随意加入或离开而无需重新接线（join or leave without rewiring）；共享状态是持久（durable）且可检视（inspectable）的。
- **挑战**：一致性（consistency）、并发控制（concurrency control）、来源追踪（provenance）、版本管理（versioning）、垃圾回收（garbage collection）。
- 图示（示例：agent 共享一个 Git 仓库——任务列表、commits、历史）：Feature agent、Refactor agent、Test agent 都读写同一个 Git repository。
- 三图刻画：**Task**：从共享状态中涌现（emerges from shared state）；**Control**：没有中心控制；**Comms**：间接，经由工作区。

### 5. Committee / Debate（委员会 / 辩论）

- **结构**：多个 agent 各自提出方案（propose）并相互讨论（discuss），然后由一个 judge（裁判）或投票（vote）来裁决分歧。
- **优点**：在判断密集型任务（judgment-heavy tasks，如评分、审核）上能提升准确率。
- **失败模式——agreement without independence（无独立性的共识）**：如果各「委员」使用相同的模型和相同的上下文，它们会有相同的盲点（same blind spot），投票只会放大而非纠正错误。独立性是委员会机制有效的前提。
- 图示（示例：essay grading 论文/作文评分）：Grader A、Grader B 两个评分 agent 输出交给 Judge 裁定。
- 三图刻画：**Task**：同一个任务并行重复执行；**Control**：judge 裁决；**Comms**：peer 之间先讨论，然后提交给 judge。

### 6. Market and Auction（市场与拍卖）

- **结构**：任务被广播（announced）后，agent 根据自身能力（capability）、成本（cost）与延迟（latency）出价（bid）。异质 agent 在模型、工具、机器、成本、专业度上各不相同；任务落到**最便宜的有能力**的 agent 上，无需中心 planner。
- **弱点**：bid 是自我申报的（self-reported）——agent 可以通过夸大话（overstating what it can do）来赢下任务，即「劣币驱逐良币」式的激励失真。
- 图示（示例：GPU job router 训练任务路由——规则：5 秒内完成的最低出价获胜）：广播「Who can run this training job?」后，A100 节点出价 $0.20 · ETA 3s；T4 节点出价 $0.05 · ETA 10s（超过 5 秒，出局）；H100 节点出价 $0.40 · ETA 1s。最终任务判给 A100 节点（Job goes to A100 node）。
- 三图刻画：**Task**：广播任务，按 bid 认领；**Control**：拍卖者（auctioneer）清算；**Comms**：广播出去、bid 收回。

### 7. Swarm（群体）

- **结构**：没有常驻协调者（no permanent coordinator），agent 之间直接谈判（negotiate）、直接交换发现（exchange findings）。需要为发现（discovery）、寻址（addressing）、同步（synchronization）、终止（termination）、信任（trust）设计协议。
- **优点**：没有协调者，就不存在单点瓶颈或单点故障；peer 随时加入退出，工作继续进行。
- **弱点**：通信复杂度是 O(n²)；冲突解决（conflict resolution）困难。**很少在产品中使用（Rarely used in products）**。
- 图示（示例：仓库机器人协商由谁拣哪个订单）：Picker 1 至 Picker 4 全互联（all-to-all）互相通信。
- 三图刻画：**Task**：局部协商决定；**Control**：无常驻协调者；**Comms**：全互联 all-to-all，O(n²)。

### 8. Dynamic Topology（动态拓扑）

- **结构**：任务执行过程中，agent 被动态地添加、移除或重新接线（added, removed or rewired）。
- **优点**：算力随难度伸缩（capacity scales with difficulty）——简单工单保持便宜，不需要为简单情况支付复杂组织的成本。
- **弱点**：每次运行的形态都不同，因此**故障难以复现**（failures are hard to reproduce）。
- 图示（示例：客服机器人）：一张普通工单（Routine ticket）只由 Support bot 处理；工单升级后（After escalation ticket escalates），Support bot 临时拉入 Billing agent 与 Log agent。
- 三图刻画：**Task**：随工作变难而重新拆分；**Control**：随 agent 加入而变化；**Comms**：运行时动态。

### 真实系统都是混合体（Real systems are hybrids）

幻灯片强调：上面的八种架构在真实产品中几乎总是被**混合**使用。图中示例：一个 Planner agent（兼有 supervisor 层次结构 + 共享记忆 + 流水线特征）维护一个**动态任务 DAG**，在「需要时重新规划」（re-plan if needed）；Coder、Researcher、Tester 作为 worker 执行，Reviewer 从共享的 Shared Git 仓库读取结果。也就是说：控制走 supervisor 层次、任务图是动态 DAG、通信同时用了直接消息与共享 Git 工作区、拓扑可以动态变化——一张系统图里同时体现多种架构。

### 八种架构汇总表

|Category（类别）|Architecture（架构）|Core idea（核心思想）|Best for（适合）|Weakness（弱点）|
|---|---|---|---|---|
| Centralized（集中式）| Supervisor–worker | One planner, many workers | Separable subtasks（可分离的子任务）| Planner bottleneck（planner 瓶颈）|
| Hierarchical（层次式）| Supervisors of supervisors | Recursive splits（递归拆分）| Errors amplify（误差放大）* | *（该单元格在 PDF 文本层为空）* |
| Pipeline / DAG | Each stage feeds the next（每阶段喂给下一阶段）| Clear ordered stages（清晰的有序阶段）* | Errors propagate（误差传播）* | *（该单元格在 PDF 文本层为空）* |
| Market / auction（市场/拍卖）| Agents bid for tasks（agent 竞价任务）| Dynamic allocation（动态分配）* | Bad bids（坏出价）* | *（该单元格在 PDF 文本层为空）* |
| Decentralized（去中心化）| Blackboard | Shared workspace（共享工作区）| One shared artifact（单一共享产物）| Stale state（过期状态）|
| Committee / debate（委员会/辩论）| Answer, then reconcile（先各自回答再调和）| Judgment calls（判断类任务）* | Groupthink（群体思维）* | *（该单元格在 PDF 文本层为空）* |
| Swarm（群体）| Direct talk, no controller（直接对话、无控制器）| Local negotiation（局部协商）* | O(n²) messages（O(n²) 消息）* | *（该单元格在 PDF 文本层为空）* |
| Hybrid（混合）| Dynamic topology（动态拓扑）| Rewires as work proceeds（随工作进展重新接线）| Unknown structure（未知结构）| Hard to debug（难以调试）|

*注：上表按 PDF 文本层逐行还原；文本层中部分单元格的列位置存在错位/空缺，各架构的完整「Best for / Weakness」论述以前面各架构单页为准。*

## 任务分解（Task decomposition）

图示：一个 Complex task（复杂任务）被拆成 Sub-task 1 / 2 / 3，各自执行后合并（merged）为最终结果。

### 按什么维度拆？

幻灯片给出六种拆分的轴：

- **Data（按数据）**：每个 agent 处理一部分文档或记录（subset of documents or records）。
- **Expertise（按专业）**：例如安全（security）、性能（performance）、正确性（correctness）、法律（legal）分析各一个 agent。
- **Stage（按阶段）**：plan（规划）、implement（实现）、test（测试）、review（评审）。
- **Hypothesis（按假设）**：多个 agent 调查相互竞争的解释（competing explanations）。
- **Tool（按工具）**：分别使用 Web、数据库、代码执行或内部文档。
- **Authority（按权限域）**：agent 在不同的管理域（administrative domains）中行动（不同权限/不同系统边界）。

示例：一个涉及 200 个文件的 PR，先按 data（文件）拆，再按 expertise（安全、性能）拆——即两种维度叠加使用。

### 创建子任务时要写清什么？

每个子任务定义应包含：

- **Objective**（目标）
- **Expected output schema**（期望的输出结构/模式）
- **Inputs and relevant context**（输入与相关上下文）
- **Completion test**（完成判据）
- **Boundaries and exclusions**（边界与排除项）
- **Budget and deadline**（预算与截止时间）
- **Available tools and permissions**（可用工具与权限）
- **Dependencies**（依赖关系）

幻灯片用对比说明：

- 差的子任务：「Research storage systems」（调研存储系统）——目标模糊、无输出结构、无边界。
- 好的子任务：「Identify storage-related papers published in 2026; return title, date, system contribution, evaluation scale and primary-source URL; exclude database query optimization.」（找出 2026 年发表的存储相关论文；返回标题、日期、系统贡献、评测规模与一手来源 URL；排除数据库查询优化。）——目标、输出字段、排除项全部明确。

### 粒度权衡（Granularity tradeoff）

- **任务太大（tasks too large）**：并行度低（little parallelism），工作仍是串行的（the work stays sequential）。
- **任务太小（tasks too small）**：调度与通信开销主导一切（scheduling and communication overhead dominates）。

幻灯片给出模型：`T ≈ T_planning + T_critical path + T_communication + T_merge`（总耗时 ≈ 规划耗时 + 关键路径 + 通信耗时 + 合并耗时）。结论：**只有当并行节省下来的串行工作，超过规划、通信与整合的成本时，并行化才有收益。**

示例：把 20 个一行就能查完的小查询（20 one-line lookups）批量成 4 个子任务，使开销低于收益（keep overhead below the gain）。

### 静态 vs 动态分解（Static versus dynamic decomposition）

幻灯片以 2×2 方式组合两个维度：

|  |  |
|---|---|
| **Static（静态）**：执行前已知；可预测、易评估。例：对上传的 5 个 PDF 各自做摘要。 | **Dynamic（动态）**：agent 根据发现即时创建新任务。例：发现一个死链（dead link）就生成一个查证任务。 |
| **Recursive（递归式）**：worker 自己也可以再委派。例：一个 review agent 为每个子领域各启动一个子 agent（spins up one sub-agent per subfield）。 | **Opportunistic（机会式）**：空闲 agent 认领新出现的任务。例：空闲 agent 领取下一份未标注的文档（picks up the next unlabeled document）。 |

重要告诫：**分解必须配备 spawn 上限（spawning limits）、预算（budgets）、深度限制（depth limits）和终止条件（termination conditions）**——否则委派会递归爆炸（delegation explodes recursively）。

### 常见分解失败（Common decomposition failures）

1. **Overlap（重叠）**：两个 agent 摘要了同一篇论文（two agents summarize the same paper）——重复劳动。
2. **Gap（缺口）**：任务范围写成「2020–2023」加上「2025–2026」，跳过了 2024——子任务并集不等于父任务全集。
3. **Hidden dependency（隐藏依赖）**：例如 Pricing（定价）依赖 Sizing（规格测算），但这个依赖只在运行时才发现（found only at run time），静态计划无法表达。
4. **Unmergeable outputs（输出不可合并）**：一个 agent 返回自由文本（free-form text），另一个返回 JSON，合并直接失败（merge fails）。
5. **Lost global context（全局上下文丢失）**：每个章节各自都没问题，但整份报告自相矛盾（Whole report ✗）——各子 agent 看不到彼此，局部正确 ≠ 全局一致。
6. **Straggler（掉队者）**：6 个 agent 中大部分在 20 秒内完成（约 20s/25s），有一个却花了 4 分钟——最慢的一个拖住整个合并。

## 智能体通信（Agent communication）

图示：User 向 Research Agent 提出请求，Research Agent 分别与 Web Agent、Coding Agent、Data Agent 交互（收发信息），最终把 Final answer 返回给 User——展示一个研究类 agent 协调多个专业 agent 再汇总回答的通信形态。

### 多智能体通信的四个维度（Four dimensions of multi-agent communication）

1. **Topology（拓扑）**：谁可以跟谁说话（who can talk to whom）？——由架构决定（前面讲过）：supervisor–worker、peer-to-peer、共享内存等。
2. **Medium（介质）**：信息如何交换（how is information exchanged）？——消息（messages）、文件（files）、数据库（database）、共享状态等。
3. **Channel（信道）**：信息如何传递（how is information passed）？——p2p、广播（broadcast）、发布–订阅（pub–sub）、共享状态（shared state）、请求–响应（request-response）。
4. **Format and Semantics（格式与语义）**：消息如何构造、信息如何表达（how is a message structured and how to express information）？——例如 delegate（委派）、report（汇报）、ask（询问）、handoff（交接）、cancel（取消）等操作类型。

### 通信介质（Communication medium）

- **Message passing（消息传递）**：agent 通过队列或总线发送显式消息。例：coder 把结果 post 到 orchestrator 的 inbox。
- **Shared memory（共享内存）**：一个进程内共享状态对象，所有 agent 读和写。例：一份随工作完成而更新的共享任务列表（shared task list）。
- **Files and artifacts，含数据库（文件与产物）**：工作产物通过文件存储交接。例：researcher 写 notes.md，writer 打开它。

### 通信信道（Communication channels）

- **Direct point-to-point messages（点对点直连消息）**：planner 把任务规格交给 coder。
- **Broadcast（广播）**：orchestrator 告诉所有 agent「构建 agent 失败了」。
- **Publish–subscribe（发布–订阅）**：agent 订阅一个「new ticket」主题，有新票据就反应。
- **Shared blackboard（共享黑板）**：agent 读写同一块共享「草稿板」（shared findings scratchpad）。
- **Request–response（请求–响应）**：agent 向 retrieval agent 查询并等待文档返回。
- **Artifact passing（产物传递）**：一个 agent 写 report.md，下一个 agent 读它。

### 消息格式（Message format）

两种极端：

- **Natural language（自然语言）**：灵活，但含糊（flexible, but ambiguous）。
- **Structured messages（结构化消息）**：容易校验，但表达力弱（easy to validate, less expressive）。

**实用设计是两者兼用**——结构化字段承载控制信息，自然语言承载内容。幻灯片示例：

```json
{
  "task_id": "T17",
  "type": "result",
  "status": "complete",
  "claim": "The regression began after commit X",
  "confidence": 0.82,
  "evidence": ["log:2391", "commit:X"],
  "artifact": "analysis/T17.json",
  "requires_response": false
}
```

其中 `claim` 是自然语言内容，`task_id`、`type`、`status`、`confidence`、`evidence`、`requires_response` 等是结构化控制字段。

### 消息应携带语义：控制与内容分离（Messages should carry semantics）

幻灯片对比两种消息设计：

| Everything in one string（一切塞进一个字符串） | 结构化控制字段（Operations the runtime knows）|
|---|---|
| `{"message": "some text"}` | `{"id": "msg-381", "task_id": "t-17", "from": "planner", "to": "researcher", "type": "DELEGATE", "payload": { ... }}` |

右侧消息中，`type` 取值为运行时可识别的操作码：**DELEGATE、QUERY、REPORT、HANDOFF、UPDATE、CANCEL、ACK、ERROR、COMPLETE**。

两条原则：

- **控制与内容分离（separate control from content）**：运行时（runtime）知道的操作（路由、重试、停止）由结构化字段驱动——「The runtime can route, retry and stop **without asking an LLM what the message meant**」（运行时不必去问 LLM「这条消息是什么意思」就能完成路由、重试和终止）。
- **「自然语言承载内容，结构化协议承载协调」（Natural language for content, structured protocol for coordination）。**

### 通信设计空间总表（Communication: the design space）

|Dimension（维度）|Options（选项）|Rule of thumb（经验法则）|
|---|---|---|
| Topology（拓扑）| supervisor–worker, peer-to-peer, mesh | Mirror the task's dependencies（镜像任务的依赖关系）|
| Medium（介质）| messages, shared memory, files | One medium per link（每条链路只用一种介质）|
| Channel（信道）| p2p, broadcast, pub–sub, request–reply | Broadcast only when all must know（只有所有人都必须知道时才广播）|
| Format（格式）| natural language + control fields | Route on the fields, not the prose（按字段路由，而不是按正文文本）|

总原则：**每个选择都在延迟（latency）、上下文（context）或可靠性（reliability）之间做权衡**（Every choice trades latency, context or reliability）。

### 通信是一个难啃的分布式系统问题（Communication is a hard distributed systems problem）

幻灯片场景：Agent A 向 Agent B 发送「purchase 8 GPU instances」（购买 8 台 GPU 实例）后**网络超时、没有回复**（network timeout — no reply）。此时面临一串经典分布式问题：

- **Did B execute the action?（B 到底执行了这个动作吗？）**——超时既可能意味着请求没到，也可能意味着请求已执行但响应丢了。
- retry, or give up?（重试，还是放弃？）
- at-most-once or at-least-once?（至多一次，还是至少一次语义？）
- is exactly-once even available here?（这里甚至能不能做到恰好一次？）

以及对应的工程手段：**在 task_id 上放幂等键（idempotency key）**、设计**补偿/回滚路径（compensation / rollback path）**——并且要回答「一次重复购买的钱谁出？」（who pays for a double purchase）。也就是说，多智能体之间的一次「发消息」就是一个完整的分布式事务问题。

### 分布式系统本来就难（Distributed systems are hard）

幻灯片列出六个经典难题，每条附多智能体场景下的表现：

1. **Unreliable network（不可靠网络）**：包延迟、丢失、乱序、重复（packet delay, drop, reordered, duplicated…）。
2. **No global clock（没有全局时钟）**：不同机器上的时钟不一致（clocks on different machines disagree）。
3. **Concurrency and non-determinism（并发与非确定性）**：多台机器同时修改状态（many machines modify state simultaneously）。
4. **Partial failure（部分失败）**：你无法区分一个**慢**的 agent 和一个**死**的 agent（you cannot tell a slow agent from a dead one）。
5. **Consistency among replicated states（复制状态之间的一致性）**：一致性、可用性、分区容忍与延迟之间的权衡（tradeoff between consistency, availability, partition, and latency，即 CAP/延迟权衡）。
6. **Debugging and observability（调试与可观测性）**：大量请求、带时钟漂移的分布式日志（many requests, distributed logs with clock drift）。

结论：**多智能体系统继承（inherit）了分布式系统的常见难题**——把 agent 之间的通信换成进程/服务之间的通信，就是同一个问题。

### 多 agent 运行时更多挑战（More challenges when the system runs multiple agents）

- **Scheduling（调度）**：谁接下来运行、运行多久（who runs next, and for how long）。
- **Resource allocation（资源分配）**：模型、CPU 等共享资源（models, CPU, and other shared resources）。
- **State management（状态管理）**：检查点（checkpoints）、内存（memory）、来源追踪（provenance）与版本（versioning）。
- **No predetermined request flow（没有预定的请求流）**：系统无法事先知道**谁（who）**需要运行、运行**多久（how long）**、每个 agent 会消耗**多少资源（how many resources）**——因为这些都取决于 LLM 的运行时行为，而非静态配置。

### 考虑黑盒 LLM 时更难（Even harder when you consider the black-box LLMs）

**Context（上下文）方面的四类问题：**

- **Information loss（信息丢失）**：摘要会丢掉 worker 知道的东西（summaries drop what the worker knew）。
- **Context pollution（上下文污染）**：重要的信息被埋掉（what matters gets buried）。
- **Stale information（过期信息）**：例如 B 仍然基于 X=3 行动，但世界已变成 X=5。
- **Conflicting beliefs（冲突信念）**：A 认为安全、B 认为有漏洞（A says safe, B says vulnerable）。

**Coordination and communication（协调与通信）方面的三类问题：**

- **Observability and failure diagnosis（可观测性与故障诊断）**：它为什么失败了？（Why did it fail?）——每个 agent 都是黑盒。
- **Lost ownership（所有权丢失）**：每个 agent 都以为另一个 agent 负责（each agent thinks another owns it）。
- **Communication loops（通信循环）**：A 问 B、B 问 C、C 又问回 A（A asks B, B asks C, C asks A）。

## A2A 协议：agent 对 agent（A2A: agent agent）

### 一个 A2A 示例

图示：Agent A 向 Agent B 委派任务：「Analyze whether company X should move its inference stack to GPUs Y.」（分析公司 X 是否应把推理栈迁到 GPU Y。）Agent B 的工作方式：

- **discover capabilities**：通过各 peer 的 **Agent Cards** 发现它们的能力；
- **send message, create task**：发送消息、创建 task，分派给各专业 agent：Research Agent（研究）、Finance Agent（估计 GPU 成本，Estimate GPU cost）、Search Agent（查找基准数据，Find benchmark data）、Coding Agent（运行这些基准，Run these benchmarks）；
- 过程中有 **progress updates**（进度更新），最终 **return artifact**（返回产物）。

### A2A Agent Card（智能体名片）

每个 A2A server 都发布一张机器可读的卡片（machine-readable card），兼具**发现（discovery）+ 能力描述（capability description）**。调用方（caller）从卡片中可学到五类信息：

- **Identity（身份）**——这个 agent 是谁；
- **Skills（技能）**——它声称能做什么；
- **Endpoints（端点）**——在哪里、如何调用；
- **Capabilities（能力）**——是否支持 streaming、push 等；
- **Auth（认证）**——需要满足哪种安全方案（security scheme）。

卡片示例（通过 `GET /.well-known/agent-card.json` 获取）：

```json
{
  "name": "Travel Agent",
  "description": "Plans business travel",
  "skills": [{ "id": "book-flight" }],
  "supportedInterfaces": [ ... ],
  "capabilities": { "streaming": true },
  "securitySchemes": { ... }
}
```

### A2A 的三个抽象（Three A2A abstractions）

核心关系：**一条 message 启动一个 task；task 以 artifact 形式返回结果**（A message starts a task; the task returns its results as artifacts）。

|Message（消息）|Task（任务）|Artifact（产物）|
|---|---|---|
| 客户端与 agent 之间的一轮交互（one turn between client and agent） | 带 ID 和生命周期（lifecycle）的有状态工作单元（stateful unit of work） | 任务产出的输出（output the task produces） |
| 例：「Book a flight to Boston」（订一张去波士顿的机票） | 例：task-42: working → completed | 例：行程单 PDF 与订票数据（Itinerary PDF and booking data） |

关系：Message **starts**（启动）Task，Task **returns**（返回）Artifact。

**任务生命周期（A2A task lifecycle）**：`Submitted → Working → Completed / Failed / Canceled`，另有 `Input required` 与 `Auth required` 两个暂停态（图中示例编号 42 的状态流转）。示例流转：「Book a flight」→ Submitted → Working → **Input required：「Which date?」** → 用户答「Oct 3」→ **Working 继续** → Completed。

要点：

- **Follow-ups join the same task（追问加入同一个 task）**：「Which date?」→「Oct 3」——多轮追问不是新任务，而是同一 task 的延续。
- **A2A 是一个有状态的任务协议（stateful task protocol）**：工作可以暂停等待输入（input）或认证（auth），然后恢复（resume）。

### 跟踪长时间运行的任务（Following a long-running task）

Task 可能运行几秒，也可能运行几小时；**调用方选择如何跟踪**：

- **Polling（轮询）**：客户端反复检查直到完成。**用于**短任务（short jobs）。
- **Streaming（流式）**：流式推送实时更新。**用于**交互式输出（interactive output）。
- **Push notification（推送通知）**：完成时触发 webhook。**用于**数小时级的长任务（hours-long jobs）。

边界原则：**A2A 标准化的是通信（communication），不是编排（orchestration）**——委派（delegation）、拆分（splitting）、停止（stopping）仍然归 harness（智能体运行时框架）负责。

## MCP：agent 的能力（MCP: agent capability）

MCP（Model Context Protocol）标准化的是 **agent 与外部能力/服务**的边界，四类标准内容：

- **tools（工具）**——可调用的、带类型的（callable, typed）能力；
- **resources（资源）**——宿主（host）可以附加的可读数据（readable data）；
- **prompts（提示模板）**——可复用的交互模板（reusable interaction templates）；
- **一个 client 可以对接多个 server**（one client speaks to many servers）；
- **是宿主（host），而不是模型（model），决定暴露什么**（the host, not the model, decides what is exposed）。

图示：一个 Agent 客户端对接 filesystem、database、GitHub、browser 等多个 MCP server。

定位：**MCP 是 agent 的服务边界（agent service boundary）：一次工具调用，一个结果（one tool call, one result）。**

## MCP vs. A2A

|（维度）|MCP|A2A|
|---|---|---|
| Primary abstraction（主要抽象）| capability / tool（能力/工具）| agent / task（智能体/任务）|
| Relationship（关系）| agent → service（智能体到服务）| agent → agent（智能体到智能体）|
| Discovery（发现）| tools, resources, prompts（工具、资源、提示）| agent capabilities（智能体能力，即 agent card）|
| Unit of work（工作单元）| one tool invocation（一次工具调用）| long-running task（长时间运行的任务）|
| Internal state（内部状态）| capability interface（能力接口，暴露）| ideally opaque（理想情况下不透明）|
| Analogy（类比）| device / API interface（设备/API 接口）| service-to-service RPC（服务到服务的 RPC）|

两层是叠加关系：**一个 A2A 远端 agent 本身可以再调用二十个 MCP server**（One A2A remote agent may itself call twenty MCP servers）——A2A 在 agent 层之上，MCP 在能力层之下。

## 设计原则（Design principles）

1. **Is multi-agent really necessary?（多智能体真的必要吗？）** 很多时候单个 agent 就够了；多个 agent 往往只是增加开销和复杂度（often only adds overhead and complexity）。默认从单 agent 出发，除非有前面讲的并行/隔离/上下文管理等明确收益。
2. **Decide topology（确定拓扑）**：让通信拓扑**反映任务的依赖关系**（reflect task dependencies），并**最小化通信**（minimize communication）。
3. **Identify information-loss points（找出信息丢失点）**：把每一个聚合节点（aggregation nodes）当作**细节被丢弃的地方**来对待（treat aggregation nodes as places where detail drops）——上游的丰富信息经过汇总/转述后会缩水，要显式管理。
4. **Identify failure-containment boundaries（确定故障隔离边界）**：确保系统不会因为单点失败而整体停摆（Make sure the system does not stall）。

收尾警句：**密集全互联（dense mesh）很少是最好的默认选择**（A dense mesh is rarely the best default）。更多的通信**会增加上下文压力，却不一定增加有用信息**（More communication can increase context pressure without increasing useful information）。

## 下次课程（Next class）

- Agent design III（智能体设计 III）

## 核心要点

- 把工作拆给多个 agent 的两大动机：**专业化与隔离**（不同模型、提示词、工具权限）和**并行与上下文管理**（独立子任务并发执行，避免每个 agent 都背全量轨迹）。
- 分析任何架构先问三个问题/画三张图：**控制图**（谁协调？单个 supervisor、层次、还是无人协调，运行时是否 handoff）、**任务图**（planner 预先规划、竞价、还是局部规则涌现）、**通信图**（直连消息、广播、还是共享工作区）。
- 八种架构各有明确适用场景与弱点：Supervisor–worker 适合独立子任务并行，但 supervisor 上下文增长最快、是瓶颈；Hierarchical 适合天然分层的任务，关键在分解位置与跨层上下文量；Pipeline/DAG 最易调试（错误可定位到阶段），但没有回头路，「一条重试边胜过多加一个 agent」；Blackboard 免接线、状态持久可检视，但有一致性/并发/溯源/版本/GC 难题；Committee 提升判断类任务准确率，但同模型同上下文 = 同盲点；Market 按能力/成本/延迟竞价实现无中心分配，但 bid 自报可以夸大；Swarm 无协调者无单点故障，但 O(n²) 通信、冲突难解，产品中很少用；Dynamic topology 让算力随难度伸缩，但每次运行形态不同、故障难复现。
- **真实系统是混合体**：典型形态是 planner + 动态任务 DAG + 共享 Git 工作区 + 按需 re-plan，同时体现 supervisor 层次、流水线与共享记忆。
- 任务分解可沿六个轴切分：data、expertise、stage、hypothesis、tool、authority，且可叠加（如 200 文件 PR 先按文件再按专业）。
- 好的子任务定义要写全：目标、期望输出 schema、输入与上下文、完成判据、边界与排除项、预算与截止时间、工具与权限、依赖。
- 粒度权衡：总耗时 ≈ 规划 + 关键路径 + 通信 + 合并；并行有收益仅当节省的串行时间超过这些开销（如 20 个一行查询合成 4 个子任务）。
- 分解有静态/动态 × 递归/机会式四种形态；无论哪种，都必须配 spawn 上限、预算、深度限制与终止条件，否则委派递归爆炸。
- 六大常见分解失败：重叠（Overlap）、缺口（Gap，如漏掉 2024 年）、隐藏依赖（运行时才发现）、输出不可合并（自由文本 vs JSON）、全局上下文丢失（每节都对但整体自相矛盾）、掉队者（Straggler，一个 agent 花 4 分钟拖住其余 20 秒完成的 5 个）。
- 通信设计有四个维度：拓扑、介质（消息/共享内存/文件与产物）、信道（p2p、广播、pub-sub、共享黑板、请求–响应、产物传递）、格式与语义（delegate/report/ask/handoff/cancel 等操作）。
- 实用消息设计 = **结构化控制字段 + 自然语言内容**（如 task_id/type/status/confidence/evidence + claim 文本）；运行时靠字段路由、重试、终止，**不用问 LLM 消息含义**；「自然语言承载内容，结构化协议承载协调」。
- 经验法则：拓扑镜像任务依赖；每条链路一种介质；只有所有人都必须知道才广播；按字段路由而不是按正文路由。每个选择都在延迟、上下文、可靠性之间权衡。
- 一次「发消息」就是分布式事务：超时时不知道对方是否已执行（如「购买 8 台 GPU 实例」），需要 task_id 上的幂等键、补偿/回滚路径，并明确重复执行的成本承担者。
- 多智能体系统继承分布式系统六大难题：不可靠网络、无全局时钟、并发与非确定性、部分失败（分不清慢与死）、复制状态一致性（CAP/延迟权衡）、带时钟漂移的分布式日志调试。
- 多 agent 运行时还要面对调度（谁运行、运行多久）、共享资源分配、状态管理（检查点/内存/溯源/版本），且**没有预定请求流**——无法预知谁运行、多久、耗多少资源。
- 黑盒 LLM 加剧一切：信息丢失、上下文污染、过期信息、冲突信念（上下文面）；故障难诊断、所有权丢失（谁以为谁负责）、通信循环（A→B→C→A）（协调面）。
- **A2A** 是 agent 对 agent 的协议：agent card（`GET /.well-known/agent-card.json`，含 Identity/Skills/Endpoints/Capabilities/Auth）用于发现；三个抽象 Message（一轮交互）→ Task（有状态工作单元，可暂停于 Input required / Auth required 再恢复，追问加入同一 task）→ Artifact（产物）；长任务跟踪可选轮询（短任务）、流式（交互输出）、推送（小时级）。**A2A 标准化通信而非编排**——委派、拆分、停止仍归 harness。
- **MCP** 是 agent 对能力/服务的协议（tools、resources、prompts；一个 client 对多个 server；宿主决定暴露什么）；定位是「agent 服务边界：一次调用一个结果」。MCP 类比设备/API 接口，A2A 类比服务间 RPC；一个 A2A 远端 agent 可以再调二十个 MCP server。
- 四条设计原则：多智能体真的必要吗（单 agent 往往够）？拓扑反映任务依赖并最小化通信？把聚合节点当信息丢失点？划清故障隔离边界让系统不停摆。警惕密集 mesh——更多通信可能只增加上下文压力而不增加有用信息。
