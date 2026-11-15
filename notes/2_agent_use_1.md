# 第2讲：用户视角的智能体 I（Claude Code 如何工作）

> 原讲义：*Agent From a User's Perspective I: How Claude Code Works*（Harvard CS2680 Modern AI Systems: Agents and System Optimizations，第 2 讲，Juncheng Yang，共 53 页）

## 本讲概览

本讲从用户视角拆解 Claude Code：当你敲下一条 prompt 时，背后发生了什么。核心是 agentic loop（智能体循环）——一次用户输入并不是一次模型请求，而是一条「收集上下文 → 模型提出动作 → harness 执行工具 → 结果折回上下文」不断重复的推理-执行链。你会看到：在敲下第一个字符之前上下文里已经有一万多 token；代码仓库不会被整体发送，而是通过 grep/read 按需拉取切片；权限层挡在模型意图与真实执行之间；上下文随轮次增长直到触发 compaction（压缩）。随后本讲讲记忆（CLAUDE.md 层级、带 `paths:` frontmatter 的 `.claude/rules/`、带 MEMORY.md 索引的 auto memory、`/memory` `/context` `/init` `/doctor` 四个命令）、六大核心工具（Read、Search、Fetch、Edit/Write、Shell、Delegate），以及四种互不可替代的扩展机制：Skill、MCP、Hook、Plugin。结尾附可选幻灯片：MCP 的架构、三大原语（tools / resources / prompts）、安全、网关（gateway）与 2026-07-28 规范。

## 一、课程更新与今日计划

### 日程调整：更多智能体、更少 GPU

- **LLM 背景知识后移**：先把 LLM 当作一个「magic reasoning box」（魔法推理盒子）——学智能体不需要先懂模型内部。
- **增加两讲 agent design（智能体设计）**：因为大部分同学现在对智能体更感兴趣。
- **减少 GPU 相关讲次**：与其他课程重合度较低地压缩，避免重复。
- **无强制论文展示**：Assignment 1 的分享改为加分项（bonus）；计分转向课堂参与（participation）与项目（project）；另有少量加分论文讨论，时间待定（TBA）。

幻灯片页脚为 **Harvard Madsys · course.agentic-system.org**。

### 其他事务

- **参与分（Participation score）**：课堂上提问 / 回答问题，每节课至多 1 分，课后可找 TA 登记。
- **新增 TA**：Advaith Ravishankar。
- **额外阅读材料为可选（optional）**，标注 ADVANCED 的部分「skim 一下，或自己多读」即可，不作要求。

### 今日计划

1. **How Claude Code works**：从 stateless LLM 到 agent；
2. **Memory（记忆）**；
3. **Tools, skills, hooks, plugins（工具、技能、钩子、插件）**。

## 二、Agentic Loop：一次 Prompt 背后发生了什么

进入第一部分的标题页之前有一张提示：*"What happens when you type a prompt into Claude Code?"*（当你把一条 prompt 敲进 Claude Code 时会发生什么？）。

### The Agentic Loop（智能体循环）

核心命题：**一次用户 prompt = 多次模型调用 + 多次工具执行，而不是单次请求。** 循环分三步：

1. **Gather context（收集上下文）**：prompt、文件内容、工具结果；
2. **Generate action（生成动作）**：运行一个工具，如 `bash`、`read`、`edit`；
3. **Run tool（执行工具）**：跑测试、拿到输出、重新读状态。

之后**重复**——每一步都以上一步返回的内容为条件（"every step conditioned on what the last one returned"）。幻灯片把系统分成三个区域：**harness（外壳程序）、model（模型）、your machine（你的机器）**。

图示：页面给出一个三段式循环图，按 harness / model / your machine 三个泳道划分：harness 收集上下文（prompt、文件、工具结果）→ 模型生成一个工具动作请求 → harness 在你的机器上执行工具（bash/read/edit、测试、输出、重读状态）→ 结果回到上下文，箭头闭环。

### 敲下第一个字符之前：上下文已经有 10+k tokens

*"Before your first keystroke, the context size is already 10+k tokens."* 会话开始、用户还没输入任何字时，上下文窗口里已经预装了一万多 token，构成如下：

| 组成部分 | 内容 |
|---|---|
| **SYSTEM** | Claude Code 的系统指令（instructions） |
| **PROJECT** | 项目环境信息 |
| **MEMORY** | 持久化项目 / 用户笔记（即 CLAUDE.md） |
| **TOOLS** | Read, Edit, Bash, Glob, Grep, Web, Agent |
| **SKILLS / MCP** | 只有名字和描述（names and descriptions） |
| **USER** | 例如："Fix the failing auth test" |

