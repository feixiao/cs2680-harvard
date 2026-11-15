# 第6讲：智能体设计 III（记忆与可靠性）

> 原讲名：Agent Design III: Memory, and Reliability — Modern AI Systems: Agents and System Optimizations（Harvard CS2680, Juncheng Yang）

## 本讲概览

本讲承接上一讲的 multi-agent 设计，聚焦两个主题：**agent memory（智能体记忆）**与 **agent reliability（智能体可靠性）**。记忆部分把记忆系统拆成一条流水线——要不要写、写成什么格式、存在哪、何时取、如何归纳、如何遗忘——每一环都是独立的策略决策（policy decision），并讨论所有权（harness 文件 vs 专用记忆系统）、失效模式与评测基准。可靠性部分从「单步 95% 成功率、50 步只剩 8% 无错」的误差复合（errors compound）出发，把故障来源分成 task spec / harness / model / tool / environment 五层，逐层给出「故障 → 行为 → 修复」对照表，最后收敛为「designing for failure（为失败而设计）」原则。

- 课程事务：office hour 本周四 3:30pm（SEC 4.308）；期末海报展示 12 月 7 日 9am–1pm。参考材料：cs2680.com/notes/agent-evaluation（AI 生成，讲师与 TF 审阅）。
- 议题：Multi-agent design（上集延续）、Agent memory、Agent reliability。图示：Context window 是临时工作态（temporary working state），Memory store 是跨交互持久态——记忆即"上下文窗口装不下部分"的外置化。

## 记忆设计六问：每阶段都是策略决策

记忆流水线的六个决策点：**Decision** — Is it worth keeping?（write or skip）；**Format** — What should it become?（encode / organize）；**Backend** — Where should it live?（store）；**Task** — Does this task need it?（retrieve）；**Lesson** — What broader lesson follows?（reflect / generalize）；**Status** — Is it still valid?（keep / update / delete）。

## Decision：何时写入记忆

核心权衡："Writing every interaction raises recall and noise"——全量写入高召回高噪声；选择性写入（selective writing）高精确。手段：显式用户请求、确定性规则（heuristics）、小分类器（small classifier）、周期性 LLM 审查（periodic LLM review）。

## Format：四种记忆格式

| 格式 | 例子 | 特点 |
|---|---|---|
| **Raw events / episodes**（原始事件） | "We moved serving from vLLM to SGLang." | 高保真，但庞大冗余 |
| **Unstructured summaries**（非结构化摘要） | "Uses SGLang for model serving." | 紧凑，但可能丢上下文 |
| **Structured state**（结构化状态） | {"serving_engine":"SGLang"…} | 可查询，但 schema 构成约束 |
| **Knowledge graph**（知识图谱） | Project → USES → SGLang | 实体与关系可随时间演化 |

## Backend：存储后端与使用时机

四类后端：**Plain files**（CLAUDE.md、scratchpad——易检查/diff/搜索）；**Key-value / relational DB**（Redis、SQLite、Postgres JSONB——精确查找、过滤、事务）；**Vector store**（pgvector、Chroma、Pinecone——精确或近似相似度检索）；**Graph database**（Neo4j、FalkorDB/Graphiti——关系查询与多跳遍历）。后端应与格式选择联动。

「何时使用记忆」三种控制方式：**Automatic**——每回合 search → LLM → add（+可预测简单；−加延迟、引入无关上下文）；**Runtime-controlled**——`if memory_needed: search()`（+有选择高效；−需规则或分类器）；**Model-controlled**——工具形式 `search_memory()` / `add_memory()` / `update_memory()` / `forget_memory()`（+按需由 LLM 决定；−可能漏读漏写）。许多系统用混合方式，且读策略与写策略可以不同。

## Retrieve：检索信号不止语义

基本流水线：Query → Vector search → Top-k memories → Prompt。关键论断："Semantic relevance is only one retrieval signal"——完整检索应综合五个信号：**Semantic**（与 query 语义匹配）、**Scope**（同一 user/project/entity/task）、**Importance**（漏掉或误纳的代价）、**Validity**（该事实此刻是否仍为真）、**Provenance**（来源、置信度与证据）。

## Reflect：从观察中归纳

图示：用户先后问 vLLM、SGLang、TRT-LLM、LLM scheduling，反思（reflection）归纳出假设"frequent interest in LLM inference systems"并标注 **Confidence: medium**——归纳结果是带置信度的推断而非确证事实。归纳（consolidation）触发时机：积累足够新证据后（如每 N 个事件或上下文填满时）；尽可能放后台任务执行，不阻塞主回路。

## Forget、Valid Time 与 Provenance

**"Forgetting is a first-class memory operation"**。为何遗忘：信息过期、错误或冲突、隐私与安全、存储与检索成本。生命周期控制：**mark invalid**（软删）、**erase permanently**（硬删）、**expire after a TTL**（到期失效）、**create tiers and evict**（分层驱逐）。

