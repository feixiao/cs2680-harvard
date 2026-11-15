# 第3讲：用户视角的智能体 II（多智能体与最佳实践）

> 原讲名：*Agent From a User's Perspective II: Multi-agent and Best Practice*（Harvard CS2680 Modern AI Systems: Agents and System Optimizations，主讲 Juncheng Yang，cs2680.com / course.agentic-system.org）

## 本讲概览

上一讲我们看了单个智能体（Claude Code）内部如何运转：agentic 循环、上下文作为工作记忆、记忆分层，以及 skill / MCP / hook / plugin 四类扩展机制。本讲把这些机制"放大"：先看两个真实插件案例——Superpowers（九个 skill 加一个 SessionStart 引导 hook）和 Caveman（skill、command、hook、MCP 加一个压缩工具输出的本地代理）——理解扩展机制如何在真实产品中组合。然后进入多智能体规模化：git worktree 手工并行、subagent、agent team、动态 workflow，以及 `/goal`、`/loop` 两个长时运行机制，并用一个 16 个智能体花约 2 万美元造 C 编译器的真实案例说明靠 Git 就能做协调。再讲"编程 3.0"与 Karpathy 的 Software 3.0，核心论点是：自然语言编程的不确定性是主题，所以要把智能体周围的系统做可靠。最后用 OpenAI Codex 2026 年 6 月与 9 月的两份使用报告，展示"从对话到委派"的真实采用曲线，并以 CLI 编码智能体生态综述作可选收尾。

## 一、课程通知与上讲回顾

- **通知**：Assignment 1 截止（due），同时开放 A1 分享（sharing）报名；要求把讲师和 TF 加到作业仓库。新增 TF：Charles Wang。课程站点：Harvard Madsys / course.agentic-system.org。
- **上讲回顾（Recap）**：
  - Agent loops 与状态管理；上下文作为工作记忆——每个用户 prompt、LLM 响应、工具调用结果都被追加（append）进上下文；
  - 智能体记忆：跨会话持久，包括 CLAUDE.md（或 AGENTS.md）与自动记忆（auto memory）；
  - 工具：内置工具，以及扩展 Claude Code 能力的四类机制：skill、MCP、hook、plugin。
- **本讲计划（Plan for Today）**：
  1. 案例研究：Superpowers 与 Caveman；用多个智能体成为 100 倍研究员/工程师；
  2. Programming / Software 3.0：编程是如何演化的；
  3. 人们如何使用 OpenAI Codex——两份报告，分别来自 2026 年 6 月和 2026 年 9 月。

## 二、案例研究：Superpowers

### 2.1 安装与核心理念：同一模型，不同工作流

Superpowers 是一个软件开发插件，安装命令：

```
/plugin install superpowers@claude-plugins-official
```

仓库地址：https://github.com/obra/superpowers

幻灯片的中心论点用一张"同一模型、不同工作流（Same Model, Different Workflow）"的表来说明。对于同一个 "Feature request"（功能请求）：

| | 阶段 | DEFAULT（无 Superpowers） | Superpowers |
|---|---|---|---|
| HUMAN | 0 | 人输入 prompt | 0 — 人输入 prompt |
| — | — | 直接开始编码，靠迭代修复 | — |
| PLAN | — | — | 1 — 澄清问题；2 — 批准设计 |
| BUILD | — | — | 3 — 写详细计划；4 — 测试驱动构建；5 — 评审并验证 |
| SHIP | — | — | 6 — 完成或集成分支 |

幻灯片强调：**两个智能体共享同一个模型和同一组工具——只有指令（instructions）不同**。也就是说，Superpowers 没有换更强的模型，只是用结构化指令把"直接开写、靠迭代碰运气"变成"澄清 → 批准设计 → 详细计划 → TDD 构建 → 评审验证 → 集成"的确定性流程。这是理解后面全部内容的钥匙：harness/指令层本身就能显著改变行为质量。

（此页后紧跟一页纯图示页，无文字层内容，应为 Superpowers 的工作流/仓库示意图。）

### 2.2 Superpowers 的九个 Skill

| Skill | 职责（Responsibility） |
|---|---|
| using-superpowers | 发现并调用 skill 的规则（bootstrap skill） |
| brainstorming | 把请求转化为一份被批准的设计 |
| writing-plans | 把设计分解为具体任务 |
| using-git-worktrees | 创建隔离的工作区 |
| test-driven-development | 强制 red、green、refactor 循环 |
| systematic-debugging | 先找根因，再提修复 |
| requesting-code-review | 对照计划评审实现 |
| verification-before-completion | 报告成功之前要求证据 |
| finishing-a-development-branch | 合并、提 PR、保留或清理 |

幻灯片还给出了插件的仓库结构与"组件地图"：

- 仓库布局：`superpowers/` 下有 `.claude-plugin/plugin.json`（插件元数据）、`hooks/session-start`（Session hook）、`skills/`（using-superpowers、brainstorming、writing-plans、test-driven-development 等）、`tests/`。
- 组件映射：**插件（plugin）是分发容器，skill 与 hook 提供行为**——Plugin metadata → Superpowers plugin；Session hook → Agent behavior；Skill library 对应各 skill 目录。
- 一句话总结：**A plugin is the distribution container — skills and hooks supply the behavior**（插件是分发容器——skill 和 hook 提供行为）。

### 2.3 一个 Skill 的解剖（Anatomy of a Skill）

以 `skills/brainstorming/` 为例（简化），目录含 `SKILL.md`、`visual-companion.md`、`scripts/`：

```markdown
---
name: brainstorming
description: Use before creative work.
---
## Workflow
1. Inspect the project
2. Classify the scope
3. Clarify requirements
4. Compare approaches
5. Present a design
6. Wait for user approval
7. Invoke writing-plans
```

要点：**front matter 是元数据（name、description），正文（body）是智能体要遵循的流程（procedure）**。注意第 6 步"等待用户批准"（人工审批门）和第 7 步"调用 writing-plans"（指向下一个 skill）。

一个 skill 文件包含六个组件：

| 组件 | 功能 |
|---|---|
| name | 稳定标识符 |
| description | 说明该 skill 何时适用 |
| Instructions | 要遵循的流程 |
| Checkpoints | 继续之前的批准检查点 |
| References | 只在需要时才加载的细节 |
| Scripts | 确定性操作 |

一个"流程型 skill"（process skill）可以定义：必需动作（required actions）、禁止动作（prohibited actions）、人工审批门（human approval gates）、验证要求（verification requirements），以及下一个适用的 skill。**每个 skill 引导智能体行为，并且可选地指名它的后继（successor）skill**——skill 之间由此串成一条受控流程。

