# 智能体设计 V:高性价比智能体(Agent design V: cost-effective agents)

## 本讲概览

本讲只聚焦 LLM 调用成本,围绕成本分解公式(用户数 × 会话 × 轮次 × 步数 × token 数 × 单价)逐项给出削减手段,并穿插课程 Claude Code 使用数据(如 97.6% 的 token 是缓存读取)。随后讨论"快"与"省"的关系——关键路径、编排、并行与投机动作 (speculative actions)。最后进入智能体架构:单体 (monolithic)、模块化 (modular)、微内核 (microkernel) 三种 harness 的对比,并逐一拆解八套编码智能体 harness 的独有设计。

## 课程事务

- 作业 3 今天开始:排行榜每天限次、无补交宽限;占成绩 20%,要当期中考对待,尽早开始。
- 作业 4 现为 20 分、作业 5 为 10 分(作业 5 太难且与课程项目重叠);部分讲座提前,另设两场 bonus 论文报告讲座。
- Claude Code 会话日志要更新;**篡改日志违反学术诚信 (academic integrity)**。
- 今日内容:Cost-effective agents → Agent architecture → Coding agent case study。

## 成本分解与使用数据

- 一个会话 = 多个 **turn(用户轮次)**,一个 turn = 多次 model call 与 tool call 交替的 **step**。
- 成本公式:**Cost = Users × Sessions/User × Turns/Session × Steps/Turn × Tokens/Step × Price/Token**;用户增长只能"做大",其余四项都要"做小"。
- 使用数据:68%–75% 的会话只有 1 个 prompt;每轮中位步数 3–4(因 effort 为 medium/high),少数轮次跑到近 1000 步。
- 主 agent 每步中位 208K–301K、p90 600K–700K token;子 agent 中位约 80K;上下文随步数累积,到第 ~500 步时约 650K–670K。
- 最典型结构:**97.6% 的 token 是缓存读取 (cache read)**;数量级上 output ≪ fresh prefill ≪ cache read(约 5× 与 100× 之差)。

## 降低每任务轮次(Turns per task)

- 第 k 轮会重读前 k−1 轮,总成本随轮数平方增长;用户回来追问多因"没先规划、半途而停、没自查"。
- 对策:**前置规划**(先确认目标与计划)、**结构化任务分解**(拆子任务,各自带完成检查)、**移交前自验证**(跑测试、查输出)。
- 目标:任务自主完成,无需用户中途介入。

## 降低每轮步数(Steps per turn)

- 每次 model call 都重读全部上下文,所以调用越少越省:把"一次一动作"改为**规划后批处理**——独立工具调用并行发出(如 5 个文件一次读),模型调用可从 4 次降到 2 次。
- 另两招:复用既往的计划与技能(不重新推导)、一开始就加载需要的上下文(不逐步补读)。
- 相关论文:技能库 Voyager (2023)、SkillRL (2026);计划模板复用 Test-Time Plan Caching (2025);经验洞察 ExpeL (2023)、ReasoningBank (2025);持久记忆 Mem0 (2025)、LightMem (2025)、SimpleMem (2026)。**经验复用只在任务反复出现时才回本,记忆维护与陈旧条目可能吃掉收益。**

## 降低每步输入 token

- 留在上下文里的 token 之后每一步都要重新付费,所以要压:
  - **丢弃过时的**:截断陈旧结果、遮掉已用过的工具输出、把旧轮次压缩成状态摘要 (compact)。
  - **压缩进入的**:只留错误信息不留完整日志;大输出写文件、上下文里只传路径。
  - **按需加载**:选择性检索工具与记忆;用子 agent 隔离探索、只带回摘要。
- 相关论文:历史压缩 ACON (2025,峰值上下文降 26–54%)、Active Context Compression (2026)、TRACE (2026,摘要会引发返工);提示压缩 LLMLingua (2023,至多 20×)、Prompt Compression in the Wild (2026,只对长提示有效);外部上下文 MemGPT (2023)、Scroll (2026);工具数据移出上下文 Code execution with MCP (2025,150K→2K)、Tool Search (2025,−85%)、Programmatic Tool Calling (−37%)。

