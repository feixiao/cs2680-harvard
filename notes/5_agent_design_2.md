# 第 5 讲:智能体设计 II(多智能体系统)

> **Agent Design II: Multi-Agent Systems** · Harvard CS2680 *Modern AI Systems: Agents and System Optimizations* · 讲师 Juncheng Yang
> 原始幻灯片:[5_agent_design_2.pdf](../5_agent_design_2.pdf)

## 本讲概览

本讲是智能体设计的第二讲,主题从「一个 agent」转向「多个 agent」:何时、为何把工作拆分给多个 agent,如何选架构、做任务分解、设计通信。课程先给出「三张图」(控制图、任务图、通信图)的分析框架,用它统一刻画八种经典架构;随后讲任务分解(拆分轴、粒度、静态/动态、失败模式)与通信(拓扑、介质、信道、格式与语义);最后指出多智能体系统继承分布式系统的经典难题,并引入 A2A 与 MCP 两个协议。贯穿全讲的核心立场:单个 agent 往往就够用,多智能体应是刻意的设计选择。

## 课程信息(Logistics)

- Claude Code Premium 席位、Assignment 1、repo URL、mini product 见 Canvas;pre-proposal(预提案)需提交。
- Assignment 2 截止约在两周后;下次 Office hour:下周四 3:30–5pm,SEC 4.308。
- 今日计划:multi-agent design(Architecture、Coordination: task decomposition、Communication)与 agent memory。

> **图示** 章节过渡页(PDF 第 4 页无文本层,位于 Plan 页与 From one agent to many 页之间)。

## 从一个 agent 到多个 agent

Multi-agent 并不新(有数十年研究史,本讲不展开历史),而是把它当作**系统工程问题**来设计,需回答三个层面:architecture(架构)、coordination(协调/任务分解)、communication(通信)。两大拆分动机:

- **Specialization & isolation(专业化与隔离)**:不同 agent 用不同模型、不同提示词,赋予不同工具权限(如只给某个 agent 危险工具以隔离风险)。
- **Parallelism & context management(并行与上下文管理)**:独立子任务并发执行,且**不要**给每个 agent 整条轨迹(entire trajectory),以控制上下文长度。

## 每个架构背后的三张图

设计任何多智能体系统前先回答三个问题(即画三张图):

- **Control graph(控制图,谁协调？)**:
  - 单一 supervisor、一套层次结构、还是根本无人协调
  - 协调关系是否在运行时变化(handoff 交接)
- **Task graph(任务图,工作如何分解？)**:
  - 由 planner 执行前预先规划
  - 由竞价(bidding)决定
  - 还是从局部规则中涌现
- **Communication graph(通信图,如何通信？)**:
  - 直接消息、广播、还是共享工作区

## 八种多智能体架构

八种架构:Supervisor–worker、Hierarchical、Pipeline/DAG、Blackboard、Committee、Market、Swarm、Dynamic topology。每种都用上述三图刻画(task / control / comms):

1. **Supervisor–worker**:一个 agent 负责 plan、delegate、integrate,worker 只看到自己的子任务
   - 子任务独立可并行时最佳;弱点:supervisor 要重读每个结果,上下文增长最快,成为瓶颈
   - 三图:supervisor 预先拆分 / 单一 supervisor / 星型(star,一切经 supervisor)
2. **Hierarchical(层次化)**:把 supervisor–worker 递归套用(supervisors 管理 sub-supervisors)
   - 适合天然分层分解的任务(存储系统、查询引擎、测试体系,如 feature build:Feature manager → Backend/Frontend lead → API、Database、UI、E2E tests)
   - 挑战:分解发生在哪一层、多少上下文跨越每层边界
   - 三图:每层再拆 / 嵌套 supervisor 链 / 树型(仅父子通信)
3. **Pipeline / DAG(流水线/有向无环图)**:固定阶段、每个边界有类型化契约(例:发票处理 OCR → extract fields → match to PO → approve → post to ledger)
   - 最便宜的调试拓扑——错误可定位到具体阶段;弱点:没有向后的路径(第 4 阶段无法回头找第 1 阶段要更好的输入源)
   - 经验:**「one retry edge beats one more agent」**(一条重试边胜过多加一个 agent)
   - 三图:阶段设计期固定 / 顺序即控制 / 阶段到阶段
