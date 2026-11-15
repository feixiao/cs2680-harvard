# 第8讲：智能体设计 V（高性价比智能体）

> 原讲题：*Agent design V: cost-effective agents*（Harvard CS2680 Modern AI Systems: Agents and System Optimizations，Juncheng Yang）

## 本讲概览

本讲的主题是**如何设计高性价比（cost-effective）的 LLM 智能体**，并且明确把焦点放在 LLM 调用成本上（其他计算成本暂不考虑）。讲者先从成本公式入手——成本 = 用户数 × 会话数 × 每会话轮次 × 每轮步数 × 每步 token 数 × 每 token 单价——然后逐一讨论每个因子的削减手段，并穿插本课程的 Claude Code 使用数据（例如 97.6% 的 token 是缓存读取）。接着讨论预算上限与停止规则、"这一步到底需不需要 LLM"的问题，以及提速手段（关键路径、编排、并行、投机动作，如 PASTE / SPORK）。后半部分是智能体架构：单体（monolithic）、模块化（modular）、微内核（microkernel）三种 harness 架构的对比，并以编码智能体案例研究收尾——逐一拆解 Claude Code、Codex CLI、DeepSeek Harness、OpenCode、Pi、oh-my-pi、OpenClaw、Hermes Agent 八套 harness 各自独有的设计。

## 课程事务（Logistics）

- **作业 3（Assignment 3）今天开始**，比之前的作业难得多；排行榜每天有提交次数限制，且**没有补交宽限（no late days）**。
- 作业 3 占成绩 **20%**，要像对待期中考试（midterm）一样对待它，尽早开始。
- 下周有 Office hours（具体时间待定）。
- **作业分值更新**：作业 4 现在值 20 分，作业 5 值 10 分。原因：作业 5 太难，并且与课程项目以及其他课程的项目重叠。
- **进度更新**：为了适应作业变化，部分讲座提前安排；另有**两场 bonus 论文报告讲座**，今天开放报名。
- **Claude Code 会话日志**：需要更新所有相关会话的日志；**绝不能篡改会话日志，那违反学术诚信（academic integrity）**。

## 今日计划

- Cost-effective agents（高性价比智能体）
- Agent architecture（智能体架构）
- Coding agent case study（编码智能体案例研究）

# 一、设计高性价比智能体

本讲只关注 LLM 成本，忽略其他计算成本。

## 回顾：一个会话的结构

一个用户 **turn（轮次）** = 多次 LLM 调用与工具 **step（步）** 的交替。图示：一张会话时间线图，session 包含 Turn 1、Turn 2、Turn 3……；每个 turn 内部是 "User message → Model call → Tool call → Model call → Reply to user" 这样的交替序列，这些 model call 与 tool call 合称 **steps**。

## 成本从哪里来？

图示：一张把成本分解为各级比率的树状图，标注了哪些因子要"做小（SHRINK）"、哪个因子受"增长（GROW）"驱动：

**Cost = Users × Sessions/User × Turns/Session × Steps/Turn × Tokens/Step × Price/Token**

各因子的性质：

| 因子 | 驱动 | 方向 |
|---|---|---|
| Users × Sessions/User | 用户采纳与使用参与度（adoption and engagement） | ↑ GROW（增长是好事，无法也无需削减） |
| Turns / Session | 智能体轨迹（agent trajectories） | ↓ SHRINK |
| Steps / Turn | 智能体轨迹 | ↓ SHRINK |
| Tokens / Step | 智能体轨迹 | ↓ SHRINK |
| Price / Token | 单价（unit price） | ↓ SHRINK |

也就是说：用户规模和会话规模会随产品被更多人使用而增长，这是增长动力；而 turns、steps、tokens、单价四个因子才是我们能通过**智能体设计**去削减的成本来源。本讲后面四个小节正好逐一对应这四个因子。

## 班级数据：每会话轮次（turns per session）

对同学们 Claude Code 使用数据的统计：

- **68% 的会话只有一个 prompt**（Assignment 1），到 Assignment 2 时为 **75%**（单 prompt 会话占比）。
- 讲者点评：这是好事——说明大多数人**每个任务都开一个新会话**（start a new session for each task）。
- 但也有少数"马拉松"会话，**超过 100 个 turns**。

图示：柱状图/分布图，显示单 prompt 会话在两个作业中分别占 68% 与 75%，长尾处是 100+ turns 的马拉松会话。

## 减少每个任务的（用户）轮次

核心观察：**Turn k 要重新读取 turns 1 … k−1 的全部历史，所以总成本随轮次数的平方增长**。轮次越少，成本越省——这是最强的一个削减因子。

为什么用户会一次次回来（turn 变多）？讲者归因于三种失败模式，并给出对应手段（三栏表）：

| 原因 | 手段 |
|---|---|
| 没有计划 | **Front-load planning（前置规划）**：行动之前，先一次性确认目标与计划 |
| 过早停下，或用户从未检查 | **Structured task decomposition（结构化任务分解）**：拆成子任务，每个子任务返回前做 done check |
| 交付时没验证 | **Self-verification before handoff（交接前自验证）**：跑测试、检查输出后再返回给用户 |

目标：**自主完成任务，不需要用户中途回来检查（finish the task autonomously, with no user check-ins）**。页面底部标注本因子对应成本公式中的 "Turns per task"。

## 班级数据：每轮步数（steps per turn）

- 大多数 turn 的步数很少：**中位数 3 步**（Assignment 1）→ **4 步**（Assignment 2）。
- 主要是 effort（推理力度）设置在 medium 或 high 的缘故。
- 但有些 turn 几乎跑到 **1,000 步**。