**Valid time**（which fact applied when——事实在什么时间段成立）与 **provenance**（where the fact came from——证据链）。图示：2026 年 4 月 Episode 28 记录"We moved serving from vLLM to SGLang"，Project → SERVES_WITH → vLLM 被标记 **superseded**，新事实 → SGLang 标记 **current** 并标注 **source: Episode 28**——"更新"不是覆盖，而是给旧事实打失效时间戳、给新事实打来源，历史全保留。

## Who owns the memory?

- **Agent-owned**：记忆即 harness 里的文件（CLAUDE.md、scratchpad、task notes），LLM 直接 read/write，harness 负责持久化到磁盘。
- **Dedicated memory system**：独立的 Memory layer（library or service），**记忆是 API，可跨 agent 与会话共享**。

代表性专用系统：**Mem0**——输入 messages（按 user/agent/run 作用域），vector search + filters（可选 graph memory），fact-centric；**Graphiti**——输入 episodes 抽取的 entities 与 time-aware facts，hybrid（semantic + keyword + graph）检索，temporal knowledge graph（如 uses → SGLang，valid Apr 2026 → present）；**supermemory**——输入关联 source 与 time 的 conversations，profile / memory / document 三类分别检索，额外维护 user profile。

## 记忆失效模式、评测与记忆栈

八大失效模式：**retrieval miss**（相关记忆没被找到）、**context pollution**（过多无关记忆入上下文）、**memory hallucination**（推断存成事实："studying at Harvard" 变 "visiting student at Harvard"）、**staleness**（旧事实覆盖新信息）、**isolation failure**（记忆跨用户边界）、**overgeneralization**（一次事件变持久偏好）、**persistent prompt injection**（不可信内容日后以指令形式返回）、**unbounded growth**（规模随生命周期增长，检索成本与质量退化）。

评测四维度：Retrieval（precision、recall）；Writes and update（precision、recall、stale-memory rate）；Governance（deletion compliance、scope isolation）；System（latency、token overhead、store growth）。

| 基准 | 出处 | 规模 | 构成 |
|---|---|---|---|
| **LoCoMo** | ACL 2024 | 1,540 questions | 10 long dialogues |
| **LongMemEval** | ICLR 2025 | 500 questions | 5 memory abilities |
| **BEAM** | ICLR 2026 | 2,000 questions | 对话长度最多 10M tokens |

主要测试对 user-assistant 历史的回忆与推理，覆盖五种能力：recall、temporal reasoning、updates、preferences、abstention（另提及 LoCoMo-Refined）。记忆栈两种形态：独立记忆层（runtime：Claude Code/Codex/Letta；管理：Mem0、Letta；存储：vector/SQL/graph）与 harness 内置（管理：Letta built-in、custom ?；存储：markdown files / object stores）。

## Reliability：误差复合

**"Errors compound"**——假设每步独立以 0.95 概率成功，全程无错概率随步数指数衰减：

| 轨迹步数 | 全程无错概率 |
|---|---|
| 1 步 | 95%（平均每 1 in 13 步出一次错） |
| 5 步 | 77% |
| 10 步 | 60% |
| 20 步 | 36% |
| 50 步 | 8% |

两个要点：**A run succeeds only if every step does**（成功当且仅当每步都成功）；**Error propagation makes real runs worse than this**（曲线假设各步独立，现实中错误向后续传播，真实更差）。

## 故障五层分类与故障明细

"Where does the fault originate?"：**User / task spec**（was the goal unambiguous?）→ specification failure；**Agent harness**（context, loop, scheduling）→ harness failure；**LLM**（reasoning and planning）→ model failure；**Tool layer**（shell, browser, APIs）→ tool failure；**Environment**（repo, OS, web, services）→ environment failure。

各层故障明细（故障 → 场景 → 智能体行为 → 修复）：

