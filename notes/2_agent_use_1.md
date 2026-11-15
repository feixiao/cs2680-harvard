# 第 2 讲：用户视角的智能体 I —— Claude Code 如何工作

> 原讲义：*Agent From a User's Perspective I: How Claude Code Works*（Harvard CS2680 Modern AI Systems: Agents and System Optimizations，Juncheng Yang）

## 本讲概览

本讲从用户视角拆解 Claude Code：当你敲下一条 prompt 时，背后是一条「收集上下文 → 模型提出动作 → harness 执行工具 → 结果折回上下文」不断重复的 agentic loop（智能体循环）。随后讲 harness 如何借助记忆（memory）、核心工具（tools）与四种互不替代的扩展机制（Skill / MCP / Hook / Plugin），把无状态的 LLM 变成 agent。结尾为可选内容：MCP 协议深入。

## 一、课程更新

- LLM 背景课移后：先把 LLM 当作「magic reasoning box」，学智能体不需要懂模型内部；新增两讲 agent design，减少 GPU 讲次（与其他课程重叠）。
- 无强制论文展示：Assignment 1 分享改为加分项；计分转向课堂参与（participation）+ 项目（project）。
- 参与分：课堂提问/回答，每节课至多 1 分，课后找 TF 登记；新 TA：Advaith Ravishankar；额外阅读为可选（optional / ADVANCED 自读即可）。

## 二、Agentic Loop：一条 Prompt 背后发生了什么

- **一次 prompt = 多次模型调用 + 多次工具执行**，不是单次请求。循环三步：Gather context（prompt、文件、工具结果）→ Generate action（run a tool: bash, read, edit）→ Run tool（跑测试、拿输出、重读状态），然后重复——**每一步都以上一步的返回为条件**；系统分三个区域：harness / model / your machine。
- **敲下第一个字符之前，上下文已有 10+k tokens**：SYSTEM（Claude Code 指令）+ PROJECT（环境）+ MEMORY（CLAUDE.md）+ TOOLS（Read, Edit, Bash, Glob, Grep, Web, Agent）+ SKILLS/MCP（**初始只有名字和描述**，完整正文等真正用到时才加载）+ USER（如 "Fix the failing auth test"）。
- **仓库不会被发送**：几千个文件留在磁盘，Claude 按需拉取切片——如 `Grep("authentication")` 只把几行匹配内容读进上下文。
- **Model proposes, harness executes**：模型只发出请求（如 `Bash("pytest")`），harness 解析、检查权限（permissions）并执行；stdout/stderr 作为 tool_result 回到模型上下文。
- **一个用户轮次展开为推理-工具交替链**：U → M₁ → T₁ → M₂ → T₂ → … → Mₙ → A；实践示例：read → edit session.py → pytest → grep → create_session → pytest → all green。
- **权限层位于意图与执行之间**：工具请求只是「提案」（proposal），结果是 allowed（直接跑）/ ask（先确认）/ denied（什么都不发生）；模式含 Manual、Accept Edits、Bypass permission、Auto（由小模型检查），例：`Bash("rm -rf build/")`。
- **上下文增长后被压缩（compaction）**：典型上下文 1M tokens（Sonnet / Opus / Fable、GPT 5.6；今年早些时候 256K 还常见）；**前缀缓存读（prefix-cache reads）占成本大头**。每步都在追加 token，膨胀后把旧轨迹总结掉、重新注入 CLAUDE.md 与 memory。上下文管理是 harness 设计的重要部分（下周讨论）。

## 三、记忆：从无状态 LLM 到有状态智能体

- LLM 是 stateless 的，每个会话从零开始；实践中「记忆」= **会话启动时加载的文件**。Context 是工作记忆（随会话死亡），persistent memory 跨会话保留并重新加载。「Every memory creation is a decision about what gets re-read forever.」
- 为什么需要记忆：重复解释 setup（repeated instructions）、压缩后丢失「为什么」(lost decisions)、反复重读文件重新认识布局（repeated discovery）、不同会话行为不一致（inconsistent behavior）。总结：「Memory is how instruction becomes convention.」
- 两个系统都**在每次会话开始时**加载进上下文：

