# 第 3 讲：用户视角的智能体 II(多智能体与最佳实践)

> **Agent From a User's Perspective II: Multi-agent and Best Practice** · Harvard CS2680 · 讲师 Juncheng Yang
> 原始幻灯片:[3_agent_use_2.pdf](../3_agent_use_2.pdf)

## 本讲概览

本讲在上一讲单个智能体机制(agentic 循环、上下文作为工作记忆、skill/MCP/hook/plugin 四类扩展)之上做"放大"。先用两个真实插件案例(Superpowers、Caveman)演示扩展机制如何组合,其中 Caveman 还加入一个本地压缩代理;再讲多智能体规模化的四条路(手工 worktree 并行、subagent、agent team、动态 workflow)与两个长时机制(`/goal`、`/loop`);随后提出"编程 3.0 / Software 3.0",核心论点是:不确定性是核心主题,要指望周围系统可靠而非智能体本身;最后用 OpenAI Codex 2026 年 6 月与 9 月的两份报告展示"从对话到委派"的真实采用曲线。

## 一、课程通知与上讲回顾

- **通知**:Assignment 1 截止 + A1 分享报名;把讲师和 TF 加进作业仓库。新增 TF:Charles Wang。
- **上讲回顾**:Agent 循环与状态管理;上下文作为工作记忆(用户 prompt、LLM 响应、工具结果都被追加);跨会话持久记忆(CLAUDE.md / AGENTS.md、auto memory);内置工具与扩展机制:skill、MCP、hook、plugin。

## 二、案例研究:Superpowers

软件开发插件,`/plugin install superpowers@claude-plugins-official`(github.com/obra/superpowers)。核心论点:**同一模型、不同工作流(Same Model, Different Workflow)**——两个 agent 共享同一模型与同一组工具,只有指令(instructions)不同:

| | 对同一个 feature request |
|---|---|
| DEFAULT | 直接开始编码 → 靠迭代修复 |
| Superpowers | 1 澄清问题 → 2 批准设计 → 3 写详细计划 → 4 测试驱动构建(TDD)→ 5 评审并验证 → 6 集成分支 |

- **九个 skill**:using-superpowers(发现与调用规则,即 bootstrap skill)、brainstorming(请求 → 被批准的设计)、writing-plans(设计 → 具体任务)、using-git-worktrees(隔离工作区)、test-driven-development(强制 red/green/refactor)、systematic-debugging(先找根因)、requesting-code-review(对照计划评审)、verification-before-completion(报告成功前要求证据)、finishing-a-development-branch(合并/PR/清理)。
- **Plugin 是分发容器,skill 与 hook 提供行为**(A plugin is the distribution container — skills and hooks supply the behavior):仓库含 `.claude-plugin/plugin.json`、`hooks/session-start`、`skills/`、`tests/`。
- **Skill 解剖**:front matter 是元数据(name、description),正文是智能体遵循的流程。skill 文件六组件:name、description、instructions(流程)、checkpoints(审批门)、references(按需加载的细节)、scripts(确定性操作)。流程型(process)skill 可定义:必需动作、禁止动作、人工审批门、验证要求,以及**指名下一个适用的 skill**——由此把各 skill 串成一条受控流程。
- **为什么只有 skill 不够**:安装只是"可用"(available),可用不保证智能体会去检查。Superpowers 用 **SessionStart hook**(matcher: `startup|clear|compact`)把 bootstrap SKILL.md 内容作为 `additionalContext` 注入:每个会话都确定性触发、在 agent 行动前运行、且在 clear 和 compaction 之后重新注入。
- **端到端走查("Add authentication")**:hook 注入 bootstrap → agent 接收选择策略 → 用户请求 → 加载 brainstorming 澄清 → 用户批准设计 → 加载 writing-plans 出实现计划 → 隔离 worktree → TDD 构建 → 代码评审 → 验证 → 分支集成。每一步由"skill 指名后继 + 人工审批门"驱动,而非模型自由发挥。
- **设计教训**:复杂行为 → 小而可组合的 skill;让 agent 记得使用 → session hook 注入 bootstrap;上下文可控 → 只在相关时加载任务 skill;阶段协调 → 每个 skill 指名自己的门与后继;安装 → 整体打包为 plugin;command/MCP 并非必需,只在需要时加。