| 层 | 故障 | 场景 | 智能体行为 | 修复 |
|---|---|---|---|---|
| spec | Ambiguous goal（目标含糊） | "Fix the login bug" | 修了三个候选中错的那个 | 指明文件、症状、复现步骤 |
| spec | Proxy objective（代理目标） | "Make the tests pass" | 删掉失败的测试 | 禁止改测试；审查 diff |
| spec | Unstated constraint（未声明约束） | "Speed up search" | 改坏公共 API | 明确"什么不能变" |
| spec | No definition of done（无完成定义） | "Clean up the parser" | 重构永不停止 | 给退出测试与停止规则 |
| spec | Conflicting goals（目标冲突） | "Minimal diff, every edge case" | 默默丢掉边界情况 | 显式排定目标优先级 |
| harness | Context truncation（上下文截断） | 裁掉最旧轮次 | 忘记"保持 API"规则 | 关键规则钉在窗口之外 |
| harness | Memory error（记忆错误） | 召回过期笔记当事实 | 编辑了已搬走的文件 | 记忆打时间戳；用前核实 |
| harness | State corruption（状态损坏） | 保留只应用一半的编辑 | 后续步骤建在坏文件上 | checkpoint；回滚失败步骤 |
| harness | Control loop（控制循环） | 无步数/成本预算 | 200 步无进展 | 步数、成本、时间设上限 |
| harness | Blocking fan-out（阻塞扇出） | 等所有子 agent 返回 | 一个慢子任务拖住全程 | 设超时；用部分结果 |
| model | Hallucination（幻觉） | "requests.fetch() exists" | 调用不存在的函数 | 对照真实文档检查 |
| model | Instruction violation（违背指令） | "Speed matters more than the API" | 改了必须保持的签名 | 重述约束；检查 diff |
| model | Faulty reasoning（推理错误） | "超时=网络断了" | 给死锁加重试 | 修复前先验证假设 |
| model | Reasoning–action mismatch（推理-行动不一致） | "只动 parser.py" | 重写了另外三个文件 | 每个行动与计划对比 |
| model | Unverified success（未验证成功） | "测试应该过了" | 什么都没跑就宣布完成 | 要求测试输出作证据 |
| model | Long-horizon degradation（长程退化） | "config 还要修" | 撤销第 12 步自己的修复 | 重读状态；拆成短任务 |
| tool | Truncated output（输出截断） | 日志前 100 行 | 漏掉第 4,000 行的错误 | 错误优先返回；允许翻页 |
| tool | Silent failure（静默失败） | exit 0、空结果 | 以为没有匹配 | 区分"空"与"失败" |
| tool | Ambiguous schema（模糊 schema） | 无时区的日期 | 任务排错 8 小时 | 用带类型、显式的 schema |
| tool | Flaky call（抖动调用） | 首次尝试超时 | 宣布服务宕机 | 判断前先重试 + 退避 |
| tool | Misleading error（误导性错误） | 拼写错误报"Permission denied" | 用 sudo 重试 | 返回精确可操作的错误 |
| env | Stale state（陈旧状态） | 昨天的缓存构建 | 在旧代码上"测试通过" | 从新缓存干净构建 |
| env | Version mismatch（版本错配） | Python 3.8 而非 3.12 | 交付了会崩溃的代码 | lockfile 锁定版本 |
| env | Random failure（随机失败） | 任务成功依赖环境 | 因闰年而失败 | 重跑失败项；隔离 flake |
| env | Changed web page layout（网页改版） | 结账页重新设计 | 点错按钮 | 行动前重读页面 |
| env | Rate limit（限流） | 50 次调用后 HTTP 429 | 迁移中途停止 | 节流 + checkpoint（长任务） |

## Designing for failure（为失败而设计）

- **Task**：把 "done" 写成测试；验收测试前置；列出不可变项；用更强模型。
- **Agent harness**：约束每次运行——步数、成本、时间上限；checkpoint 并回滚。
- **Model**：索要证据——每个声明都要 proof；判断前先验证。
- **Tool**：fail loudly（大声失败）；typed schemas；区分错误；重试 flake。
- **Environment**：pin 并隔离——全新 pinned sandbox；空环境验证；重跑失败项、隔离 flake。

结语（slide 原话）："We do not yet understand agents at scale, and there is little formal best practice."

## 核心要点

1. 记忆系统 = 六阶段流水线（write or skip / encode·organize / store / retrieve / reflect·generalize / keep·update·delete），**每阶段都是策略决策**。
2. 写入的核心权衡是 recall vs noise：全量写高召回高噪声；选择性写（显式请求 / 启发式 / 小分类器 / 周期 LLM 审查）高精确。
3. 格式光谱：raw episodes（保真冗余）→ 摘要（紧凑）→ 结构化状态（schema 约束）→ 知识图谱（关系随时间演化）；后端对应 plain files / DB / vector / graph DB。
4. 记忆使用三种控制（每回合自动 / harness 运行时判断 / LLM 工具调用），实践多为混合，读写策略可不同。
5. 检索不能只靠语义相似度，还要 Scope、Importance、Validity、Provenance 四个信号。
6. 遗忘是一等操作（mark invalid / erase / TTL / 分层驱逐）；记忆须带 valid time 与 provenance，"更新"= 旧事实标 superseded + 新事实标 current 与来源。
7. 所有权两路线：harness 文件（CLAUDE.md 式）vs 专用记忆系统（Mem0 事实中心、Graphiti 时序知识图谱、supermemory 含用户画像）；记忆可升级为跨 agent/会话共享的 API。
8. 记忆八大失效模式：retrieval miss、context pollution、memory hallucination、staleness、isolation failure、overgeneralization、persistent prompt injection（尤须警惕）、unbounded growth。
9. 评测四维（检索 P/R、写入更新 + stale rate、治理之删除合规与作用域隔离、系统之延迟/token/增长）；基准 LoCoMo（1,540 题 / 10 长对话，ACL 2024）、LongMemEval（500 题 / 5 能力，ICLR 2025）、BEAM（2,000 题 / 最长 10M tokens，ICLR 2026），覆盖 recall、temporal reasoning、updates、preferences、abstention。
10. 可靠性是误差复合：单步 95% 成功，50 步全程无错仅 8%（0.95^50），错误传播使真实更差。
11. 故障五层（spec / harness / model / tool / environment），修复各不同：澄清规格、pin 规则 + 预算 + checkpoint、索要证据、fail loudly + 显式 schema、pin + 隔离 + 节流。
12. 当前无规模化 agent 的形式化最佳实践，可靠性是开放工程问题；下讲预告：agent evaluation、cost-effective agent、case studies。
