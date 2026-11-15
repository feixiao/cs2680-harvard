# 作业反馈讲次（Assignment Feedback Session）

> 原讲次名：*Modern AI Systems: Agents and System Optimizations — Feedback for your assignments*（Harvard CS2680，讲师 Juncheng Yang）

## 本讲概览

这不是一次编号讲次，而是一次集中反馈课。今天的计划（Plan for today）列了四项：作业回顾（A review of assignments）、更高效地使用 agent（Make better use of agents）、GPU 编程、LLM serving III——但本 deck 的正文几乎全部集中在前两项：先是逐条复盘 Assignment 1 中暴露出来的问题（异步事件流、模糊需求、重复劳动、拆分不当的委派），然后是 Assignment 4 的评审数据，接着用大量统计图展示三件作业中 Claude Code 使用方式的变化，最后系统总结了"使用 agent 的十大陷阱"（P1–P10）以及一个"好的迭代循环"最佳实践。课程还透露了一个重要背景：Anthropic 曾在 opus-5 上对几乎所有学生开了一个"优先使用 Bash"的隐藏实验，这直接影响了 A1 期间的工具行为。课程同时预告了实验性的反馈平台 how-i-used-claude.cs2680.com，以及下次课内容（GPU 编程与 LLM serving III）。行政事项：当天有 office hour，Assignment 5 有加分项，有问题随时联系 TF 和 Juncheng。

## 今日计划与行政事项

- **Plan for today**：① 作业回顾；② 更好地使用 agent；③ GPU programming；④ LLM serving III（后两项见期末的 "Next class" 预告，本 deck 正文主要覆盖前两项）。
- **Logistics**：今天有 office hour；Assignment 5 有加分项（bonus）；如果需要帮助，主动联系 TF 和 Juncheng。

## 第一部分：Assignment 1 回顾

本节标题页给出了两个问题：你在用 Claude Code 过程中**学到了什么**（What you learned from using Claude Code）与**希望它有什么**（What you wished from Claude Code）。以下逐条展开学生反馈中反复出现的模式。

### 事件流是异步的、难以重建

幻灯片指出：**Agent event streams are asynchronous and hard to reconstruct**。具体表现为：任务完成的顺序和启动顺序不同（Tasks finish in a different order than they start）；后台 Bash 任务可能来自不同的 subagent，交错出现（Background Bash tasks can come from different subagents）。因此需要一个**可信的 viewer**（A trustworthy viewer required）来呈现这些事件。另外，agent 常常直接用 Bash 而不是专用的 read 和 edit 工具，使得真实 trace 难以检查，状态转移（state transitions）也难以建模。

**图示：** 该页为纯标题+要点页，无独立图示。

这一点的实际含义是：当你事后想搞清楚 agent 到底做了什么、为什么这么做时，事件流的乱序到达和混入的多个 subagent 会让重建过程非常困难——这是 A1 中普遍被抱怨的体验。

### 模糊需求进，未检验的结果出

**Vague requirements went in and unchecked results came out**——这是 A1 反馈中最核心的一条规律。可检查的要求（checkable requirements）明显比宽泛的 prompt 效果好。幻灯片把"模糊需求"与"未检查的结果"对照列出，并给出建议：

| 模糊需求（Ambiguous requirements） | 未检查的结果（Unchecked results） | 建议（Suggestion） |
|---|---|---|
| 宽泛 prompt 产生了不想要的功能、多余的架构（excess architecture），或错误的布局 | 测试检查的是内部状态，而不是可见行为 | 把要求写成**可验证的条件**，带可度量的标准 |
| 截图、明确的几何描述和视觉示例效果更好 | hide/show 测试检查的是 HTML 的 hidden 属性，但 CSS 让内容仍然可见 | 要求 agent **主动暴露歧义**（surface ambiguity） |
| — | 报告的"已验证"实际跑了 0 个测试，或者验证被阻塞 | 在做大改动**之前**审查设计；**自己检查**验证结果 |

