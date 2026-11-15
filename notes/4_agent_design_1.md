# 第 4 讲:智能体设计 I(上下文管理与工具设计)

> **Agent Design I: Context and Tool Design** · Harvard CS2680 · 讲师 Juncheng Yang · course.agentic-system.org
> 原始幻灯片:[4_agent_design_1.pdf](../4_agent_design_1.pdf)
> 今日计划:Agent loop (ReAct)、工具设计、上下文管理(prompt engineering → context engineering)

## 本讲概览

本讲回答"如何设计一个 coding agent":核心论点是 **Agent = Model × Harness** —— 模型能力决定上限,harness(循环、工具、提示、上下文管理)决定实际表现。先给出 ReAct 循环与最小 agent loop 伪代码;再系统比较搜索/读取、编辑、执行三类工具的四种方案及取舍;然后从 prompt engineering 过渡到 context engineering:上下文是有限资源,用 admission / offloading / transformation / compaction 四个杠杆管理;最后用 SWE-bench 数据说明仅改 harness 就能让准确率约翻倍。

## ReAct 循环与 Agent Loop

- **ReAct**(arXiv:2210.03629)在同一个循环里既推理又行动,每步三要素:
  - **Thought**——我知道什么、缺什么、下一步做什么
  - **Action**——向环境发出结构化调用
  - **Observation**——环境用事实作答
- 三者缺一不可:
  - 只用 Reason 无校验:小误差复利成自信的幻觉
  - 只用 Act 无计划:模型原地重复
  - ReAct 中 thought 引导下一个 action,observation 纠正下一个 thought,循环直到问题被回答或停止规则生效
- 最小 agent loop 伪代码:
  - messages 初始为 system + user
  - 循环 `for step in range(MAX_STEPS)`:调用 `call_model(messages, tools)`,有 final answer 则返回
  - 否则对每个 tool call `validate` 参数、`execute_tool`,把结果以 `{"role": "tool", ...}` 追加回 messages
  - 超限则 `raise RuntimeError("Agent exceeded its step limit")`
- 作为 harness 设计者,你负责:写工具定义、组装上下文、校验请求/检查权限并执行、按需处理结果并管理上下文。

## Coding Agent 的三大组件

三个组件共享同一个上下文窗口,必须一起设计:

- **Model + agent loop**——智能体 = 模型加一个循环(LLM 提出动作、看结果、重复直到完成)
- **Tools and guardrails**——工具决定能力,guardrails(权限、沙箱、审批)保证安全
- **State:context and memory**——组装当前窗口内容,保留跨步骤存活的状态

## 工具设计:搜索与读取

| Approach | Finds code by | Best when | Main cost |
|---|---|---|---|
| glob / grep | literal names and paths | the name is known or guessable | turns and context per search |
| Semantic index | meaning of embedded chunks | wording won't match the code | building and re-syncing the index |
| Extrinsic signals | traces, failing tests, git history | a report already points at code | only exists for some tasks |
| Language server | the compiler's symbol graph | edits must follow references | a live server per language |

- **glob / grep**:无需建索引、永远反映 live repo;但烧轮次和上下文,字面匹配会漏掉换词表述
- **语义索引**:嵌入代码块按含义检索(结构式:文件树 + 排序符号,如 Aider repo map);查询快,但建索引和再同步有成本
- **外部信号**:stack trace、失败的测试、git 历史——调试时精度最高,但只在存在此类信号时有用
- **语言服务器 (LSP)**:查询编译器索引(定义、引用、符号、类型),能解析 grep 只能猜的 import/重载/重命名;成本是每种语言一个 live server、冷启动慢
- **实践建议**:先 grep,名字不够用再上索引或 LSP

## 工具设计:编辑

| 方案 | 优点 | 成本 |
|---|---|---|
| 整文件重写 (whole-file rewrite) | 无 patch 语法可错,总是干净应用 | 输出随文件大小增长,未改动代码可能漂移 |
| Unified diff / patch | 紧凑、可 review,人类与 CI 已用 | 行号/上下文漂移时 hunk 失败 |
| Search / replace | 输出与改动量成正比,与文件大小无关 | 锚点歧义、过期、空白不对则失败 |
| 结构化 / AST 编辑 | 免疫格式问题,不会产出非法语法 | 每种语言单独工具,可表达的编辑有限 |

权衡轴:**token 成本 vs 健壮性**(编辑是否落在预期位置)。

## 工具设计:执行(shell)

- 执行工具"实际上就是一个 shell"——最强也最危险:
  - **组合性**:chain / filter / loop
  - **可达性**:文件系统、网络、包管理器、已装二进制
  - **持久性**:文件与进程比单次调用活得久
  - **爆炸半径**:shell 能做什么,agent 就能做什么