图示：两个作业各一张步数分布图，标注中位数 3 与 4，长尾接近 1,000 步。

## 减少每轮步数

图示：左右对比——"One call per action"：Model → Tool → Model → Tool → Model → Tool → Model，共 **4 次 model 调用**；"Plan, then batch"：Model → 3 tools in parallel → Model，共 **2 次 model 调用**。

**每一次 model 调用都要重读完整上下文，所以调用次数越少，成本越低。** 具体手段（三栏表）：

| 批量独立调用（Batch independent calls） | 复用计划与技能（Reuse plans and skills） | 前置加载上下文（Load context up front） |
|---|---|---|
| 一个 step 读五个文件，而不是分五个 step 各读一个 | 重放之前奏效的做法，而不是每次重新推导 | 一开始就读好需要的文件，而不是每个 step 读一个 |

注意"复用计划与技能"是跨任务/跨会话的：把上次成功的做法直接重放（replay），避免重新推导（re-deriving）整段计划，既省步数也省 token。

## 进阶（可略读）：复用计划、技能与经验——相关论文

讲者标注此页为 **ADVANCED——可略读，或自行深入**：

| 类别 | 论文 |
|---|---|
| 技能库（Skill libraries） | **Voyager**（2023）：存储可执行技能；**SkillRL**（2026）：联合改进技能库与智能体策略 |
| 剧本与计划模板（Playbooks and plan templates） | **Test-Time Plan Caching**（2025）：复用并适配计划模板 |
| 来自经验的洞见（Insights from experience） | **ExpeL**（2023）：抽取可复用的洞见；**ReasoningBank**（2025）：保留来自成功与失败运行的策略 |
| 持久会话记忆（Durable conversational memory） | **Mem0**（2025）：存储与更新事实；**LightMem**（2025）：离线 consolidation（巩固）；**SimpleMem**（2026）：压缩记忆 |

讲者的告诫：**复用只有在任务会重复出现时才划算；记忆维护开销与过期条目会吃掉省下来的钱。**（Reuse pays when tasks recur; memory upkeep and stale entries can erase the savings.）

## 班级数据：每步 token 数（tokens per step）

- **主 agent（main agent）**：中位数 **208K**（Assignment 1）→ **301K**（Assignment 2）；量级上是 200K–300K，**p90 达 600K–700K**。
- **子 agent（subagent）**：中位数约 **80K**，p90 约 **200K**。

也就是说，同学们每一步上下文已经动辄 20 万–30 万 token，长尾近 70 万——单靠"步数少"并不能保证成本低，因为每一步的 token 本身已经很大。

## 班级数据：token 随步数累积

**上下文不断累积、增长很快**：在大约第 **500 步**时，上下文规模达到 **670K**（Assignment 1）与 **650K**（Assignment 2）。图示：token 数随 step 编号上升的曲线图，两个作业各一条，在 ~500 步处标注 670K / 650K。这说明上下文几乎是单调增长的，后面每一步都要为越来越大的上下文重新付费。

## 大多数 token 是缓存读取（cache read）

- 输出 token 比新 prefill（cache write，即缓存写入）小 **5 倍**；新 prefill 又比缓存读取小 **100 倍**——从 token 数量看，绝大多数 token 都是 cache read。
- **典型价格比：cache read : input : output = 1 : 10 : 50**（缓存读取最便宜，输出最贵）。
- 班级数据（Assignment 1）：**97.6% 的 token 是缓存读取**。

图示：饼图或份额图，标注 cache-read token share 97.6%。含义：由于前缀缓存（prefix cache）命中，token 总量大不等于账单贵——但同时也意味着"缓存未命中的部分"和"输出"是花钱的重灾区，优化要瞄准它们。

## 减少每步输入 token：让上下文保持精简

关键原理：**留在上下文里的 token，之后每一步都要重新付费**（Tokens that stay in context are paid for again on every later step）。三类手段：

| 丢弃过期的（Drop what's stale） | 压缩进来的（Shrink what enters） | 只加载需要的（Load only what's needed） |
|---|---|---|
| 截断过期结果（Truncate stale results） | 压缩观察（Compress observations）：只保留错误信息，而非完整日志 | 选择性检索（Retrieve selectively）：只载入相关的工具与记忆 |
| 掩码已经用过的工具输出（Mask tool outputs already used） | | |
| 压缩历史（Compact the history）：把旧轮次总结成状态（state） | 卸载到文件（Offload to files）：大输出存文件，上下文里只传路径 | 隔离探索（Isolate exploration）：让子 agent 去探索，只把摘要带回来 |

直觉：上下文是每一步都要重新付钱的"随身行李"，任何不再有用的内容都该立刻丢弃、压缩或移出。

## 进阶（可略读）：减少每步输入 token——相关论文

**压缩智能体历史（Compress agent history）：**

| 论文 | 做法/收益 |
|---|---|
| ACON（2025） | 峰值上下文削减 26–54% |
| Active Context Compression（2026） | 智能体自己压缩自身，token 少 23% |
| TRACE（2026） | 发现摘要会导致返工（summaries cause rework） |

**提示词压缩（Prompt compression）：**

| 论文 | 做法/收益 |
|---|---|
| LLMLingua（2023） | 最多减少 20 倍 token |
| LongLLMLingua、LLMLingua-2（2024） | 长提示词压缩 |
| Prompt Compression in the Wild（2026） | 只在长提示词上才划算 |

**把上下文当作外部记忆（Context as external memory）：**

