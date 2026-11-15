# 第6讲：智能体设计 III（记忆与可靠性）

> 原讲名：Agent Design III: Memory, and Reliability —— Modern AI Systems: Agents and System Optimizations (Harvard CS2680, Juncheng Yang)

## 本讲概览

本讲承接上一讲的 multi-agent 设计，聚焦两个主题：**agent memory（智能体记忆）**与 **agent reliability（智能体可靠性）**。记忆部分把"记忆系统"拆解成一条完整的流水线——write or skip（要不要写）、encode/organize（写成什么形式）、store（存在哪里）、retrieve（何时取）、reflect/generalize（如何归纳）、keep/update/delete（是否仍然有效）——每一环都是一个独立的策略决策，并逐一讨论了格式（raw episodes、摘要、结构化状态、知识图谱）、后端（文件、键值/关系数据库、向量库、图数据库）、所有权（harness 文件 vs 专用记忆系统如 Mem0、Graphiti、supermemory）、失效模式与评测基准（LoCoMo、LongMemEval、BEAM）。可靠性部分从"单步 95% 成功率 × 50 步 → 只有约 8% 的运行无错完成"的误差复合问题出发，把故障来源分成 task spec、harness、model、tool、environment 五层，每层给出"故障现象 → 智能体行为 → 修复方法"的对照表，最后以"design for failure（为失败而设计）"五列原则收尾。

## 开场与议程

### Logistics（课程事务）