4. **Blackboard / shared memory(黑板/共享内存)**:agent 通过共享状态协调而非直接互发消息
   - workspace 可以是数据库、向量库、文件系统、Git 仓库或任务图(例:多个 agent 共享一个 Git 仓库)
   - 优点:agent 随意加入/退出无需重新接线,共享状态持久(durable)且可检视(inspectable)
   - 挑战:一致性、并发控制、来源追踪(provenance)、版本管理、垃圾回收
   - 三图:任务从共享状态中涌现 / 无中心控制 / 经工作区间接通信
5. **Committee / debate(委员会/辩论)**:多个 agent 各自提出并讨论,由 judge 或投票裁决(例:essay grading,Grader A/B + Judge);提升判断密集型任务的准确率
   - 失败模式——**无独立性的共识(agreement without independence)**:相同模型 + 相同上下文 = 相同盲点,投票只放大错误;独立性是机制有效的前提
   - 三图:同一任务并行重复 / judge 裁决 / peer 先讨论再交 judge
6. **Market / auction(市场/拍卖)**:agent 按能力(capability)、成本(cost)、延迟(latency)竞价
   - 异质 agent(不同模型/工具/机器/成本/专业度)中,任务落到**最便宜的有能力者**身上,无需中心 planner
   - 例:GPU job router——5 秒内最低出价获胜:A100 $0.20 · ETA 3s 胜出,T4 $0.05 · ETA 10s 超时出局,H100 $0.40 · ETA 1s
   - 弱点:bid 自我申报,可夸大能力赢单
   - 三图:广播任务、按 bid 认领 / auctioneer 清算 / 广播出去、bid 收回
7. **Swarm(群体)**:无常驻协调者,agent 直接谈判、直接交换发现
   - 需要为发现(discovery)、寻址(addressing)、同步(synchronization)、终止(termination)、信任(trust)设计协议(例:仓库机器人协商拣单)
   - 无单点瓶颈/单点故障;弱点:通信复杂度 O(n²)、冲突解决困难,**产品中很少用(rarely used in products)**
   - 三图:局部协商 / 无常驻协调者 / 全互联 all-to-all
8. **Dynamic topology(动态拓扑)**:任务运行中 agent 被动态添加、移除、重新接线(例:客服 bot 升级工单后才拉入 Billing agent 与 Log agent)
   - 算力随难度伸缩、简单工单保持便宜;弱点:每次运行形态不同,故障难以复现
   - 三图:随工作变难重新拆分 / 控制随 agent 加入而变 / 运行时动态

> **真实系统都是混合体(Real systems are hybrids)**:典型形态是 Planner agent(结合 supervisor 层次 + 共享记忆 + 流水线特征)维护一个动态任务 DAG、需要时重新规划,worker(Coder/Researcher/Tester)执行、Reviewer 从共享 Git 仓库读取——一张系统图同时体现多种架构。

八种架构汇总表(按 PDF 文本层还原):

|Category|Architecture|Core idea|Best for|Weakness|
|---|---|---|---|---|
|Centralized|Supervisor–worker|One planner, many workers|Separable subtasks|Planner bottleneck|
|Hierarchical|Supervisors of supervisors|Recursive splits|Errors amplify||
|Pipeline / DAG|Each stage feeds the next|Clear ordered stages|Errors propagate||
|Market / auction|Agents bid for tasks|Dynamic allocation|Bad bids||
|Decentralized|Blackboard|Shared workspace|One shared artifact|Stale state|
|Committee / debate|Answer, then reconcile|Judgment calls|Groupthink||
|Swarm|Direct talk, no controller|Local negotiation|O(n²) messages||
|Hybrid|Dynamic topology|Rewires as work proceeds|Unknown structure|Hard to debug|

## 任务分解(Task decomposition)

复杂任务拆成若干子任务各自执行,最后合并(merge)为最终结果。

### 六个拆分轴

- **Data**:每个 agent 处理一部分文档/记录
- **Expertise**:安全、性能、正确性、法律各一个
- **Stage**:plan、implement、test、review
- **Hypothesis**:多个 agent 调查竞争性解释
- **Tool**:Web、数据库、代码执行、内部文档
- **Authority**:在不同管理域中行动