### 2.4 为什么只有 Skill 还不够

幻灯片指出了一个关键问题：**安装 skill 只是让它"可用"（available）——但可用并不保证智能体真的会去检查它**。智能体不会主动想起"哦还有个 skill 我该读"，所以需要一个确定性的触发点。

Superpowers 的解法是一个 **SessionStart hook**，`hooks/hooks.json`：

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup|clear|compact",
      "hooks": [{ "type": "command",
        "command": "run-hook.cmd",
        "async": false }]
    }] }
  }
}
```

这个 hook 保证三件事：

1. **确定性的时机，每个会话都触发**（matcher 匹配 startup / clear / compact 三种情况）；
2. **在智能体行动之前运行**（runs before the agent acts）；
3. **在 clear 和 compact（压缩）之后重新运行**（re-runs after clear and compaction）——这点很重要：上下文被清空或压缩后，skill 的使用规则会再次注入，不会被"忘掉"。

### 2.5 Session-Start 脚本

`hooks/session-start`（简化版 bash）：

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(plugin_root)"
skill="$ROOT/skills/using-superpowers/SKILL.md"
content="$(cat "$skill")"
printf '{"hookSpecificOutput": {
"hookEventName": "SessionStart",
"additionalContext": "%s" }}' \
"$(escape_json "$content")"
```

执行步骤：

1. 定位已安装的插件根目录；
2. 读取 bootstrap SKILL.md（`using-superpowers/SKILL.md`）；
3. 把 Markdown 内容转义为 JSON；
4. 以 `additionalContext` 字段返回；
5. Claude Code 把它追加进上下文。

于是每个会话一开始（以及每次 clear/compact 后），"如何使用 skill 体系"的元规则都会确定性地出现在上下文里，智能体随后按 using-superpowers 的规则去加载具体任务的 skill。

### 2.6 端到端走查（"Add authentication"）

以用户请求"添加认证"为例，运行时序：

- **Hook** → 读取 bootstrap skill；**Agent** → 接收选择策略（selection policy）；
- **User** → "Add authentication"；**Agent** → 加载 brainstorming，澄清需求；
- **User** → 批准设计；**Agent** → 加载 writing-plans（生成实现计划）；
- 后续阶段：隔离 worktree（isolated worktree）→ 测试驱动构建（test-driven build）→ 代码评审（code review）→ 验证（verification）→ 分支集成（branch integration）。

整条链路里，每一步都是"skill 指名下一个 skill + 人工审批门"在驱动流程，而不是模型自由发挥。

### 2.7 从 Superpowers 得到的设计教训

| 设计问题 | Superpowers 的答案 |
|---|---|
| 复杂行为应该如何表示？ | 小而可组合的 skill（small, composable skills） |
| 智能体如何记得去用它们？ | 通过 session hook 注入 bootstrap skill |
| 上下文如何保持可控？ | 只在相关时加载任务 skill |
| 各阶段如何协调？ | 每个 skill 指名自己的门（gates）与后继（successor） |
| 用户如何安装这个系统？ | 把所有东西打包为一个 plugin |
| 每个 plugin 都需要 command 或 MCP 吗？ | 不需要——只在需要时才加 |

最后一条尤其值得注意：**扩展机制要按需取用**。Superpowers 只用了 skill + hook + plugin 三种机制，没有 command 和 MCP，因为它的目标只是改变智能体在软件开发流程上的行为。

## 三、案例研究：Caveman

### 3.1 五个扩展机制 + 一个本地代理

Caveman 的安装：

```
claude plugin marketplace add JuliusBrussee/caveman
claude plugin install caveman@caveman
```

它是"五个扩展机制——外加一个本地代理"的完整示范：skills、commands、hooks、MCP server、plugin 包，再加一个夹在智能体与模型提供商之间的**本地压缩代理（local proxy）**。它的主题是：**压缩智能体的 token**。

### 3.2 为什么要压缩智能体的 token？

幻灯片先指出上下文的三大压力：

- **上下文会被日志塞满**：日志、diff、工具输出挤占真正的工作空间。示例：一次 `npm test` 输出 786 行——`FAIL src/api/client.test.ts`、`● client › retries on 5xx`、`connect ETIMEDOUT 10.0.3.8:443 at client.ts:88`、"… 776 more lines …"、`3 failed, 214 passed`；
- **token 双重昂贵**：既付费（paid for）又等待（waited on）——prefill 延迟与成本都随 token 数走；
- **事后裁剪上下文会丢掉重要信息**：在上下文增长之后做 compaction，会丢失细节（compaction loses detail）。

所以策略是：**双向压缩——输入和输出都压——并且保留原文可随时取回**（keep the original available for retrieval）。对照示例：

- BEFORE（上下文里）：786 行测试输出；
- AFTER（模型实际读到的）：`3 tests fail: ETIMEDOUT at client.ts:88`。

### 3.3 两个方向的压缩

`/caveman ultra` 之后对智能体说"Run the tests and explain the failure"：

- **AGENT INPUT**（模型读入的日志、工具结果、diff、文件）→ **本地代理 + 压缩引擎** → 模型；
- **AGENT OUTPUT**（模型响应）→ **响应 skill（injected）** → 压缩后的输出。

核心区分：**skill 改变模型"怎么写"（how the model writes），代理改变模型"读什么"（what it reads）**。

- 报告的效果：**输出 token 减少 65%**（Reported: 65% fewer output tokens）；
- 但要诚实：skill 本身会往输入里增加 token，所以整场会话的净节省要小于 65%。

一次完整交互的顺序（/caveman ultra 之后）：

1. Hook 存储 ultra 模式；
2. Hook 注入"简洁响应"提醒；
3. 智能体执行命令（由 LLM 发起）；
4. Caveman（代理）压缩嘈杂的测试输出；
5. 模型收到被削减的上下文；
6. 模型返回简洁的诊断；
7. MCP 按需取回原始内容（MCP retrieves the original on demand）。

（此页后有一页纯图示页，无文字层内容，应为 Caveman 数据流示意图。）

### 3.4 插件打包（Plugin Packaging）

仓库结构：

```
caveman/
├─ .claude-plugin/plugin.json
├─ skills/
│   caveman, -commit, -review, -compress, -stats
├─ commands/
├─ src/hooks/
├─ mcp/
├─ proxy/
├─ engine/
└─ agents/
```

插件清单（`.claude-plugin/plugin.json`）：

```json
{
  "name": "caveman",
  "hooks": {
    "SessionStart": ["caveman-activate.js"],
    "UserPromptSubmit": ["caveman-mode-tracker.js"]
  }
}
```