注意 SKILLS / MCP 条目**初始只加载名字和描述**——完整正文只有在 Claude 真正「伸手去拿」（actually reaches for）某个 skill / MCP 时才加载。这就是后面讲 skill 上下文成本的伏笔。

### 它不会发送你的代码仓库

*"The repo stays on disk. Claude pulls slices of it on demand."* 仓库几千个文件静静躺在磁盘上，Claude 不会把它们全部塞进上下文。流程是：Claude 自问 "what do I need?" → 发起一次 `Grep("authentication")` → 只有**几行**匹配内容返回 → 这几行切片（slice）进入上下文。也就是说，**仓库内容是以「按需取切片」的方式进入上下文的**，上下文里永远只有与当前任务相关的最小片段。

### Model Proposes, Harness Executes（模型提议，外壳执行）

模型本身不能碰你的机器。流程是：

1. **Claude 模型**发出一个请求：`Bash("pytest")`；
2. **Claude Code harness**接收这个请求：解析它、**检查权限（checks permissions）**、执行；
3. **你的机器**上 `pytest` 真正运行，产生 stdout / stderr；
4. 输出作为 **tool_result** 回到**模型的上下文**里。

关键语义：模型「提议」（propose）动作，harness「执行」（execute）动作；模型看到的只是结构化工具结果。

### 一次用户轮次触发多次 LLM 推理

一个用户轮次展开为交替的推理与工具执行链：**U → M₁ → T₁ → M₂ → T₂ → … → Mₙ → A**（prompt → inference → tool → inference → tool → … → answer）。

幻灯片给出的实践示例（一次修 bug 的会话）：`read` → `edit session.py` → `pytest` → `grep` → `create_session`（新增函数）→ `pytest` → **all green**（全绿）。

要点：**每一个请求（request）都以「上一次推理 + 上一次工具结果」为条件**——这正是 agentic 能力在系统层的全部形态：没有神秘规划器，只有条件化的反复调用。

### 权限：位于意图与执行之间

*"A tool request is a proposal that needs your or another model's approval."* 工具请求只是一个**提案（proposal）**，中间隔着 **Permission layer（权限层）**，可能得到三种结果之一：

- **allowed** —— 命令直接运行；
- **ask** —— 先由你确认，再运行；
- **denied** —— 什么都不发生。

幻灯片举例：`Bash("rm -rf build/")`。给出的权限模式有：**Manual**（手动）、**Accept Edits**（自动接受编辑）、**Bypass permission**（绕过权限检查）、**Auto**（由一个小模型来检查判断）。这层设计把「模型想做什么」与「系统允许做什么」解耦：破坏性命令（如 `rm -rf`）可以走 ask，而读取类操作可以放行。

### 上下文增长，然后被压缩（Compaction）

两个前提：

- **典型上下文规模**：1M tokens（幻灯片列举：Sonnet / Opus / Fable、GPT 5.6）；今年早些时候 256K 还很常见。
- **上下文不是免费的**：前缀缓存读（prefix-cache reads）占了成本的大部分。

随着循环推进，每个请求都往上下文里追加 token：模型回复、文件内容、命令输出。于是出现 **COMPACTION（压缩）**：把旧轨迹（old trajectory）**总结成摘要**，同时**重新注入 CLAUDE.md 与 memory**，保证关键约定不因压缩而丢失。幻灯片用 Request 1 → 2 → 3 → N → N+1 示意：N 步之后上下文膨胀，N+1 请求基于压缩后的轨迹继续。

结论（也是课程主线预告）：**上下文管理（context management）是 harness 设计的重要组成部分——下周讨论**（对应第 4 讲上下文工程）。

### 循环小结

四句话收束第一部分：

1. Prompt + 模型上下文 → **proposes**（提出动作）；
2. **Harness executes**（外壳执行）；
3. **Result folds into context**（结果折回上下文）；
4. **The loop repeats until the task is done**（循环往复，直到任务完成）。

## 三、记忆：让无状态的 LLM 成为有状态的智能体

分隔页「**Tools and Memory Enable Agentic Capability**」（工具与记忆赋予智能体能力）给出经典智能体框图。

图示：一个中心「Agent / LLM（Reasoning & Planning，推理与规划）」方框，向外发出 **Tool / Action（工具/动作）** 作用于 **Environment（环境）**，环境返回 **Observation（观察）**；智能体的整体状态（State）由 **context + memory** 组成。第二张同主题的图强调三要素分工：**LLM 是 stateless（无状态）的**、**Tools 负责 act（行动）**、**State = context + memory**。

### 上下文是记忆的一种形式

- 智能体**跨运行是无状态的**——每个会话都从零开始（every session starts from zero）。
- 实践中，「记忆」就是**会话启动时加载的文件**（in practice, "memory" is just files loaded at session startup）。
- 划重点：**"Every memory creation is a decision about what gets re-read forever."**（每一次写记忆，都是在决定「什么内容将被永远重新读入」。）