## 三、案例研究:Caveman

安装:`claude plugin marketplace add JuliusBrussee/caveman` + `claude plugin install caveman@caveman`。主题:**压缩智能体的 token**——"五个扩展机制 + 一个本地代理"的完整示范。

- **为什么压缩**:日志、diff、工具输出挤占工作空间(示例:一次 `npm test` 输出 786 行);token 既付费又等待;事后 compaction 会丢细节。策略:**双向压缩(输入+输出),且保留原文可随时取回**——模型实际读到的从 786 行测试输出变成 `3 tests fail: ETIMEDOUT at client.ts:88`。
- **两个方向**:skill 改变模型**怎么写**(输出方向),本地代理改变模型**读什么**(输入方向)。报告输出 token 减少 **65%**;但 skill 本身增加输入 token,整场会话的净节省更低。
- **响应 skill**(`skills/caveman/SKILL.md`):保留技术术语、命令、路径、代码、报错、数字、单位、否定词;删除填充词、重复、客套、含糊其辞;短句、主动语态。
- **Commands 给用户显式控制**:`/caveman [lite|full|ultra|off]`(未给档位默认 full),以及 `-commit`、`-review`、`-compress`、`-stats`、`-help`。
- **Hooks 让 prompt 时的选择持久化**:SessionStart → `caveman-activate.js`(为本会话决定模式、安全存储状态、作为隐藏上下文注入规则、compact 后恢复、清理旧状态);UserPromptSubmit → `caveman-mode-tracker.js`(检查每条用户 prompt,检测 `/caveman ultra` 或"normal mode"之类短语,更新会话模式)。
- **MCP 把压缩暴露为可调用工具**:`caveman_compress`(压缩 + 返回 recovery handle)、`caveman_retrieve`(按句柄取回逐字节一致的原文)、`caveman_stats`、`caveman_toon_encode/decode`(JSON↔TOON)。结果示例:`{"compressed": "3 tests fail. Root error: timeout.", "ratio": 0.72, "recovery_handle": "ccr_abc123"}`。
- **本地代理(agent → 本地代理 → 模型提供商)做类型感知压缩(type-aware)**:日志留错误/堆栈/头+尾;代码留 imports/签名/类型/函数体;diff 留文件+hunk 头与变更行;JSON 留键/结构/错误子树;搜索留高价值匹配与诊断;HTML/文本留标题与相关段落。
- **代理 vs MCP vs hook**:代理拦截**每一个**请求(MCP 只在被调用时运行)、位于智能体与提供商**之间**(MCP 在旁边)、能改变上下文本身(MCP 不能);hook 能拦截请求但**不能透明地改写发往 LLM 的请求**——要透明改写必须用代理(除非自己写 harness)。
- **架构总图**:plugin 是唯一安装/更新单元;机制层 = skills(简洁风格、聚焦工作流)+ commands(选模式、发操作)+ hooks(激活、跟踪、强化模式)+ MCP(压缩、取回、统计、编码);状态与引擎 = 会话模式状态 + 压缩引擎;拦截层 = 本地代理。

## 四、用多个智能体成为 100 倍工程师

开场反问"如何两小时做完作业"(到场 + 保持清醒?),答案是**多个长时运行的智能体(multiple long-running agents)**;并提醒:**智能体并行扇出,账单也扇出(Agents fan out in parallel. So does the invoice.)**

### 4.1 规模化的三个轴

| 轴 | 机制 | 买到什么 |
|---|---|---|
| 并行智能体 | 多个独立任务,各在隔离 worktree | **范围(scope)**:更少干预下做更多工作 |
| 子智能体(subagents) | 把有界任务委派给全新上下文,拿回摘要 | **吞吐 + 专注**:父智能体永远不见中间混乱 |
| 长时智能体 | 让大任务跨许多步推进 | **时间(duration)**:墙钟时间,而非答案质量 |

Agent team 与 dynamic workflow 是把这些轴组合起来。

### 4.2 手工并行:git worktree