- 必须考虑:
  - **隔离**:在哪跑、能触达什么
  - **失败信号**:错误要让 agent 能行动
  - **输出量**:足够但别太多
  - **时长**:长时/后台进程
  - **预算**:何时停止重试、交还控制权

### 其余常用工具

- **记忆与笔记**:计划可存活压缩
- **子智能体/委托**:探索只返回 shortlist,而非 40 个文件读取
- **网页搜索与抓取**:先读已装源码再上网
- **浏览器与视觉反馈**:截图渲染回喂
- **询问用户**:一个便宜的问题胜过自信的错误补丁

### 工具设计最佳实践

- 少而正交(重叠的工具会让模型纠结)
- 专用而非通用(`search_orders(customer_id)` 优于裸 `run_sql`)
- 输出 token 便宜(截断/分页/摘要——**工具设计就是上下文设计**)
- 会"教"的错误(返回修复提示,而非只说"invalid argument")
- 默认幂等(可安全重试)

> **实验**(留待 assignment):"能否只给 shell?"GPT-4 上各配置得分——专用 SWE-agent 式 18.0%、完整交互历史 15.0%、整文件视图 12.7%、仅 shell 11.0%、无专用编辑器 10.3%。

## 上下文管理 (I):Prompt Engineering

- 术语演进:
  - 2023–24 **Prompt Engineering**——如何指示模型?措辞/示例/输出格式
  - 2025–26 **Context Engineering**——模型该看到什么?检索/记忆/历史/输出压缩
  - 2026 **Harness Engineering**——智能体如何运作?循环/工具/沙箱/重试/停止/权衡
  - 未来 **Goal Engineering**——什么算成功?目标/判据/约束
- 八大技术(每页给出示例、适用时机、何时换用下一个):
  - **Zero-shot**:仅指令;任务常见且格式可一句话说清
  - **Few-shot**:指令 + 示例;输出形状不寻常、规则"易展示难表述"
  - **Role & persona**:给角色;语气或判断重要、受众明确
  - **Chain-of-thought**:显式分步推理再给答案;任务天然多步、错误来自跳步
  - **Tree-of-thought**:分支、打分、剪枝;多条路线皆可能且可便宜评分
  - **Self-consistency**:多次采样 + 多数投票(如 5 次,T=0.7);唯一正确答案且判错代价高
  - **Prompt chaining**:一次调用干一件事、交接处做校验;可拆分阶段且每步可验证(某阶段 schema 失败只重试该阶段)
  - **Meta prompting**:让模型改写自己的 prompt;有 eval 集可评分(示例中 8/10 → 10/10)
- 选型逻辑:从简(零样本为基线)→ 加推理(思维链/树/自一致)→ 工程化系统(链式/meta);部分技术已"过期",留待 assignment 自己发现
- 四条设计最佳实践:
  - 从简单开始再迭代,只在需要时加上下文
  - 分节(上下文、指令、工具、输出规格;顺序:instruction → delimiter → data)
  - 具体而简洁,花哨措辞无收益
  - 大任务拆子任务,别前置复杂度

> **提示技巧是模型相关的**——换模型就要重调。

## 上下文管理 (II):Context Engineering

> "Context engineering is the delicate art and science of filling the context window with just the right information for the next step" —— Andrej Karpathy

- **上下文是有限资源**:
  - 每一步都重发整个窗口 → 每轮再付一次成本
  - prompt 越大 prefill/decode 越慢 → 循环变慢
  - 窗口填满后回忆衰减、中间容易被漏 → **上下文更多 ≠ 答案更好**
- 长度与位置都损失准确率(Context Rot (Chroma);Liu et al., "Lost in the Middle," TACL 12 (2024)):
  - 简单查找任务准确率:100% → 76% → 71% → 61% → 55%
  - 带干扰项:100% → 73% → 59% → 46%
  - 答案所在文档位置(1st…20th)影响显著
- 单个 agent turn 的示例 token 预算:
  - system prompt ~2K
  - tool definitions ~6K
  - retrieved context ~25K
  - project environment ~8K
  - message history ~80K 且持续增长

### 四个管理杠杆(从预防无损 → 有损不可逆)

- **Admission(准入,守门)**:
  - targeted retrieval:窄查询、取字段不取整文档
  - tool output shaping:丢 DOM 留提取
  - truncation:仅当 shaping 不够时
  - isolation:原始载荷交给子智能体
  - 示例:48,000 tokens 原始 DOM → 900 tokens(小 98%,答案相同)