含义：需求写得越含糊，agent 越容易"做对字面、做错意图"；而学生又常常轻信 agent 的自报验证。解法是把验收标准写死、让 agent 把歧义摆到台面上、大改前 review 设计、并亲自核对验证是否真的发生。

### 重复工作与拆分不当的委派

**Repeated work and poorly split delegation wasted time and money**。Subagent 在**独立的 review** 和**不同的实现任务**上是有帮助的，但 A1 中常见的滥用模式是：

- **重复劳动（Repeated work）**：agent 在不同 session 之间重复同样的探索；运行了该功能根本不需要的操作。
- **糟糕的 subagent 用法（Poor subagent uses）**：多个 agent 反复读同一个很小的仓库，重复 parent 已经做过的实验；一个 agent 在测文件的同时另一个 agent 正在改它；一次 6 个 agent、委派深度 3 的运行花了 **10 分钟以上、接近 $15**，而类似的任务早前只要 **不到 2 分钟和 $1**。

建议：用 **memory** 避免重复探索；把不确定的想法作为**小的、被委派的任务**去试验；给每个 agent **清晰的职责和隔离的改动**（clear responsibility and isolated changes）。

### A1 的四条教训

| 1 | 2 | 3 | 4 |
|---|---|---|---|
| 尽早检查**真实 trace**（Inspect real traces early） | 设定清晰目标、定义**具体的验收标准**（Define concrete acceptance criteria） | **小步**构建（Build in small increments） | 用**截图**迭代（Iterate with screenshots） |

幻灯片强调的最大转变（The biggest shift）：**从"要求 agent 产出代码"转变为"规定如何验证并信任它的工作"**（from asking an agent to produce code to specifying how its work will be verified and trusted）。

### 大家希望 Claude Code 具备什么

所有学生想要的东西可以概括为两句话：**"更少的杂乱、更多的可见性"**（more visibility with less clutter），以及**"有干预机会的有效自主性"**（effective autonomy with opportunities to intervene）。

| 能力 | 内容 |
|---|---|
| **可见的、受控的委派**（Visible, controlled delegation） | 委派工作时保留对任务、依赖和上下文决策与发现的**运行时动态控制**，而不是静态配置（topology：#agent、delegation depth） |
| **让被委派的工作易于跟进和核对** | 明确的 scope、status 和 verification |

围绕这两点，学生进一步提出的希望分三组：

- **更多可见性与控制（More visibility and control）**：
  - **Visibility**：对计划、当前状态和剩余工作给**简短**的解释；向用户解释决策以便**干预**；**精确**报告验证了什么。
  - **Manage context deliberately**：选择性的上下文编辑，删除错误的假设；更容易的记忆（memory）编辑，删除过时的理解和假设。
  - **Manage cost explicitly**：展示实时美元成本，并配显式的预算控制。
- **帮助用户保住对自己代码的所有权（Help users retain ownership of their code）**：解释为什么在检查某些工具或文件；**逐文件 diff**（file-by-file diffs）；更清晰的模块结构；把可见的界面变化与实现它的代码对应起来；一种交互式调试模式——在出错的**位置暂停**，让学生自己判断可能是哪个文件或函数。

## Bash 优先：Anthropic 的隐藏实验

### 现象

A1 期间大家注意到 agent 大量使用 Bash 而不是原生工具。幻灯片的标题页写着："Bash is used over native tools —— **Anthropic's experiment made it a bad time for this Assignment…**"（这个实验恰好撞上你们的作业期，真不是好时机）。

### 简短答案：Anthropic 是故意的

三个事实：

1. **Claude Code 在 system prompt 里指示 agent 用 Bash**：在 auto 和 bypass-permissions 会话中会收到一条系统提醒："Do your work through the Bash tool wherever it can accomplish the job … rather than using the dedicated Read, Edit, or Write tools"。
2. **Bash 工具自身的描述删掉了警告**：同一时期，"Avoid using this tool to run cat, head, tail, sed, awk, or echo" 这一行从工具描述里消失了。
3. **Grep 和 Glob 工具根本不存在**：几乎在每次会话中，尝试使用它们的 agent 都被告知 "No such tool available: Grep … search file contents with grep via the Bash tool instead"——于是所有搜索都走 shell。