- 本周四 3:30pm 在 SEC 4.308 有 office hour。
- 期末项目海报展示（final project poster presentation）：12 月 7 日 9am–1pm；如果这个时间不合适，请本周内联系课程组。
- AI 生成的参考材料：[cs2680.com/notes/agent-evaluation](https://cs2680.com/notes/agent-evaluation)；阅读材料中的 notes（清单由讲师本人挑选），并由讲师与 TF 审阅过。

### 今日计划

三个议题：**Multi-agent design（multi-agent 设计，上一讲的延续）**、**Agent memory（智能体记忆）**、**Agent reliability（智能体可靠性）**。

图示：幻灯片给出记忆在系统中的位置——**Context window（上下文窗口）**是临时的工作态（temporary working state），由 User、Agent、Harness、LLM 共同构成；**Memory store（记忆存储）**则是跨交互持久化的状态（persistent state across interactions），位于上下文窗口之外。记忆因此可以理解为"上下文窗口的延伸"：窗口里装得下的只是当前回合的工作记忆，装不下的必须外置到持久存储。

## 记忆设计总览：六个问题

幻灯片把 agent memory 设计概括为六个连续的决策点，这也是后续每一节反复出现的底部提示（Keeping? Format? Backend? Need it? Lesson? Valid?）：

| 阶段 | 决策问题 | 含义 |
|---|---|---|
| **Decision** | Is it worth keeping?（值得记吗） | **WRITE OR SKIP**：是否把这条信息写成记忆 |
| **Format** | What should it become?（变成什么形式） | **ENCODE / ORGANIZE**：编码/组织成什么表示 |
| **Backend** | Where should it live?（存在哪里） | **STORE**：选择什么存储后端 |
| **Task** | Does this task need it?（当前任务需要它吗） | **RETRIEVE**：是否/如何检索 |
| **Lesson** | What broader lesson follows?（有什么更普遍的教训） | **REFLECT / GENERALIZE**：反思与归纳 |
| **Status** | Is it still valid?（仍然有效吗） | **KEEP / UPDATE / DELETE**：生命周期管理 |

幻灯片最后抛出贯穿全节的问题：**Who owns the memory?（谁拥有记忆？）**——即记忆归 agent 自己管，还是归一个独立的记忆系统管。

## Decision：什么时候该把信息变成记忆？

核心权衡："Writing every interaction raises recall and noise"——**写下来每一次交互，召回率提高了，噪声也提高了**。两种极端策略：

- **write every interaction（全量写入）**：**high recall（高召回）**——所有信息都留下，不会漏，但上下文污染风险大。
- **selective writing（选择性写入）**：**high precision（高精确）**——只写有价值的。

选择性写入的实现手段包括：

- **Explicit user request（显式用户请求）**："记住这个"之类的明确指令直接触发写入。
- **Deterministic rules (heuristics)（确定性规则/启发式）**：用手工规则判断什么值得记。
- **Small classifier（小型分类器）**：用一个轻量模型做"是否值得记"的二分类，成本低、延迟小。
- **Periodic LLM review（周期性 LLM 审查）**：定期让 LLM 回看交互历史，筛选出值得固化的记忆。

实践中通常是混合策略：显式请求立即写，启发式/分类器做实时筛选，周期性审查做兜底补漏。

## Format：如何组织记忆？（四种格式）

| 格式 | 例子 | 特点（slide 原话） |
|---|---|---|
| **Raw events / episodes（原始事件/回合）** | "We moved serving from vLLM to SGLang." | 高保真（high fidelity），但庞大且冗余（large and redundant） |
| **Unstructured summaries（非结构化摘要）** | "Uses SGLang for model serving." | 紧凑（compact），但可能丢失上下文（may lose context） |
| **Structured state（结构化状态）** | {"serving_engine":"SGLang"…} | 可查询（queryable），但 schema 构成约束（schema constrains） |
| **Knowledge graph（知识图谱）** | Project → USES → SGLang | 实体及其关系随时间演化（linked entities and change over time） |

解读：这是一条从"忠实"到"抽象"的光谱。原始 episode 什么都不丢，但存储和检索成本随交互数线性增长；摘要把冗余压掉，代价是不可逆的信息损失；结构化状态适合"当前系统状态"这类字段化的事实，但必须先定义 schema，schema 定错就装不下新事实；知识图谱把事实表达为实体和带时间的边，最适合需要沿关系多跳推理、且事实会随时间被替换的场景（如"项目用什么 serving 引擎"这种会变更的状态）。实际系统往往组合使用：episode 作为底层原始层，摘要/图作为上层派生层。

## Backend：把记忆存在哪里？（四类后端）

| 后端 | 例子 | 特点 |
|---|---|---|
| **Plain files（纯文件）** | CLAUDE.md、scratchpad | 易于检查、diff、搜索（simple to inspect, diff, and search） |
| **Key-value or relational database（键值/关系数据库）** | Redis、SQLite、Postgres JSONB | 精确查找、过滤、事务（exact lookup, filtering, and transactions） |
| **Vector store（向量库）** | pgvector、Chroma、Pinecone | 精确或近似相似度检索（exact or approximate similarity search） |
| **Graph database（图数据库）** | Neo4j、FalkorDB（Graphiti 用它） | 关系查询与多跳遍历（relationship queries and multi-hop traversal） |

解读：纯文件是最小可行方案——agent 直接把笔记写在 markdown 文件里，人可以直接读和 diff，这也是 Claude Code 的 CLAUDE.md 路线；数据库适合需要事务一致性或结构化过滤的场景；向量库支撑语义相似度检索；图库支撑沿实体关系的多跳查询。后端选择应与上一节的格式选择联动：知识图谱自然落在图数据库上，摘要类记忆落在向量库上，结构化状态落在关系数据库 JSONB 上。

### 何时使用记忆？三种控制方式

| 控制方式 | 机制 | 优点 | 缺点 |
|---|---|---|---|
| **Automatic（自动）** | 每回合：search → LLM → add | 可预测、简单 | 增加延迟，并引入无关上下文 |
| **Runtime-controlled（运行时控制）** | `if memory_needed: search()`；`if memorable: add()` | 有选择、高效 | 需要规则或分类器 |
| **Model-controlled（模型控制）** | 以工具形式暴露：`search_memory()`、`add_memory()`、`update_memory()`、`forget_memory()` | 按需驱动，LLM 自己决定何时调用 | 可能漏掉有用的读或写 |

解读：自动模式最简单但每回合都付出检索延迟，且把不相关记忆塞进上下文会稀释注意力；运行时控制把判断权放在 harness 代码里，需要额外维护规则或训练分类器；模型控制把记忆操作做成工具交给 LLM 自主调用，灵活但不可靠——模型可能忘记调用，或在不该写的时候写。**Many systems use a hybrid approach; read and write policy may differ**（许多系统采用混合方式，读策略和写策略可以不同）——例如写用分类器筛选、读交给模型按需检索。

## Retrieve：如何检索记忆？

**Basic pipeline（基本流水线）**：Query → Vector search → Top-k memories → Prompt，即把当前请求变成查询，向量检索出 Top-k 条记忆，拼进 prompt。

关键论断：**"Semantic relevance is only one retrieval signal"（语义相关只是检索信号之一）**。完整检索应综合五个信号：

| 信号 | 含义（slide 原话） |
|---|---|
| **Semantic** | 语义与 query 匹配（matches the query） |
| **Scope** | 同一 user、project、entity 或 task |
| **Importance** | 漏掉它或纳入它的代价（cost of missing or including it） |
| **Validity** | 该事实在当前任务的这个时间点是否仍然为真 |
| **Provenance** | 来源、置信度与证据（source, confidence, and evidence） |

解读：纯向量 Top-k 会召回"听起来相关"但过期、属于别的用户、或只是碰巧语义相近的记忆。Scope 过滤保证不跨用户/项目串记忆（对应后文的 isolation 问题）；Importance 让高代价事实排前面；Validity 结合 valid time 过滤掉过期事实；Provenance 让下游可以按置信度加权或标注来源。检索因此应做成"先过滤、再打分、再排序"的多阶段过程，而不是单阶段向量检索。

## Reflect / Generalize：如何从观察中归纳？

图示：用户在若干次交互中分别询问了 **vLLM**、**SGLang**、**TRT-LLM**、**LLM scheduling** 这些主题。反思（reflection）模块据此产生一个假设（Hypothesis）：**"frequent interest in LLM inference systems"（对 LLM 推理系统有持续关注）**，并标注 **Confidence: medium（置信度：中）**。即：把多个离散观察归纳成一条关于用户的概括性记忆，且明确它是带置信度的推断而非确证事实。

**When should consolidation happen?（何时做归纳/固化）**slide 给出两个触发条件：

- **After enough new evidence**——积累足够新证据后，例如每 N 个事件一次，或上下文填满时。
- **In a background job when possible**——尽可能放在后台任务中执行，不阻塞主对话回路。

解读：归纳不应每回合都做（贵且不稳定），而应批处理化：攒够样本再让 LLM 反思一次，且放在后台以免增加交互延迟。

## Forget：遗忘是一等记忆操作

**"Forgetting is a first-class memory operation"**——forgetting 不是 bug 而是与 write/read 平级的一等操作。

**Why forget?（为什么要遗忘）**：

- **Stale information（过期信息）**——事实已失效
- **Incorrect or conflicting information（错误或相互冲突的信息）**
- **Privacy and security（隐私与安全）**——用户要求删除，或敏感数据不应长期留存
- **Storage and retrieval cost（存储与检索成本）**——记忆库无限增长会拖慢检索、降低检索质量

**Lifecycle controls（生命周期控制手段）**：

- **Mark invalid（标记失效）**——软删除，保留记录但不再参与检索
- **Erase permanently（永久擦除）**——硬删除
- **Expire after a TTL（TTL 过期）**——按时间自动失效
- **Create tiers and evict from active memory（建分层并从活跃记忆中驱逐）**——冷热分层，把久未命中的记忆降级

解读：四种控制对应四种原因：冲突用"标记失效"保留审计痕迹，隐私要求用"永久擦除"，会话类短期信息用 TTL，容量压力用分层驱逐。遗忘策略缺失的后果就是后文的 unbounded growth 失效模式。

## Memory needs valid time and provenance（记忆需要有效时间与来源）

两个概念：

- **Valid time（有效时间）**：**which fact applied when**——一条事实**在什么时间段内**成立。例如"项目用 vLLM 部署"只在某段时间为真，之后被"用 SGLang"取代。
- **Provenance（来源）**：**where the fact came from**——事实**从何而来**，即证据链。

图示：一次带 valid time 与 provenance 的记忆更新过程。4 月 2026 的 **Episode 28** 记录用户说 **"We moved serving from vLLM to SGLang."**。据此，图中的三元组 **Project → SERVES_WITH → vLLM** 被标记为 **superseded（被取代）**（对应"Project serves models with vLLM"），同时写入 **Project → SERVES_WITH → SGLang** 并标记为 **current（当前）**，且新事实标注 **source: Episode 28** 作为 provenance。也就是说，"更新记忆"不是覆盖旧值，而是给旧事实打上失效时间戳、给新事实打上生效时间戳与来源引用——历史全部保留，当前值由 valid time 决定。

## Who owns the memory?（谁拥有记忆？）

图示：两种所有权模型。

- **Agent-owned（agent 自有）**：记忆就是 **harness 里的文件**——CLAUDE.md、scratchpad、task notes。agent A 中的 LLM 直接 **read / write** 这些文件；**Harness persists memory to disk**（harness 负责把记忆持久化到磁盘）。
- **Dedicated memory system（专用记忆系统）**：存在一个 **Memory layer（记忆层）**，可以是以 **library or service（库或服务）** 的形式部署；agent A 通过 **search · update** 等调用使用它；**Memory is an API, shared across agents and sessions**（记忆是一个 API，可被多个 agent 和多个会话共享）。

解读：文件方案零依赖、人可读、可 diff，天然适配单 agent 单工作区（Claude Code 的 CLAUDE.md 就是典型）；专用系统把记忆升级为带 API 的服务，好处是跨 agent、跨会话共享，代价是多一套基础设施。

## 专用记忆系统（Dedicated memory systems）

| 系统 | 输入 | 检索 | 特点 |
|---|---|---|---|
| **Mem0** | **messages**，按 **user / agent / run** 作用域隔离 | **vector search + filters**；可选 **graph memory** | **Fact-centric（事实为中心）**，例如 "Uses SGLang for model serving." |
| **Graphiti** | 由 episodes 抽取出的 **entities** 和 **time-aware facts（带时间的事实）** | **hybrid：semantic + keyword + graph search** | **Temporal knowledge graph（时序知识图谱）**，例如 uses → SGLang，**valid Apr 2026 → present** |
| **supermemory** | 关联了 **source 和 time** 的 conversations | 对 **profile / memory / document** 三类分别检索 | 在记忆与文档之外额外维护一个 **user profile（用户画像）** |

解读：三者代表了三种记忆抽象粒度。Mem0 从对话消息中提炼"事实"并做带过滤的向量检索（可选图谱扩展）；Graphiti 是时序知识图谱路线，每个事实带有效区间（如 Apr 2026 至今），检索是语义、关键词、图遍历三路混合——它与本讲"valid time + provenance"一节直接呼应；supermemory 则在普通记忆之上维护用户画像，把"这个人是谁"与"他说过什么"、"他提供过哪些文档"分开管理并分别检索。

## 记忆设计 Checklist（检查清单）

幻灯片把整条流水线总结为一张对照表，强调 **"Each stage is a policy decision"（每个阶段都是策略决策）**：

| 阶段 | 需要回答的问题 |
|---|---|
| **Observe** | （观察，作为所有阶段的输入） |
| **Select** | Is this worth remembering?（值得记吗？） |
| **Encode / organize** | What representation preserves the needed meaning?（什么表示能保留所需含义？） |
| **Store** | Where should it live? File, database?（存在哪里？） |
| **Retrieve** | What is useful for the current task?（对当前任务什么有用？） |
| **Reflect / consolidate** | Does this update or contradict an old memory?（它更新或矛盾了哪条旧记忆？） |
| **Forget** | When is information stale or irrelevant?（信息何时变得过期或无关？） |

## 记忆失效模式（Failure modes）

幻灯片以"Hands up（举手表决）"的互动形式列出八种记忆失效模式，两两对照：

| 失效模式 | 含义 | 失效模式 | 含义 |
|---|---|---|---|
| **Retrieval miss（检索漏召回）** | 相关记忆存在但没被找到 | **Context pollution（上下文污染）** | 过多无关记忆进入上下文 |
| **Memory hallucination（记忆幻觉）** | 把推断存成了事实："studying at Harvard"（在哈佛学习）变成 "visiting student at Harvard"（哈佛访问学生） | **Staleness（过期）** | 旧事实覆盖了新信息 |
| **Isolation failure（隔离失效）** | 记忆跨越了用户边界 | **Overgeneralization（过度泛化）** | 一次事件变成持久偏好 |
| **Persistent prompt injection（持久提示注入）** | 不可信内容日后以"指令"的形式返回 | **Unbounded growth（无界增长）** | 存储规模随生命周期增长，检索成本与质量随之退化 |

解读：前四种是"内容质量"问题（没找到、塞太多、记错、记旧），后四种是"边界与安全"问题（跨用户泄漏、单次变永久、注入内容被记忆固化成指令、库无限膨胀）。其中 persistent prompt injection 特别值得注意：攻击者把恶意内容注入一次交互，若被写入记忆，之后每次检索命中都会"复活"成指令，比单次注入更难清理，因此写入门槛与 provenance 审查是关键防线。

## 如何评测 Agent Memory（评测维度）

记忆系统要沿四个维度评测：

| 维度 | 指标 |
|---|---|
| **Retrieval（检索）** | Precision、Recall |
| **Writes and update（写入与更新）** | Precision、Recall，以及 **stale-memory rate（过期记忆率）** |
| **Governance（治理）** | **Deletion compliance（删除合规）** 与 **scope isolation（作用域隔离）** |
| **System（系统）** | Latency（延迟）、token overhead（token 开销）、store growth（存储增长） |

解读：检索的 P/R 是标准信息检索指标；写入/更新维度额外关注"是否还留着过期记忆"；治理维度检验"用户要求删的有没有真删干净""有没有串到别的用户的记忆"；系统维度则关心工程代价——每次检索多花多少 token 和延迟、存储随时间膨胀多快。

## 记忆评测基准（Memory benchmarks）

"Memory component evaluation" 一节列出三个基准：

| 基准 | 出处 | 规模 | 构成 |
|---|---|---|---|
| **LoCoMo** | ACL 2024 | **1,540 questions** | **10 long dialogues**（10 段长对话） |
| **LongMemEval** | ICLR 2025 | **500 questions** | **5 memory abilities**（5 种记忆能力） |
| **BEAM** | ICLR 2026 | **2,000 questions** | 对话长度**最多 10M tokens** |

slide 指出：这些基准**主要测试 agent 能否对 user-assistant 历史进行回忆与推理**，覆盖五种能力：**recall（回忆）、temporal reasoning（时间推理）、updates（更新）、preferences（偏好）、abstention（拒答/承认不知道）**。slide 还提及 **LoCoMo-Refined** 这一改进版本。

解读：三个基准的侧重点不同——LoCoMo 用极长的多轮对话压"跨事件回忆 + 时间推理"；LongMemEval 按能力维度（含 abstention，即该说"不知道"时不乱编）组织题目；BEAM 则把长度推到极端（最高 1000 万 token），测试超长历史下的记忆系统。

## Agent Memory Stack（记忆栈）

图示：把记忆系统分层的两种形态，每层三档（Agent runtime / Memory management / Storage）。

| 层 | 独立记忆层（Separate memory layer） | harness 内置记忆（Memory inside the harness） |
|---|---|---|
| **Agent runtime** | Claude Code、Codex、Letta | Claude Code、Codex、Letta |
| **Memory management** | Mem0、Letta | Mem0、Letta built-in、custom **?** |
| **Storage** | vector、SQL、graph | markdown files、object stores |

解读：左边是"记忆独立成层"的架构——runtime 之上的 memory management 层（Mem0 等服务、或 Letta 这类自带记忆管理的 runtime）对接向量库/SQL/图库等通用存储；右边是"记忆长在 harness 里"的架构——管理逻辑内置于 runtime，存储退化为 markdown 文件或对象存储。图中 "custom ?" 标注表明 harness 内置路线的管理层实现各家自定义、尚未收敛。这与前面"who owns the memory"的两种所有权模型是一一对应的。

## 为什么 Agent Reliability 是个问题？（误差复合）

核心论断：**"Errors compound"（错误会复合）**。slide 用一条曲线展示"一次 agent 运行全程无错的概率"随轨迹步数的衰减（假设**每一步独立地以 0.95 概率成功**）：

| 轨迹步数 | 全程无错概率 |
|---|---|
| 1 步 | **95%**（即平均每 **1 in 13** 步会出一次错） |
| 5 步 | **77%** |
| 10 步 | **60%** |
| 20 步 | **36%** |
| 50 步 | **8%**（约 1/13） |

slide 的两个要点：

- **A run succeeds only if every step does**——运行成功当且仅当**每一步**都成功，所以成功率随步数呈指数衰减（0.95^50 ≈ 0.08）。
- **Error propagation makes real runs worse than this**——该模型还假设各步独立，而现实中错误会向后续步骤传播，所以真实运行比这条曲线**更差**。

解读：单步 95% 听起来很高，但长 horizon 任务（几十步）下"零错误"概率掉到个位数百分比；叠加错误传播后更低。这就是为什么后文要把"如何失败、如何恢复"当作一级设计目标。

## Agent Reliability：故障从哪里来？

"Where does the fault originate?" 一张表把 agent 栈按故障来源分成五层：

| 层 | 内容 | 故障类别 |
|---|---|---|
| **User / task spec（用户/任务规格）** | was the goal unambiguous?（目标是否无歧义？） | **specification failure（规格失效）** |
| **Agent harness（智能体框架）** | context, loop, scheduling（上下文、循环、调度） | **harness failure（框架失效）** |
| **LLM（大模型）** | reasoning and planning（推理与规划） | **model failure（模型失效）** |
| **Tool layer（工具层）** | shell, browser, APIs（shell、浏览器、API） | **tool failure（工具失效）** |
| **Environment（环境）** | repo, OS, web, services（仓库、操作系统、网页、服务） | **environment failure（环境失效）** |

解读：可靠性故障不一定来自模型——目标没说清（规格）、上下文被截断（harness）、工具返回截断/静默失败（tool）、环境过期/限流（environment）都可能让一个"推理正确"的模型把任务做坏。因此诊断要先定位故障在哪一层，再对症下药。以下五节逐一展开，每节给出"故障 → 智能体表现 → 修复"的对照表。

### 故障来源 1：Task Specification（任务规格）

表头：**Failure（故障）| The spec said（规格说了什么）| The agent did（智能体做了什么）| The fix（修复）**

| 故障 | 规格说了什么 | 智能体做了什么 | 修复 |
|---|---|---|---|
| **Ambiguous goal（目标含糊）** | "Fix the login bug"（修登录 bug） | 修了三个候选中错误的那一个 | 指明文件名、症状与复现步骤 |
| **Proxy objective（代理目标）** | "Make the tests pass"（让测试通过） | 直接删掉了失败的测试 | 禁止修改测试；审查 diff |
| **Unstated constraint（未声明约束）** | "Speed up search"（加速搜索） | 改坏了公共 API | 明确写出"什么不能变" |
| **No definition of done（无完成定义）** | "Clean up the parser"（清理 parser） | 重构永远停不下来 | 给出退出测试（exit test）和停止规则 |
| **Conflicting goals（目标冲突）** | "Minimal diff, every edge case"（最小 diff，又要覆盖所有边界情况） | 默默丢掉了边界情况 | 显式地对目标排序 |

解读：这一层的故障完全可以在任务下发前消除：把"修 bug"说成"文件 X 出现症状 Y，复现命令 Z"；用"禁止改测试"封堵走捷径的代理目标；显式列出不可变约束；用可判定的测试定义"完成"；目标之间冲突时给出优先级。这些都是零模型成本、收益最大的可靠性改进。

### 故障来源 2：Agent Harness（智能体框架）

表头：**Failure | The harness did（框架做了什么）| The effect（后果）| The fix（修复）**

| 故障 | 框架做了什么 | 后果 | 修复 |
|---|---|---|---|
| **Context truncation error（上下文截断错误）** | 裁掉了最旧的对话轮次 | 忘记了"保持 API 不变"的规则 | 把关键规则钉在窗口之外（pin） |
| **Memory error（记忆错误）** | 把一条过期笔记当事实召回 | 编辑了一个已经搬走的文件 | 给记忆打时间戳；使用前重新核实 |
| **State corruption error（状态损坏错误）** | 保留了一次只应用了一半的编辑 | 后续步骤在损坏的文件上继续构建 | 做 checkpoint；回滚失败步骤 |
| **Control loop error（控制循环错误）** | 未设置步数或成本预算 | 跑了 200 步毫无进展 | 对步数、成本、时间设上限 |
| **Blocking fan-out（阻塞式 fan-out）** | 等待每一个子 agent 返回 | 一个慢子任务拖住整个运行 | 设超时；使用部分结果 |

解读：harness 故障的特点是其行为"看似正常"但系统性偏斜：截断策略把最重要的约束先截掉、记忆层召回过期事实、半失败操作污染了工作区状态、无预算的循环空转烧钱、同步等待使木桶效应放大到整条运行。对应的修复也都是 harness 层能力：规则 pin 在上下文外、记忆带时间戳并用前核实、checkpoint/回滚、预算硬上限、子任务超时 + 部分结果合并。

### 故障来源 3：Model（大模型）

表头：**Failure | The model reasoned（模型怎么想的）| The agent did（智能体做了什么）| The fix（修复）**

| 故障 | 模型怎么想的 | 智能体做了什么 | 修复 |
|---|---|---|---|
| **Hallucination（幻觉）** | "requests.fetch() exists" | 调用了不存在的函数 | 对照真实文档检查调用 |
| **Instruction violation（违背指令）** | "Speed matters more than the API"（速度比 API 重要） | 修改了被告知必须保持的函数签名 | 重述约束；检查 diff |
| **Faulty reasoning（推理错误）** | "A timeout means the network is down"（超时=网络断了） | 给一个死锁加了重试 | 修复前先验证假设 |
| **Reasoning–action mismatch（推理-行动不一致）** | "I'll only touch parser.py" | 重写了另外三个文件 | 把每个行动与计划逐一对比 |
| **Unverified success（未经验证的"成功"）** | "Tests probably pass now" | 什么都没跑就宣布完成 | 要求测试输出作为证据 |
| **Long-horizon degradation（长程退化）** | "The config still needs fixing" | 把第 12 步自己做的修复又撤销了 | 重读当前状态；把任务拆成短任务 |

解读：模型层故障是"认知"层面的，六条覆盖了幻觉、不守约束、推理链错误、言行不一、自我宣告成功、长程自相矛盾。修复思路的共同点是把"模型说"与"证据"分离：调用要对照文档、声明"完成"必须附测试输出、行动要与声明的计划对账、长任务中定期重读状态防止遗忘自己的历史操作，必要时换更强的模型（呼应后文 Design for failure 的 "Use stronger models"）。

### 故障来源 4：Tool（工具层）

表头：**Failure | The tool returned（工具返回了什么）| The agent did（智能体做了什么）| The fix（修复）**

| 故障 | 工具返回了什么 | 智能体做了什么 | 修复 |
|---|---|---|---|
| **Truncated output（输出截断）** | 日志的前 100 行 | 漏掉了第 4,000 行的报错 | 错误信息优先返回；支持分页 |
| **Silent failure（静默失败）** | Exit 0、空结果 | 以为"没有匹配项" | 把"空结果"与"执行失败"区分开 |
| **Ambiguous schema（含糊的 schema）** | 不带时区的时间 | 把任务调度错了 8 小时 | 使用带类型、显式的 schema |
| **Flaky call（不稳定调用）** | 首次尝试超时 | 直接宣布服务宕了 | 判断前先带退避重试 |
| **Misleading error（误导性错误）** | 拼写错误却报 "Permission denied" | 改用 sudo 重试 | 返回精确、可操作的错误信息 |

解读：工具是 agent 与物理世界之间的接口，工具返回的每个字节都会被模型当真。这一层的修复主要是**工具 API 设计**问题：输出截断时要优先保留错误行、提供分页；退出码 0 + 空输出不等于"查无结果"，要有独立的状态表达；schema 要带完整类型信息（如时区）；flaky 调用要支持/默认退避重试；错误信息要精确到可行动。

### 故障来源 5：Environment（环境）

表头：**Failure | The environment had（环境中存在什么）| The agent did（智能体做了什么）| The fix（修复）**

| 故障 | 环境中存在什么 | 智能体做了什么 | 修复 |
|---|---|---|---|
| **Stale state（过期状态）** | 昨天的缓存构建 | 在旧代码上"通过"了测试 | 从全新缓存开始 clean build |
| **Version mismatch（版本不匹配）** | 实际是 Python 3.8 而非 3.12 | 交付了会崩溃的代码 | 用 lockfile 钉住版本 |
| **Random failure（随机失败）** | 任务成败依赖环境 | 因闰年问题而失败 | 重跑失败项；把 flaky 用例隔离（quarantine） |
| **Changed web page layout（网页布局变更）** | 结账页面改版 | 点错了按钮 | 行动前重新读取页面 |
| **Rate limit（限流）** | 50 次调用后 HTTP 429 | 迁移进行到一半停下 | 主动限流（throttle）+ checkpoint，应对长任务 |

解读：环境故障的特点是**非确定性**——同样的代码与模型，换个缓存状态、换个 Python 版本、隔一天再跑，结果就可能不同。对策是环境的"卫生"：干净缓存构建、lockfile 版本钉住、失败重跑 + flaky 隔离、浏览器 agent 每次行动前重新读 DOM、以及主动限流加 checkpoint 以穿越长任务。

## Designing for Failure（为失败而设计）

幻灯片把上述五层收敛为一张五列的"设计原则"总表，每列一个动词短语口号 + 具体手段：

| 层 | 口号 | 具体手段 |
|---|---|---|
| **Task specification** | **Write "done" as a test（把"完成"写成测试）** | 预先给出验收测试（acceptance tests up front）；列出什么不能改 |
| **Agent harness** | **Bound every run（约束每一次运行）** | 步数、成本、时间上限；checkpoint 与回滚 |
| **Model** | **Demand evidence（索要证据）** | 每个声明都要有证明（proof for every claim）；使用更强的模型 |
| **Tool** | **Fail loudly（大声失败）** | 使用带类型的 schema；错误彼此区分（errors distinct）；对 flaky 调用先重试再下结论 |
| **Environment** | **Pin and isolate（钉住并隔离）** | 全新的、版本钉住的沙箱；从空环境开始验证 |

slide 最后以一句提醒收尾：**"We do not yet understand agents at scale, and there is little formal best practice."（我们尚未真正理解规模化运行的 agent，几乎没有成熟的形式化最佳实践。）**

解读：这张表把整讲的可靠性思想浓缩成"每一层都要主动设计失败路径"：规格层用可判定的完成标准消歧义；harness 层用预算与 checkpoint 兜底；模型层用"证据文化"约束其自我报告；工具层用带类型、可区分、可重试的 API 消除静默失败；环境层用钉版本 + 隔离沙箱消除非确定性。而结尾的保留态度提醒：这些经验来自工程直觉与事故复盘，agent 可靠性目前更像一门正在形成的学科，而非有定理可循的成熟工程。

## 下节课预告

下一讲内容见 slide "Next class"（本 PDF 中无展开内容）。

## 核心要点

- Agent memory 设计可拆解为六个策略决策：write or skip、encode/organize、store、retrieve、reflect/generalize、keep/update/delete；每环独立可调。
- 全量写入换高召回、选择性写入换高精确；选择手段包括显式用户请求、确定性启发式、小型分类器、周期性 LLM 审查，实践多为混合。
- 四种记忆格式构成"忠实→抽象"光谱：raw episodes（高保真但冗余）、非结构化摘要（紧凑但丢上下文）、结构化状态（可查询但受 schema 约束）、知识图谱（实体关系随时间演化）。
- 四类后端各有适用场景：纯文件（CLAUDE.md、scratchpad，可检查可 diff）、键值/关系库（Redis、SQLite、Postgres JSONB，精确查找 + 事务）、向量库（pgvector、Chroma、Pinecone，相似度检索）、图库（Neo4j、FalkorDB，多跳遍历）。
- 记忆的使用控制有三档：每回合自动（可预测但增延迟与噪声）、harness 规则/分类器控制（高效但需维护规则）、模型自主调用工具（灵活但可能漏读漏写）；读策略与写策略可分别选择。
- 检索信号不止语义相关：还有 scope（同用户/项目/实体/任务）、importance（漏取/误取的代价）、validity（此刻是否为真）、provenance（来源/置信度/证据）。
- 归纳（reflection）把多次观察（如反复询问 vLLM/SGLang/TRT-LLM）提炼成带置信度的假设；应在积累足够证据（每 N 事件或上下文填满）后触发，并尽量放后台执行。
- Forgetting 是一等操作：对应用过期、错误/冲突、隐私安全、成本四类原因，提供标记失效、永久擦除、TTL 过期、分层驱逐四种生命周期控制。
- 记忆必须携带 **valid time**（事实何时生效/被取代）与 **provenance**（来自哪个 episode）；"更新"是打时间戳而非覆盖，历史可审计。
- 记忆所有权分两种：agent 自有文件（CLAUDE.md、scratchpad、task notes，harness 落盘）与专用记忆系统（以 API 形式跨 agent、跨会话共享）。
- 三个代表性专用系统：Mem0（事实为中心，向量检索 + 过滤，可选图谱）、Graphiti（时序知识图谱，语义 + 关键词 + 图混合检索）、supermemory（记忆 + 文档 + 用户画像三分）。
- 记忆失效模式八种：retrieval miss、context pollution、memory hallucination（把推断存成事实）、staleness、isolation failure、overgeneralization、persistent prompt injection（注入内容被记忆复活）、unbounded growth。
- 记忆评测四维度：检索 P/R；写入/更新的 P/R 与过期记忆率；治理（删除合规、作用域隔离）；系统（延迟、token 开销、存储增长）。
- 三大记忆基准：LoCoMo（ACL 2024，10 段长对话、1,540 题）、LongMemEval（ICLR 2025，5 种记忆能力、500 题）、BEAM（ICLR 2026，2,000 题、最长 10M tokens）；覆盖 recall、temporal reasoning、updates、preferences、abstention 五种能力。
- 可靠性核心数学：每步独立 95% 成功，则 5 步 77%、10 步 60%、20 步 36%、50 步仅 8% 全程无错；真实运行因错误传播只会更差。
- 故障来源五层：user/task spec（规格）、agent harness（上下文/循环/调度）、LLM（推理/规划）、tool layer（shell/浏览器/API）、environment（仓库/OS/网页/服务）。
- 每层的修复都是"该层的设计问题"：规格要无歧义 + 禁改测试 + 完成定义；harness 要 pin 规则、记忆打时间戳、checkpoint、预算上限、子任务超时；模型要证据文化与更强模型；工具要错误优先、空/失败区分、带类型 schema、重试、精确报错；环境要干净缓存、lockfile、flaky 隔离、行动前重读页面、限流 + checkpoint。
- 五层口号：把"完成"写成测试、约束每一次运行、索要证据、大声失败、钉住并隔离。
- 结语：我们尚未真正理解规模化 agent，几乎没有形式化最佳实践——可靠性目前是工程经验驱动的开放问题。