- **Offloading(卸载,需要时才载入,保持可检索而非常驻)**:
  - 渐进工具定义、工具索引按需取回
  - 工具输出只返回句柄
  - 任务表外置磁盘、持久记忆写盘
  - 示例:60 个常驻 schema 42,000 tokens → 索引 + 3 个 schema 3,100 tokens(小 93%,60 个仍可达)
- **Transformation(转换,选择性丢弃历史)**:
  - 去重:只留每个对象最新状态
  - observation masking:掩掉 N 步以前的工具结果
  - sliding window:只留近期轮次 + 头部
  - 示例:96,000 → 24,000 tokens(小 75%,未做任何摘要)
- **Compaction(LLM 兜底,最后手段)**:
  - rolling summary:滚动摘要旧工具结果
  - full summary:到上限时重写全部历史
  - auto memory:关键事实持久化到窗口外
  - 警告:给输出预留 headroom、保留 system prefix、压缩后重新注入关键事实

### 上下文失败的五种方式

> Breunig, "How Contexts Fail and How to Fix Them", 2025 —— 命名失败,修复就变清晰

- **Poisoning**:幻觉进入窗口,之后被当作事实引用
- **Distraction**:历史膨胀,agent 开始模仿自己过去的行为
- **Confusion**:无关工具与文档把答案带偏
- **Clash**:新旧信息矛盾,双双未解决
- **Drift**:真实目标被埋没,被邻近子目标替换

## Agent = Model × Harness

- 模型能力设上限,harness 决定实现表现。仅改 harness 即可约 2 倍提升(Lewis, "Same Model, Different Harness: Different Coding-Agent Results", arXiv:2608.26218, 2026):

| Benchmark | Basic harness | Improved harness | What changed |
|---|---|---|---|
| SWE-bench Verified | 43 / 169 | 72 / 169 | 旧工具输出压缩;近期观察保持可见;检测重复与停滞;卡住时干预 |
| SWE-bench Pro | 31 / 316 | 72 / 316 | 同上 |

> 许多看似"模型失败"的,其实是上下文与控制循环的失败。

- 留待 assignment 亲手实验:agent loop、prompt、工具、上下文管理、失败处理全都重要。

## 核心要点

- 智能体 = 模型 + 循环;ReAct 三要素 Thought/Action/Observation 互相校准,缺一则幻觉复利或原地重复。
- 最小 harness:循环调模型 → final answer 即返回,否则执行 tool calls 并把结果追加回 messages;MAX_STEPS 超限抛错。
- 三大组件(循环、工具 + guardrails、上下文与记忆)共享一个窗口,必须联合设计。
- 搜索/读取四方案各有适用场景:grep 零成本起步,语义索引抗换词,外部信号(trace/失败测试/git)调试精度最高,LSP 跟随引用;名字不够用再升级。
- 编辑四方案在 token 成本与健壮性之间权衡:整文件重写最稳但贵,diff 紧凑但怕行漂移,search/replace 最省但怕锚点失效,AST 编辑免疫格式但语言覆盖有限。
- shell 是最强最危险的执行工具:组合性、可达性、持久性、爆炸半径;必须配隔离、可用错误信号、输出量控制、时长与预算。
- 工具设计五原则:少而正交、专用优先、输出 token 便宜、错误要教人、默认幂等——工具设计就是上下文设计。
- 仅给 shell 不够:GPT-4 实验 18.0%(专用 SWE-agent 式)vs 11.0%(仅 shell)vs 10.3%(无专用编辑器)。
- 上下文是有限资源:每轮重发、越长越慢、长度与位置都损失准确率(Lost in the Middle / Context Rot)——更多上下文不带来更好答案。
- 窗口管理四杠杆按"无损 → 有损"排序:Admission 守门、Offloading 按需、Transformation 去重掩码、Compaction 兜底压缩;各有 98%/93%/75% 级别的缩减示例。
- 压缩时务必:保留输出 headroom、保留 system prefix、压缩后重注入关键事实。
- 上下文五败:Poisoning、Distraction、Confusion、Clash、Drift。
- 术语演进:Prompt → Context → Harness → Goal Engineering;提示技巧模型相关,换模型要重调。
- 仅改 harness(压缩旧输出、保留近期观察、检测停滞并干预)即可让 SWE-bench 准确率约翻倍——许多"模型失败"是 harness 失败。

## 下讲预告与选读

- 下讲 Agent Design II:agent(持久)记忆、高性价比 agent、安全、多智能体设计。
- 选读(ReAct 之外的循环形态):
  - **Reflexion**:失败后循环:Attempt → Evaluate → Critique → Retry
  - **Plan-and-execute**:偏离时重规划:Plan → Execute steps → Re-plan
  - **Tree search**:无循环——并行探索分支、只留最优