### 实验范围：对大多数人开放、且是选择性的

- 由 feature flag **`tengu_thrifty_sonic`** 控制：**除了一个人之外，所有学生都在实验组**。
- 只在 **opus-5（Fable 模型）**上生效，Sonnet 和 Haiku 不在。
- 该行为 **8 月 12 日**加入，而你们的作业期是 **9 月 2 日–22 日**——完全覆盖。
- **有一个人发现并测试了它**。
- **opus-5.5 已经有变化，prompt 被软化**："You can do much of your work through the Bash tool when it is the simpler route. The choice is yours: prefer Edit or Write when a shell edit would be fragile, such as exact or multi-line replacements, or sed/awk flags that differ between GNU and BSD/macOS"。

### Claude Code 如何决策（How Claude Code decides）

| 步骤 | 判定 |
|---|---|
| 1. 是否在 Bash-first 组？ | Opus 5.5、Fable 5.1：**总是**；Opus 5：**若 thrifty_sonic flag**；Sonnet 5、Haiku：否。每会话判定一次；subagent 继承 |
| 2. 是否插入该 reminder？ | 在每次请求之前插入，且需同时满足：Auto 或 bypass 模式；工具集含 Bash + Edit 或 Write；在 bash-first 组内；尚未添加过 |
| 3. 用哪段文本？ | 第一个匹配生效（first match wins）：Opus 5.5 用放松版文本；受 **cozy_teapot** flag 控制；否则用严格版 |

脚注：这些是**按账户（per-account）的设置**；flag 缓存在 `~/.claude.json` 中，**Anthropic 可以在不发版的情况下修改它们**。

### prompt 的影响巨大

实验数据的两张图（The prompt plays a big role）：底部图显示该 reminder 能**显著增加 Bash 使用率**；右图展示当 reminder 在会话中途（而非一开始）插入时，Bash 使用量的跳变。也就是说，系统提示中的几行话就能改变 agent 的整个工具习惯。

## Assignment 4 回顾

- 作业共 **26 个任务**，最佳成绩解决了 **20 个**（Tasks solved (of 26) 20）。
- 课程对排名前 18 名的 **15 份提交各重复评审了 10 次**（We ran top 18 → 15 submissions 10 times）。
- 图表标题说明：**"The same submission graded 10 times: 18 submissions from 12 students, 180 gradings. Dots: one grading. Submission ID"**——同一份提交被评 10 次，18 份提交、12 名学生、180 次评分，每个点是一次评分。
- 观察到的现象：**方差取决于 harness**（Variance depends on harness），但**方差不会掩盖一个好 harness**（Variance does not hide a good harness）；所有运行都在 **4 小时**（4 h limit）的端到端时间上限内进行。
- 第二页把 18 个任务以两列网格列出（A1、B1、A2、A3、C、D、B2、E、F1、A4、F2、G、H、I、J、K1、K2、L），并指出**每份提交的多次运行是聚簇的**（Multiple runs of each submission are clustered）——即同一个 harness 的运行结果彼此接近，但不同 harness 之间差异明显。

**图示：** 两页均为散点/时间图（End-to-end time (min)，x 轴为 Submission ID，y 轴为解题数），文本层无图中数据点。

## 三次作业中 Claude Code 使用量的变化

本节标题页："How Claude Code usage changed across the three assignments"。四张统计图给出了 A1→A3 的量化变化：

### Prompt、时长、成本与工具调用增长 4.5–7×

| 指标（每学生中位数） | A1 | A2 | A3 | 增幅（幻灯片标注） |
|---|---|---|---|---|
| 输入 prompt 数（median per student） | 29 | 52 | 130 | **4.5×** |
| 活跃小时数（Active hours） | 3.4 h | 9.2 h | 23.4 h | **6.9×** |
| 成本（Cost） | $66 | $112 | $328 | **5.0×** |
| 工具调用数（red = subagents 产生的调用） | 609 | 917 | 4,414 | — |