两种记忆形态的对照：

| | Context（工作记忆） | Persistent Memory（持久记忆） |
|---|---|---|
| 定义 | 模型现在能看到的东西 | 能跨会话存活、下次重新加载的东西 |
| 生命周期 | **随会话死亡**（dies with the session） | 跨会话保留 |

### 为什么智能体需要记忆

四个痛点（左右两两对照）：

- **Repeated instructions（重复的指令）**：同一套 setup 每个会话都要解释一遍；
- **Lost decisions / assumptions（丢失的决定/假设）**：上下文窗口一压缩，"为什么这么做"就消失了；
- **Repeated discovery（重复的发现）**：智能体反复重读同样的文件，只为重新认识代码布局；
- **Inconsistent behavior（不一致的行为）**：不同会话对同一问题做出不同选择。

总结句：**"Memory is how instruction becomes convention."**（记忆是把「一次性指令」变成「长期惯例」的机制。）

### 两个系统承载知识传递

*"Both load at the start of every session into context."* 这张对照表在连续两页幻灯片上出现（渐进式展示）。两个系统都在**每次会话开始时**加载进上下文：

| | CLAUDE.md 文件 | Auto memory（自动记忆） |
|---|---|---|
| **谁写它** | 你（You） | Claude |
| **包含什么** | 指令与规则（instructions and rules） | 学到的东西与模式（learnings and patterns） |
| **作用域** | 项目、用户或组织 | 按仓库（per repository），跨 worktree 共享 |
| **加载方式** | 每个会话 | 每个会话（**前 200 行 / 25KB**） |
| **用途** | 标准（standards）、工作流（workflows）、架构（architecture） | 你的偏好（preferences）、纠正（corrections）、项目上下文（project context） |

一句话区别：**CLAUDE.md 是你写的规矩，auto memory 是 Claude 自己记的笔记。**

### CLAUDE.md 住在哪：四级层级

*"Files load broadest-scope first; the closest file is read last."*（最宽作用域的优先加载，离得最近的最后读。）四级结构，从宽到窄：

| 级别 | 位置 | 说明 |
|---|---|---|
| **1. Managed policy** | `…/ClaudeCode/CLAUDE.md` | 组织级（org-wide），**不可排除（cannot be excluded）** |
| **2. User instructions** | `~/.claude/CLAUDE.md` | 你的个人偏好，对**每个项目**生效 |
| **3. Project instructions** | `./CLAUDE.md` 或 `./.claude/CLAUDE.md` | 团队共享，**通过源码控制（source control）**分发 |
| **4. Local instructions** | `./CLAUDE.local.md` | 个人本地，**gitignored**（不进版本库） |

**什么该写进 CLAUDE.md**（幻灯片的核心判据：**agent 无法廉价推断的事实**，the agent cannot cheaply infer）：

| ✅ Belongs（属于） | ❌ Doesn't belong（不属于） |
|---|---|
| **Commands**：怎么跑 build、测试、linter | 模型**已经知道**的语言 / 框架知识 |
| **Hard constraints**：永不 commit 到 main、永不编辑生成文件 | linter / formatter **已经强制**的风格偏好 |
| **Layout, ownership, gotchas**：目录结构、模块归属、坑 | 长散文、changelog，以及**任何机密（secret）** |

配套的四条写作纪律：

- **Size（体积）**：每个文件 **200 行以内**——"context is rented, memory is owned"（上下文是租来的，记忆是你自己的）；
- **Structure（结构）**：Markdown 标题 + 要点列表；
- **Specificity（具体性）**：写具体规则，不写模糊规则；
- **Consistency（一致性）**：不要自相矛盾或过期的规则——**有意识地决定你维护什么**。

图示：紧随其后的纯图片页（第 21 页，无文本层）按上下文推断是对上述 CLAUDE.md 四级文件位置的示意图（managed / user / project / local 的目录树状图），与上一页文字内容配套。

### 太长了？拆进 .claude/rules/

*"One topic per file — and each rule loads only when it is relevant."* 当 CLAUDE.md 膨胀时的解法：**一个文件一个主题**，每条规则文件只覆盖单一关注点，从而保持**短小且具体**；再配上 **`paths:` frontmatter**，规则**只在 Claude 触碰匹配文件时加载**（没有 `paths:` 的规则则每个会话都加载）。

幻灯片给出的例子——`.claude/rules/` 下：`testing.md`、`api-style.md`、`db-migrations.md`。

三条教训（The lesson）：

- 作用域规则（scoped rules）保持上下文窗口更小；
- 只有与当前工作匹配的规则才会被加载；
- **CLAUDE.md 保持简短，细节下沉到 rules 里**。