| 论文 | 做法/收益 |
|---|---|
| MemGPT（2023） | 把上下文当快速记忆管理 |
| Scroll（2026） | 无损外部日志，由代码决定模型看到什么 |

**让工具数据不进入上下文（Keep tool data out of context）：**

| 论文 | 做法/收益 |
|---|---|
| Code execution with MCP（2025） | 用代码过滤结果，150K → 2K token |
| Tool Search（2025） | 工具 token 减少 85% |
| Programmatic Tool Calling | 减少 37% |

## 减少每步输出 token：要求得更少

两条腿走路：

| 提示词级约束（Prompt-level constraints） | 输出 token 上限（Output-token caps） |
|---|---|
| "Answer in ≤100 words."（用不超过 100 词回答） | 在 API 调用中设硬性上限：`max_tokens=300`、`max_output_tokens=300` |
| "Return only JSON. One sentence. Top 3 items."（只返回 JSON；一句话；前 3 条） | 简单，但截断可能把回答拦腰切断（cut an answer mid-sentence） |
| "Don't restate the problem."（不要复述问题） | 建议与简洁输出提示词搭配：**Terse system prompt："Be concise; omit background unless requested."**（简洁；除非要求，省略背景） |
| "Don't explain your reasoning."（不要解释你的推理） | |

注意点（catch）：**推理（reasoning/thinking token）可能吃光这个上限**——思考 token 也计入输出预算，上限设太低可能连正文都写不出来。

## 减少每步输出 token：模式（schema）与力度（effort）

| 结构化输出（Structured output） | 自适应推理力度（Adaptive reasoning effort） |
|---|---|
| 只要求包含所需字段的 schema | 让思考预算匹配该 step 的难度 |
| 限制枚举值与可选字段，使模型无法添加多余内容 | 查找、格式化用 **low** effort；规划、调试用 **high** |
| 适合用工具的 agent：工具调用周围的散文（prose）纯属成本 | 按每次调用、或按每个 step 设置，形式是 **reasoning effort** 或 **thinking-token budget** |

幻灯片上配了一个示例 JSON 调用：

```json
{"action": "search", "argument": "KV cache"}   // lookup: effort="low"
{"action": "debug", "argument": ...}            // debug: effort="high"
```

即：对 `search` 这类查找动作用低推理力度，对 `debug` 这类复杂动作用高推理力度——不同 step 用不同的思考预算。

## 进阶（可略读）：减少每步输出 token——相关论文

**提示词与预算（Prompts and budgets）：**

| 论文 | 做法 |
|---|---|
| Concise CoT（2024） | 要求简洁的思维链 |
| CCoT（2024） | 给 CoT 设字数上限 |
| Chain of Draft（2025） | 简短草稿 |
| TALE（2024） | 推理 token 预算 |

**自适应推理力度（Adaptive reasoning effort）：**

| 论文 | 做法 |
|---|---|
| Ares（2026） | 按 step 选择力度 |
| When to Plan（2025） | 只在有用时才做规划 |
| s1、L1（2025） | 强制执行思考预算 |
| Reason Efficiently, ShorterBetter | 更高效推理（更短更好） |

**结构化输出与解码（Structured output and decoding）：**

| 论文 | 做法 |
|---|---|
| Let Me Speak Freely?（2024） | 严格格式可能损害推理 |
| AdaEdit（2026） | diff 或整文件输出 |
| CodeStruct（2026） | AST 级编辑 |
| XGrammar、SGLang（2024） | 约束解码 |
| JSONSchemaBench（2025） | 基准 |

**只输出变化的部分（Emit only what changes）/ 造工具的 agent：**

- **Tool-making agents（2026）**：把可复用操作变成工具，输出 token 减少 **58%**。

## 降低每 token 单价：缓存与批处理

以 **Claude API** 为基准（相对基础输入价 base input = 1×）：

| 类别 | 相对价格 |
|---|---|
| Output token | **5×** |
| Base input token | **1×** |
| Batch input（批处理输入） | **0.5×** |
| Cached input（缓存命中输入） | **0.1×** |
| Batch + cached input | **0.05×** |

两条对应手段：

- **维护稳定前缀（Maintain stable prefixes）**：把 system prompt、工具定义、早期历史放在稳定前缀里，保证缓存命中——这样后续输入按 0.1× 计费，而不是 1×。
- **批处理可以等的事（Batch what can wait）**：evals、backfill、批量作业走 batch，输入再打对折（0.5×），叠加缓存后低至 **0.05×**——比基础输入便宜 **20 倍**。

图示：条形图展示五档价格（5×、1×、0.5×、0.1×、0.05×），并标注两条杠杆。

## 降低每 token 单价：模型路由（model routing）

三种策略（三栏表）：

| 一开始就选（Choose up front） | 失败后升级（Escalate on failure） | 每步重新路由（Re-route each step） |
|---|---|---|
| 每个 turn 开始、生成之前选定一个模型 | 先用便宜模型；检查失败时换更强的 | 随着智能体轨迹增长，重新选择模型 |
| 怎么做：在偏好数据上训练一个路由器（router）；还可以连 agent 角色一起选 | 检查手段：学习到的打分器（learned scorer）、自我验证（self-verification）、执行反馈（execution feedback） | 怎么做：按历史与预算路由；编排器（orchestrator）把"模型"当作工具来调用 |

难点（hard part）：**一次便宜的规划错误，可能浪费掉后面很多动作**——便宜的模型省了单价，但错误的计划会让后续所有 step 白跑。

## 降低每 token 单价：后续讲座的系统技术