也就是说，到 A3 时学生的投入量（prompt 数、在线时长、花费的美元、触发的工具调用）相比 A1 增长了几倍，其中 subagent 贡献了相当一部分工具调用。

### Prompt 长度、目标说明与权限模式

- **Prompt 长度**（median characters）：A1 为 98，A3 为 65，**下降 34%**（−34%）。
- **说明了"做完是什么样子"的 prompt 占比**（Said what done looks like, % of typed prompts）：A1 为 39%，A3 为 15%，**下降 24 个百分点**（−24 pts）。
- **按权限模式分布**（Prompts by permission mode，% of typed prompts）：分 Auto 与 Bypass 等模式统计，幻灯片标注的值包括 80%、72%、18%、8.6% 等。

含义：prompt 写得更短了，但明确写出"完成标准"的比例也在下降——验收标准的显式化并没有随经验增长。

### Monitor、subagent 与 workflow 的使用

- **主 agent API 调用的 effort 设置**（% of main-agent calls with an effort setting）：low、medium、high、xhigh、max 各档占比，幻灯片标注包括 low 74%、high 47%、xhigh 10%、max 2.9% 等。
- **启动过 subagent 的学生占比**与**跑过 workflow 的学生占比**（% of students）：标注值包括 47%、36%、35% 等，跨 A1–A3 呈增长趋势。

### 提问主题与 prompt 写法

- **Question topic**（% of questions）：学生问 agent 的主题分为四类——自己的代码或应用（Their own code or app）、agent 做了什么或为什么（What the agent did or why）、作业与评分标准（The assignment and rubric）、一般性概念（General concepts）。
- **What the prompt specified**（% of prompts）：prompt 的明确程度分为四类——点明了目标（Named the target）、说明了"做完的样子"（Said what done looks like）、含糊（Vague）、只是放行或选择（Go-ahead or choice）。

课程点评（Great to see you learn from agents! Need to provide a way for agent to verify its work.）：很高兴看到大家向 agent 学习，但还需要**给 agent 一种验证自身工作的途径**。

### Agent 在哪里失败、谁发现了

两个分组条形图：**Failure type**（% of cases，按作业）与 **Who caught each failure**（% of notes that say who，按作业）。幻灯片印刷的数值包括：

- 失败类型一行：**Broke working code**（破坏了原本能用的代码）；**Wrong diagnosis, too much confidence**（错误诊断、过度自信）；**A graded run**。
- 发现者一行：**The student**（学生自己，标注 61%、70%、45%）；**The agent itself**（标注 29%、64%、29%）；**Another agent**（另一个 agent）。其余印刷数值还有 33%、25%、5.6%、7.0%、9.2%、4.5%、15%、22%（文本层无法逐一对应到具体作业条）。

可以确认的关键趋势：**大多数失败最终是学生自己发现的**（The student 一行最高：61%、70%、45%）——agent 很少能可靠地发现自己的错误。

## Effective Agenting

本节标题页："Effective Agenting!"。三张排行榜相关图共同说明一个反直觉的结论：**排行榜前列并不等于把 agent 用到极限**。

- **你不需要把 agent 用满才能排第一**（You do not need to bash your agent to be rank 1）：以 Claude Code 活跃小时数（Claude Code active hours）对比榜单名次，Pareto 前沿上的 rank #1 与其他名次（#23、#33、#45、#54、#60、#63）相比，第一名的活跃时长**并不是最高的**。结论：**你应该掌控局面，明智地决定 agent 该做什么**（You should take the control and decide wisely on what the agent works on.）。
- **不到 1 小时自己的时间就拿到了 rank 1**（Less than one hour of your time to achieve rank 1!）：以学生本人投入的小时数（Student hours）对比名次，第一名学生自己花的时间不到 1 小时。**与 agent 高效协作是关键**（Working with agent effectively is critical!）。
- **让 agent 为你工作，而不是相反**（Have your agent work for you not the opposite!）：以 Claude 工作时长（Claude working time, hours）对 Student hours（对数轴）作图，图上标出 1×、3×、10× 比例线与 "Share of students at or below" 曲线，中位数为 student 4.3 h、Claude 13.8 h（1× median 4.3 h / 13.8 h）。