图示：紧随其后的纯图片页（第 23 页，无文本层）按上下文推断是对应 `.claude/rules/` 目录结构 / paths 匹配加载的示意图，与上一页配套。

### Auto Memory：Claude 自己的笔记

存储位置：`~/.claude/projects/<project>/memory/`，目录示例为 `MEMORY.md` + `user_role.md`、`feedback_testing.md` 等主题文件。四类内容（每类都有 **type 字段**标注）：

| 类型 | 内容 |
|---|---|
| **user** | 你的角色、专长与工作偏好 |
| **feedback** | 你给出的纠正、你确认过的做法 |
| **project** | 进行中的工作、代码里看不到的决定 |
| **reference** | 信息在项目外部 |

行为特性：

- **`MEMORY.md` 是索引**——每个会话只加载它的**前 200 行（25KB）**；
- 机器本地（machine-local）；同一仓库的多个 **worktree 共享该目录**；
- **默认开启**，可用 **`/memory`** 关闭。

### 检索使用索引（Retrieval Uses an Index）

*"The index is always loaded; topic files are read only when they are relevant."* 五步：

1. **Session starts**（会话开始）；
2. **Load MEMORY.md**（加载索引）；
3. **Identify relevant topic**（识别相关主题）；
4. **Read topic file on demand**（按需读取主题文件）；
5. **Apply to the task**（应用于任务）。

设计意图与 skill 相同：**索引常驻上下文窗口很小，只有任务真正需要的主题文件才会被读进来**——用「索引 + 按需展开」控制记忆的成本。

### 检查与控制记忆：四个斜杠命令

*"Four commands for seeing — and steering — what Claude remembers."*

| 命令 | 作用 |
|---|---|
| **`/memory`** | 浏览（browse）、编辑（edit）、删除（delete）或禁用（disable）记忆 |
| **`/context`** | 查看哪些指令文件（instruction files）被加载了 |
| **`/init`** | 生成一个起步版 CLAUDE.md |
| **`/doctor`** | 找出**可能不该**放进 CLAUDE.md 的内容 |

### 记忆的成本

两条硬约束：**上下文大小有限 + 你为发送给 Anthropic 的每个 token 付费**。

- **每个永久 token 都是租金**——每次会话开始时都要付一次；
- **记忆与任务争抢同一个窗口**（Memory competes with the task for the same window）；
- **过期的记忆比没有记忆更糟**：它会主动误导（actively misleads）；
- 对待记忆要像对待代码：**审（review）、修剪（prune）、放进版本控制**（keep it in version control）。

## 四、核心工具：让智能体「有手」

### 六大核心工具一览

| 工具 | 作用 | 备注 |
|---|---|---|
| **Read** | 打开文件、检查状态 | 最常用的工具（the most used tool） |
| **Search** | `grep` 和 `glob` | 不读全部文件就能找到目标 |
| **Fetch** | 拉取网页或文档 | 把**不可信文本**带进上下文（brings untrusted text inside） |
| **Edit / Write** | 修改文件 | **第一个有后果**（consequences）的工具 |
| **Shell** | build、test、git | 未沙箱化时等于**整机权限**（the whole machine） |
| **Delegate** | 派生一个子智能体（subagent） | 一个**只返回摘要**的工具 |

两条补充说明：

- **模型自己决定用哪些工具，你基本不需要做什么**（Model will decide which tools to use, not much you need to do）；
- **作业 2（Assignment 2）里你会亲手实现这些工具**。

## 五、扩展机制：Skill、MCP、Hook、Plugin

### 四种机制解决四个不同的问题

*"Four mechanisms, four different problems — and they are not interchangeable."*（四种机制、四个不同的问题——它们**互不可替代**。）

| 机制 | 回答的问题 |
|---|---|
| **Skill** | 智能体**应当如何执行**某任务（How the agent should perform a task） |
| **MCP** | 它能触达**哪些外部数据与动作**（Which external data and actions it can reach） |
| **Hook** | 在某个**生命周期事件**上**自动发生什么**（What happens automatically at a lifecycle event） |
| **Plugin** | 扩展如何**打包与分发**（How the extensions are packaged and distributed） |

口诀：**skill 决定「怎么做」（decides how），MCP 触达外部（reaches outside），hook 强制执行（enforces），plugin 分发（distributes）**——四层各管一层。

### 智能体循环中的扩展点

每种机制挂在循环的不同位置（user request → model reasoning → tool selection → tool execution）：

- **Skill** 在模型推理阶段提供**知识与程序**（knowledge and procedure）；
- **MCP** 在工具选择阶段提供**外部工具**（external tools）；
- **Hook** 可以在**循环的任何阶段**检查（inspect）、阻止（block）或响应（react）；
- **Plugin** 把 skills、MCP servers 与 hooks **打包成一个可安装单元**（one installable unit）。