注意与 Superpowers 的对比：Superpowers 用 SessionStart 做引导，Caveman 同时注册了 SessionStart 和 **UserPromptSubmit** 两个 hook——因为它的模式状态要在会话中持续跟踪（见 3.7）。

### 3.5 响应 Skill：让输出不再啰嗦

`skills/caveman/SKILL.md`：

```markdown
---
name: caveman
description: Compressed mode
---
# Caveman response mode
Preserve: technical terms, commands, paths, code, errors,
numbers, units, negation
Remove: filler, repetition, pleasantries, hedging
Short sentences. Active voice.
```

即"原始人模式"：**保留**技术术语、命令、路径、代码、报错、数字、单位、否定词；**删除**填充词、重复、客套、含糊其辞（hedging）；短句、主动语态。这个 skill 改变的是**智能体的沟通方式**（how the agent communicates），是输出方向的压缩。

### 3.6 Commands：给用户显式控制

| Command | 功能 |
|---|---|
| /caveman | 激活默认 full 模式 |
| /caveman ultra | 最大压缩 |
| /caveman off | 关闭该风格 |
| /caveman-commit | 简洁的 commit message |
| /caveman-review | 简洁的评审发现 |
| /caveman-compress | 压缩一个记忆文件 |
| /caveman-stats | 会话 token 统计 |
| /caveman-help | 查看可用操作 |

`commands/caveman.md` 示例：

```markdown
---
description: Activate Caveman mode
argument-hint: [lite|full|ultra|off]
---
Activate Caveman mode: $ARGUMENTS
If no level is supplied, use full.
If off, deactivate.
```

command 的作用是把模式选择显式交给用户（lite/full/ultra/off 四档），而不是让智能体自己决定。

### 3.7 Hooks：让 prompt 时的选择持久化

- **SessionStart → `caveman-activate.js`**：为本会话决定模式；安全地存储模式状态；把规则作为隐藏上下文注入；compact 之后恢复规则；清理旧状态、提供状态行（status line）。
- **UserPromptSubmit → `caveman-mode-tracker.js`**：检查每一条用户 prompt；检测 `/caveman ultra`；检测类似"normal mode"的短语；更新会话模式；在"聚焦操作"（focused ops）之后恢复模式。

即：**SessionStart 负责初始化行为，UserPromptSubmit 负责在对话中途检测变化**。配置里两条 hook 都写成 `node xxx.js` 命令。

### 3.8 MCP：把压缩暴露为可调用的工具

五个 MCP 工具：

| 工具 | 功能 |
|---|---|
| caveman_compress | 压缩 + 返回恢复句柄（recovery handle） |
| caveman_retrieve | 按句柄取回逐字节一致的原文（byte-exact original） |
| caveman_stats | 压缩统计 |
| caveman_toon_encode | JSON 转 TOON |
| caveman_toon_decode | TOON 转回 JSON |

MCP 配置：

```json
{"mcpServers": {
  "caveman": {
    "command": "npx",
    "args": ["-y","caveman-mcp"]
  }
}}
```

工具结果示例：

```json
{
  "compressed": "3 tests fail. Root error: timeout.",
  "ratio": 0.72,
  "recovery_handle": "ccr_abc123"
}
```

`recovery_handle` 是"保留原文可取回"这一承诺的实现：智能体（或用户）任何时候都可以用 `caveman_retrieve` 拿回逐字节一致的原始内容，压缩因此是无损可逆的。

### 3.9 本地代理：压缩模型"读到"的东西

数据流：**编码智能体 → 本地 Caveman 代理 → 模型提供商**。

按内容类型做**类型感知压缩（type-aware compression）**——各类型分别保留什么：

| 类型 | 保留 |
|---|---|
| 日志 | 错误、堆栈、头 + 尾 |
| 代码 | imports、签名、类型、函数体 |
| Diff | 文件 + hunk 头、变更行 |
| JSON | 键、结构、错误子树 |
| 搜索 | 高价值匹配、诊断信息 |
| HTML / 文本 | 标题、相关段落 |

**代理 vs MCP 的关键区别**：

- 代理**拦截每一个请求**（intercepts every request）；MCP 只在被调用时才运行；
- 代理位于智能体与提供商**之间**（between agent and provider）；MCP 在旁边（sits beside it）；
- 代理能**改变上下文本身**（changes context）；MCP 不能。

幻灯片还澄清了一个常见的误解：**Hook 能拦截请求——但它不能"透明地"改写发往 LLM 的请求；要透明改写就需要一个代理。除非你自己写 harness，那就是另一回事了**（If you write your own harness, then yes.）。

最后给出一张"Caveman 各能力如何被使用"的总图：

- **PACKAGE（打包）**：Caveman plugin——一个安装与更新单元；
- **MECHANISMS（机制）**：Skills（简洁风格、聚焦工作流）、Commands（选择模式、发起操作）、Hooks（激活、跟踪、强化模式）、MCP server（压缩、取回、统计、编码）；
- **STATE + ENGINE（状态与引擎）**：会话模式状态 + 压缩引擎；
- **INTERCEPT（拦截）**：本地代理——位于智能体与模型提供商之间。

（此页后有一页纯图示页，无文字层内容，应为 Caveman 架构/使用图。）

## 四、用多个智能体成为 100 倍工程师

开场幻灯片反问："你如何在两小时内完成作业？1 · 到场（Show up）2 · 保持清醒（Stay awake）——午饭前做完"，然后给出答案：**用多个长时运行的智能体（multiple long-running agents）**，四条路：**手工并行（Parallel Agents by Hand）、Subagent、Agent team、Dynamic Workflow**。并提醒一句：**智能体并行扇出（fan out），账单也跟着扇出**（So does the invoice）——并行不是免费的。

### 4.1 规模化的三个轴

| 轴 | 机制 | 买到什么 |
|---|---|---|
| 并行智能体（parallel agents） | 运行多个独立任务，每个在隔离的 worktree 里 | 买**范围**（scope）：更少干预下做更多工作 |
| 子智能体（subagents） | 把一个有界任务委派给一个全新上下文；拿回一份摘要 | 买**吞吐 + 专注**：父智能体永远看不到中间混乱 |
| 长时智能体（long-running agent） | 让一个大任务跨许多步推进 | 买**时间**（duration）：墙钟时间，而不是答案质量 |

幻灯片总结：**Agent team 和 dynamic workflow 是把这些轴组合起来**。

### 4.2 手工并行：git worktree

**一个会话一个任务，每个会话放在自己的 git worktree 里**——worktree 是与主仓库共享历史、但有独立工作目录和分支的检出。

```
claude -w feature-payments
claude -w bugfix-auth
```