可叠加:200 文件的 PR 先按 data(文件)拆,再按 expertise(安全、性能)拆。

### 子任务定义:八要素

- objective
- 期望输出 schema
- 输入与相关上下文
- 完成判据
- 边界与排除项
- 预算与截止时间
- 可用工具与权限
- 依赖关系

对比:差的「Research storage systems」;好的「Identify storage-related papers published in 2026; return title, date, system contribution, evaluation scale and primary-source URL; exclude database query optimization.」

- **粒度权衡**:
  - 任务太大 → 并行度低、工作仍串行
  - 任务太小 → 调度与通信开销主导

> **模型**:`T ≈ T_planning + T_critical path + T_communication + T_merge`——并行化有收益**仅当**节省的串行工作超过规划/通信/整合成本(例:20 个一行查询批量成 4 个子任务)。

- **静态/动态 × 递归/机会式**:
  - **Static**:执行前已知、可预测易评估(对 5 个上传 PDF 各做摘要)
  - **Dynamic**:根据发现即时建任务(死链生成查证任务)
  - **Recursive**:worker 自己可再委派(review agent 每个子领域各开一个子 agent)
  - **Opportunistic**:空闲 agent 认领新任务(领下一份未标注文档)

> **分解必须配备 spawn 上限、预算、深度限制与终止条件**,否则委派递归爆炸。

### 六大常见失败

- **Overlap** 重叠(两个 agent 摘要同一篇论文)
- **Gap** 缺口(「2020–2023」+「2025–2026」漏掉 2024)
- **Hidden dependency** 隐藏依赖(Pricing 依赖 Sizing,只在运行时发现)
- **Unmergeable outputs** 输出不可合并(一个返回自由文本、另一个返回 JSON,merge 失败)
- **Lost global context** 全局上下文丢失(每节都对、整份报告自相矛盾)
- **Straggler** 掉队者(6 个 agent 五个 20–25s 完成、一个 4 分钟)

## 智能体通信(Agent communication)

> **图示** User 向 Research Agent 提请求,其与 Web / Coding / Data Agent 交互后返回 final answer。

- **四个维度**:
  - **Topology**:谁可以跟谁说话——由架构决定
  - **Medium**:信息如何交换:消息、共享内存、文件、数据库
  - **Channel**:信息如何传递:p2p、broadcast、pub–sub、共享状态、request–response
  - **Format and Semantics**:delegate、report、ask、handoff、cancel 等操作
- **介质(Medium)**:
  - **message passing**:经队列/总线,如 coder 把结果 post 到 orchestrator 的 inbox
  - **shared memory**:进程内共享状态对象,如随工作更新的共享任务列表
  - **files and artifacts**(含数据库):如 researcher 写 notes.md、writer 读取

### 信道(Channel):六种形式

- 点对点直连
- 广播(orchestrator 告知所有 agent「构建 agent 失败了」)
- 发布–订阅(订阅「new ticket」主题)
- 共享黑板(共享 findings scratchpad)
- 请求–响应
- 产物传递(写 report.md、下一个读)

- **消息格式(Message format)**:
  - 自然语言:灵活但含糊
  - 结构化消息:易校验但表达力弱
  - **实用设计两者兼用**——结构化字段承载控制信息,自然语言承载内容:

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

- **消息应携带语义**:
  - 对比「一切塞进一个字符串」(`{"message": "some text"}`)与结构化控制字段(`id`、`task_id`、`from`、`to`、`type`、`payload`)
  - `type` 取运行时可识别的操作码:**DELEGATE、QUERY、REPORT、HANDOFF、UPDATE、CANCEL、ACK、ERROR、COMPLETE**
  - 原则:**控制与内容分离**——运行时据此路由、重试、终止,**无需询问 LLM 消息含义**;「自然语言承载内容,结构化协议承载协调」
- **设计空间经验法则**(每个选择都在 latency / context / reliability 之间权衡):

|Dimension|Options|Rule of thumb|
|---|---|---|
|Topology|supervisor–worker, peer-to-peer, mesh|Mirror the task's dependencies|
|Medium|messages, shared memory, files|One medium per link|
|Channel|p2p, broadcast, pub–sub, request–reply|Broadcast only when all must know|
|Format|natural language + control fields|Route on the fields, not the prose|