- 一个会话一个任务,各在自己的 **git worktree**(独立工作目录+分支,共享仓库历史):`claude -w feature-payments`;`claude -w bugfix-auth`。
- 一份共享历史、多个检出;一个会话的编辑绝不碰到另一个会话的文件;不用 stash、不用二次 clone;桌面版中每个新会话自动获得 worktree。
- **天花板**:计划在你脑子里(会话间互不可见,交接只有你能带过去);分支冲突由你对齐;运行过程什么都没写下来,不可复现。**"计划你能持有多少:3 个会话 = 你;20 个会话 = 你 + 一个克隆的你。"**

### 4.3 Subagents

- 定义:**拥有自己上下文窗口、工具与权限的专用助手**。五大好处:保护主上下文(日志、搜索结果、文件转储留在主对话外);约束可用工具与模型;面向领域的聚焦 prompt 可跨项目/团队复用;独立子任务并发(总时间 = 最慢者);路由到更快更便宜的模型(frontmatter 里 `model: haiku`)。
- **内置三个**:Explore(只读搜索,Write/Edit 被拒绝,每次调用可设 thoroughness)、Plan(plan 模式研究,让探索远离主窗口)、General-purpose(探索+行动的复杂多步工作)。Explore 与 Plan 会跳过 CLAUDE.md 和 git status 以保持快速便宜。
- **定义**:带 YAML frontmatter 的 Markdown 文件,正文即 system prompt。项目作用域 `.claude/agents/`(check 进版本控制,团队共享),用户作用域 `~/.claude/agents/`。
- **嵌套**:frontmatter 的 `tools` 中必须出现 `Agent` 才能派生子代;最多 5 层,**2–3 层是甜点区**。常见模式:Level 0 主智能体持计划 → Level 1 implementer/debugging/review → Level 2 test-writer/verification;**每一层从全新上下文开始,只返回摘要**。
- **显式委派三档(控制递增)**:自然语言("Use the test-runner subagent to fix tests",一次性,模型自决是否委派)→ `@agent-code-reviewer`(单任务保证运行)→ `claude --agent code-reviewer`(整会话采用其 prompt/工具/模型)。
- **留主对话还是委派?**subagent 从全新上下文起步:看不见历史,还要付收集上下文的延迟成本。留主对话:迭代来回、共享上下文的阶段、快速精准修改、延迟敏感、简单活(可交给小模型)。委派:不会复用的啰嗦输出、工具/权限限制、返回摘要的自包含工作、并行独立工作。**想要主上下文里可复用的流程?用 Skill。**

### 4.4 Agent Teams

- 定义:多个 Claude Code 会话协作——**一个 lead,若干 teammate**。实验性,**默认关闭**(code.claude.com/docs/en/agent-teams)。
- 四种典型用法:Review(队友从不同角度探查并互相质疑);Independent(各管一块,互不踩脚);Debugging(竞争性假设并行测试,收敛更快);Cross-layer(前端/后端/测试各归一个队友)。
- **接线四部分**:team lead(主会话:派生队友、协调、综合结果);teammates(独立实例,各有自己的上下文窗口);共享 task list(队友认领并标记完成);每个 agent 一个 JSON mailbox。**teammate 直接互相说话,且不继承你的对话**——自动加载 CLAUDE.md 与 skills,任务细节写进 prompt。
- **vs Subagents**:subagents 自己的窗口、只回传调用方、lead 管理、token 成本低、适合"只要结果"的任务;teams 独立窗口、队友互聊、共享任务清单、成本更高、适合需要讨论的工作。**Teams 更贵——只有工作真的需要讨论时才用**;顺序任务、同文件编辑或强依赖 → 用一个会话或 subagent。

### 4.5 Dynamic Workflow

- 一段 **JavaScript 脚本**在后台编排许多 subagent;当任务需要的 agent 数超过一个对话能协调时使用(全代码库 bug 扫描、500 文件迁移、多角度核查的研究、多方案计划)。
- 两种启动:在 prompt 中输入 `ultracode`,或 `/effort ultracode` 让 Claude 自己决定;两条路都派生大量 subagent——plan、design、implement、review。**是脚本持有计划,而不是聊天(a script holds the plan, not the chat)。**

### 4.6 长时智能体