- 终端 1 在自己的分支上开发功能，终端 2 修 bug，互不干扰；
- **一个会话里的编辑绝不会碰到另一个会话的文件**（edits in one session never touch the files in another）；
- 不用 stash，不用第二次 clone；桌面版（desktop app）里每个新会话都会自动拿到一个 worktree。

图示：一个仓库（`../repo-main` 分支 main，含 .git 的 history/branches/objects/remotes），加两个 worktree——`../feat-auth`（feature/auth 分支，Agent 2 在 build）和 `../fix-flaky`（fix/flaky-test 分支，Agent 3 在 debug），外加 Agent 1 在 review。**一份共享历史，三个检出（checkouts），不用切分支，不用 stash。**

**手工并行的天花板**（幻灯片明确划出边界）：

| 限制 | 说明 |
|---|---|
| 计划在你脑子里 | 每一次交接和下一步，只有你能把它们带过去——会话之间互相看不见 |
| 分支由你对齐 | 冲突归你处理——合并顺序、冲突解决 |
| 不可复现 | 这次运行什么都没写下来，无法重跑 |

量化感受：**3 个会话 = 你；20 个会话 = 你 + 一个你的克隆**（You can hold the plan: 3 sessions = you; 20 sessions = you + a clone）。几个会话是生产力提升，二十个就需要"一个克隆的你"来协调——这正是 subagent/team 要解决的。

### 4.3 子智能体（Subagents）：为什么？

定义：**一个拥有自己上下文窗口、工具与权限的专用助手**（a specialized assistant with its own context window, tools and permissions）。五大好处：

| 好处 | 说明 |
|---|---|
| 保护上下文 | 日志、搜索结果、文件转储都留在主对话之外 |
| 施加约束 | 限制子智能体可用哪些工具、跑哪个模型 |
| 随处复用 | 面向特定领域的聚焦 prompt，跨项目、跨团队共享 |
| 并行化 | 独立子任务并发运行，总时间由最慢的那个决定 |
| 控制成本 | 把任务路由到更快更便宜的模型，如 Haiku |

最后一点在 frontmatter 里就能实现：`model: haiku`（写在 subagent 的 frontmatter 里）。参考文档：code.claude.com/docs/en/sub-agents。

### 4.4 内置子智能体

Claude 会自动委派给三个内置 subagent：

| 内置 Subagent | 用途 |
|---|---|
| Explore | 代码库的只读搜索；Write 和 Edit 被拒绝（禁止写/编辑），以保持彻底且便宜；每次调用可设 thoroughness |
| Plan | 在 plan 模式里做研究，让探索远离主窗口 |
| General-purpose | 需要"探索 + 行动"两者的复杂多步工作 |

注意：**Explore 和 Plan 会跳过 CLAUDE.md 和 git status，以保持快速和便宜**——这是一个"上下文准入"的微调：不需要记忆文件的只读探索就不付这个 token 成本。

### 4.5 定义一个 Subagent

**一个带 YAML frontmatter 的 Markdown 文件，正文（body）就是它的 system prompt**：

```
.claude/agents/code-reviewer.md
---
name: code-reviewer
description: Reviews code for quality
tools: Read, Glob, Grep
model: sonnet
---
You are a code reviewer. Analyze the code and give actionable feedback.
```

作用域分两级：

- **项目作用域**：`.claude/agents/` —— check 进版本控制，团队共享；
- **用户作用域**：`~/.claude/agents/` —— 你所有项目可用。

**嵌套子智能体（nested subagents）**：

- frontmatter 示例：`name: my-orchestrator`、`tools: Read, Grep, Agent`、`model: claude-sonnet-5-0`；
- 最多允许 **5 层嵌套**；**2–3 层是甜点区**（the sweet spot）；
- 关键规则：**父 subagent 的 tools 里必须出现 `Agent` 工具，它才能派生子智能体**。

图示：父 subagent 通过 Agent 工具调用派生出 Child subagent 1 和 Child subagent 2。

### 4.6 多层子智能体：一种常见模式

- **Level 0**：主智能体——持有计划（owns the plan）；
- **Level 1**：Implementer subagent、Debugging subagent、Code-review subagent；
- **Level 2**：Test-writer subagent、Verification subagent。

**每一层都以全新上下文开始，且只返回一份摘要**（Every level starts with fresh context and returns only a summary）。这就是"买专注"的结构性保证：中间过程的噪声（日志、试错、搜索）被逐层吸收，只有结论向上传递。

### 4.7 与 Subagent 协作的三种方式

自动委派是自发发生的——**它没发生时，就显式升级（escalate）**。三种显式手段，控制力递增：

| 方式 | 用法 | 作用域 |
|---|---|---|
| 1 · 自然语言 | "Use the test-runner subagent to fix tests" | ONE-OFF：Claude 自行决定是否委派 |
| 2 · @-mention | "@agent-code-reviewer look at auth changes" | ONE TASK：选中即保证运行该 subagent |
| 3 · --agent flag | `claude --agent code-reviewer` | WHOLE SESSION：整个会话采用它的 prompt、工具与模型 |

### 4.8 Subagent，还是主对话？

判断原则：**subagent 从全新上下文起步：它看不见任何历史，还要付一笔"收集上下文"的延迟成本**。

- **留在主对话**：需要反复来回的迭代；共享上下文的多个阶段；快速、精准的修改；延迟敏感；简单的活可以委派给小模型。
- **委派给 subagent**：你不会复用的啰嗦输出；需要工具/权限限制；返回摘要的自包含工作；并行独立工作。

最后一句：**如果你想要的是一个"在主上下文里可复用的工作流"？那应该用 Skill，而不是 subagent。**（Skill 是"流程"的可复用单元，subagent 是"隔离执行"的单元。）

### 4.9 Agent Teams

定义：**多个 Claude Code 会话协作：一个 lead，若干 teammate**。四种典型用法：

| 模式 | 说明 |
|---|---|
| Review | 队友从不同角度探查，然后互相质疑对方的发现 |
| Independent | 每个队友负责一块独立的部分，互不踩脚 |
| Debugging | 竞争性假设并行测试，收敛更快 |
| Cross-layer | 前端、后端、测试，各有一个队友 |

两个重要提醒：

- **不是免费的**：协调开销和 token 成本随团队规模增长（coordination overhead and token cost scale with the team）；
- **实验性**：默认关闭（Experimental — off by default）。参考文档：code.claude.com/docs/en/agent-teams。

**顺序任务、同文件编辑或强依赖——用一个会话或 subagent 就够了。**

### 4.10 一个 Team 如何接线

四部分，**teammate 之间直接互相说话**：