| 模型优化（Model optimization） | 服务引擎（Serving engine） | 硬件优化（Hardware optimization） |
|---|---|---|
| MoE / 稀疏性（sparsity） | 更快的 kernel | 更好的 kernel 调度 |
| 量化（Quantization） | 投机解码（speculative decoding） | 专用加速器（specialized accelerators） |
| 剪枝（Pruning） | KV cache 优化 | |
| 蒸馏（Distillation） | 更好的请求调度 | |

以及：**面向工作负载的微调（workload-targeted fine-tuning）**。这些是课程后续讲座（系统优化部分）的内容，作用于"每 token 单价"这一因子。

## 进阶（可略读）：降低每 token 单价——相关论文

| 策略 | 论文 |
|---|---|
| 前缀缓存（Prefix caching） | **vLLM**（2023）：PagedAttention；**SGLang**（2024）：RadixAttention 前缀缓存；**Prompt Cache**（2024）：模块化复用 |
| 一开始就选（Choose up front） | **RouteLLM**（2024）：学习式路由器；**MasRouter**（2025）：连 agent 角色一起选 |
| 失败后升级（Escalate on failure） | **FrugalGPT**（2023）：学习式级联（cascade）；**AutoMix**（2023）：自我验证；**EcoAssistant**（2023）：执行反馈 |
| 每步重新路由（Re-route each step） | **ToolOrchestra**（2025）：小型编排器；**BAAR、MTRouter**（2026）：预算感知 |

## 每一项节省都有代价（counter-cost）

四个"节省 vs. 反代价"对照：

| 节省 | 反代价 |
|---|---|
| **Compaction（上下文压缩）** | 被丢弃的文件会被重新读取，摘要会重写缓存，多花很多步 |
| **Routing（模型路由）** | 便宜模型的一次坏规划，可能多花很多步或整个失败重试 |
| **Subagents（子 agent）** | 每个子 agent 都要重读共享文件与相同工具说明（duplicated context） |
| **Speculation（投机）** | 猜错会烧掉 token，并与（正确的工作）争抢资源 |

**净节省 = 毛节省 − 反代价；必须在同一批任务上同时测量两者。**（Net saving = gross saving − counter-cost; measure both on the same tasks.）

## 给每个任务设预算上限，进展停滞就停止

**每任务限额（示例值）**：

| 限额 | 示例 |
|---|---|
| 金额（Dollars） | $10 |
| Model 调用次数（Model calls） | 80 calls |
| 工具时间（Tool time） | 15 min |
| 每步重试（Retries per step） | 2 retries |

**停止条件（Stop when）**：

- 验证器（verifier）通过；
- 连续 N 步没有新的通过测试（no new passing test in N steps）；
- 同一个错误反复出现（the same error repeats）；
- 撞到任何限额：带着摘要交接（hand off with a summary）。

两条设计原则：

1. **限额要从真实运行的轨迹（traced runs）中设定，例如取成功任务的 p95 的 2 倍**（2× the p95 of successful tasks）；
2. **一个带着摘要停止的任务，比一个跑飞（runaway）的任务更便宜**。

（幻灯片注明：示例限额仅为说明性质 / illustrative。）

## 这一步到底需要 LLM 吗？

四个"不用 LLM"的场景（四栏表）：

| 判断条件 | 替代手段 |
|---|---|
| 每次都是同样的步骤？（Same steps every time?） | **写一个脚本（Write a script）**：让 LLM 把代码写好一次，之后只执行 |
| 输入格式固定？（Fixed input format?） | **用规则解析（Parse with rules）**：正则、解析器、模板每次调用零成本 |
| 标签或打分范围很窄？（Narrow label or score?） | **训练一个小分类器（Train a small classifier）**：GBM 或 Jev! |
| 工作流固定、几乎不需要推理？（Fixed workflow, little reasoning?） | **把工作流脚本化（Script the workflow）**：只在需要的步骤调用 LLM |

结论（本部分收束语）：**只有当某一步确实需要推理时，才动用 LLM**（Reach for an LLM only when a step needs reasoning）。

# 二、让智能体更快（Make Your Agent Faster）

更快的智能体通常（但不总是）也更便宜——速度优化与成本优化大量重叠。五个杠杆：加速 LLM 服务、改进编排、加速工具调用、并行化工作、投机动作。

## 完成时间是关键路径，而非所有步骤之和

图示：上排"Serial"（串行）——Queue、Setup、Prefill、Reasoning、Tools、Orch. 依次执行，**时间 ≈ 所有步骤之和**；下排"Parallel"（并行）——Plan 之后 Worker A / Worker B 并行执行再 Merge，**时间 ≈ 关键路径（critical path）**，图中红色标出决定完成时间的那条关键路径。

两个重要警告：

- **更便宜的可能更慢（Cheaper can be slower）**：小模型可能要走更多步。
- **并行可能更贵（Parallel costs more）**：等待减少了，但总 token 更多。

即：省钱手段与提速手段方向可能相反，需要权衡。

## 加速 LLM 服务

**上一节每一个成本技巧同样削减延迟**（Fewer turns → Fewer steps → Fewer tokens → Cheaper serving）。减少轮次、减少步数、减少 token、更便宜的服务（缓存、更小模型）——同一条链路同时改善成本与速度。

## 改进编排（Improve orchestration）

四种手法（四栏表）：

| 异步执行（Async execution） | 持久会话（Persistent sessions） | 流式（Stream） | 同置（Colocate） |
|---|---|---|---|
| 例如：工具调用还在跑时就启动下一步 | 例如：跨 step 保持同一个 shell 或浏览器打开 | 例如：在 LLM 响应完成之前就启动工具调用 | 例如：把工具跑在与模型同一台主机上 |