## 降低每步输出 token

- **提示级约束**(≤100 词、只回 JSON)与 **API 输出上限**(max_tokens=300):简单但会在句中截断,且推理 (reasoning) 可能吃掉配额,要配简洁的系统提示。
- **结构化输出 (structured output)**:schema 只含必需字段、限制枚举与可选项,工具调用周围的散文是纯成本。
- **自适应推理 effort**:查询/格式化用 low,规划/调试用 high;按调用或按步设置 (reasoning effort / thinking-token budget)。
- 相关论文:简洁 CoT Concise CoT / CCoT (2024)、Chain of Draft (2025)、TALE (2024);Ares (2026)、When to Plan (2025)、s1 / L1 (2025);格式与解码 Let Me Speak Freely? (2024,严格格式可能伤推理)、XGrammar / SGLang (2024)、AdaEdit (2026,diff 输出)、CodeStruct (2026,AST 级编辑)、工具自制 agent (2026,输出 token −58%)。

## 降低每 token 单价

- **前缀缓存 (prefix caching) + 批处理 (batching)**:Claude API 相对基础输入价,cache read 0.1×、batch 0.5×、batch+cache 0.05×、输出 5×。做法:维持稳定前缀(系统提示、工具、早期历史),可等的工作走 batch。
- **模型路由 (model routing)**:① 开轮前选定(在偏好数据上训练的 router,也可选 agent 角色);② 失败升级(先跑便宜模型,校验不过再换强的);③ 逐步重路由(按历史与预算,orchestrator 把模型当工具调用)。难点:便宜模型一次规划错误可能浪费后续大量动作。
- 相关论文:vLLM (2023)、SGLang RadixAttention (2024)、Prompt Cache (2024)、RouteLLM (2024)、MasRouter (2025)、FrugalGPT (2023)、AutoMix (2023)、EcoAssistant (2023)、ToolOrchestra (2025)、BAAR / MTRouter (2026)。
- 后续讲座的系统级手段:模型优化(MoE、量化、剪枝、蒸馏、面向负载的微调)、服务引擎(更快 kernel、投机解码、KV-cache 与请求调度)、硬件(专用加速器)。

## 每项节省都有反成本

- 压缩 (compaction) 会让文件被重读、摘要把缓存重写;路由失败会让错误规划多走许多步;子 agent 会重复读共享文件与指令;投机猜错白白烧 token。
- **净节省 = 毛节省 − 反成本,必须在同一批任务上实测两者。**

## 给任务设预算与停止规则

- 每任务设限:金额(示例 $10)、模型调用次数(80)、工具时间(15 min)、每步重试(2 次);从跟踪到的成功任务 p95 的 ~2 倍定限。
- 停止条件:验证器通过 / N 步内无新通过的测试 / 同一错误重复。
- 触限即带摘要移交(hand off);**带摘要停下的任务比失控跑完的更便宜。**

## 这一步到底需不需要 LLM?

- 每步都一样 → 让 LLM 写一次脚本然后直接跑;固定输入格式 → 正则/解析器/模板(每次调用零成本);窄分类或打分 → 训练小分类器(GBM);固定工作流 → 脚本化,只在需要推理的步骤调用 LLM。
- 原则:**只有真正需要推理的步骤才用 LLM。**

## 让智能体更快