- **`/goal "npm run lint exits with zero errors"`**:交出一个**可验证的终态**;evaluator 在每次尝试后重新检查条件再把 Claude 放回去;目标达成或 `--max-tries` 耗尽时自停。"all integration tests pass" 可验证;"refactor the code" 不行。
- **`/loop 5m "check CI, fix whatever broke"`**:触发器而非测试——交出间隔,prompt 原样重跑,直到你按 Esc;可在 `.claude/loop.md` 放默认 prompt。**/goal 在条件成立时停;/loop 在你要求时停。**
- 小结:四种"更多 agent 同时跑"(手工并行 / subagents / teams / workflows)+ 两种"一个 agent 跑更久"(/goal / /loop)。

## 五、(可选)案例:16 个智能体造了一个 C 编译器

- 能构建 Linux 内核的 Rust 语言 C 编译器——**16 个 agent、约 2,000 个会话、两周;2B 输入 / 140M 输出 token;API 成本略低于 $20,000**(anthropic.com/engineering/building-c-compiler)。
- 结果:约 100,000 行代码;构建 Linux 6.9(x86、ARM、RISC-V);跑通 QEMU、FFmpeg、Postgres、Redis、Doom;主要测试套件约 99% 通过。
- 协调**只靠普通基础设施——容器、Git、文本文件**(Plain infrastructure — containers, Git and text files — did the orchestration):每个 agent 在隔离容器 + 自己的 Git checkout;通过**简单锁文件**认领任务;新会话读进度文档恢复上下文;专门 agent 负责文档/性能/质量/去重;自动化测试作为进度信号。
- **Git 即协调层**:没有聊天、没有管理者 agent——clone、扫文档、读仓库、认领任务(锁文件)、实现、测试、合并推送、解锁,循环重复;agent 自己挑下一个显而易见的任务,**Git 裁决重复认领、冲突自动了结**;README/进度文档/CI 失败等制品为新会话承载上下文。
- 但**成功而不完全**:合并冲突仍频繁;所有 agent 撞上同一个内核失败后并行不再有帮助;16-bit x86 部分仍依赖 GCC;生成代码效率低于 GCC 输出。**Agent 还不完美,你前面还有更多工作。**

## 六、编程 3.0 / Software 3.0

- **Programming 3.0(讲师自己的定义,与 Karpathy 的不同)**:1.0 编程硬件(人 → 显式机器指令/汇编 → 硬件);2.0 编程语言(加编译器,买生产率、引入不确定性);3.0 **表达目标**(人 → 自然语言 → Agent → 机器)。
- **Software 3.0(Andrej Karpathy)**:1.0 = 源代码(写 Python/C++);2.0 = 神经网络权重(收集数据 + 优化);3.0 = LLM prompt(自然语言)。引用视频:*Software Is Changing (Again)*。**"知道 1.0、2.0、3.0 之间边界画在哪里,是一项重要的工程技能。"**
- **不确定性是核心主题,要学会与它共处**。它不是新事物(同源代码 ≠ 同输出早已存在),三源对照:硬件(32/64 位、字节序;2.0 靠定宽类型/交叉编译/虚拟化,3.0 新增 GPU 非确定性 kernel、浮点方差)、环境(并发、不可靠网络;2.0 靠内存一致性模型/幂等 API,3.0 新增智能体一边写代码一边触碰环境)、软件(编译器版本、依赖漂移;2.0 靠升级前全面测试,3.0 新增不同 kernel、模型采样)。3.0 链路(人 → LLM/agent → 程序 → 结果)还多了**单一 prompt 带来的含糊输入**。
- **不确定性遍布全栈**:自然语言(语义不确定)→ 检索/上下文(索引更新、分块、截断 = 检索漂移)→ 模型生成(采样、软硬件非确定性)→ agent/工具循环(轨迹/工具失败、环境变化)→ 生成的程序(通常生成后即确定,**除非运行时调用模型或工具**)。
- **最佳实践三步**:① **DEFINE**——先写假设;让模型执行前确认任何含糊处;规定结果、不变量、约束与验收测试,而不只是 prompt。② **CONTROL**——智能体先提计划,任何提交前先验证(提案与执行分离);显式管理上下文:自己的记忆与出处(provenance),让过期信息失效。③ **VERIFY & GOVERN**——收紧"生成–执行–验证"循环,便宜频繁的检查胜过一次昂贵的终末评审;测深一层:造测试、测多指标、用你能推理的合成工作负载。
- 收束纲领:**不要指望智能体是确定性的;要让周围系统可靠(Do not expect the agent to be deterministic; make the surrounding system dependable.)** 自治度与风险匹配:autonomy 越高,不确定性与风险越高。