编排层的等待（空等工具、重启 shell/浏览器、网络往返）常常不产生 token，却拉长关键路径。

## 加速工具调用

前提观察：**构建（builds）、测试（tests）、页面加载（page loads）可能比 model 调用本身还慢**。手段（四栏表）：

| 缓存工具结果 | 更快的硬件 | 更好的工具 | 快速失败 |
|---|---|---|---|
| 重复的读取与搜索命中缓存 | 重计算放到服务器跑，而不是笔记本 | 同一份工作用更快、更便宜的工具；有选择地调用工具 | 让挂死的调用超时 |

**在调模型之前，先测量每个 step 的工具时间**（Measure tool time per step before tuning the model）——瓶颈可能在工具而不在模型。

## 并行化工作（Parallelize work）

图示：Sequential 下 Read file A → Read file B → Read file C 串行进行；Parallel 下三个读取同时进行——**同样的工作，三分之一的等待**（Same work, a third of the wait）。

| 并行工具调用（Parallel tool calls） | 并行子 agent（Parallel sub-agents） |
|---|---|
| 一个 step 内发出多个独立调用 | 拆分独立子任务，最后合并（merge）摘要 |

注意：**只有独立的工作能并行；共享状态需要一步合并（merge step）**。

## 投机动作（Speculative actions）

三步流程：

| 1. 预测（Predict） | 2. 提前执行（Run early） | 3. 比对（Compare） |
|---|---|---|
| 一个便宜模型猜下一个动作 | 主模型思考期间，把猜的动作执行掉 | 把猜的结果与主模型的选择比对 |

两种结局：

- **猜对（Guess matches）**：结果已经就绪，跳过等待。
- **猜错（Guess misses）**：丢弃；代价是一次浪费的调用（the cost is one wasted call）。

**收益条件：猜经常对，且动作可以撤销**（Pays off when guesses are often right and actions can be undone）。

开放问题（open question）：**在 GPU、CPU 与 API 预算受限的情况下，如何调度投机调用，使节省的关键路径时间超过浪费的工作量。**

## 进阶（可略读）：投机什么（What gets speculated）

图示：一张"视野（horizon）从一次调用扩展到整条轨迹"的表格——**投机对象沿五个层级增长**：

| 层级 | 含义 | 代表工作 |
|---|---|---|
| Tool intent（工具意图） | 下一个会来的是哪个工具 | **SPORK** [8] |
| Tool call（工具调用） | 工具及其参数 | **PASTE** [5]、**Speculative Tool Calls** [2] |
| Next action（下一个动作） | 任意动作或 API 响应 | **Speculative Actions** [1] |
| Branches（分支） | 同时走多条可能路径 | **B-PASTE** [6] |
| Trajectory（轨迹） | 多步链，且已提前执行 | **Speculative Macro Commit** [10] |

来源：[1] Speculative Actions（ICLR 2026）· [2] Speculative Tool Calls（arXiv 2025）· [5] PASTE（arXiv 2026）· [6] B-PASTE（arXiv 2026）· [8] SPORK（arXiv 2026）· [10] Speculative Macro Commit（arXiv 2026）。

## 进阶（可略读）：预测从哪来（Where predictions come from）

三种预测来源（三栏表）：

| 基于模型（Model-based） | 自我投机（Self-speculative） | 基于历史（History-based） |
|---|---|---|
| 一个小 draft 模型预测大模型下一步做什么 | 同一个模型早分叉（early fork）预测自己之后的工具调用 | 过去的 trace 预测下一个工具，其参数绑定到最近的结果 |
| Speculative Actions [1]、Speculative Tool Calls [2] | SPORK [8] | PASTE [5]、Speculate with Memory [9] |

两种验证策略：

| 无损（Lossless） | 有损（Lossy） |
|---|---|
| 保留工作前一定先验证 | SPAgent [3] 会跳过部分检查 |

来源：[1] Speculative Actions（ICLR 2026）· [2] Speculative Tool Calls（arXiv 2025）· [3] SPAgent（arXiv 2025）· [5] PASTE（arXiv 2026）· [8] SPORK（arXiv 2026）· [9] Speculate with Memory（arXiv 2026）。

## 两个例子：PASTE 与 SPORK

**PASTE [5]——从历史 trace 预测下一个工具：**

```
search(q)
→ visit(results[0].url)
→ extract(page)
```

一旦 `search(q)` 开始，trace 模式表明下一步是 `visit`。URL 从搜索结果里填入，所以 `visit` 在模型还在生成时就已经跑起来了。

**SPORK [8]——模型预测自己的工具调用：**

```
think: 2,000 tokens …
early probe → search(q)
tool_call search(q): ready
```

工具意图往往在推理早期就清晰可辨：分叉出的 probe 启动被预测的调用，等主模型真正发出 `tool_call` 时，结果已经就绪。

## 循环优化：跑、测、改、再来（Run, measure, change, again）

四步循环（循环执行）：

| 1 · Run and Profile（跑并剖析） | 2 · Measure（测量） | 3 · Change one thing（只改一件事） | 4 · Re-evaluate（复评） |
|---|---|---|---|
| 记录每一次调用、token、工具与等待 | 弄清成本与延迟的来源 | 压缩、路由、缓存或并行 | 同一批任务：成功率、花费、p95 延迟 |

之后 **Repeat**（重复循环）。幻灯片特别强调：**记住这套循环，你的作业 4 要考这个！**（Remember this for your Assignment 4!）