### 示例：一次完整的发布工作流

场景：*"Prepare a release, validate it, publish it to GitHub, notify the team."*（准备一个版本、校验它、发布到 GitHub、通知团队。）四个需求分别由四种机制承担：

| 需求 | 机制 |
|---|---|
| 遵循发布流程（Follow the release procedure） | **Skill** |
| 创建 GitHub release（Create the GitHub release） | **MCP** |
| 测试失败时阻止发布（Prevent publishing when tests fail） | **Hook** |
| 分享整套配置（Share the complete setup） | **Plugin** |

### Skill：可复用的程序（Reusable Procedures）

定义：**任务需要时智能体加载的「知识 + 程序」**（knowledge and procedure the agent loads when the task calls for it）。一个 skill 承载的东西：

- **Domain knowledge**（领域知识）；
- **Reference material**（参考资料）；
- **Repeatable workflows**（可重复的工作流）；
- **Model- and user-invoked**（可被模型或用户触发）；
- **Reasoning at run time**（运行时推理）。

幻灯片把 skill 定位为**上下文工程（context engineering）**手段，例子：`/release 2.4.0`。

**Skill 的目录结构**——一个文件夹 + 控制发现的 description + 承载程序的 body：

```
.claude/skills/release/
├── SKILL.md
├── references/
└── scripts/
```

工作方式三条：

- **description 控制发现**（controls discovery）；
- **body 承载程序**（holds the procedure）；
- 支撑文件（references/、scripts/）提供额外引用与脚本。

`SKILL.md` 示例 frontmatter：`name: release` / `description: Prepare a release`。用户也可以直接运行它：`/release`。正文示例（发布五步）：

1. Read the release notes（读发布说明）；
2. Confirm the version（确认版本）；
3. Run the tests（跑测试）；
4. Prepare the commit（准备提交）；
5. **Ask before publishing**（发布前先征求同意）。

**调用方式与上下文成本**——两种模式、两种成本：

- **Model-invoked（模型触发）**：Claude 发现 skill 的 description 与任务匹配时自动加载；
- **User-invoked（用户触发）**：用户显式运行 `/<skill-name>`。

成本要点：

- **description 在会话开始时加载**；**完整 body 只在 skill 真正运行时才加载**——与 MCP 条目「先名字后正文」是同一套按需加载设计；
- **有副作用的工作流（side-effecting workflows）通常应要求显式调用**；
- **清晰、互异的 description 能减少错误的 skill 选择**。

### MCP：外部能力层

*"Model Context Protocol connects agent to external services through a standard Protocol."*（MCP 通过一个标准协议把智能体连到外部服务。）幻灯片列举的能力示例：读和更新 GitHub issues、查询数据库、拉取监控数据、访问 Figma 设计稿、向 Slack 发消息、控制浏览器。核心句：**MCP 给 Claude 的能力既不在模型里、也不在本地文件里**（MCP gives Claude capabilities that exist neither in the model nor in local files）。

**一次 MCP 工具调用的六步**（*"Six steps from intent to structured result."*）：

1. Claude 识别出需要的动作（identifies a needed action）；
2. **MCP client** 调用一个 tool；
3. **MCP server** 处理这次连接（handles the connection）；
4. 外部服务执行操作（performs the operation）；
5. **结构化结果**返回给 Claude；
6. Claude 评估结果（evaluates the result）。

侧栏要点（**几乎与本地工具相同**，Almost identical to a local tool）：

- 相同的**名字、描述与类型化 schema**（Same name, description and typed schema）；
- 相同的**调用-返回契约**（Same call-and-return contract）；
- 只是**运行在另一个进程里**（It just runs in another process）。

结论句：**协议承载调用（the protocol carries the call），但「是否发起调用」仍由智能体自己决定。**

### Hook：生命周期自动化

*"A session runs left to right; a hook can fire at each marked event."*（会话自左向右推进，hook 可以在每个标记事件上触发。）

会话时间线上的事件（底部一行）：**session start → user prompt → tool call → tool result → model reasoning → stop**。顶部标注各事件上可挂的动作（按幻灯片版式推断对应关系）：

- **Session start**：load context（加载上下文）；
- **User prompt**：format、validate or add（格式化、校验或增补）；
- **Before tool use**：inspect or log（检查或记录）；
- **After tool use**：test / verify / block（跑测试、核验、阻止）；
- **Model reasoning**：**不是 hook 事件**（"No hook — reasoning is not an event"）；
- **Stopping**：会话停止点。

能力总结：**hooks 按事件触发，可以执行命令（commands）、HTTP 请求（HTTP requests）、MCP 工具（MCP tools）、提示词（prompts）或子智能体（subagents）**——hook 本身就是一个「在事件上跑一段逻辑」的自动化机制。