| 组件 | 说明 |
|---|---|
| Team lead | 主会话：派生队友、协调工作、综合结果 |
| Teammates | 独立的 Claude Code 实例，各有自己的上下文窗口 |
| Task list | 共享工作项清单，队友认领并标记完成 |
| Mailbox | 每个智能体一个 JSON 收件箱 |

关键细节：**teammate 不继承你的对话**。它们会自动加载 CLAUDE.md 和 skills，任务细节要写进 prompt。

**Subagent vs Agent team 的结构对比**：subagent 的结果都报回主智能体（result report back）；team 里队友共享任务清单、互相发消息（claim tasks and message each other）——**subagents 向 lead 汇报；teammates 共享任务清单并互相交谈**。

### 4.11 Subagents vs Agent Teams（决策表）

| 维度 | Subagents | Agent teams |
|---|---|---|
| 上下文 | 自己的窗口，结果返回调用方 | 自己的窗口，彼此独立 |
| 通信 | 只回传调用方 | 队友对队友 |
| 协调 | Lead 管理工作 | 共享任务清单 |
| 最适合 | 只要结果的任务（result-only tasks） | 需要讨论的工作 |
| Token 成本 | 较低 | 较高 |

结论：**teams 更贵——只有当工作真的需要讨论时才用**（Teams cost more — use them only when the work needs discussion）。

### 4.12 动态 Workflow（Dynamic Workflow）

定义：**一段 JavaScript 脚本，在后台编排许多 subagent**。

- 使用时机：**当任务需要的智能体数量超过一个对话能协调的规模**；
- 典型场景：全代码库的 bug 扫描（codebase-wide bug sweep）、500 个文件的迁移（a 500-file migration）、从多个角度核查的研究（research cross-checked angles）、多方生成的计划（an plan from several angles）。
- 两种启动方式：在 prompt 里直接输入 `ultracode`，或者说 `/effort ultracode` 让 Claude 自己决定。两条路都会派生许多 subagent——plan、design、implement、review。

要点：与手工聊天式协调不同，**是脚本持有计划，而不是聊天**（a script holds the plan, not the chat）。

### 4.13 长时智能体 I：`/goal`

定义：**交出一个可验证的终态（verifiable end state）；Claude 持续工作直到它成立**。

```
/goal "npm run lint exits with zero errors"
```

三列拆解：

| 定义完成 | 自检 | 自己停下 |
|---|---|---|
| Claude 能测试的条件：测试通过、零 lint 错误 | 每次尝试后，evaluator 重新检查条件，再把 Claude 放回去 | 目标达成时结束；或 `--max-tries` 用完时结束 |

示例对比：**"all integration tests pass" 可以（可验证！）；"refactor the code" 不行**（不可验证——没有明确的"成立"条件，循环不知道何时该停）。

### 4.14 长时智能体 II：`/loop`

定义：**按时间表重跑一个 prompt；它会一直继续，直到你叫停**。

```
/loop 5m "check CI, fix whatever broke"
```

三列拆解：

| 触发器，不是测试 | 由你终止 | 自带默认 |
|---|---|---|
| 你交出间隔；同一个 prompt 每次都原样重跑 | 它迭代运行，直到你按 Esc；两次运行之间它处于等待 | 在 `.claude/loop.md` 里放一个默认 prompt |

核心对比：**`/goal` 在条件成立时停；`/loop` 在你要求时停。** goal 适合有明确成功判据的任务，loop 适合周期性巡检类任务（CI、监控）。

### 4.15 小结：四种放大 + 两个长时

**更多智能体同时跑**：

- **手工并行智能体**——你自己对账（reconcile）；
- **Subagents**——Claude 委派，结果回到它那里；
- **Agent teams**——一个 lead 通过共享清单监督同级；
- **Workflows**——脚本持有计划，而不是聊天。

**一个智能体跑更久**：

- **`/goal`**——一直运行到可验证的终态成立；
- **`/loop`**——按时间表重跑，直到你叫停。

## 五、案例：16 个智能体造了一个 C 编译器

（可选阅读）一个能构建 Linux 内核的 Rust 编写的 C 编译器——**16 个智能体、约 2000 个会话、两周**。出处：https://www.anthropic.com/engineering/building-c-compiler

### 5.1 规模与结果

| 规模 | 结果 |
|---|---|
| 16 个智能体并行工作 | 约 100,000 行代码 |
| 两周内约 2,000 个会话 | 构建出 Linux 6.9（x86、ARM、RISC-V） |
| 2B 输入 / 140M 输出 token | 跑通 QEMU、FFmpeg、Postgres、Redis、Doom |
| API 成本略低于 $20,000 | 主要测试套件约 99% 通过率 |

### 5.2 十六个智能体如何协调

**纯基础设施——容器、Git、文本文件——就完成了编排**（Plain infrastructure — containers, Git and text files — did the orchestration）。没有专用编排框架：

- 每个智能体在隔离容器 + 自己的 Git checkout 里；
- 通过**简单的锁文件**认领任务（tasks claimed through simple lock files）；
- **Git 作为协调与集成层**；
- 新会话读取进度文档（progress docs）来恢复上下文；
- 专门智能体负责文档、性能、质量、去重；
- 自动化测试给智能体一个进度信号。

**Git 作为协调层的循环**：每个智能体在自己的容器里先 `clone`、`scan docs`；**读仓库、认领任务（current_tasks/ 下的锁文件）、实现、跑测试、合并推送、解锁**；循环重复——智能体自己挑下一个显而易见的任务，Git 裁决重复认领。两个自稳定机制：

- **冲突自动消解**：同一任务被认领两次？一个智能体移开（moves on），Git 让重复认领自动了结；
- **上下文由制品承载**：README、进度文档、CI 失败信息让新会话（新智能体实例）无需聊天历史即可接棒。

**没有任何聊天，也没有管理者智能体**——agents 通过共享的 Git 状态协调。

### 5.3 成功了，但还不完美

- 合并冲突仍然频繁；
- 一旦所有智能体都撞上同一个内核失败，并行就不再有帮助（parallelism stopped helping once every agent hit the same kernel failure）；
- 16 位 x86 的部分仍依赖 GCC；
- 生成的代码效率低于 GCC 输出。

结论（幻灯片标题语）：**Agent 还不完美，你前面还有更多工作！**——多智能体能把工程推进到惊人规模，但"最后一公里"（正确性尾部、性能）仍需人。

## 六、编程 3.0 / Software 3.0

### 6.1 编程 3.0（讲师自己的定义）

幻灯片先声明：**"编程 3.0"是我（Juncheng Yang）造的词，与 Andrej（Karpathy）下一张幻灯片的定义不同**。