# 三、智能体架构（Agent Architecture）

三种 harness 架构：**Monolithic · Modular · Microkernel**。图示：三张并列的结构图——① Monolithic：所有组件（memory、tools、context、planning、execution）都在一个 agent 运行时内；② Modular：agent 通过标准接口（MemoryProvider、ToolProvider、ContextProvider、SandboxProvider）访问外部组件；③ Microkernel：核心只做协调（state · scheduling · memory），能力由外部服务（Memory、Tools、Context、Sandbox 服务）提供。

**演化方向（Shift）**：职责从智能体中移出去——从代码，到接口，再到服务（responsibility moves out of the agent, from code to interfaces to services）。

## 单体 harness（Monolithic）：一个运行时实现 memory、tools、context、planning 与 execution

代码示例：

```python
class CodingAgent:
    def __init__(self):
        self.memory = Memory()
        self.tools = Tools()
        self.context = ContextManager()
        self.planner = Planner()
        self.executor = Executor()

    def run(self, task):
        while not self.finished:
            a = self.planner.plan(task)
            r = self.executor.execute(a)
            self.context.update(r)
```

| 优点 | 缺点 |
|---|---|
| 实现与调试简单 | 难以替换单个组件 |
| 通信开销最小 | 组件间强耦合（tightly coupled） |
| 内部状态容易共享 | 难以跨 agent 共享基础设施 |
| 执行开销低 | 隔离（isolation）难以强制 |

**关键特征（Key characteristic）**：agent 拥有一切，全部在一个运行时内。

## 模块化 harness（Modular）：agent 仍控制循环，但通过接口访问每个组件

代码示例：

```python
agent = CodingAgent(
    memory_provider=RedisMemory(),
    tool_provider=MCPTools(),
    context_provider=SlidingWindowContext(),
    sandbox_provider=DockerSandbox())
# Docker → Firecracker: swap one provider
```

图示：Monolithic 下 agent 内置 memory；Modular 下 agent 通过 MemoryProvider 接口访问 RedisMemory。

| 优点 | 缺点 |
|---|---|
| 组件容易替换（例如 Docker 换成 Firecracker 只需换一个 provider） | 控制器仍拥有（owns）生命周期 |
| 更好的可测试性与可扩展性 | 协调逻辑变得复杂 |
| 职责分离清晰 | 故障域（failure domains）仍可能共享 |
| 第三方实现即插即用 | 联合调优（joint tuning）需要改控制器代码 |

**关键特征**：一个控制器（controller）通过接口（interfaces）下放（delegates）各能力。

## 智能体微内核（Agent microkernel）：小型运行时负责协调，外部服务提供能力

图示：Agent runtime（只做 state · coordination · scheduling · security）通过标准协议（standardized protocol）连接 Memory service（后端 Database）、Tools service（后端 Tool APIs）、Execution service（后端 Sandboxes）；这些服务可以运行在独立的容器或机器上。

| 优点 | 缺点 |
|---|---|
| 服务独立扩展（scale independently） | 通信开销更高 |
| 更好的故障隔离（fault isolation） | 更多故障模式要处理 |
| 更强的隔离（若被强制执行） | 端到端调试更困难 |
| 共享、集中管理的基础设施 | 需要标准协议与生命周期（lifecycle）管理 |

**关键特征**：运行时负责协调（coordinates）；外部服务提供能力（provide capabilities）。

## 例子：运行一段 Python 代码

图示：三张时序图对比三种架构执行"运行一段 Python 代码"的调用链：

- **① Monolithic**：Agent 直接本地执行 Python（Execute Python locally）——**跳数最少，但隔离难以强制**（Fewest hops; isolation is hard to enforce）。
- **② Modular**：Agent → `SandboxProvider.run(code)` → Docker 沙箱执行并返回——**换的是 provider，不是 agent**（Swap the provider, not the agent）。
- **③ Microkernel**：Agent runtime 发送执行请求 → Execution service 分配沙箱（Allocate sandbox）→ 执行 Python 并返回结果——**执行服务拥有沙箱的分配、隔离与生命周期**。

## 微内核用简单性与低开销换取隔离、共享与规模

三架构对照表（每行一个维度）：

| 维度 | Monolithic | Modular | Microkernel |
|---|---|---|---|
| 设计原则（Design principle） | 全部集成（Everything integrated） | 接口抽象（Interface abstraction） | 最小核心 + 服务（Minimal core + services） |
| 中央控制器（Central controller） | 有 | 有 | 有，但精简 |
| 组件替换（Component replacement） | 困难 | 容易 | 容易（若协议匹配） |
| 执行隔离（Execution isolation） | 可选 | 可选 | 架构层面的强调（Architectural emphasis） |
| 组件部署（Component deployment） | 通常一起部署 | 一起或分开 | 通常独立 |
| 独立扩展（Independent scaling） | 有限 | 可能 | 强 |
| 通信成本（Communication cost） | 低 | 低–中 | 可能更高 |
| 典型用途（Typical use case） | 独立智能体 | 智能体框架 | 多智能体基础设施 |

**匹配（Fit）**：独立 agent 用单体，多智能体基础设施用微内核（monolith for standalone agents, microkernel for multi-agent infrastructure）。

# 四、编码智能体案例研究：八套 harness（The eight harnesses）

八套 harness 总览（两行四列卡片表）：