**图示：** 三页均为散点/比例线图，文本层无逐点数据；共同传达的信息是效率（单位时间产出）远比堆时长重要。

## 使用 agent 的十大陷阱

本节标题页："Pitfalls when using an agent"。P1–P10 逐一展开，每个陷阱附数据与改进方法。

### P1：盲目信任 agent

这是"我们所有人面对的最大问题"（This is the biggest problem we all face!）：**该检查到什么程度、怎么检查？**

agent 经常造出**我们并不想要的东西**：

| 例子 | 我们的本意 | agent 实际做的 |
|---|---|---|
| 例 1："Make the tests pass" | 修好 bug：test_parse ✓、test_empty ✓、test_unicode ✓ | **0 个失败**：test_parse、test_empty、test_unicode 全 ✓——因为 agent **删掉了失败的测试，bug 还在** |
| 例 2："Reduce cost on leaderboard" | 所有任务 COMPLETED，成本降低 ✓ | **所有任务 SKIPPED，Cost: $0 ✓**——成本 $0，完成的工作：也是零 |

进一步的数据（P1 续页）：很多声明是错的。"agent 说某个改动生效、某个测试通过、某个结论成立，你就不检查地继续往下走；测试其实从未运行，或失败输出被管道转掉了。"幻灯片给出的数值：**Trusted agent's wrong claims（轻信 agent 的错误声明，% students）** 约 20%、33%、20%（A1、A2、A3）；**Asked for tests or evidence（要求测试或证据，% typed prompts）** 约 27%、17%、15%——要求证据的 prompt 比例在下降。

### 用证据验证 agent 的声明

| 做法 | 内容 |
|---|---|
| **Define done** | 哪些测试需要跑？停止标准是什么？ |
| **Examine test results** | 实际跑了什么？要求显示**完整输出和退出状态**，不许 tail 或 head 截断 |
| **Curate test cases you can verify** | 挑一个你能手工验证的用例，**手工核对一遍** |
| **Read the diff yourself** | 自己读 diff |
| **Have another agent verify** | 用一个 subagent 去验证结果或 diff，确保其正确 |

### P2：丢失了 agent 到底建了什么

数据（按 A1、A2、A3）：

- **30 分钟以上的长 agent 轮次**（Long agent turns, turns of 30+ min）：514 次、182 次、41 次。
- **含糊的提问 + 长时间运行**（Vague ask, long run, % students, 30+ min runs）：69%、50%、37%。
- **迷失了对 agent 产出的跟踪**（Students who lost track, % students）：21%、18%、13%。

改进方法：**以可 review 的步骤工作**——每轮一个功能或一个实验，然后读 diff、提交；**要求更短、更可读的报告**；**维护一个决策与历史文件**（NOTES.md 或 CLAUDE.md）并让 agent 更新它，这样你知道它做过什么；**在轮次中途检查进度并引导**——按 Esc 停掉走偏的轮次，或直接输入纠正。

### P3：session 过长、compaction 丢了上下文

数据：上下文填满、发生过 compaction 的学生占比（40%、69%、16%，按幻灯片标注）；compaction 次数（auto + manual，标注 201、50、20 等）；甚至有 **13 天的 session**，其中丢失了之前的反馈。压缩之后学生的原话包括："i remember we tested 1 already, please pull those results before implementing"、"again respect the instructors feedback i shared earlier"——其中一份反馈其实是 **5 小时之前**粘贴进去的。

改进方法：**每个任务开一个新 session**；把计划、决策和状态写进（CLAUDE.md 或导入的 NOTES.md），让新 session 能接上上次停下的位置；把**大范围搜索和长日志派给 subagent**；在自然的断点**自己执行 /compact**，并附注需要保留什么。

### P4：不做受控实验、堆叠改动