三代演进：

- **1.0（programming hardware）**：人 → 显式机器指令/汇编 → 硬件；
- **2.0（programming language）**：人 → 编程语言指令 → 编译器 → 机器 → 硬件；编译器买来了**生产率（productivity）**，但也引入**不确定性（uncertainty）**；
- **3.0（expressing goal）**：人 → 自然语言 → Agent →（编程语言/指令）→ 机器 → 硬件；不确定性进一步提高（图中 More / Higher 标注），但人的抽象层级也更高——表达目标即可。

### 6.2 Software 3.0（Andrej Karpathy）

| 范式 | 程序是什么？ | 如何创建？ |
|---|---|---|
| 1.0 | 源代码 | 写 Python/C++ |
| 2.0 | 神经网络权重 | 收集数据 + 优化 |
| 3.0 | LLM prompt | 自然语言 |

三条管线：Software 1.0 = 人 → 代码（language）→ 计算机；Software 2.0 = 人 → 数据 → 优化器（optimizer）→ 神经网络；Software 3.0 = 人 → 自然语言 → LLM → 行动（action），LLM 持有上下文。幻灯片引用的视频为 Karpathy 的《Software Is Changing (Again)》（YouTube）。

最重要的工程论断：**知道 1.0、2.0、3.0 之间的边界画在哪里，是一项重要的工程技能**（Knowing where to draw the boundary between 1.0, 2.0 and 3.0 is an important engineering skill）。即：什么逻辑用确定性代码写、什么交给学习模型、什么交给 LLM，这个划分本身是设计决策。

### 6.3 编程 3.0 中的不确定性

核心论断：**不确定性成为核心主题，你要学会与它共处**（Uncertainty becomes the core theme, and you should learn to live with it!）。

首先回答"不确定性是新东西吗？"——**不是**：同一段源代码 ≠ 同样输出，这种情况很早就存在了。对照表：

| 不确定性来源 | Programming 2.0 的形态 | 2.0 如何解 | Programming 3.0 新增 |
|---|---|---|---|
| 硬件 | 架构：32 位 vs 64 位、字节序（endianness） | 定宽类型、交叉编译、虚拟化 | GPU 计算非确定性 kernel、浮点方差 |
| 环境 | 并发、不可靠网络 | 内存一致性模型、幂等 API | 代码生成与环境的交互——智能体一边写代码一边触碰环境 |
| 软件 | 编译器版本、依赖漂移 | 升级前全面测试 | 编译器、模型——不同 kernel、采样（sampling） |

（此页后有一页纯图示页，无文字层内容。）

### 6.4 从意图到结果的一点更多不确定性

图示对比两条链路：

- **1.0 / 2.0**：human (PM) → programmer → 程序 → 结果；
- **3.0**：human → LLM/agent → 程序 → 结果。

3.0 链路上标注了新的不确定性：**输入因单一 prompt 而含糊**（ambiguous input due to a single prompt）；执行"需要环境、需要记忆"（need env, memory）；形式化验证（formal verification）在上一页讨论过；标注"仍需更多研究"（more research needed）。

### 6.5 与不确定性共处：按层拆解

- **自然语言**：语义不确定性（semantic uncertainty）；
- **检索 / 上下文（Retrieval / context）**：检索漂移（retrieval drift）——索引更新、分块（chunking）、上下文截断；
- **模型生成（Model generation）**：1. 采样带来的概率性变化；2. 软件与硬件非确定性；
- **智能体 / 工具循环（Agent / tool loop）**：轨迹 / 工具失败 + 环境非确定性（环境会变化）；
- **生成的程序（Generated program）**：通常生成后就是确定性的——**除非它在运行时调用模型或工具**。

即不确定性遍布整条栈，每一层都有独立的失效源；而"生成的程序"这个中间产物反而是最确定的一层（只要它不再调用非确定性组件）。

### 6.6 编程 / Software 3.0 的最佳实践

三步：**1 · 定义（DEFINE）2 · 控制（CONTROL）3 · 验证与治理（VERIFY & GOVERN）**：

| 1 · DEFINE | 2 · CONTROL | 3 · VERIFY & GOVERN |
|---|---|---|
| 把假设写出来（state assumptions up front） | 提案与执行分离（separate proposal from execution） | 收紧"生成—执行—验证"循环（tighten the generate–execute–verify loop） |
| 让模型在执行前确认任何含糊之处（Have the model confirm anything ambiguous before it executes） | 智能体先提计划；任何提交之前先验证（validate before anything commits） | 便宜、频繁的检查胜过一次昂贵的终末评审（Cheap, frequent checks beat one expensive review at the end） |
| 规定结果（outcomes），而不是……prompt：给出需求、不变量（invariants）、约束与验收测试 | 显式管理上下文：自己的记忆与出处（provenance）；让过期信息失效（expire stale information） | 测"深一层"的指标：造测试、测多个指标、用你能推理的合成工作负载 |

### 6.7 收束

- **不要指望智能体是确定性的；要让周围的系统可靠**（Do not expect the agent to be deterministic; make the surrounding system dependable.）
- **自治程度要与风险匹配**：autonomy 越高，不确定性和风险越高（the more autonomy the higher uncertainty and risk）。

这两句是本讲的工程纲领：把不确定性当一等公民，用确定性的外壳（测试、验证、状态文件、审批门）包裹非确定性的内核。

## 七、来自一线的证据：Codex 使用报告

本节用 OpenAI 的两份内部使用报告（2026 年 6 月与 2026 年 9 月，*"The Shift to Agentic AI: Evidence from Codex"* 与 *"Research acceleration: The view inside OpenAI"*）展示多智能体使用在真实世界中的演进。

### 7.1 从对话到委派（From Conversation to Delegation）

两种使用模式的对比：

- **对话式 AI（Conversational AI）**：人提问 → 模型回答 → **人执行工作**（human is the executor）；
- **智能体式 AI（Agentic AI, Codex）**：人委派任务 → 智能体规划、调用工具、编辑文件、运行命令 → 交付物或行动被交付 → **人保持参与（stays in the loop），评审与集成**（human reviews and integrates）。

近 28 天内使用 Codex 的用户中转向"委派"模式的比例，按群体：

| 群体 | 委派比例 |
|---|---|
| 个人用户（Individual） | < 1% |
| 组织用户（Organizational） | 17.3% |
| OpenAI 员工（OpenAI workers） | 几乎全部（nearly all） |

另：**2026 上半年，Codex 活跃用户增长超过 5 倍**（Active users grew more than 5× in the first half of 2026）。

### 7.2 被委派的任务越来越大（Delegated Tasks Are Getting Much Bigger）