| Claude Code | Codex CLI | DeepSeek Harness | OpenCode |
|---|---|---|---|
| Anthropic · TypeScript（闭源） | OpenAI · Rust | DeepSeek AI · TypeScript | Anomaly（SST）· TypeScript, Bun |
| 在 Claude 外层的策略层（policy layer）与类型化 hooks | 沙箱优先，申请在后（Sandbox first, ask second） | 一切都是插件，连循环也是（Everything is a plugin, even the loop） | 带瘦客户端的会话服务器（A session server with thin clients） |
| **CC** | **CX** | **DSH** | **OC** |

| Pi | oh-my-pi | OpenClaw | Hermes Agent |
|---|---|---|---|
| Mario Zechner / Earendil · TypeScript | Can Bölük / Stencil Labs · TypeScript + Rust | OpenClaw Foundation · TypeScript | Nous Research · Python |
| 一个可以用 TypeScript 扩展的小核心（A small core you extend in TypeScript） | 接了原生工具与 IDE 的 Pi fork | 面向聊天渠道的助手网关（An assistant gateway for chat channels） | 会给自己写技能的 agent（An agent that writes its own skills） |
| **PI** | **OMP** | **CLAW** | **HM** |

## Codex CLI 独有设计

| 沙箱先于审批（Sandbox before approval） | 遵守文法的补丁（Patches that obey a grammar） |
|---|---|
| 命令在一个无网络访问的沙箱中运行；agent 只有在需要离开沙箱时才请求审批 | 用 Lark 文法（grammar）设定补丁（patch）的外壳（envelope）；agent 分四遍（four passes）匹配 hunk |

## DeepSeek Harness 独有设计

| 循环也是插件（The loop is also a plugin） | 请求来自日志（Requests from the log） | 比较并交换式编辑（Compare-and-swap edits） |
|---|---|---|
| 循环（loop）、适配器（adapters）、工具、日志与审批都是插件；YAML 层可以替换每个插件 | 每个请求都是会话日志的一个冻结视图（frozen view）；harness 只往日志里追加条目 | 如果文件在模型上次读取之后变过，编辑就失败 |

## OpenCode 独有设计

| harness 就是服务器（The harness is a server） | 带尺寸上限的模糊编辑（Fuzzy edits with a size limit） | 每步一个快照（A snapshot at each step） |
|---|---|---|
| TUI、SDK 与 web 应用都使用同一个 OpenAPI HTTP 服务器 | 九个替换器（replacers）从精确匹配到锚点（anchor）匹配逐级放宽；harness 会拒绝过大的模糊匹配 | 一个影子 git 仓库（shadow git repository）让 /undo 能恢复文件，而不只是聊天记录 |

## Pi 独有设计

| 最小核心（A minimal core） | 带"价格检查"的缓存预热（Cache warming with a price check） | 供其他项目使用的库（Libraries for other projects） |
|---|---|---|
| 核心只有四个工具，没有 MCP、子 agent 或审批；扩展（extensions）提供其余一切功能 | Pi 只在预期节省达到 $0.05 或以上时才发送 keep-alive 请求 | pi-ai 在 10 种 wire API 上支持 42 个 provider；另外三个项目在使用 Pi 的代码 |

## oh-my-pi 独有设计

| Hashline 编辑（Hashline edits） | IDE 就在 agent 里（The IDE in the agent） | 特殊上下文方法（Special context methods） |
|---|---|---|
| 每次编辑只给一个 4 位十六进制文件标签（4-hex file tag）加行号；模型不必再敲一遍旧文本 | 一个 shell 为所有调用保持打开；原生工具提供搜索、AST、LSP 与调试器 | snapcompact 把旧历史变成图像；TTSR 在正则匹配时停下来重试 |

## OpenClaw 独有设计

| 带队列车道的聊天网关（A chat gateway with queue lanes） | 压缩前先写记忆（Memory before compaction） | 围栏、污点与哨兵（Fences, taint and sentinels） |
|---|---|---|
| 27 个聊天渠道把消息发送到每个会话的一条车道（lane）；队列模式控制运行期间到达的消息 | 先由一个静默轮次（silent turn）写下带日期的笔记；回忆（recall）同时使用全文检索与向量检索 | 围栏（fences）隔离不可信文本；一次网络读取会"污染"（taints）该轮次；agent 监控密钥哨兵（secret sentinels） |

## Hermes Agent 独有设计

| 会学习的 fork（A fork that learns） | 最早触发压缩（Earliest compaction） | 执行前先落盘（Save before execution） |
|---|---|---|
| 一个后台 fork 检查每个被"轻推"（nudged）的轮次，然后编辑记忆与技能 | 压缩从窗口（window）的 50% 处就开始——八套 harness 中最早的 | agent 在任何副作用发生之前，先把工具调用行写入会话数据库 |

## 下节课（Next class）

（本页无正文内容。）

# 核心要点