### Plugin：打包与分发层

*"One installable unit that carries skills, hooks, agents and MCP configuration."*（一个可安装单元，承载 skills、hooks、agents 与 MCP 配置。）目录结构：

```
plugin/
├── skills/
├── hooks/
├── agents/
├── .mcp.json
├── .lsp.json
└── .claude-plugin/plugin.json
```

打包带来的五个好处：

- **Installation（安装）**——一条命令；
- **Versioning（版本化）**——钉住发布（pinned releases）；
- **Namespacing（命名空间）**——无名字冲突；
- **Team reuse（团队复用）**——一套配置人人可用；
- **Distribution（分发）**——通过 marketplace 共享。

结论句：**A plugin is how a working setup becomes something other people can install**（插件就是让「一套好用的配置」变成「别人也能安装的东西」的方式）。

### 四种机制如何拼在一起

*"Judgment, capability, enforcement — and the package that ships all three."*（判断、能力、强制——以及把它们一起交付的打包层。）整体关系：

- **Skill**：知识与程序（knowledge and procedure）；
- **MCP**：GitHub · Slack · 数据库等外部系统；
- 两者共同喂给 **Claude**（负责推理与工具使用，reasoning and tool use）；
- **Hook**：在生命周期事件上触发——**每次工具调用前后**（before and after every tool call）；
- **Plugin**：把 skill、MCP 配置与 hooks 打包起来，**供别处安装**（for install elsewhere）。

### Inside .claude/ 与分类练习

`.claude/` 目录的职能划分（`~/.claude/` 存在同样的布局作为用户作用域；**项目设置优先于用户设置**，Project settings win over user settings）：

| 职能 | 对应文件 / 目录 |
|---|---|
| **Memory（记忆）** | `CLAUDE.md`、`rules/` |
| **Configuration（配置）** | `settings.json`、`settings.local.json`（permissions, hooks, env） |
| **Workflows（工作流）** | `commands/`、`skills/` |
| **Delegation & guardrails（委派与护栏）** | `agents/`、`hooks/` |

**课堂设计练习（Design Exercise，加分题）**："把每个需求分类到正确机制，并说明为什么其他机制不合适。"幻灯片给出的分类：

| 需求 | 机制 |
|---|---|
| 应用公司 API 约定（Apply the company API conventions） | **Skill** |
| 从 Jira 读一个 issue（Read an issue from Jira） | **MCP** |
| 每次编辑后跑格式化（Run formatting after every edit） | **Hook** |
| 引导多步部署（Guide a multi-step deployment） | **Skill** |
| 发送完成通知（Send a completion notification） | **Hook plus MCP** |
| 阻止写入生产环境（Block writes to production） | **Hook or policy** |
| 在多个仓库间共享一切（Share everything across repositories） | **Plugin** |

记忆口诀（幻灯片收尾）：**Skill = knowledge and procedure（知识与程序）· MCP = external access（外部访问）· Hook = event automation（事件自动化）· Plugin = packaging and distribution（打包与分发）。**

图示：设计练习后一页（第 42 页）为纯图片页（无文本层），按上下文推断是上述四种机制对照 / 分类练习的图示版。

### 下节课预告

**Next class: Agent from a user's perspective II**（用户视角的智能体 II，即第 3 讲：多智能体与最佳实践）。

## 六、可选幻灯片：MCP 深入

分隔页「Optional slides」之后为可选内容（标注 *optional — extra reading, not required*），聚焦 MCP 本身。

### MCP：是什么、为什么

动机之问：*"What if I need to access external services? Gmail, GitHub, …"*（如果我要访问外部服务呢？）。**MCP 存在的理由：访问外部工具与服务。**

- **MCP 之前**：N×M 实现——每个 AI 客户端 × 每个服务都要各写一套集成；
- MCP **避免了为每个 AI 客户端构建独一无二的集成**（avoids building a unique integration for every AI client）。

官方定义（无状态开放协议）：**"An open protocol (stateless) that lets an AI application discover and use capabilities exposed by external servers."**（一个开放的、无状态的协议，让 AI 应用能够发现并使用外部服务器暴露的能力。）官网：https://modelcontextprotocol.io

### MCP 架构

四个角色：

| 角色 | 职责 |
|---|---|
| **Host（宿主）** | 你对话的那个应用——如 Claude Code |
| **MCP client** | 宿主运行；**每个 server 一条连接**（one connection per server） |
| **MCP server** | 把一个系统的能力暴露为 tools |
| **External system** | GitHub、Slack、PostgreSQL、某个本地服务 |

Host 内的 client 与 server 之间走 **MCP protocol**（协议）。注意「每 server 一条连接」的架构含义：server 很多时连接会很多——这正是后面 gateway 登场的动机。