- 完成时间 = **关键路径 (critical path)** 而非所有步之和:串行时是求和,并行时由最长链决定;更快的 agent 通常也更便宜,但"更便宜"可能更慢、"并行"可能花更多 token。
- **LLM 服务**:上一节所有降本手段同时降延迟;再用缓存与小模型。
- **编排**:异步执行(工具调用期间先跑下一步)、常驻会话(shell/浏览器跨步保持)、流式边收边启工具、服务与模型同机。
- **工具调用**:构建/测试/网页加载可能比模型调用还慢——缓存工具结果、重计算放服务器、换更快的工具、挂起调用设超时;先测量每步工具耗时再调模型。
- **并行化**:独立调用合并到一步(三个文件并行读,等待时间约 1/3);独立子任务并行、共享状态需要合并步;只有独立的工作能并行。
- **投机动作 (speculative actions)**:① 便宜模型预测下一动作 → ② 主模型思考期间提前执行 → ③ 与主模型选择比对,命中则跳过等待、不中则丢弃(浪费一次调用)。在"猜得常对且动作可撤销"时回本。
- 相关论文:投机对象从单步工具调用 (Speculative Actions ICLR 2026、Speculative Tool Calls 2025) 到工具意图 (PASTE/B-PASTE 2026)、整条轨迹分支 (SPORK 2026、Speculative Macro Commit 2026);预测来源有模型式 (draft model)、自投机 (同一模型早期分叉)、历史式 (PASTE 用过去 trace、Speculate with Memory 2026);SPAgent (2025) 跳过部分校验属有损 (lossy)。
- 两个例子:PASTE 预测 search 之后必是 visit,URL 由搜索结果填好,visit 在模型生成期间完成;SPORK 在推理 2000 token 早期分叉探测,预测出工具调用并提前跑完。
- 开放问题:GPU/CPU/API 预算受限时,如何调度投机调用使关键路径节省超过浪费的工作。

## 优化循环

Run & Profile(记录每次调用、token、工具、等待)→ Measure(弄清成本与延迟来源)→ Change one thing(压缩/路由/缓存/并行)→ Re-evaluate(同批任务看成功率、花费、p95 延迟),循环往复。**作业 4 要记住这个循环。**

## 智能体架构:三种 harness

- **单体 (monolithic)**:内存、工具、上下文、规划、执行全在一个 runtime 内(如 `CodingAgent` 持有 `Memory`/`Tools`/`ContextManager`/`Planner`/`Executor`)。优点:简单、通信开销小、状态易共享;缺点:难替换组件、耦合紧、隔离难强制。特征:agent 拥有一切。
- **模块化 (modular)**:agent 仍控制循环,但通过接口访问组件(`MemoryProvider=RedisMemory()`、`ToolProvider=MCPTools()`、`SandboxProvider=Docker→Firecracker` 只换一个 provider)。优点:易替换、好测试扩展;缺点:控制器仍管生命周期、联合调优要改控制器。特征:一个控制器经接口委托。
- **微内核 (microkernel)**:核心 runtime 只做状态/协调/调度/安全,能力由外部服务提供(memory、tools、execution 服务,可跨容器/机器)。优点:独立扩缩、故障与隔离更强、基础设施共享;缺点:通信开销更高、失败模式更多、端到端调试难、依赖标准协议。特征:runtime 只协调,服务提供能力。
- 例:执行一段 Python——单体在本地直接跑(跳数最少但隔离难);模块化经 SandboxProvider 换实现;**微内核把沙箱的分配、隔离与生命周期都交给独立的执行服务**。

## 三种架构对比

| 维度 | 单体 | 模块化 | 微内核 |
|---|---|---|---|
| 设计原则 | 全部集成 | 接口抽象 | 最小核心 + 服务 |
| 中央控制器 | 是 | 是 | 是,但更弱 |
| 组件替换 | 困难 | 容易 | 协议匹配时容易 |
| 执行隔离 | 可选 | 可选 | 架构级强调 |
| 组件部署 | 通常一起 | 一起或分离 | 通常独立 |
| 独立扩缩 | 有限 | 可能 | 强 |
| 通信成本 | 低 | 低–中 | 可能更高 |
| 典型用途 | 独立 agent | agent 框架 | 多 agent 基础设施 |

## 八套 harness 案例:各自独有的设计