- **发消息 = 分布式事务问题**:Agent A 向 B 发「purchase 8 GPU instances」后网络超时——B 到底执行了没有？
  - 需回答:retry 还是放弃、at-most-once 还是 at-least-once、能否 exactly-once
  - 工程手段:**task_id 上的幂等键(idempotency key)、补偿/回滚路径(compensation / rollback)**,以及「重复购买的钱谁出？」

### 继承分布式系统六大难题

- 不可靠网络:包延迟、丢失、乱序、重复
- 无全局时钟
- 并发与非确定性:多机同时改状态
- **部分失败**:分不清慢 agent 与死 agent
- 复制状态一致性:一致性/可用性/分区/延迟权衡
- 调试与可观测性:大量请求、带时钟漂移的分布式日志

- **多 agent 运行时的额外挑战**:
  - 调度:谁接下来运行、运行多久
  - 资源分配:模型、CPU 等共享资源
  - 状态管理:检查点、内存、来源追踪、版本
  - **没有预定请求流(no predetermined request flow)**——系统无法预知谁运行、运行多久、每个 agent 消耗多少资源(取决于 LLM 运行时行为)
- **黑盒 LLM 让一切更难**:
  - **上下文面**:
    - 信息丢失:摘要丢掉 worker 知道的东西
    - 上下文污染:重要信息被埋掉
    - 过期信息:B 仍按 X=3 行动,世界已是 X=5
    - 冲突信念:A 说安全、B 说有漏洞
  - **协调面**:
    - 故障诊断难:为什么失败？每个 agent 都是黑盒
    - 所有权丢失:每个 agent 以为对方负责
    - 通信循环:A 问 B、B 问 C、C 又问 A

## A2A 协议:agent 对 agent

> **图示** Agent A 委派「Analyze whether company X should move its inference stack to GPUs Y」给 Agent B;B 经各 peer 的 **agent card** 发现能力,发消息创建 task 分派给 Research / Finance(Estimate GPU cost)/ Search(Find benchmark data)/ Coding(Run these benchmarks)agent,收进度更新,最终返回产物。

- **Agent card**:每个 A2A server 发布机器可读卡片(`GET /.well-known/agent-card.json`),兼发现 + 能力描述;调用方可学到:
  - **Identity**:是谁
  - **Skills**:声称能做什么
  - **Endpoints**:在哪里、如何调用
  - **Capabilities**:streaming、push
  - **Auth**:需满足哪种安全方案

  例:`{"name": "Travel Agent", "skills": [{"id": "book-flight"}], "capabilities": {"streaming": true}, ...}`。
- **三个抽象:Message → Task → Artifact**:
  - **Message** = 客户端与 agent 之间一轮交互(「Book a flight to Boston」),**启动**一个 Task
  - **Task** = 带 ID 与生命周期的有状态工作单元(task-42: working → completed),**返回** Artifact(行程单 PDF 与订票数据)
  - **追问加入同一个 task**(「Which date？」→「Oct 3」不是新任务,是同一 task 的延续)
- **任务生命周期**:`Submitted → Working → Completed / Failed / Canceled`,另有 `Input required` 与 `Auth required` 两个暂停态

> **A2A 是有状态任务协议(stateful task protocol)**:工作可暂停等输入/认证,然后恢复(resume)。

> **图示** 第 40 页为 task 42 的状态流转图(无文本层)。

- **跟踪长任务**(task 可运行几秒到几小时,由调用方选择):
  - **Polling**:短任务
  - **Streaming**:流式实时推送,交互式输出
  - **Push notification**:完成时 webhook 触发,小时级任务

> **边界:A2A 标准化的是通信(communication),不是编排(orchestration)**——委派、拆分、停止仍归 harness(智能体运行时框架)负责。

## MCP:agent 的能力

- MCP(Model Context Protocol)标准化 **agent ↔ 外部能力/服务** 的边界:
  - **tools**:可调用的、带类型的能力
  - **resources**:宿主可附加的可读数据
  - **prompts**:可复用的交互模板
- **一个 client 可对接多个 server**(filesystem、database、GitHub、browser 等)
- **是宿主(host)而非模型决定暴露什么**
- 定位:**MCP 是 agent 的服务边界——一次工具调用,一个结果(one tool call, one result)**