| | CLAUDE.md 文件 | Auto memory |
|---|---|---|
| Who writes it | You | Claude |
| What it contains | Instructions and rules | Learnings and patterns |
| Scope | Project, user, or org | Per repository, shared across worktrees |
| Loaded into | Every session | Every session (first 200 lines / 25KB) |
| Use for | Standards, workflows, architecture | Your preferences, corrections, project context |

- **CLAUDE.md 四级层级**（broadest-scope first，最近的最后读）：① Managed policy `…/ClaudeCode/CLAUDE.md`（org-wide，**不可排除**）→ ② User `~/.claude/CLAUDE.md` → ③ Project `./CLAUDE.md` 或 `./.claude/CLAUDE.md`（经 source control 团队共享）→ ④ Local `./CLAUDE.local.md`（gitignored）。
- **只写 agent 无法廉价推断（cannot cheaply infer）的事实**：Commands（build / 测试 / linter 怎么跑）、Hard constraints（never commit to main、never edit generated files）、Layout / ownership / gotchas。不写：模型已知的语言框架知识、linter/formatter 已强制的风格、长散文与 changelog、机密。纪律：每文件 **< 200 行**（"context is rented, memory is owned"）、Markdown 标题+要点、具体规则、无矛盾过期规则。
- **太长了？拆进 `.claude/rules/`**：一文件一主题 + `paths:` frontmatter，**只在 Claude 触碰匹配文件时加载**（无 paths 则每会话都加载）；CLAUDE.md 保持短小，细节下沉到 rules。
- **Auto memory（Claude 自己的笔记）**：存于 `~/.claude/projects/<project>/memory/`，四类：user（你的角色/偏好）、feedback（你的纠正）、project（进行中工作、代码外的决定）、reference（项目外信息），每文件带 type 字段；`MEMORY.md` 是索引，每会话只载前 200 行 / 25KB；worktree 共享目录；默认开启，`/memory` 可关闭。
- **检索靠索引**：session starts → load MEMORY.md → identify relevant topic → 按需 read topic file → apply。索引常驻，只有任务相关的主题文件被读入——与 skill 的按需加载同一设计。
- **四个命令**：`/memory`（浏览/编辑/删除/禁用）、`/context`（查看加载了哪些指令文件）、`/init`（生成起步 CLAUDE.md）、`/doctor`（找出可能不该进 CLAUDE.md 的内容）。
- **记忆的成本**：上下文有限 + 每个发给 Anthropic 的 token 都要付费——**每个永久 token 都是租金**，每次会话开始都付一次；记忆与任务争抢同一窗口；**过期记忆比没有更糟**（会主动误导）。对待记忆要像代码：review、prune、进版本控制。

## 四、核心工具

| 工具 | 功能 | 备注 |
|---|---|---|
| Read | 打开文件、检查状态 | 最常用 |
| Search | grep 和 glob | 不读全部文件就能找到目标 |
| Fetch | 拉取网页/文档 | 把不可信文本带进上下文（untrusted text） |
| Edit / Write | 修改文件 | 第一个有后果（consequences）的工具 |
| Shell | build、test、git | 未沙箱化 = 整机（the whole machine） |
| Delegate | 派生子智能体 | 只返回摘要 |

- 模型自己决定用哪些工具，你基本不需要做什么；**作业 2（Assignment 2）里你会亲手实现这些工具**。

## 五、扩展机制：Skill、MCP、Hook、Plugin

- 四种机制解决四个不同问题，**互不替代**：

| 机制 | 回答的问题 |
|---|---|
| Skill | How the agent should perform a task |
| MCP | Which external data and actions it can reach |
| Hook | What happens automatically at a lifecycle event |
| Plugin | How the extensions are packaged and distributed |

