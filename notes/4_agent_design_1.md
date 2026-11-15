# 第4讲：智能体设计 I（上下文管理与工具设计）

> 原讲次：*Agent Design I: context management and tool design*，Harvard CS2680《Modern AI Systems: Agents and System Optimizations》（Juncheng Yang，cs2680.com）

## 本讲概览

本讲是智能体设计系列的第一讲，围绕一个核心论点展开：**智能体 = 模型 × 执行框架（Agent = Model × Harness）**——模型能力决定上限，而 harness（循环、工具、提示、上下文管理、失败处理）决定实际表现。全讲分三块：先给出 ReAct 循环与 agent loop 的代码实现，讲清「一个 agent 就是模型加一个循环」；接着系统比较四类工具设计——搜索/读取（glob/grep、语义索引、外部信号、LSP）、编辑（整文件重写、unified diff、find/replace、AST 编辑）、执行（shell 及其风险与防护），并总结工具设计最佳实践；然后进入上下文管理，从 prompt engineering 讲到 context engineering：上下文是有限资源，用四个杠杆（admission 准入、offloading 卸载、transformation 转换、compaction 压缩）管理，并归纳上下文失败的五种模式（poisoning、distraction、confusion、clash、drift）。最后用 SWE-bench 数据说明：只改 harness 就能让准确率约翻倍。

## 课程信息（Logistics）与今日计划

- Assignment 1 本周日截止。
- 分享你的 repo：填写 Google form；Assignment 1 sharing 报名本周四。
- 课程主页：Harvard Madsys，course.agentic-system.org。

今日计划（Plan for today）：

- Agent loop（ReAct）与工具设计（Tool designs）
- 上下文管理（Context management）：prompt engineering 与 context engineering

## The ReAct 循环