| Harness | 一句话 | 独有设计 |
|---|---|---|
| **Claude Code** (Anthropic, TS) | 围绕 Claude 的策略层 | 策略层与类型化 hooks |
| **Codex CLI** (OpenAI, Rust) | 先沙箱、后提问 | 无网络命令先跑沙箱,出界才申请批准;patch 遵循 Lark 语法,四遍匹配 hunk |
| **DeepSeek Harness** (TS) | 一切皆插件 | 循环/适配器/工具/日志/审批都是插件,YAML 分层替换;请求是会话日志的冻结视图,日志只追加;编辑走 compare-and-swap(文件自模型上次读后变过就失败) |
| **OpenCode** (SST, TS/Bun) | 会话服务器 + 瘦客户端 | TUI/SDK/Web 共用同一 OpenAPI HTTP 服务;9 种替换器从精确到锚点匹配,过大模糊匹配被拒;每步 shadow git 快照,`/undo` 恢复文件而非聊天记录 |
| **Pi** (Mario Zechner) | 可扩展的小核心 | 核心仅 4 个工具,无 MCP/子 agent/审批,扩展提供其余功能;只在预期节省 ≥$0.05 时发 keep-alive 预热缓存;pi-ai 在 10 种 wire API 上支持 42 家供应商 |
| **oh-my-pi** (Pi fork) | 原生工具 + IDE | hashline 编辑(4 位十六进制文件标签+行号,模型不必再打旧文本);常驻一个 shell,原生 search/AST/LSP/调试器;TTSR 正则失配时停止重试;图像化的 snappass 压缩旧历史 |
| **OpenClaw** (基金会, TS) | 聊天渠道网关 | 27 个渠道、每会话一条 lane,队列模式控制运行中进来的消息;先写带日期笔记再压缩,回忆用全文+向量检索;围栏 (fences) 隔离不可信文本、网络读取标记污染 (taint)、秘密哨兵 (sentinel) 监控 |
| **Hermes Agent** (Nous Research, Python) | 会写自己技能的 agent | 后台 fork 检查每个被提示轮次并编辑记忆与技能;压缩在窗口 50% 处开始(八者最早);副作用发生前先把工具调用行写入会话数据库 |

## 下节课

- Agent safety and security(智能体安全)
- Self-evolving harness(自演化 harness)

## 核心要点

- 成本 = 用户 × 会话 × 轮次 × 步数 × token × 单价:前两项靠增长,后四项逐项压缩。
- 轮数是最危险的因子:每轮重读历史,总成本随轮数平方增长;靠前置规划、任务分解、自验证压轮数。
- 每次 model call 都重读全部上下文 → 批处理独立调用、复用计划、前置加载上下文。
- 97.6% 的 token 是缓存读取,缓存命中是成本结构的决定性事实;维持稳定前缀 + batch 可把单价降到 0.05×。
- 上下文里留下的每个 token 每一步都要重新付费 → 压缩历史、大输出落盘传路径、子 agent 隔离探索。
- 输出端:提示约束 + 输出上限 + 结构化 schema + 按步调 reasoning effort;推理 token 可能吃掉输出配额。
- 模型路由三策略(开轮选定/失败升级/逐步重路由)的最大风险是便宜模型的一次坏规划。
- 每项节省都有反成本(重读、重复上下文、猜错),净节省必须同批任务实测。
- 每任务设预算(金额/调用数/时间/重试),触限带摘要移交;从 p95 的 ~2 倍定限。
- 不需要推理的步骤用脚本、正则、小分类器替代 LLM。
- 完成时间由关键路径决定;提速靠编排(异步/常驻/流式/同机)、工具缓存与超时、并行独立工作、投机动作。
- 投机动作 = 预测→提前执行→比对,命中跳过等待、不中丢弃一次调用;在猜得常对且可撤销时回本。
- 三种架构沿"代码 → 接口 → 服务"下放职责:单体适合独立 agent,模块化适合框架,微内核适合多 agent 基础设施。
- 优化是循环:跑并记录 → 度量 → 只改一件事 → 同任务复评(成功率/花费/p95 延迟)。