### 三大核心原语（Three Core Primitives）

| 原语 | 定义 | 示例 |
|---|---|---|
| **Tools（工具）** | Claude 可调用的**动作**（Actions Claude can call） | `create_issue(…)` |
| **Resources（资源）** | 服务器暴露的**可读数据**（Readable data）——如 issue、schema | `github://issues/123` |
| **Prompts（提示词）** | **可复用的提示词模板**（Reusable prompt templates） | `triage_issue(…)` |

关于 **Prompts** 的两个要点：

- **A prompt returns instructions（提示词返回指令）**。模板示例：Review issue #123 → Determine whether it is reproducible（判断是否可复现）→ Assess its severity as high（把严重性评为 high）→ Recommend an owner and next action（推荐负责人与下一步）。
- **Prompts are user-controlled（提示词由用户控制）**：应用把它们呈现为命令或菜单选项；在 Claude Code 中是**带命名空间的斜杠命令**：`/mcp__github__triage_issue 123 high`。

**三原语协作示例（How They Work Together）**：假设你问 *"Triage issue #123 and assign it if it is a critical authentication bug."*（triage issue #123，如果是一个关键的认证 bug 就指派）。三个原语这样配合：

| 原语 | 实例 | 提供 |
|---|---|---|
| **Prompt** | `triage_issue` | 组织的 triage 流程（supplies the organization's triage procedure） |
| **Resource** | `github://issues/123` | issue 的**内容**（supplies the issue's content） |
| **Tool** | `get_related_errors` | 当前的**诊断信息**（retrieves current diagnostic information） |

### MCP 安全：本质部分

前提警告：**"A connected server can see what you send it and act with your credentials."**（已连接的 server 能看到你发给它的一切，并用你的凭据行动。）

五条安全原则：

1. **Least privilege（最小权限）**——把 token 的作用域限定到你真正需要的 repo、表或频道；
2. **Read vs. write（读写分离）**——读与写分开；**变更（mutations）放在审批（approval）之后**；
3. **Distrust tool output（不信任工具输出）**——绝不把返回内容当作指令（never trust returned content as instructions）——即防 prompt injection 的基本立场；
4. **Vet before installing（安装前审查）**——第三方 server 可能携带 prompt injection，要审查后再装；
5. **Ask before connecting（连接前先问）**：这个 server 能**读**什么？能**改**什么？

### MCP Gateway（网关）

*"A control layer between an AI client and one or more MCP servers."*（AI 客户端与一个或多个 MCP server 之间的控制层。）架构：Claude Code / agent → **MCP gateway**（auth · policy · logging · routing · rate limits）→ 下游的 Database、GitHub MCP、Jira MCP 等。两个关键定性：

- **像一个 API gateway，但它说的是 MCP**：`tools/list`、`tools/call`、resources、prompts、schemas、protocol versions；
- 它是一种**架构模式**；对客户端而言，网关**看起来就是又一个 MCP server**（to client it just looks like another MCP server）——客户端代码零改动。

**网关做的六件事**（可选深入页）：

| # | 功能 | 说明 |
|---|---|---|
| 1 | **Aggregate（聚合）** | 一条连接、一个带命名空间的目录：`github.*`、`jira.*`、`postgres.*` |
| 2 | **Route（路由）** | 把每次调用转发给归属 server；用 **`Mcp-Method` 头**路由，**无需读取请求体** |
| 3 | **Enforce policy（执行政策）** | 谁能连接、哪些工具可见 / 可调用 / 需要人工审批 |
| 4 | **Broker identity（代理身份）** | 客户端只认证一次；上游凭据留在网关后面 |
| 5 | **Observe（可观测）** | 中央审计日志：身份、工具、决策、延迟、结果、成本 |
| 6 | **Scale（扩展）** | 负载均衡、重试、熔断器（circuit breakers）、目录缓存、配额（quotas） |

**何时值得上网关**：用户多、agent 多、server 多、凭据多或凭据范围过大、丢失了终端用户身份（lost end-user identity）、名字冲突、日志里出现机密、合规规则需要统一治理。**但它同时是一个信任边界（a trust boundary）**——集中化带来集中风险。

### 新变化：Spec 2026-07-28

*"The largest revision of MCP since launch."*（自发布以来最大的一次修订。）三个要点：

- **Stateless core（无状态内核）**：不再需要维持会话（No sessions to hold）；任意请求可以落到任意实例，后面挂一个**普通负载均衡器**即可；
- **Routing（路由）**：`Mcp-Method` 头让网关**不读 body 就能路由**；**list 结果可以带 TTL 缓存**（cacheable with a TTL）；
- **Extensions（扩展）**：用于长时任务的 **Tasks** 与用于服务端渲染 UI 的 **MCP Apps** 现在以扩展（extensions）形式提供。