ReAct（Reasoning + Acting，出自论文 [arXiv:2210.03629](https://arxiv.org/pdf/2210.03629)）是智能体最基础的循环模式：**在同一个循环里既推理又行动**。每个循环迭代由三要素组成：

- **Thought（思考）**：我已知什么、缺什么、下一步做什么？模型先梳理当前状态与计划。
- **Action（行动）**：向环境发出一次结构化的调用（tool call），由环境实际执行。
- **Observation（观察）**：环境用事实作答，把结果放回上下文。

幻灯片用对比说明为什么「三者缺一不可」：

- **只用 Reason**：没有任何东西校验推理，小误差会复利式累积，最终变成自信的幻觉。
- **只用 Act**：工具调用背后没有计划，模型会原地打转、重复自己。
- **ReAct**：thought 引导下一个 action，observation 纠正下一个 thought——思考与观察互相校准。
- 如此**循环（Repeat）**，直到 observations 真正回答了问题，或某个停止规则（stopping rule）结束运行。

图示：三栏分别对应 Thought / Action / Observation 三个阶段，下方用「Reason only / Act only / ReAct / Repeat」四种组合的优劣对比说明完整的 ReAct 循环才是稳健的做法。

## The Agent Loop（用代码写出智能体循环）

幻灯片给出一个最小 agent harness 的伪代码——它展示了整个循环的工程形态：

```python
messages = [
    {"role": "system", "content":
        "Solve the task using the tools."},
    {"role": "user", "content": user_request},
]
for step in range(MAX_STEPS):
    response = call_model(messages, tools)
    messages.append(response.message)
    if response.final_answer:
        return response.final_answer
    for call in response.tool_calls:
        args = validate(call.arguments)
        result = execute_tool(call.name, args)
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": serialize(result),
        })
raise RuntimeError(
    "Agent exceeded its step limit")
```

代码要点：

- 上下文就是一个不断追加的 `messages` 列表：system 提示 + 用户请求，随后模型回复、工具调用、工具结果逐条 `append` 回去——**历史就是上下文本身**。
- 每个 `MAX_STEPS` 内先调用模型；若模型给出 `final_answer` 就直接返回，否则遍历所有 `tool_calls`：先 `validate` 参数，再 `execute_tool`，最后把 `serialize(result)` 作为 `role: "tool"` 的消息写回。
- 超过 `MAX_STEPS` 就抛出 `RuntimeError("Agent exceeded its step limit")`——停止规则必须显式实现，否则循环可能永不终止。

配套的第二张幻灯片把循环拆成五个阶段，并标注「作为 agent harness 设计者，你要做什么」：

| 循环阶段 | harness 设计者的工作 |
|---|---|
| User request（收到用户请求） | Write tool definitions（写工具定义） |
| Model（调用模型，产出 final answer 或 tool call） | Assemble the context（组装上下文） |
| Next action?（决定是否调用工具） | Validate request, check permission and run it（校验请求、检查权限并执行） |
| Execute tool（执行工具） | Optionally process the result（按需处理结果） |
| Return tool result（把结果放回上下文） | and manage context（并管理上下文） |

图示：左半部分是循环流程（User request → Model →「final answer / Next action? tool call」→ Execute tool → Return tool result → Return answer），右半部分把 harness 设计者的五项职责与循环各节点对应起来。

这张表点出本讲的工具设计与上下文管理两块内容在 harness 中的位置：**工具定义与执行**对应「Next action? / Execute tool」，**上下文组装与管理**贯穿「Model / Return tool result」。

## Coding Agent 的组成

幻灯片提出 coding agent 的三个组成部分——「三个组件、同一个上下文窗口，必须一起设计」：

1. **Model + agent loop（模型 + 智能体循环）**：LLM 提出一个行动、看到结果、重复，直到完成。→ *An agent is a model plus a loop*（一个 agent 就是模型加一个循环）。
2. **Tools and guardrails（工具与护栏）**：search、read、edit、run tests 和 shell——全部位于 permissions（权限）、sandboxing（沙箱）和 approval（审批）之后。→ *Tools set capability; guardrails keep it safe*（工具划定能力上限，护栏保证安全）。
3. **State: context and memory（状态：上下文与记忆）**：此刻窗口里装了什么，加上 agent 在步骤之间向前携带了什么。→ *Assemble it; keep what outlives the turn*（组装上下文；保留那些比单个 turn 活得更久的东西）。

强调：三者共享同一个 context window，因此任何一块的设计都会影响另外两块，不能孤立设计。

## 工具设计（Tool Design）

本节以一系列「举手打分」提问（Hands up = score）展开：应该给 agent 提供什么工具？搜索/读取（Search / Read）、编辑/写入（Edit / Write）、执行（Execution）、其他（Others）。

### 搜索与读取：如何找到相关代码？

#### glob 与 grep：词法搜索

- agent 直接循环调用 `ls`、`glob`、`grep`——**没有任何东西需要构建或保持同步**，永远反映仓库的实时状态（live repo）。
- 代价：每次搜索都烧 turn 和上下文；词法匹配（lexical matching）会漏掉换一种说法的等价代码（paraphrase）。
- 示例——任务「fix the login timeout」：
  1. `grep -rn "timeout" src/` → 37 个命中、分布在 12 个文件；
  2. `glob src/**/auth/*.ts` → 缩小到 `auth/retry.ts`；
  3. `read auth/retry.ts` → 看到 `RETRY_MS = 500`，打补丁。

图示：三步流水线（grep → glob → read + patch），每步标注命令与结果，展示词法搜索靠「逐步缩小范围」收敛到目标文件。

#### 语义搜索（Semantic search）

- **Semantic（语义）**：把代码切块（code chunks）做 embedding，按含义检索；
- **Structural（结构）**：文件树加上按重要性排序的符号（Aider 的 repo map，仓库地图）；
- 查询时很快；代价在**构建索引与重新同步索引**（仓库变了索引要跟着更新）。
- 示例——「where do we rate-limit?（我们的限流在哪里做的？）第一次查询就返回 `throttle.ts`。

图示：左为 embedding search——查询向量在向量空间中靠近语义相同的 chunk（「同样的含义、不同的措辞——向量落在彼此附近」）；右为 structural search 的 repo map，例如：

```
aider/coders/base_coder.py:
  class Coder:
    def apply_updates(self)
aider/commands.py: class Commands
```

即文件、类、函数签名的按秩排序大纲（ranked outline of files, classes and signatures）。

#### 外部信号（Extrinsic signals）

- 来源在源码之外的证据：stack trace（堆栈跟踪）、failing tests（失败的测试）、git history（版本历史）。
- 调试时这是**精度最高**的信号；但它只在该信号存在时才帮得上忙。
- 示例——checkout 时的崩溃报告：
  1. 读信号：stack trace 指向 `cart.ts:88`，共 3 个栈帧（frames）被命名；
  2. 打开这些栈帧：`read tax.ts:20-60`，看到 `applyTax` 里的 rounding（取整）逻辑；
  3. 打补丁 + 重跑：`pytest tests/tax.py` → 转绿，**全程没有用任何搜索**。

图示：三步流水线（read the signal → open those frames → patch + re-run），展示堆栈跟踪如何把搜索成本降为零。

#### 语言服务器（Language server protocol, LSP）

- 直接查询**编译器的索引**：definitions（定义）、references（引用）、symbols（符号）、types（类型）。
- 能解析 grep 只能瞎猜的东西：import 别名、重载（overloads）、重命名（renames）。
- 代价：每种语言要跑一个**活着的服务器**；冷启动慢。
- 示例——把 `charge()` 重命名为 `capture()`：
  1. 找引用：`textDocument/references` → 42 个调用点、7 个文件；
  2. 重命名符号：`textDocument/rename` → 别名 import 也被包含在内；
  3. 验证：type check → 无未解析符号（no unresolved symbols）。

#### 四种搜索/读取方式对比

| Approach（方式） | Finds code by（依据什么找代码） | Best when（何时最佳） | Main cost（主要代价） |
|---|---|---|---|
| glob / grep | literal names and paths（字面名称与路径） | 名称已知或可猜测 | 每次搜索烧 turn 和上下文 |
| Semantic index（语义索引） | meaning of embedded chunks（embedding 块的含义） | 措辞与代码对不上时 | 构建与重新同步索引 |
| Extrinsic signals（外部信号） | traces, failing tests, git history（堆栈、失败测试、git 历史） | 报告已经指向了代码 | 只对部分任务存在 |
| Language server（语言服务器） | the compiler's symbol graph（编译器符号图） | 编辑必须跟随引用时 | 每种语言一个活服务器 |

实践结论（幻灯片原话）：**先上 grep；当名称猜不出来时，再上索引或 LSP**（In practice — start with grep; reach for an index or LSP when names run out）。

### 编辑工具：agent 如何改代码？

#### 整文件重写（Whole-file rewrite）

- 模型重新生成整个文件，工具直接覆盖。
- 优点：不存在会写错的 patch 语法——每个编辑都干净地应用成功。
- 代价：**输出量随文件规模线性增长**（token 成本高）；未改动的代码也可能在重新生成中悄悄漂移（drift）。
- 示例——给 API client 加重试：`read client.ts`（120 行进上下文）→ `write client.ts`（整文件，只改了 4 行）→ 与上一版 diff，一次成功。

#### unified diff / patch

- 模型发出补丁，由独立工具应用（如 `git apply`）。
- 紧凑、可审查，而且是**人类与 CI 已在用的格式**——生态现成。
- 代价：当行号或上下文发生漂移时，hunk 应用会失败。
- 示例——在两个文件里调高重试上限：先 `read client.ts, api.ts` 拿到行号 → 发出补丁（`@@ -41,3 +41,3 @@`，6 行、两个 hunk）→ `git apply patch.diff`，两个 hunk 全部应用成功。

#### 查找替换（Search and replace）

- 模型给出精确的锚点字符串 + 替换内容。
- 输出量只与**改动本身**成比例，与文件大小无关（token 最省）。
- 代价：锚点不唯一（ambiguous）、过期（stale）或空白符对不上（whitespace-off）时失败。
- 示例——把重试次数调大：`grep -n "retries = 3"` 定位到唯一匹配 → 一次替换 `retries = 3 → 5`（不调用、不重写）→ 读回该代码块验证，文件其余部分原封不动。

#### 结构化 / AST 编辑（Structured / AST edits）

- 模型只对符号命名一个操作：rename（重命名）、add parameter（加参数）等。
- 对格式变化免疫（formatting-immune）；**在构造上不可能产生非法语法**（valid by construction）。
- 代价：每种语言都要专门工具链；能表达的编辑种类有限。
- 示例——给 `fetchUser()` 加一个 timeout 参数：命名操作 `add_param(fetchUser)`（timeout，默认 5s）→ 工具重写签名**以及全部 18 个调用方** → parse + type check，构造上必然合法。
- 延伸阅读（幻灯片给出）：抽象语法树视频 [youtube.com/watch?v=lCrC-qojPpU](https://www.youtube.com/watch?v=lCrC-qojPpU)；语言服务器原理 [pierce.dev/notes/how-language-servers-work](https://pierce.dev/notes/how-language-servers-work)。

#### 编辑方式 2×2 对比（Token cost × Robustness）

幻灯片用一个二维矩阵总结——横轴是 **token cost（token 成本）**，纵轴是 **robustness（稳健性：编辑是否落在它该在的地方）**：

| 方式 | 弱点 |
|---|---|
| Whole-file rewrite（整文件重写） | 长文件上会发生漂移（drifts on long files） |
| Unified diff | 旧行号/上下文会导致应用失败（breaks on stale lines） |
| Search / replace block | 需要精确且唯一的匹配（needs an exact, unique match） |
| Structured / AST edit | 语言覆盖有限（limited language coverage） |

四种方式各有取舍：没有全能选手，harness 往往要组合提供。

### 执行工具：本质上就是一个 shell

幻灯片称 shell 是**最强大也最危险**的工具，危险来自四个属性：

- **Composition（可组合）**：一次调用可以串联、过滤、循环、重试——表达力极强。
- **Reach（触达范围）**：文件系统、网络、包管理器、已安装的二进制文件，全能触及。
- **Persistence（持久性）**：文件与进程的生命周期长于单次调用。
- **Blast radius（爆炸半径）**：shell 能做什么，agent 就能做什么。

#### 执行工具必须想清楚的事

- **Isolation（隔离）**：代码在哪里运行、能触达什么。
- **Failure signal（失败信号）**：错误必须是 agent 真正能据此行动的信息（而不是模糊的退出码）。
- **Output（输出）**：够用但不过量（呼应上下文管理：工具输出也是上下文）。
- **Duration（时长）**：长时运行与后台进程如何处理。
- **Budgets（预算）**：何时停止重试、把控制权交还。

#### 另外五种常用工具

- **A. Memory and notes（记忆与笔记）**：把发现写入文件——计划能在 compaction 之后存活。
- **B. Subagents and delegation（子智能体与委派）**：探索性搜索返回一个短名单（shortlist），而不是 40 个文件读取记录。
- **C. Web search and fetch（网络搜索与抓取）**：先读已安装的源码，再上网。
- **D. Browser and visual feedback（浏览器与视觉反馈）**：对渲染结果截图并回喂给模型。
- **E. Asking the user（询问用户）**：一次廉价的提问，胜过一次自信的错补丁（a confident wrong patch）。

### 工具设计最佳实践（Tool design best practices）

- **Few, orthogonal tools（少而正交）**：功能重叠的工具会让模型在多个工具之间犹豫不决（dither）。
- **Purpose-built, not generic（专用而非通用）**：`search_orders(customer_id)` 优于裸的 `run_sql` 工具。
- **Token-cheap output（token 便宜的输出）**：截断、分页、摘要——**工具设计就是上下文设计**（tool design is context design）。
- **Errors that teach（会教学的错误）**：返回修复提示（the fix hint），而不是一句「invalid argument」。
- **Idempotent by default（默认幂等）**：任何时候重试都安全。

### 我们能不能只提供一个 shell 工具？

幻灯片给出 SWE-agent 的实验结果（在 GPT-4 上，无专用编辑器）：

| 编辑器配置 | 得分 |
|---|---|
| Purpose-built SWE-agent…（专用编辑器） | 18.0% |
| Full interaction history（完整交互历史） | 15.0% |
| Full-file view（整文件视图） | 12.7% |
| Shell only（只有 shell） | 11.0% |
| No specialized editor（无专用编辑器） | 10.3% |

结论方向明确：只给 shell 不是最优解——专用编辑器显著更好。幻灯片原话把完整结论留给了作业：**「Find out when you work on the assignment!（做作业的时候自己得出完整结论！）」**

## 上下文管理（Context Management）

本节从 prompt engineering 讲到 context engineering，最后落到「Agent = Model × Harness」。

### 从 Prompt Engineering 到 Agent Systems

讲师先自嘲：「人们热衷于造词。我用这些词是为了让你们见到它们时知道含义，但这不代表我同意或喜欢它们。」随后给出一个时间线（*From Prompts to Agent Systems*）：

| 时期 | 术语 | 核心问题 | 关注内容 |
|---|---|---|---|
| 2023–2024 | Prompt Engineering（提示工程） | 「我们应该如何指示模型？」 | 措辞、示例、输出格式 |
| 2025–2026 | Context Engineering（上下文工程） | 「模型应该看到什么？」 | 检索（retrieval）、记忆（memory）、历史（history）、压缩（compaction） |
| 2026 | Harness Engineering（执行框架工程） | 「智能体应该如何运转？」 | 循环（loop）、工具（tools）、沙箱（sandbox）、重试（retries）、停止（stopping） |
| Now → Next | Goal Engineering（目标工程） | 「什么才算成功？」 | 目标（objectives）、判据（criteria）、约束（constraints）、权衡（tradeoffs） |

趋势：优化对象从「措辞」→「模型所见」→「整个 agent 系统」→「目标与判据」逐层上移；本讲覆盖前两列。

### Prompt Engineering

幻灯片列出八种技术：Zero-shot、Few-shot、Role & persona、Chain-of-thought、Tree-of-thoughts、Self-consistency、Prompt chaining、Meta prompting。每种都按「示例 + 何时使用 + 何时该换下一种」三栏讲解。

#### 1. Zero-Shot：只给指令

- 示例（工单分类）：

  ```
  You are a support triage assistant.
  Classify the ticket as one of:
  billing | bug | feature | other
  Reply with JSON only: {"label": ...}
  If unclear, use "other".

  Ticket: "Crashes when I export a PDF."
  → {"label": "bug"}
  ```

- 何时使用：任务常见且广为人知；格式用文字就能说清。
- 何时该升级：**规则是隐性知识（tacit）时 → few-shot**。

#### 2. Few-Shot：指令 + 示例

- 示例：指令「Classify the ticket. Reply with JSON only.」加三个示范：

  | 输入 | 输出 |
  |---|---|
  | "Charged twice this month." | → `{"label": "billing"}` |
  | "Can you add dark mode?" | → `{"label": "feature"}` |
  | "asdfgh" | → `{"label": "other"}` |
  | "Crashes when I export a PDF." | → ? |

- 何时使用：**输出形状不寻常**（模型光看指令猜不准格式）；**规则「展示」比「说明」更容易**时。
- 何时该升级：任务需要多步推理 → chain-of-thought。

#### 3. Role & Persona：给一个角色

- 示例：

  ```
  You are a senior SRE reviewing a
  postmortem for an exec audience.
  Flag evidence gaps; never speculate.
  Be direct: at most five bullets.
  → "Timeline omits the 04:12 alert
     ack — evidence gap, not a cause."
  ```

  用角色引导行为：资深 SRE 评审给高管看的复盘，只标记证据缺口、绝不猜测、最多五条要点。
- 何时使用：**语气或判断力（judgement）重要**；受众明确特定。
- 何时该升级：需要多步推理 → chain-of-thought。

#### 4. Chain-of-Thought（CoT）：把步骤显式化

- 示例：

  ```
  Work through it in numbered steps,
  then end with: ANSWER: <value>
  Q: 3 features/week for 4 weeks,
  then 5/week for 2 weeks. Total?

  1. 3 × 4 = 12
  2. 5 × 2 = 10
  3. 12 + 10 = 22
  ANSWER: 22
  ```

  原则：**先推理步骤、后给答案**（Reasoning steps first, answer last）。
- 何时使用：任务确实有多个步骤；错误来自跳步（skipped work）。
- 何时该升级：存在多条可行路径 → tree-of-thought。

#### 5. Tree-of-Thought（ToT）：分支、打分、剪枝

- 示例：「Propose 3 ways to cut checkout latency. Score each 1-5 on impact and effort, then expand the best.」

  | 路径 | Impact（1-5） | Effort（1-5） |
  |---|---|---|
  | A cache warm-up（缓存预热） | 3 | 2 |
  | B drop 3rd-party（去掉第三方调用） | 5 | 4 |
  | C lazy-load asset（资产懒加载） | 4 | 1 |

  决策：展开 C、再展开 B，剪掉 A。
- 何时使用：**多条路线都貌似可行**，且你能**廉价地给它们打分**。
- 何时该升级：只有一个正确答案 → self-consistency。

#### 6. Self-Consistency：多次采样、投票

- 示例：同一提示采样 5 次（T = 0.7），问题「Is this invoice a duplicate?」→ 结果 `yes | yes | no | yes | yes` → 多数决 **yes（4/5 = 0.8）**。规则：阈值 0.8 达标 → 直接回答；若只有 3/5，**转人工**。
- 何时使用：存在唯一正确答案；**一次错判代价很高**。
- 何时该升级：工作可拆成可分离的阶段 → prompt chaining。

#### 7. Prompt Chaining：一次调用干一件事

- 示例（三阶段，交接处做校验）：
  - Stage 1 extract：in: email text → out: `{vendor, amount, date}`
  - Stage 2 validate + enrich → out: `{..., vendor_id}`
  - Stage 3 draft reply → out: `{subject, body}`
  - 任何阶段 schema 校验失败 → **只重试该阶段**（retry that stage only）。
- 何时使用：工作可拆成阶段；每阶段输出都可校验。
- 何时该升级：你要调优的正是提示本身 → meta prompting。

#### 8. Meta Prompting：让模型自己写提示

- 示例：「Here is my prompt, 10 test cases and the 3 it fails. Rewrite the prompt to fix those 3 without breaking the other 7. Return only the new prompt.」→ v2 加了一条显式的拒绝规则（refusal rule），eval set 上 **8/10 → 10/10**。
- 何时使用：**手里有评分用的 eval set**；提示本身就是被调优的对象。
- 何时该升级：收益停滞 → 回头重新审视技术选型。

#### 如何选择正确的技术

幻灯片把八种技术归成三档，给出决策顺序：

- **Start simple（从简单开始）**：
  - Zero-shot —— 任何常见任务的基线；
  - Few-shot —— 输出形状不寻常、或规则是隐性知识；
  - Role & persona —— 语气或判断力重要。
- **Add reasoning（加推理）**：
  - Chain-of-thought —— 任务需要多步推理；
  - Tree-of-thought —— 有多条值得打分的路线；
  - Self-consistency —— 问多次、取多数票。
- **Engineer the system（把系统工程化）**：
  - Prompt chaining —— 可分离的阶段、可校验的交接；
  - Meta prompting —— 提示本身就是交付物。

#### 有些技术已经过期了

幻灯片专门用一页强调：**「Some of the techniques are already expired（有些技术已经过期了）」**——哪些技术在新模型上已经没用了？「Find out yourself in assignment!（做作业时自己发现！）」

#### 提示设计的四条最佳实践

1. **Start simple, then iterate**：从简单开始再迭代——只在需要时才加上下文（add context only when you need it）。
2. **Partition into sections**：分节组织——Context、instructions、tools、output spec；顺序为**指令、分隔符、数据**（Instruction, delimiter, data — in that order）。示例提示：

   ```
   ### Instruction ###
   Translate the text below to Spanish:
   Text: "hello!"
   → 输出：¡Hola!
   ```

3. **Be specific and concise**：具体而简洁——**花哨的措辞一分钱都不值**（Clever phrasing buys nothing）。
4. **Split big tasks into subtasks**：大任务拆子任务——不要前置复杂度（don't front-load complexity）。

底部提示：**提示建议是模型相关的（model-specific）——每次换模型都要重新调优。**

### Context Engineering

#### Karpathy 的定义

> "Context engineering is the delicate art and science of filling the context window with just the right information for the next step"
> —— Andrej Karpathy（Karpathy, X (2025)，x.com/karpathy/status/1937902205765607626）

即：上下文工程是「往上下文窗口里放进下一步恰好需要的那些信息」的精微艺术与科学。

#### 上下文是有限资源（Context is a finite resource）

| 维度 | 机制 | 后果 |
|---|---|---|
| **Cost（成本）** | 每一步都重新发送整个窗口 | 每一轮都要再付一次钱 |
| **Latency（延迟）** | 更大的 prompt 需要更长的 prefill 和 decode | 每个 turn 循环都更慢 |
| **Attention（注意力）** | 窗口越满，回忆越淡；中间部分最容易被漏掉 | **更多上下文 ≠ 更好的答案** |

#### 长度与位置都会伤准确率

「Accuracy decays as input grows, and it also depends on where in the window the answer sits（准确率随输入增长而衰减，且取决于答案在窗口中的位置）。」幻灯片给出两张图：

- 左图：准确率 vs **input tokens in context**，两条曲线 **Simple lookup**（简单查找）与 **With distractors**（带干扰文档）——随 token 数增长，准确率从 100% 一路下降，标注数值包括 100%、76%、73%、61%、59%、55%、46%。
- 右图：准确率 vs **答案在 20 个文档中的位置**（1st、5th、10th、15th、20th）——位置越靠中间/靠后准确率越低，标注数值包括 76%、71%、59%、55%、61%、46%。

来源：**Context Rot（Chroma）**；**Liu et al., "Lost in the Middle," TACL 12 (2024)**。含义：上下文越长、关键信息越靠中间，模型越容易漏——这是后面「压缩/转换」类杠杆存在的实证基础。

图示：两张折线图，分别展示「准确率随上下文 token 数增长而衰减」与「准确率随答案位置（第 1 → 第 20 个文档）变化」，后者呈现中间位置最弱的衰减形态。

#### 上下文窗口的解剖（Anatomy of the context window）

幻灯片给出一份单 agent turn 的示例 token 预算（illustrative token budget）：

| 组成 | 说明 | 预算 |
|---|---|---|
| System prompt | 角色、规则、输出契约——静态、始终常驻 | ~2K |
| Tool definitions | 每个 schema 都花 token，用不用都算 | ~6K |
| Retrieved context | 按需拉入的文件、搜索命中、文档 | ~25K |
| Message history | 用户 + LLM + 工具调用结果；turn 加原始工具输出——**增长最快** | ~80K and growing |
| Project environment | 刻意读回的草稿纸（scratchpads）与笔记 | ~8K |
| （Headroom） | 为模型自己的回复预留的 token | — |

由此引出核心问题：**当上下文变得太大时该怎么办？（What to do when context becomes too large?）**

#### 管理上下文窗口的四个杠杆

**Admission（准入）→ Offloading（卸载）→ Transformation（转换）→ Compaction（压缩）**，谱系从「预防性、无损」走向「有损、不可逆」（Preventive and lossless → lossy and irreversible）。优先级越靠前，越应该优先使用。

##### 杠杆一：Admission（准入）——守住进入窗口的东西

口号：**在门口整形（shape at the door）**。案例：网页抓取后把原始 DOM 直接传入 = **48,000 tokens**；整形后只留价格与标题 = **900 tokens**——**小 98%，答案不变**。四个手段：

| 手段 | 做法 |
|---|---|
| **Targeted retrieval（定向检索）** | 查询收窄；取字段，不取整篇文档（fetch fields, not docs） |
| **Tool output shaping（工具输出整形）** | 丢掉 DOM，只留抽取出的内容（drop the DOM, keep the extract） |
| **Truncation（截断）** | 只有在整形都搞不定时才用大小上限兜底（cap size only when shaping cannot） |
| **Isolation（隔离）** | 把原始大载荷交给 subagent 处理，窗口里只进结论（hand the raw payload to a subagent） |

图示：左为「Before」——Prefix + Raw DOM + Task work 几乎塞满窗口（48,000 tokens）；右为「After」——Prefix + Extract + Work + Headroom，900 tokens，回答相同。

##### 杠杆二：Offloading（卸载）——需要时才加载

口号：**保持可检索，而不是常驻**（keep it retrievable, not resident）。案例：60 个工具 schema 常驻 = **42,000 tokens**；换成索引 + 按需加载 3 个 = **3,100 tokens**——**小 93%，60 个仍可全部触达**。五个手段：

| 手段 | 做法 |
|---|---|
| **Progressive tool definition（渐进式工具定义）** | 只在需要时加载 schema |
| **Tool search（工具搜索）** | 保留一份索引，按需取回（fetch on demand） |
| **Tool output offload（工具输出卸载）** | 返回一个句柄（handle），需要时再载入 |
| **Externalised task list（外置任务列表）** | 计划放在磁盘上 |
| **Persistent memory（持久记忆）** | 笔记写到外部，只保留一个小索引 |

图示：左「Before」——Prefix + 60 tool schemas + Task work（42,000 tokens）；右「After」——Prefix + Index + 3 schemas + Work + Headroom（3,100 tokens）。

##### 杠杆三：Transformation（转换）——有选择地丢弃历史

案例：每个工具结果都保留 = **96,000 tokens**；只保留每个对象最新状态 = **24,000 tokens**——**小 75%，且没有任何摘要**（nothing summarized，因此仍是无损/低损操作）。三个手段：

| 手段 | 做法 |
|---|---|
| **Deduplication（去重）** | 每个对象只留最新状态，清掉过期快照（stale snapshots） |
| **Observation masking（观察掩码）** | 剥掉 N 步以前的工具结果 |
| **Sliding window（滑动窗口）** | 只保留最近若干 turn 和开头 |

图示：左「Before」——System prefix + 大量 Stale snapshots + Recent（96,000 tokens）；右「After」——System prefix + Kept + Recent + Headroom（24,000 tokens）。

##### 杠杆四：Compaction（压缩）——LLM 是最后手段

「LLM as the last resort」：只有前面三个杠杆都不够用，才动用模型做有损压缩。三个手段：

| 手段 | 做法 |
|---|---|
| **Rolling summary（滚动摘要）** | 边进行边摘要旧的工具结果 |
| **Full summary（整体摘要）** | 到达上限时重写整条历史 |
| **Auto memory（自动记忆）** | 把关键事实持久化到窗口之外 |

⚠️ **WARNING（三条铁律）**：

- **Reserve headroom for output**：为模型的输出预留空间（否则压缩完也没法回答）；
- **Preserve the system prefix**：系统前缀原样保留；
- **Re-inject critical facts after**：压缩后把关键事实重新注入。

图示：「At the limit」时 System prefix + Old tool results + Recent 把窗口塞满；经 LLM compaction 后变为 System prefix + Summary + Recent + Headroom——headroom 恢复，模型又能继续工作。

#### 上下文失败的五个方式（Five ways context fails）

「Name the failure and the fix becomes obvious（给失败命名，解法就显而易见）。」五种失败模式（引自 Breunig, *How Contexts Fail and How to Fix Them* (2025)）：

| 失败模式 | 含义 |
|---|---|
| **Poisoning（投毒）** | 一次幻觉进入窗口，之后被当作事实引用 |
| **Distraction（分心）** | 历史越积越长，agent 开始模仿自己过去的行动 |
| **Confusion（困惑）** | 无关的工具和文档把答案带偏 |
| **Clash（冲突）** | 新信息与旧信息矛盾，两者同时留存、未决 |
| **Drift（漂移）** | 真实目标被埋没，被一个邻近的子目标替换 |

#### Agent = Model × Harness

本节收束点：**「Model capability sets the ceiling; Harness determines realized performance（模型能力设定上限；harness 决定实际表现）」**——同一个模型，换 harness，结果可以差出数倍。

证据（Lewis, S., *Same Model, Different Harness: Different Coding-Agent Results* (arXiv:2608.26218, 2026)）：**Changing the Harness Improves Accuracy by 2×**

| Benchmark | Basic harness | Improved harness | What changed（改了什么） |
|---|---|---|---|
| SWE-bench Verified | 43 / 169 | 72 / 169 | 旧工具输出被压缩（old tool outputs compacted） |
| SWE-bench Pro | 31 / 316 | 72 / 316 | 近期观察保持可见（recent observations kept visible）；检测重复与停滞（repetition and stalls detected）；卡住时干预（interventions when stuck） |

（「What changed」四点是改进版 harness 的共享清单：① 旧工具输出压缩；② 近期观察保持可见；③ 检测重复与停滞；④ 卡住时干预。）

结论：**许多看似「模型失败」的现象，其实是上下文与控制循环的失败**（Some apparent "model failures" are actually context- and control-loop failures）。而模型本身没有变——变的只是 harness。

幻灯片最后把实验权交给学生：「**Experiment yourself in assignment（在作业里自己实验）**——Agent loop、prompt、tool、context management、failure handling **all matter!（全都重要！）」**

## 下次课程预告（Next class）

- Agent design II（智能体设计 II）
- Agent (persistent) memory（智能体持久记忆）
- Cost-effective agents（高性价比智能体）
- Safety and security（安全与保密）
- Multi-agent designs（多智能体设计）

## 延伸阅读：Beyond ReAct Loop（可选阅读）

幻灯片对比了 ReAct 之后的几种循环/搜索形态（底部标注了每步的性质：model call / app·tool action / chosen outcome）：

| 形态 | 循环特征 | 步骤 |
|---|---|---|
| **ReAct** | 每一步都循环（loops every step） | Thought → Act → Observe |
| **Reflexion** | 失败之后才循环（loops after a failure） | Attempt → Evaluate → Critique → Retry |
| **Plan-and-execute** | 偏离时才重新循环（loops on deviation） | Plan → Execute steps → Re-plan |
| **Tree search** | 不循环——一遍式、宽搜索（no loop — one pass, wide） | State → Branch A · B · C（分支并行探索——只有一个存活）→ Keep best |

## 核心要点

- **ReAct 循环** = Thought（我知道什么、缺什么）→ Action（结构化调用）→ Observation（环境用事实作答）；纯 Reason 会累积成自信幻觉，纯 Act 会原地打转；循环到观察回答问题或触发停止规则为止（arXiv:2210.03629）。
- **Agent loop 的骨架**就是 `messages` 列表的追加：system + user → 模型回复 → `validate` 参数 → `execute_tool` → 以 `role:"tool"` 写回；`MAX_STEPS` 超限即抛错——停止规则必须显式实现。
- **一个 agent = 模型 + 循环**；coding agent 三组件——Model + agent loop、Tools and guardrails（权限/沙箱/审批）、State: context and memory——共享同一个上下文窗口，必须一起设计。
- 搜索读取四件套：**glob/grep**（零构建、永远实时，但词法匹配会漏改写）；**语义/结构索引**（Aider repo map，查询快但要建索引与同步）；**外部信号**（stack trace、失败测试、git history，调试时精度最高但只在信号存在时有用）；**LSP**（编译器符号图，能解析别名/重载/重命名，但每种语言一个活服务器、冷启动慢）。实践顺序：先 grep，名称猜不出再上索引或 LSP。
- 编辑四件套各有软肋：**整文件重写**（输出随文件规模涨、未改代码会漂移）；**unified diff**（紧凑可审查、人机 CI 通用，但行号/上下文漂移会让 hunk 失败）；**find/replace**（输出只与改动成比例，但要求锚点精确且唯一）；**AST 编辑**（构造上合法、对格式免疫，但语言覆盖有限）。按 token cost × robustness 权衡组合使用。
- **Shell 是最强大也最危险的工具**：可组合、触达广（文件系统/网络/包管理器/二进制）、有持久性、爆炸半径 = shell 能力上限；harness 必须处理隔离、可行动的失败信号、适度输出、长时进程、重试预算。
- 工具设计五原则：少而正交；专用而非通用（`search_orders(customer_id)` > 裸 `run_sql`）；token 便宜的输出（截断/分页/摘要——**工具设计即上下文设计**）；会教学的错误信息；默认幂等。SWE-agent 数据（GPT-4）：专用编辑器 18.0% vs 只有 shell 11.0%——不能只给 shell。
- 八种提示技术按三档选型：基线（zero-shot / few-shot / role & persona）→ 加推理（CoT / ToT / self-consistency，如 5 次采样 T=0.7 多数决、阈值 0.8 否则转人工）→ 系统级（prompt chaining 阶段校验、meta prompting 让模型改自己的提示，8/10 → 10/10）。注意：**有些技术已过期**（作业里自己发现），且**提示建议是模型相关的，换模型必须重新调优**。
- 提示设计四实践：从简单开始再迭代；分节（指令、分隔符、数据的顺序）；具体简洁（花哨措辞一文不值）；大任务拆子任务。
- **上下文是有限资源**：每步重发整个窗口（成本）、prompt 越大 prefill/decode 越慢（延迟）、窗口越满中间越容易漏（注意力）——更多上下文 ≠ 更好答案。长度与位置都伤准确率（Context Rot (Chroma)；Liu et al. "Lost in the Middle" TACL 2024：从 ~100% 跌到 46% 区间）。
- 单 turn 示例 token 预算：system prompt ~2K、tool definitions ~6K、retrieved context ~25K、message history ~80K 且增长最快、project environment ~8K，另需为输出预留 headroom。
- 四个上下文杠杆按「预防/无损 → 有损/不可逆」排序：**Admission**（门口整形：定向检索、输出整形、截断兜底、隔离给 subagent——48,000 → 900 tokens，小 98% 答案不变）；**Offloading**（可检索而非常驻：渐进工具定义、工具搜索、输出卸载、外置任务列表、持久记忆——42,000 → 3,100 tokens，小 93%）；**Transformation**（有选择丢历史：去重留最新状态、掩码旧观察、滑动窗口——96,000 → 24,000 tokens，小 75% 且无摘要）；**Compaction**（LLM 是最后手段：滚动摘要/整体摘要/自动记忆；三条铁律：为输出留 headroom、保留系统前缀、压缩后重注入关键事实）。
- 上下文五失败模式：**Poisoning**（幻觉入窗后被当事实引用）、**Distraction**（历史增长致 agent 模仿自己的过去）、**Confusion**（无关工具/文档带偏答案）、**Clash**（新旧信息矛盾未决）、**Drift**（真实目标被邻近子目标替换）——给失败命名，解法就清晰（Breunig 2025）。
- **Agent = Model × Harness**：模型能力定上限，harness 定实际表现；只改 harness（旧工具输出压缩、近期观察保持可见、检测重复与停滞、卡住时干预）即可让 SWE-bench Verified 43/169 → 72/169、SWE-bench Pro 31/316 → 72/316，约翻倍——许多「模型失败」其实是上下文与控制循环的失败（Lewis, arXiv:2608.26218, 2026）。