MCP vs. A2A:

| |MCP|A2A|
|---|---|---|
|Primary abstraction|capability / tool|agent / task|
|Relationship|agent → service|agent → agent|
|Discovery|tools, resources, prompts|agent capabilities|
|Unit of work|one tool invocation|long-running task|
|Internal state|capability interface|ideally opaque|
|Analogy|device / API interface|service-to-service RPC|

> **两层叠加:一个 A2A 远端 agent 本身可以再调用二十个 MCP server**——A2A 在 agent 层之上,MCP 在能力层之下。

## 设计原则(Design principles)

1. **多智能体真的必要吗？** 单 agent 往往够用,多 agent 常常只增加开销与复杂度——默认从单 agent 出发。
2. **确定拓扑**:通信拓扑反映任务依赖关系,并最小化通信。
3. **找出信息丢失点**:把每个聚合节点当作细节被丢弃的地方对待。
4. **确定故障隔离边界**:确保系统不因单点失败而整体停摆。

> **收尾警句:密集全互联(dense mesh)很少是最好的默认选择**——更多通信可能只增加上下文压力,而不增加有用信息。

## 核心要点

- 拆工作的两大动机:**专业化与隔离**(不同模型/提示词/工具权限)与**并行与上下文管理**(独立子任务并发、每个 agent 不背全量轨迹)。
- 用三张图刻画任何架构:控制图(谁协调、运行时是否 handoff)、任务图(planner 预规划/竞价/局部规则涌现)、通信图(直连/广播/共享工作区)。
- 八种架构各有适用与弱点:supervisor–worker(独立子任务并行,但 supervisor 上下文增长最快)、层次化(天然分层任务,关键是分解位置与跨层上下文量)、pipeline/DAG(最易调试,「一条重试边胜过多加一个 agent」,但无回头路)、blackboard(免接线、状态持久可检视,但一致性/并发/溯源/版本/GC 难)、committee(判断类任务提准确率,但同模型同上下文 = 同盲点)、market(竞价无中心分配,但自报 bid 可夸大)、swarm(无单点故障,但 O(n²) 且产品少用)、dynamic topology(算力随难度伸缩,但故障难复现)。
- **真实系统是混合体**:supervisor 层次 + 动态任务 DAG + 共享 Git 工作区 + 按需 re-plan。
- 任务分解六轴:data、expertise、stage、hypothesis、tool、authority,可叠加使用。
- 好的子任务定义写全八要素:目标、输出 schema、输入与上下文、完成判据、边界与排除项、预算与截止时间、工具与权限、依赖。
- 粒度:`T ≈ T_planning + T_critical path + T_communication + T_merge`;并行收益须超过规划/通信/整合开销。
- 分解必须配 spawn 上限、预算、深度限制、终止条件;六大失败:overlap、gap、hidden dependency、unmergeable outputs、lost global context、straggler。
- 通信四维度:拓扑、介质、信道、格式与语义;经验法则:拓扑镜像任务依赖、每条链路一种介质、只在所有人都必须知道时广播、按字段而非正文路由;每个选择在延迟/上下文/可靠性间权衡。
- 实用消息设计 = 结构化控制字段 + 自然语言内容;运行时不询问 LLM 消息含义即可路由、重试、终止。
- 一次发消息 = 分布式事务:幂等键、补偿/回滚路径、明确重复执行的成本承担者。
- 多智能体系统继承分布式系统六大难题(含「分不清慢与死」),且无预定请求流;黑盒 LLM 再叠加上下文四类问题与协调三类问题。
- **A2A**(agent↔agent):agent card 用于发现;message → task(有状态生命周期,可暂停于 input/auth 再恢复)→ artifact;长任务用轮询/流式/推送跟踪;标准化通信而非编排。
- **MCP**(agent↔能力):tools/resources/prompts,宿主决定暴露什么,一次调用一个结果;与 A2A 分层叠加,一个 A2A agent 可再调二十个 MCP server。
- 四条设计原则:多智能体真的必要吗;拓扑反映依赖并最小化通信;聚合节点 = 信息丢失点;划清故障隔离边界;警惕 dense mesh。