（讲义最后一页为无文本层的结束页，无额外内容。）

## 核心要点

1. **一次 prompt ≠ 一次请求**：agentic loop = 收集上下文 → 模型提议动作 → harness 执行 → 结果折回上下文，循环到任务完成；每一步以上一步的结果为条件。
2. **第一个字符敲下前，上下文已有 10+k tokens**：system 指令、项目环境、memory（CLAUDE.md）、工具 schema、skill/MCP 的名字与描述。
3. **仓库不会被发送**：几千个文件留在磁盘，Claude 用 `Grep("authentication")` 之类按需拉取切片，只有几行进入上下文。
4. **模型提议、harness 执行**：模型发 `Bash("pytest")` 请求，harness 解析、查权限、执行；stdout/stderr 作为 tool_result 回到模型上下文。
5. **一个用户轮次 = U M₁ T₁ M₂ T₂ … Mₙ A** 的推理-工具交替链，例如 read → edit session.py → pytest → grep → create_session → pytest → all green。
6. **权限层挡在意图与执行之间**：提案可能被 allowed / ask / denied；模式含 Manual、Accept Edits、Bypass permission、Auto（小模型检查）。
7. **上下文 1M tokens**（Sonnet / Opus / Fable、GPT 5.6；年初 256K 常见）；前缀缓存读占成本大头；compaction = 总结旧轨迹 + 重新注入 CLAUDE.md 与 memory。
8. **LLM 无状态，记忆 = 会话启动时加载的文件**：「每次写记忆都是决定什么会被永远重读」；记忆把一次性指令变成长期惯例。
9. **CLAUDE.md 四级层级**（managed policy → user → project → local），最宽作用域先加载、最近的文件最后读；managed 不可排除，local 进 gitignore。
10. **CLAUDE.md 只写 agent 无法廉价推断的事实**（命令、硬约束、布局与坑）；不写模型已知知识、linter 已强制的风格、长散文和机密；每文件 <200 行。
11. **太长就拆 `.claude/rules/`**：一文件一主题 + `paths:` frontmatter，只在触碰匹配文件时加载。
12. **Auto memory 是 Claude 自己记的笔记**（user/feedback/project/reference 四类，带 type 字段），存于 `~/.claude/projects/<project>/memory/`，MEMORY.md 索引每会话只载前 200 行/25KB，worktree 共享，默认开启（`/memory` 关闭）。
13. **检索靠索引**：索引常驻，主题文件按需读取——索引让上下文窗口保持小。
14. **四个记忆命令**：`/memory`（浏览/编辑/删除/禁用）、`/context`（看加载了哪些指令文件）、`/init`（生成起步 CLAUDE.md）、`/doctor`（找出不该进 CLAUDE.md 的内容）。
15. **记忆有成本**：每个永久 token 都是每次会话要付的租金，记忆与任务争抢同一窗口；过期记忆比没有更糟——像对待代码一样 review、prune、进版本控制。
16. **六大核心工具**：Read（最常用）、Search（grep/glob）、Fetch（引入不可信文本）、Edit/Write（第一个有后果的工具）、Shell（未沙箱 = 整机）、Delegate（返回摘要的子智能体）——模型自选；作业 2 亲手实现。
17. **四种扩展机制互不可替代**：Skill 决定怎么做、MCP 触达外部、Hook 在生命周期事件上强制（reasoning 不是事件）、Plugin 打包分发；skill 的 description 会话开始就加载、body 运行时才加载。
18. **发布工作流是四机制的最小示例**：流程→Skill、GitHub release→MCP、测试失败阻止发布→Hook、整套共享→Plugin。
19. **MCP 本质**：无状态开放协议，消除 N×M 集成；client 每 server 一条连接，server 把系统能力暴露为 tools；对本地工具「同名同 schema 同契约，只是另一个进程」。
20. **MCP 三原语**：tools（动作）、resources（可读数据，如 `github://issues/123`）、prompts（模板，Claude Code 中呈 `/mcp__github__triage_issue 123 high` 形式的命名空间斜杠命令，用户可控）。
21. **MCP 安全五原则**：最小权限、读写分离（变更过审批）、不信任工具输出、安装前审查（防 prompt injection）、连接前先问「能读什么、能改什么」。
22. **MCP gateway**：像 API gateway 但说 MCP（tools/list、tools/call、resources、prompts、schemas、协议版本）；聚合/路由/策略/身份/观测/扩展六职能，对客户端看起来只是又一个 server；是信任边界。
23. **Spec 2026-07-28 为发布以来最大修订**：无状态内核（任意请求落任意实例，普通负载均衡即可）、`Mcp-Method` 头免读 body 路由 + list 结果 TTL 缓存、Tasks 与 MCP Apps 转为扩展。