按任务时长分层（图表）：

| 任务规模 | 2025 年 12 月 | 2026 年 5 月 |
|---|---|---|
| 任务 ≥ 1 个人工时 | 35.4% | 70.2% |
| 任务 ≥ 8 个人工时（全天任务） | 2.1% | 25.6% |

**挑战全天任务（full-day tasks）的用户增长了 12 倍**（2.1% → 25.6% ≈ 12×）。人们委派给智能体的任务在时间尺度上持续变大：从小时级走向全天级。

### 7.3 一个人，许多智能体（One Human, Many Agents，2026 年 6 月）

模式：人同时运行 Agent A（build feature）、Agent B（run analysis）、Agent C（debug + test），然后 **评审 · 集成 · 再委派**（Review · integrate · re-delegate）。

数据：

- **28.6%** 的 OpenAI 用户在一天内同时运行 5+ 个智能体（一周内）；
- 中位数（median）OpenAI 员工每天约 **2.5 个智能体小时**（agent-hours）；
- 第 99 百分位每天约 **71 个智能体小时**（99th percentile）；
- 相比 4 月 **+88%**。

结论：**人的角色转变为规划者、委派者、监控者、评审者、集成者**（The human role shifts to planner, delegator, monitor, reviewer, integrator）。

### 7.4 智能体工作日如今远超人类研究员（2026 年 9 月）

- **2026 年 6 月之前，智能体运行时间（agent runtime）落后于人力（human labor）；如今智能体做的工作是人的 3.14 倍**（agent do 3.14x more work than human）；
- 多数研究员同时有 4+ 条并行的 workflow（图表未单独显示）。

即人机工作量的平衡点在 2026 年年中发生了反转。

### 7.5 工程师交付速度接近 8 倍（Engineers Are Shipping Almost 8x Faster）

（图表页）工程师的交付/发布速度接近 8 倍提升。（本页仅标题，图表细节在图中。）

### 7.6 智能体解决越来越复杂的任务，但仍需人类介入

（图表页）智能体可解决的任务复杂度持续上升，但人类介入（human intervention）仍然必要。（本页仅标题，图表细节在图中。）

### 7.7 编码智能体正在重塑 OpenAI 研究员的日常（2026 年 9 月）

（综合图表页）来源为 OpenAI 内部报告《Research acceleration: The view inside OpenAI》。

### 7.8 委派阶梯（The Delegation Ladder）

| 层级 | 含义 |
|---|---|
| 1 · Chatbot | AI 回答；人干活 |
| 2 · Assistant | 人与 AI 一起做任务 |
| 3 · Agent | 人委派一整块工作 |
| 4 · Multi-agent worker | 人协调多个智能体 |
| 5 · Systematized workflows | skill 与智能体运行流程 |

现状判断：**OpenAI 的员工大多还处在阶梯底部**（OpenAI's workforce sits near the bottom）——即便在重度用户里，真正走到 4、5 层的仍是少数，上方空间巨大。

## 八、可选幻灯片：CLI 编码智能体综述

### 8.1 超越 Claude Code（Beyond Claude Code）

*《State of CLI Coding Agents, Mid-2026 (July 2026)》*——按四个象限盘点生态：

| 模型实验室（Model labs） | 平台 CLI（Platform CLIs） | 开源（Open source） | 最小内核（Minimal cores） |
|---|---|---|---|
| Claude Code | Copilot CLI | OpenCode | Deepseek Harness |
| Codex CLI | Cursor CLI | Crush · Goose | Pi · oh-my-pi (Omp) |
| Antigravity CLI | Amp | Aider · Cline | mini-SWE-agent |
| Grok Build | Auggie | Kilo · Continue | gptme |
| Mistral Vibe | Droid | OpenHands | Open Interpreter |
| Kimi Code | Junie CLI | Reasonix | Qwen Code |
| Qoder | Codebuff | CodeBuddy | — |

各列定位——Model labs：**模型 + harness 一体**（model + harness in one）；Platform CLIs：**嵌在开发工具栈里**（inside a dev stack）；Open source：**自带 key**（bring your own key）；Minimal cores：**小而可审计**（small and auditable）。

### 8.2 它们的差异：五个重要轴（How They Differ: Five Axes That Matter）

五个轴：**开放 vs 封闭（Open vs closed）；锁定 vs BYOK（Locked vs BYOK）；沙箱 vs 提示（Sandbox vs prompt）；本地 vs 云端（Local vs cloud）；全功能 vs 极简（Maximal vs minimal）**。

文字层给出的三组具体划分：

| 轴 | 开放 | 封闭 |
|---|---|---|
| Open vs closed | Codex CLI、OpenCode、Goose、Cline、Pi | Claude Code、Copilot CLI、Cursor、Droid、Junie |
| Locked vs BYOK | —（单一供应商）：Claude Code、Antigravity CLI、Grok Build | —（任意端点）：OpenCode 支持 75+ providers、Kilo 支持 500+ models |
| Sandbox vs prompt | OS 沙箱：Codex CLI、Copilot CLI、OpenHands（容器） | 权限提示（permission prompts）：Claude Code 与大多数其他产品 |

图示：本地 vs 云端、全功能 vs 极简两轴的具体产品分组在图表中（文字层未含）。

### 8.3 下讲预告

Next class：Agent design I（智能体设计 I）；并提醒：找 TF 领取你的课堂参与分（participation score）。

## 核心要点