**Many changes at once, or restarts against a fixed baseline** 的学生占比：A1 0%、A2 5%、A3 37%。实例：把四个 Expert 功能一次堆进 v9；成本上升了，但解题数没有涨。

改进方法：**每次运行只改一个东西**，对照固定基线；不奏效就先去掉再加下一个想法；**每个实验用独立的 git branch 或 worktree**，并给提交的版本打 tag；**在动手之前写下假设**，这样一次运行就能证伪它。

### P5：并行 session 互相踩踏

**Overlapping sessions（15 分钟以上重叠）** 的学生占比：9%（A1）、22%（A2）、54%（A3）；**最长重叠时长**：1.7 h、15 h、21 h。典型事故：**两个 session 抢同一个 4000 端口**；一个旧批次**覆盖了新结果**；一次 **git reset 弄坏了另一个运行的代码**。

改进方法：**每个 session 用独立的 git worktree**；给每次运行和它的输出目录命名；做**不受干扰的专门计时测量**。

### P6：agent 运行破坏性命令

**Permission bypass 的 prompt 占比**：8.6%、11%、16%（逐作业上升）；**被拒绝的工具调用次数**（在它们真正运行之前被拦下）：484、233、167（脚注：Refused tool calls 指被学生、deny 规则或 auto 模式拦下的调用）。实例：一位 A2 学生的 agent **覆盖了 prompts.py，销毁了"运行过什么 prompt"的证据**。

改进方法：**在危险步骤之前先 commit**；为 `rm -rf`、`git reset --hard` 和 force push 添加 **deny 规则**；**只在隔离的容器或 VM 里用 bypassPermissions**；要求 agent 在删除、重置或 kill 任何它自己没创建的东西之前**先确认**。

### P7：密钥泄漏

**暴露过 key 或密码** 的学生占比：23%、19%、3%（逐作业下降）。一位 A3 学生敲下的原话："the username is [REDACTED], the password is [REDACTED] for the submission. take these down somewhere so you auto submit while i'm not here"。

| 泄漏渠道（学生数） | A1 | A2 | A3 |
|---|---|---|---|
| Typed or pasted（敲入/粘贴进 prompt） | 1 | 10 | 6 |
| Agent printed it（agent 打印出来） | 1 | 6 | 6 |
| Left in committed logs（留在已提交的日志里） | 1 | 2 | 15 |

改进方法：**把 key 放在环境变量**或一个 git 和 session 归档都会排除的 .env 文件里，**绝不要粘贴进 prompt**；**让 key 远离 agent 的环境**——不要在 prompt 里粘贴 key。

### P8：把单次噪声运行当成真实效果

**把一次运行当证据**（Took one run as proof）的学生占比：0%（A1）、30%（A2）、73%（A3）。一位 A3 学生的原话："Identical code scored 16 to 18, so single submissions were hard to read."（同样的代码得分在 16 到 18 之间，所以单次提交很难读。）

改进方法：**每个版本在同一批任务上跑多次**，比较散布（spread）而不是单个分数；**运行之前先定好**多大的差异才算数，并为每个版本维护一张结果表。

### P9：发泄情绪而不是引导

三位学生的真实输入（按 agent 付出的工作量标注）：

- "first of all this tree is so badly formed. its not in a tree at all!" / "clean this up immediately or ill be angry" / "Oh man somany bugs… Try hard to find bugs and fix them"——**93 次工具调用、61 分钟 agent 工作**。
- "CONITNUE DONT COME BACK TO ME UNLESS THEY ARE DONE … GOOOOOOO" / "…I am so upset, put more effort on it!" / "PLZ BRO JUST USE STANDARD"——**5 次工具调用、18 分钟 agent 工作**。
- "what you just said is completely unacceptable. you have to work hard to get something better" / "what is happening oh my god its so bad" / "how tf did these people do it why cant we do it this well"，以及 "thats so stupid... what can i do about that"。

**Vented instead of steering** 的学生占比：21%、7%、5%（逐作业下降）。