- 各挂在循环不同位置：Skill 在模型推理阶段提供 knowledge and procedure；MCP 在工具选择阶段提供外部工具；Hook 可在循环任意阶段 inspect / block / react；Plugin 把 skills + MCP servers + hooks 打包成一个可安装单元。口诀：skill 决定 how、MCP 触达 outside、hook 强制 enforce、plugin 分发 distribute。
- 发布工作流示例（prepare → validate → publish to GitHub → notify team）：遵循发布流程 → Skill；创建 GitHub release → MCP；测试失败时阻止发布 → Hook；分享整套配置 → Plugin。
- **Skill = 可复用程序（上下文工程）**：结构是文件夹——`SKILL.md`（frontmatter: name + description；body 承载程序）+ `references/` + `scripts/`，例 `.claude/skills/release/`；**description 控制发现**（会话开始就加载），**完整 body 只在 skill 运行时加载**；可 model-invoked（description 与任务匹配）或 user-invoked（`/release`）；**有副作用的工作流通常应要求显式调用**；清晰互异的 description 减少错误选择。
- **MCP = 外部能力层**：标准协议把 agent 连到外部服务（GitHub、数据库、监控、Figma、Slack、浏览器）——给的能力既不在模型里也不在本地文件里。一次调用六步：Claude 识别动作 → MCP client 调 tool → MCP server 处理连接 → 外部服务执行 → 结构化结果返回 → Claude 评估。**几乎与本地工具相同**（同 name / description / typed schema，同 call-and-return 契约，只是跑在另一个进程里）；协议承载调用，是否发起仍由 agent 决定。
- **Hook = 生命周期自动化**：会话时间线事件为 session start → user prompt → tool call → tool result → model reasoning → stop（reasoning **不是** hook 事件）；hook 按事件触发，可执行命令、HTTP 请求、MCP 工具、prompts 或子智能体。
- **Plugin = 打包层**：一个可安装单元，含 `skills/ hooks/ agents/ .mcp.json .lsp.json .claude-plugin/plugin.json`；好处：一条命令安装、版本钉住、命名空间（无冲突）、团队复用、经 marketplace 分发。「A plugin is how a working setup becomes something other people can install.」
- **`.claude/` 目录**：Memory（CLAUDE.md、rules/）· Configuration（settings.json、settings.local.json：permissions/hooks/env）· Workflows（commands/、skills/）· Delegation & guardrails（agents/、hooks/）。`~/.claude/` 有同样的用户作用域布局，**项目设置优先于用户设置**。
- 设计练习（分类需求）：应用公司 API 约定 → Skill；从 Jira 读 issue → MCP；每次编辑后跑格式化 → Hook；引导多步部署 → Skill；发送完成通知 → Hook plus MCP；阻止写入生产 → Hook or policy；跨仓库共享一切 → Plugin。

## 六、可选幻灯片：MCP 深入

- **为什么有 MCP**：要访问外部服务（Gmail、GitHub…）；MCP 之前是 N×M 实现，MCP 避免了为每个 AI 客户端各写一套集成。定义：**开放的、无状态的协议**，让 AI 应用发现并使用外部服务器暴露的能力（modelcontextprotocol.io）。
- **架构四角色**：Host（如 Claude Code）运行 MCP client（**每个 server 一条连接**）↔ MCP server（把系统能力暴露为 tools）↔ External system（GitHub、Slack、PostgreSQL、本地服务）。
- **三大原语**：Tools = Claude 可调用的动作（`create_issue(…)`）；Resources = 服务器暴露的可读数据（`github://issues/123`）；Prompts = 可复用模板（`triage_issue(…)`），返回指令、**用户可控**，在 Claude Code 中呈现为命名空间斜杠命令（如 `/mcp__github__triage_issue 123 high`）。协作示例（triage issue #123）：prompt 给流程、resource 给 issue 内容、tool 给诊断信息。
- **安全五原则**（连接后的 server 能看到你发的内容并用你的凭据行动）：Least privilege（token 作用域限到真正需要的 repo/表/频道）；Read vs write（变更留在审批之后）；Distrust tool output（绝不把返回内容当指令，即防 prompt injection）；Vet before installing（第三方 server 可能携带注入）；Ask before connecting（能读什么？能改什么？）。
- **MCP gateway（网关）**：AI 客户端与一个或多个 MCP server 之间的控制层（auth · policy · logging · routing · rate limits），像 API gateway 但说 MCP（tools/list、tools/call、resources、prompts、schemas、协议版本）；做六件事：Aggregate（一条连接、命名空间目录 github.* / jira.* / postgres.*）、Route（用 `Mcp-Method` 头路由、**不读 body**）、Enforce policy（谁能连、哪些工具可调用/需审批）、Broker identity（客户端认证一次、上游凭据藏在网关后）、Observe（中央审计：身份/工具/决策/延迟/成本）、Scale（负载均衡、重试、熔断、目录缓存、配额）；**对客户端看起来就是又一个 MCP server**；用户/agent/server/凭据多、合规需统一治理时值得上，但它同时是一个信任边界。
- **Spec 2026-07-28（发布以来最大修订）**：Stateless core（无会话，任意请求落任意实例，普通负载均衡即可）；Routing（`Mcp-Method` 头免读 body 路由，list 结果可带 TTL 缓存）；Extensions（长时任务的 Tasks 与服务端渲染 UI 的 MCP Apps 以扩展形式提供）。