1. **Superpowers 的哲学是"同一模型、不同工作流"**：不换模型、不加工具，只用结构化指令把"直接开写"变成 澄清→批准设计→详细计划→TDD 构建→评审验证→集成 的流程；两个 agent 只有 instructions 不同。
2. Superpowers 含 9 个 skill（using-superpowers、brainstorming、writing-plans、using-git-worktrees、test-driven-development、systematic-debugging、requesting-code-review、verification-before-completion、finishing-a-development-branch），plugin 只是分发容器，skill 与 hook 才提供行为。
3. 一个 skill = front matter 元数据（name/description）+ 正文流程；可含必需/禁止动作、人工审批门、验证要求与后继 skill 指针。
4. **只有 skill 不够**：可用 ≠ 会被检查。Superpowers 用 SessionStart hook（matcher: startup|clear|compact）在每个会话开始、clear 和 compaction 后确定性地注入 bootstrap skill。
5. Caveman 演示"五个扩展机制 + 本地代理"的完整组合：skill 改模型怎么写，command 给用户显式控制（/caveman lite|full|ultra|off），hook 让模式跨 prompt/compact 持久（SessionStart + UserPromptSubmit），MCP 提供压缩/取回/统计工具，**本地代理透明压缩模型读入的一切**——因为 hook 能拦截但不能透明改写发往 LLM 的请求，要透明改写必须有代理（除非自己写 harness）。
6. Caveman 报告输出 token 减少 65%；类型感知压缩（日志留错误/堆栈/头尾，代码留签名/类型，diff 留 hunk 头，JSON 留键与错误子树），且原文保留可用 recovery_handle 逐字节取回；skill 自身增加输入 token，故净节省更低。
7. **规模化三轴**：并行智能体买范围（scope）、subagent 买吞吐+专注（父从不见中间混乱）、长时 agent 买时间（duration）；agent team 与 workflow 是组合拳。记住：智能体扇出，账单也扇出。
8. 手工并行的最小单元是 git worktree（`claude -w branch`：独立工作目录+分支，共享历史；编辑互不干扰；无需 stash/二次 clone；桌面版自动分配）。天花板：3 个会话你还能持计划，20 个就需要"一个克隆的你"——计划在你脑中、冲突你处理、不可复现。
9. Subagent = 自己的上下文窗口 + 工具 + 权限 + 模型：保护主上下文、施加约束、跨项目复用、并行化、可路由到便宜模型（frontmatter 里 `model: haiku`）；内置三个：Explore（只读，禁写改，跳过 CLAUDE.md/git status 以快且省）、Plan（plan 模式研究）、General-purpose（探索+行动）。
10. Subagent 是带 YAML frontmatter 的 Markdown（body = system prompt）；项目作用域 `.claude/agents/` 进版本控制，用户作用域 `~/.claude/agents/`；嵌套最多 5 层、2–3 层是甜点区，且 tools 里必须有 `Agent` 才能再派生子代。
11. 显式委派三档、控制递增：自然语言（一次性，模型自决）→ @-mention（单任务保证）→ `--agent` flag（整会话采用其 prompt/工具/模型）。留主对话 vs 委派 subagent 的判据：迭代/共享上下文/延迟敏感/简单活留主对话；啰嗦输出/权限限制/自包含/并行才委派；**主上下文里可复用的流程该用 Skill**。
12. Agent team = 多个 Claude Code 会话：lead + teammates + 共享 task list + 每 agent 一个 JSON mailbox，teammate 直接互聊、不继承主对话（自动加载 CLAUDE.md 与 skills）。vs subagent：subagent 只回传调用方、token 成本低、适合"只要结果"；team 互相通信、成本高、只在工作需要讨论时用（如多角度评审、独立模块、竞争假设调试、跨层分工）。实验性，默认关闭。
13. 动态 workflow 用一段 JS 脚本后台编排大量 subagent（`ultracode` 或 `/effort ultracode` 启动），适合"一个对话协调不过来"的规模：全库 bug 扫描、500 文件迁移、多角度研究。
14. 长时机制二选一：**`/goal` 交给可验证终态**（evaluator 每轮重检条件，达成或 `--max-tries` 耗尽时自停；"all integration tests pass" 可，"refactor the code" 不可）；**`/loop` 交给时间表**（如 `/loop 5m "check CI, fix whatever broke"`，跑到你按 Esc 为止；`.claude/loop.md` 可放默认 prompt）。goal 按条件停，loop 按你停。
15. 16 智能体 C 编译器案例：16 agents、~2,000 sessions、两周、2B 输入/140M 输出 token、约 $20k API 成本；产出 ~100k 行代码的 Rust C 编译器，构建 Linux 6.9（x86/ARM/RISC-V）、跑通 QEMU/FFmpeg/Postgres/Redis/Doom，主要测试套件 ~99% 通过。协调零框架：容器 + **Git（共享状态即协调层）** + 文本文件（进度文档、锁文件认领任务、自动测试当进度信号）；冲突由 Git 自动了结，上下文由制品承载。
16. 但"成功但不完全"：合并冲突频繁；所有 agent 撞同一内核失败时并行失效；16-bit x86 部分仍靠 GCC；生成代码效率低于 GCC。多智能体能推进规模，最后一公里仍需人。
17. 编程三代：1.0 写机器指令（人→汇编→硬件）、2.0 写编程语言（买生产率、引入不确定性）、3.0 表达目标（人→自然语言→Agent）；Karpathy 的 Software 3.0：1.0=源代码（写代码）、2.0=权重（数据+优化器）、3.0=prompt（自然语言）。**在 1.0/2.0/3.0 之间画边界是一项关键工程技能**。
18. 不确定性不是新事物（2.0 时代就有硬件/环境/软件三源不确定性），但 3.0 新增了 GPU 非确定性 kernel、采样、智能体-环境交互等来源，遍布自然语言→检索→模型→工具循环→生成程序全栈。最佳实践三步：**DEFINE**（先写假设、让模型确认含糊处、规定结果/不变量/约束/验收测试而非只给 prompt）、**CONTROL**（提案与执行分离、提交前验证、显式管理上下文与出处、过期信息失效）、**VERIFY & GOVERN**（收紧生成-执行-验证循环、廉价频繁检查胜过昂贵终审、测深一层：测试+多指标+可推理的合成负载）。
19. 纲领性结论：**不要指望 agent 确定性，要让周围系统可靠；自治度与风险匹配**——autonomy 越高，不确定性与风险越高。
20. 一线证据（Codex 报告）：对话→委派转变（28 天内个人 <1%、组织 17.3%、OpenAI 员工几乎全部）；委派任务变大（≥1 人时 35.4%→70.2%，≥8 人时 2.1%→25.6%，全天任务用户 12×，2025-12→2026-05）；一人多 agent（28.6% 的 OpenAI 用户一天同时跑 5+ agent，中位 ~2.5 agent-hours/天，P99 ~71 agent-hours/天，较 4 月 +88%；人的角色=规划/委派/监控/评审/集成）；2026-09 反转（agent runtime 是人力 3.14×，之前还落后）；工程师交付近乎 8×；但任务越复杂越仍需人类介入。委派阶梯五层（chatbot→assistant→agent→multi-agent worker→systematized workflows），**OpenAI 员工目前仍集中在底部**。
21. CLI 编码智能体生态（2026 年中）四分：模型实验室（Claude Code、Codex CLI 等，模型+harness 一体）、平台 CLI（Copilot CLI、Cursor CLI 等，嵌开发栈）、开源（OpenCode、Cline、OpenHands 等，BYOK）、最小内核（Deepseek Harness、Pi、mini-SWE-agent、gptme 等，小而可审计）；差异五轴：开放/封闭、锁定/BYOK（OpenCode 75+ providers、Kilo 500+ models）、沙箱/提示、本地/云端、全功能/极简。