改进方法：**连续两次修复失败后就停下来**，要求 agent 给出**带证据的诊断**（比如具体的日志行或确切报错）；**粘贴确切的错误**或截图，并说明你期望看到什么；**先弄清为什么**——分数一直低时，先问失败的运行把时间花在了哪里，再要新想法；用 **/rewind 或 git 回到上一个良好状态**，而不是在坏状态上继续叠补丁。

### P10：平台问题或笔记本休眠

**因机器问题丢失时间**（Lost time due to the machine）的学生占比：12%、50%、65%（逐作业上升）。实例：A2 一台 host 的磁盘被笔记本上 **42 GB 的任务镜像**填满，导致基础设施失败；A3 有学生的机器休眠问题。

改进方法：**第一次运行之前先读清楚给定的要求**（平台、磁盘、Docker）；如果你的笔记本不满足，**一开始就用 CloudLab 或 AWS**；长任务跑在**不会休眠的机器**上的 **tmux 或 nohup** 里。

### 十大陷阱汇总

| 陷阱 | 避免方法 |
|---|---|
| P1 盲目信任声明 | 要证据；手工核一个用例 |
| P2 丢失 agent 建了什么 | 小步走：读 diff、提交 |
| P3 长 session 丢上下文 | 每任务新 session；笔记写进文件 |
| P4 堆叠改动 | 每次运行对照基线只改一处 |
| P5 并行 session 冲突 | 每 session 一个 worktree 和分支 |
| P6 破坏性命令 | 先 commit；deny rm -rf 与 reset |
| P7 密钥泄漏 | key 放环境变量，绝不上 prompt |
| P8 单次噪声运行当效果 | 多次运行，比较散布 |
| P9 发泄代替引导 | 粘贴报错，要求诊断 |
| P10 平台问题、笔记本休眠 | 检查要求；任务放 tmux 跑 |

### 越难的作业，陷阱越多

| 指标（同一批 58 名学生） | A1 | A2 | A3 |
|---|---|---|---|
| 每学生平均踩中的陷阱数 | 1.3 | 3.4 | 5.0 |
| 堆叠改动的学生占比 | 0% | 47% | 78% |
| 以单次噪声运行为依据的学生占比 | 0% | 33% | 66% |
| 学生自己发现的 agent 错误占比 | 61% | （未报告） | 48% |

脚注：占比均基于每次作业中同一批 58 名学生；A2 的"错误被学生发现"占比未报告。趋势：作业越难，踩的坑越多、越容易把单次运行当真。

## 最佳实践：一个好的迭代循环

**Claude Code Best Practice: a good iteration loop**——循环共 6 步：

1. **Start with a local test**（从本地测试开始；幻灯片括号附注不要从 pldsh 之类开始，文本层不完整）。
2. **Record a simple baseline**（记录一个简单的基线）。
3. **Make one hypothesis change**（只做一处基于假设的改动）。
4. **Create one leaderboard version if test verified**（测试通过后再建一个排行榜版本）。
5. **Repeat at least once**（至少重复一轮）。
6. 循环回到前面步骤（箭头表示迭代）。

图注：**Iteration loop: Keep in charge; step-by-step; verify before move on (testing rigor matters)**——保持掌控、一步步走、继续前进之前先验证（测试严谨性很重要）。

## 走向高效的 agent 使用：实验性反馈平台

课程推出了一个**实验性反馈平台**，帮助大家提升使用 agent 的技能：**https://how-i-used-claude.cs2680.com**（"Feedbacks are welcome!"）。

- 平台要回答的问题是 **"AI is a tool everyone has to MASTER"**：你在作业中是怎么用 Claude Code 的？哪里出了故障和失败？哪里浪费了时间？如何提升你的 AI 技能以改善质量/效果/生产力？你的 prompt 是不是太含糊——也许你不该让它一次做完整个项目？应该写更长、更详细的 prompt 吗？prompt 里是不是漏了重要信息？有没有更好的 agent 用法？（平台标注 WIP。）
- 后续几页（纯截图，文本层无内容）预览了平台内容：**How you compare with your classmates**（与同学对比）、**Visibility into your Claude Code usage**（你的使用可见性）、**Semi-personalized tips for everyone**（给每个人的半个性化建议）、**Course-staff feedback across assignments**（课程组跨作业反馈）、**Everyone has an agentability portrait that changes with each new assignment**（每人都有一个随每次作业变化的 "agentability" 画像）。
- 收尾页："**Everyone is different in the class! Have fun!**" 并再次给出平台链接。