## 核心要点

1. 一次 prompt ≠ 一次请求：agentic loop = 收集上下文 → 模型提议动作 → harness 执行 → 结果折回上下文，循环直到任务完成，每步以上一步为条件。
2. 敲下第一个字符前上下文已有 10+k tokens：系统指令、项目环境、CLAUDE.md、工具 schema、skill/MCP 的名字与描述。
3. 仓库从不整体发送，只把按需拉取的切片（如 grep 的几行）读进上下文。
4. Model proposes, harness executes：模型只发请求，harness 解析、查权限、执行，tool_result 回到模型上下文。
5. 权限层把工具请求判为 allowed / ask / denied；模式含 Manual、Accept Edits、Bypass permission、Auto（小模型检查）。
6. 典型上下文 1M tokens（Sonnet / Opus / Fable、GPT 5.6；年初 256K 常见）；prefix-cache 读占成本大头；compaction = 总结旧轨迹 + 重新注入 CLAUDE.md 与 memory。
7. LLM 无状态，记忆 = 会话启动时加载的文件；「每次写记忆都是决定什么会被永远重读」；记忆把一次性指令变成长期惯例。
8. CLAUDE.md 四级层级（managed / user / project / local），最宽作用域先加载、最近的最后读；只写 agent 无法廉价推断的事实，每文件 < 200 行。
9. 太长拆进 `.claude/rules/`（一文件一主题 + `paths:` 作用域加载）；auto memory 是 Claude 自己记的笔记（user/feedback/project/reference），MEMORY.md 索引常驻、主题文件按需读，每会话只载前 200 行 / 25KB。
10. 记忆有成本：每个永久 token 都是每次会话的租金，与任务争抢同一窗口；过期记忆比没有更糟——像代码一样 review、prune、进版本控制；`/memory` `/context` `/init` `/doctor` 四个命令检查与控制。
11. 六大核心工具：Read（最常用）、Search、Fetch（引入不可信文本）、Edit/Write（第一个有后果的）、Shell（未沙箱 = 整机）、Delegate（返回摘要的子智能体）；模型自选，作业 2 亲手实现。
12. 四种扩展机制互不替代：Skill = how（知识与程序，description 常驻、body 按需）、MCP = reaches outside（外部能力，与本地工具同契约、跑在另一进程）、Hook = event automation（reasoning 不是事件）、Plugin = packaging & distribution。
13. MCP：无状态开放协议消除 N×M 集成；client 每 server 一条连接；三原语 tools / resources / prompts；安全关键是最小权限、读写分离、不信任工具输出、安装前审查。
14. MCP gateway 像 API gateway 但说 MCP，做聚合/路由/策略/身份/观测/扩展六件事，对客户端只是又一个 server，是信任边界。
15. Spec 2026-07-28 为发布以来最大修订：无状态内核（普通负载均衡）、`Mcp-Method` 头路由 + list 结果 TTL 缓存、Tasks 与 MCP Apps 转为扩展。