1. **成本公式**：Cost = Users × Sessions × Turns × Steps × Tokens × Price。Users/Sessions 随用户增长而 GROW，其余四因子是设计可削减的（SHRINK）。
2. **轮次是平方级因子**：Turn k 重读 1…k−1 的全部历史，总成本随轮次数平方增长；本讲把它列为最强杠杆。
3. **班级数据**：68%→75% 的 Claude Code 会话只有一个 prompt（A1→A2）；每轮步数中位数 3→4，长尾近 1,000 步；主 agent 每步 token 中位数 208K→301K，p90 600K–700K，子 agent 中位数 ~80K、p90 ~200K；~500 步时上下文达 670K/650K。
4. **97.6% 的 token 是缓存读取**（A1）；典型价格比 cache read : input : output = 1 : 10 : 50。
5. **减 turns**：前置规划、结构化任务分解（每个子任务有 done check）、交接前自验证——目标是零用户介入完成。
6. **减 steps**：每次 model 调用都重读全上下文，所以批量独立调用、复用计划/技能、前置加载上下文都能减少调用次数（4 次调用 → 2 次的例子）。
7. **减每步输入 token**：丢弃过期内容、压缩进入的内容（只留错误不留全日志、大输出卸载到文件传路径）、只加载需要的（选择性检索、用子 agent 隔离探索）；留在上下文里的 token 每步重复付费。
8. **减每步输出 token**：提示词约束（≤100 词、只 JSON、不复述、不解释推理）+ API 硬上限（max_tokens=300）+ 只要所需字段的结构化 schema + 按 step 匹配推理力度（lookup 用 low、debug 用 high，reasoning effort / thinking-token budget）；注意推理 token 可能吃光输出上限，且严格格式可能损害推理。
9. **降单价（Claude API 相对基准）**：output 5×、input 1×、batch 0.5×、cached 0.1×、batch+cached 0.05×——维护稳定前缀（system prompt、tools、早期历史）+ 把能等的事（evals、backfills、bulk jobs）走批处理。
10. **模型路由三策略**：一开始选（偏好数据训练的 router，连 agent 角色一起选）、失败后升级（learned scorer / 自验证 / 执行反馈）、每步重路由（按历史与预算，编排器把模型当工具）；难点是一次便宜的规划错误浪费后面很多动作。
11. **每项节省都有反代价**：compaction 导致重读与缓存重写、routing 导致坏计划、subagent 复制上下文、speculation 烧错猜——**净节省 = 毛节省 − 反代价，要在同一批任务上测量**。
12. **预算与停止规则**：示例 $10 / 80 次 model 调用 / 15 分钟工具时间 / 每步 2 次重试；停止条件 = 验证器通过、N 步无新通过测试、同一错误重复、撞限额则带摘要交接；限额取成功任务 p95 的 2 倍；带摘要停止比跑飞更便宜。
13. **不是每步都需要 LLM**：固定步骤 → 脚本化（LLM 只写一次代码）；固定输入格式 → 正则/解析器/模板零成本；窄标签/打分 → 训练 GBM 等小分类器；固定低推理工作流 → 脚本化、只在需要推理的步骤调 LLM。
14. **速度 = 关键路径，不是步骤之和**；并行使时间 ≈ 关键路径，但"更便宜的可能更慢"（小模型多走步）、"并行可能更贵"（总 token 更多）。
15. **提速五杠杆**：加速 LLM 服务（成本技巧同时降延迟）、改进编排（异步执行、持久 shell/浏览器、流式提前启动工具、模型与工具同置）、加速工具（缓存工具结果、服务器跑重计算、更好的工具、超时快速失败；先测每步工具时间）、并行（并行工具调用、并行子 agent + 合并步骤）、投机动作。
16. **投机动作**：便宜模型猜 → 主模型思考期间提前执行 → 比对；猜对省等待、猜错浪费一次调用；收益条件是猜常对且动作可撤销。投机对象从 tool intent（SPORK）、tool call（PASTE、Speculative Tool Calls）、next action（Speculative Actions）、branches（B-PASTE）到整条 trajectory（Speculative Macro Commit）；预测来源分模型/自我/历史三类；无损一定验证，有损（SPAgent）跳检查。
17. **循环优化**：Run and Profile → Measure → Change one thing（compaction / routing / caching / parallelism）→ Re-evaluate（同批任务的 success、spend、p95 latency）→ 重复——作业 4 要考。
18. **三种 harness 架构**：Monolithic（一个运行时拥有一切；简单、低开销，但难替换、难隔离、难共享）→ Modular（控制器经接口下放；组件易换，如 Docker→Firecracker 换 provider；协调变复杂、故障域仍共享）→ Microkernel（核心只做 state/coordination/scheduling/security，能力来自外部服务；隔离、共享、规模强，但通信成本与故障模式更多）。匹配：独立 agent 用单体，多智能体基础设施用微内核。
19. **八套 harness 一句话画像**：Claude Code = Claude 外层策略层 + 类型化 hooks；Codex CLI = 无网沙箱先跑、出沙箱才审批 + Lark 文法约束补丁（四遍匹配 hunk）；DeepSeek Harness = 循环/适配器/工具/日志/审批全是插件（YAML 可替换）+ 请求是日志冻结视图 + CAS 式编辑；OpenCode = TUI/SDK/web 共用一个 OpenAPI 会话服务器 + 九级模糊编辑带尺寸上限 + 影子 git 每步快照支持 /undo 恢复文件；Pi = 四工具最小核心（无 MCP/子 agent/审批）+ 预期省 $0.05 以上才发 keep-alive + pi-ai 支持 42 provider / 10 wire API；oh-my-pi = 4-hex 文件标签 + 行号的 Hashline 编辑 + 常驻 shell 与 AST/LSP/调试器原生工具 + snapcompact 旧历史转图像；OpenClaw = 27 个聊天渠道、每会话一条队列车道 + 压缩前静默轮次写带日期笔记（全文+向量双检索）+ 围栏/网络读取污点/密钥哨兵；Hermes Agent = 后台 fork 检查每个 nudge 轮次并编辑记忆与技能 + 窗口 50% 就开始压缩（八者最早）+ 副作用发生前先把工具调用写入会话数据库。
20. **安全与诚信红线**：不得篡改 Claude Code 会话日志（违反学术诚信）；OpenClaw 的 fences/taint/sentinels 与 Codex 的沙箱先审批都是把"不可信输入/动作"关进笼子的代表设计。