## 七、一线证据:OpenAI Codex 报告(2026 年 6 月 / 9 月)

- **从对话到委派(From Conversation to Delegation)**:对话式 AI = 人提问、模型回答、**人执行工作**;智能体式 AI = 人委派任务、agent 规划/调工具/编辑文件/运行命令、**人保持参与,评审与集成**(stays in the loop)。近 28 天 Codex 用户中委派者占比:个人 **< 1%**、组织 **17.3%**、OpenAI 员工**几乎全部**;2026 上半年活跃用户增长 **5× 以上**。
- **被委派的任务越来越大**(2025-12 → 2026-05):≥ 1 人时 35.4% → **70.2%**;≥ 8 人时(全天任务)2.1% → **25.6%**——**挑战全天任务的用户增长 12 倍**。
- **一人多 agent(2026-06)**:28.6% 的 OpenAI 用户一周内一天同时跑 5+ agent;OpenAI 员工中位约 **2.5 agent-hours/天**,第 99 百分位约 **71 agent-hours/天**(较 4 月 +88%)。**人的角色转为:规划者、委派者、监控者、评审者、集成者。**
- (2026-09)**智能体工作日如今远超人类研究员**:2026 年 6 月之前 agent runtime 还落后于人力,**如今 agent 做的工作是人的 3.14 倍**;多数研究员同时有 4+ 条并行 workflow。另两页(图表):工程师交付速度**接近 8×**;agent 解决越来越复杂的任务,但**人类介入仍然必要**。来源:*The Shift to Agentic AI: Evidence from Codex* 与 *Research acceleration: The view inside OpenAI*。
- **委派阶梯(Delegation Ladder)**:1 Chatbot(AI 回答,人干活)→ 2 Assistant(人与 AI 一起做)→ 3 Agent(委派一整块工作)→ 4 Multi-agent worker(人协调多个 agent)→ 5 Systematized workflows(skills 与 agents 运行流程)。**OpenAI 的员工目前仍集中在阶梯底部。**

## 八、(可选)CLI 编码智能体生态(2026 年中)

- *State of CLI Coding Agents, Mid-2026 (July 2026)* 四个象限:**模型实验室**(model + harness 一体:Claude Code、Codex CLI、Antigravity CLI、Grok Build、Mistral Vibe、Kimi Code、Qoder 等);**平台 CLI**(嵌在开发栈:Copilot CLI、Cursor CLI、Amp、Auggie、Droid、Junie CLI 等);**开源**(自带 key:OpenCode、Crush、Goose、Aider、Cline、Kilo、Continue、OpenHands、Reasonix、Qwen Code、Codebuff、CodeBuddy 等);**最小内核**(小而可审计:Deepseek Harness、Pi · oh-my-pi (Omp)、mini-SWE-agent、gptme、Open Interpreter)。
- **差异五轴**:开放 vs 封闭(开放:Codex CLI、OpenCode、Goose、Cline、Pi;封闭:Claude Code、Copilot CLI、Cursor、Droid、Junie);锁定 vs BYOK(单一供应商:Claude Code、Antigravity CLI、Grok Build;任意端点:OpenCode 75+ providers、Kilo 500+ models);沙箱 vs 提示(OS 沙箱:Codex CLI、Copilot CLI、OpenHands 容器;权限提示:Claude Code 与大多数);本地 vs 云端(本地优先无遥测:Goose、Nanocoder、gptme;云端移交:Copilot CLI、Codex、Mistral Vibe 远程 agent);全功能 vs 极简(功能最全:Omp、Claude Code;仅四个工具:Pi、mini-SWE-agent,约 100 行 Python)。
- 下讲预告:Agent design I(智能体设计 I);提醒找 TF 领取课堂参与分。

## 核心要点