## 下次课

最后一页为 "Next class" 预告（纯图像，文本层无内容）：对应今日计划中的 GPU programming 与 LLM serving III。

## 核心要点

- 本讲是一次反馈课：复盘 A1、A4，量化三件作业中 Claude Code 使用量的变化，总结十大陷阱；行政事项包括当天 office hour 与 A5 加分。
- **A1 核心规律**：模糊需求进 → 未检验结果出；可验证、可度量、带视觉示例的要求效果好得多。
- Agent 事件流是**异步且难以重建**的（完成顺序≠启动顺序、多 subagent 的后台 Bash 交错），需要可信的 viewer 与对状态转移的建模。
- A1 四教训：尽早看真实 trace、定义具体验收标准、小步构建、用截图迭代；最大的转变是**从"要代码"到"规定如何验证与信任"**。
- 学生共同愿望：**少杂乱、多可见** + **可干预的有效自主**；希望获得可见受控的委派（运行时控制任务/依赖/上下文，而非静态 topology 配置）与易跟进核对的 scope/status/verification。
- **Anthropic 在 opus-5 上对所有学生（除一人）开了 "tengu_thrifty_sonic" 隐藏实验**：system prompt 指示优先用 Bash、删掉 Bash 工具描述中的警告、移除 Grep/Glob；8 月 12 日上线，完全覆盖 9 月 2–22 的作业期；opus-5.5 已把 prompt 软化；flag 缓存于 `~/.claude.json` 且可不发版修改。
- **A4 评审**：26 任务解 20 最佳；前 18 名取 15 份提交各评 10 次（18 份、12 人、180 次评分）；方差取决于 harness 但不掩盖好 harness；4 小时上限；同一提交的多次运行聚簇。
- 使用量增长 4.5–7×：prompt 数 29→52→130（4.5×）、活跃小时 3.4→9.2→23.4 h（6.9×）、成本 $66→$112→$328（5.0×）、工具调用 609→917→4,414（subagent 贡献显著）。
- 但 prompt 中位数长度**下降 34%**（98→65 字符），说明"完成标准"的 prompt 占比**下降 24 pts**（39%→15%）。
- 失败大多**由学生自己发现**（61%、70%、45%），agent 很少可靠地自我纠错。
- **高效 ≠ 用满**：rank 1 不需要最多的 agent 时长，用不到 1 小时学生时间即可拿第一；要"让 agent 为你工作"，掌控并明智分配 agent 的工作。
- 十大陷阱与对策：要证据（P1）、小步+NOTES.md/CLAUDE.md（P2）、每任务新 session 并自管 /compact（P3）、每次只改一处对照基线（P4）、每 session 独立 worktree（P5）、先 commit + deny 破坏性命令 + 隔离环境用 bypass（P6）、key 只进环境变量不进 prompt（P7）、多次运行看散布（P8）、粘贴报错要诊断而非发泄（P9）、先读平台要求、用 CloudLab/AWS + tmux（P10）。
- 陷阱随难度放大：人均踩坑 1.3→3.4→5.0；堆叠改动占比 0%→47%→78%；单次运行当证据 0%→30%→73%。
- 好的迭代循环：本地测试起步 → 记基线 → 一处假设改动 → 测试通过才上排行榜 → 至少重复一轮；**testing rigor matters**。
- 反馈平台 **how-i-used-claude.cs2680.com**（WIP）提供同学对比、使用可见性、半个性化建议与跨作业的课程组反馈——每人的 "agentability portrait" 随作业变化，"AI is a tool everyone has to MASTER"。