1. **Superpowers 的哲学是"同一模型、不同工作流"**:不换模型不加工具,只用结构化指令把"直接开写、迭代碰运气"变成 澄清 → 批准设计 → 详细计划 → TDD → 评审验证 → 集成 的受控流程;plugin 只是分发容器,skill 与 hook 才提供行为。
2. Skill = front matter 元数据 + 正文流程;流程型 skill 可定义必需/禁止动作、人工审批门、验证要求与后继 skill 指针,九个 skill 由此串成软件开发流水线。
3. **只有 skill 不够**:可用 ≠ 会被检查。Superpowers 用 SessionStart hook(matcher: startup|clear|compact)在每个会话开始、clear 与 compaction 之后确定性地注入 bootstrap skill。
4. Caveman = 五机制 + 本地代理的完整组合:skill 改模型怎么写(报告输出 token −65%),command 给用户 lite/full/ultra/off 显式控制,hook 让模式跨 prompt 与 compact 持久,MCP 提供压缩/取回/统计(recovery handle 可逐字节取回原文),**本地代理透明压缩模型读入的一切**——hook 能拦截但不能透明改写发往 LLM 的请求,透明改写必须靠代理。
5. **规模化三轴**:并行 agent 买范围、subagent 买吞吐 + 专注(父不见中间混乱)、长时 agent 买时间;team 与 workflow 是组合。记住:agent 扇出,账单也扇出。
6. 手工并行的最小单元是 git worktree(共享历史、隔离目录,`claude -w <branch>`);天花板:计划在你脑中、冲突你处理、不可复现——3 个会话你还能持计划,20 个就需要"一个克隆的你"。
7. Subagent = 自己的上下文窗口 + 工具 + 权限 + 模型:保护主上下文、施加约束、跨项目复用、并行化、可路由便宜模型;内置 Explore(只读、跳过 CLAUDE.md 与 git status 以求快省)/Plan/General-purpose;嵌套 ≤5 层、2–3 层为甜点区,且 tools 须含 `Agent`。
8. 显式委派三档控制递增:自然语言(一次性)→ @-mention(单任务)→ `--agent`(整会话)。委派判据:啰嗦输出、权限限制、自包含、并行 → subagent;迭代/共享上下文/延迟敏感/简单活 → 主对话;可复用流程 → Skill。
9. Agent team = lead + teammates + 共享 task list + 每 agent 一个 JSON mailbox;teammate 直接互聊、不继承你的对话;相比 subagent 成本更高,只在工作需要讨论时用(实验性,默认关闭)。
10. 动态 workflow 用一段 JS 脚本后台编排大量 subagent(`ultracode` 或 `/effort ultracode`),适合单对话协调不过来的规模(全库扫描、500 文件迁移、多角度研究)——脚本持有计划,而不是聊天。
11. **/goal 按可验证条件停**(evaluator 每轮重检,`--max-tries` 兜底);**/loop 按你按 Esc 停**(时间触发,`.claude/loop.md` 放默认 prompt)。
12. 16 agent C 编译器:约 $20k、~2,000 会话、两周 → ~100k 行代码、构建 Linux 6.9(x86/ARM/RISC-V)、~99% 测试通过;协调零框架:容器 + **Git(共享状态即协调层)** + 文本文件(锁文件认领、制品承载上下文、Git 裁决冲突);但合并冲突频繁、同一内核失败使并行失效、效率低于 GCC——最后一公里仍需人。
13. 编程 3.0 = 表达目标(人 → 自然语言 → Agent);Karpathy Software 3.0:1.0=源代码、2.0=权重、3.0=prompt;**在 1.0/2.0/3.0 之间画边界是核心工程技能**;不确定性是核心主题,来源遍布 自然语言 → 检索/上下文 → 模型生成 → agent/工具循环 → 生成的程序 全栈。
14. 最佳实践三步:DEFINE(先写假设、模型确认含糊处、规定结果/不变量/约束/验收测试)、CONTROL(提案与执行分离、提交前验证、显式管理上下文与出处、过期信息失效)、VERIFY & GOVERN(廉价频繁检查、测深一层)。纲领:**不要指望 agent 确定性,要让周围系统可靠;自治度与风险匹配**。
15. 一线证据:委派占比 个人 <1% / 组织 17.3% / OpenAI 员工几乎全部;全天任务 2.1% → 25.6%(12×);28.6% 用户同时跑 5+ agent、P99 ~71 agent-hours/天;agent runtime 达人力 3.14×、工程师交付 ~8× 更快,但人类介入仍必要;OpenAI 员工仍集中在五级委派阶梯底部。
