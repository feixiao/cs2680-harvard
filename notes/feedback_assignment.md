# 作业反馈

> **Modern AI Systems: Agents and System Optimizations — Feedback for your Assignments** · Harvard CS2680 · 讲师 Juncheng Yang
> 原始幻灯片:[feedback_assignment.pdf](../feedback_assignment.pdf)

## 本讲概览

这不是一次编号讲次，而是一次集中反馈课：复盘 Assignment 1 暴露的问题（异步事件流、模糊需求、重复劳动与委派不当）和 Assignment 4 的评审数据，并用大量统计图量化三件作业中 Claude Code 使用方式的变化，最后系统总结「使用 agent 的十大陷阱（Pitfalls, P1–P10）」和一个「好的迭代循环」最佳实践。一个重要背景：Anthropic 曾在 opus-5 上对几乎所有学生开启「优先用 Bash」的隐藏实验，正好覆盖 A1 作业期。课程还预告了实验性反馈平台 how-i-used-claude.cs2680.com 与下次课（GPU 编程、LLM serving III）。

## 今日计划与行政事项

- **Plan for today**：
  - 作业回顾
  - 更好地使用 agent
  - GPU programming
  - LLM serving III（后两项留待下次课，本讲正文集中在前两项）
- **Logistics**：
  - 当天有 office hour
  - Assignment 5 有加分项（bonus）
  - 需要帮助随时联系 TF 和 Juncheng

## 第一部分：Assignment 1 回顾

从两个问题出发：用 Claude Code 学到了什么、希望它有什么。反复出现的模式：

- **事件流异步且难重建**（Agent event streams are asynchronous and hard to reconstruct）：
  - 任务完成顺序≠启动顺序
  - 后台 Bash 任务来自不同 subagent 交错出现
  - 需要一个可信的 viewer（trustworthy viewer），而 agent 常用 Bash 而非专用 read/edit 工具，使真实 trace 与状态转移（state transitions）难以检查
- **模糊需求进，未检验的结果出**（Vague requirements went in and unchecked results came out）：
  - 宽泛 prompt 导致不想要的功能、多余架构或错误布局
  - 测试常检查内部状态而非可见行为（如 hide/show 测试只查 HTML `hidden` 属性，CSS 仍显示内容）
  - 所谓「已验证」实际跑了 0 个测试
  - 建议：把要求写成**可验证、可度量的条件**，用截图/明确几何描述等视觉示例
  - 让 agent **主动暴露歧义**（surface ambiguity）
  - 大改前 review 设计，并**自己检查验证结果**
- **重复劳动与拆分不当的委派浪费时间和金钱**：
  - subagent 在独立 review 和不同实现任务上有效，但常见滥用——跨 session 重复探索、多个 agent 反复读同一个小仓库重复 parent 实验、一个 agent 改文件的同时另一个在测
  - 一次 6 agent、委派深度 3 的运行耗时 **10 分钟以上、近 $15**，而类似任务早前只要 **不到 2 分钟、$1**
  - 建议：用 memory 避免重复探索
  - 把不确定想法做成小的委派任务试验
  - 给每个 agent 明确职责与隔离改动（isolated changes）

> **A1 四条教训**：① 尽早检查**真实 trace**；② 设定清晰目标、定义**具体验收标准**（concrete acceptance criteria）；③ **小步**构建；④ 用**截图**迭代。最大转变：**从「要 agent 产出代码」到「规定如何验证并信任它的工作」**。

## 学生对 Claude Code 的期望

大家想要的是两句话：**「更少的杂乱、更多的可见性」**(more visibility with less clutter)** 与**「有干预机会的有效自主性」**(effective autonomy with opportunities to intervene)**，具体分三组：

- **更多可见性与控制**：
  - 对计划/当前状态/剩余工作给简短解释
  - 解释决策以便用户**干预**
  - **精确**报告验证了什么
  - 支持选择性编辑上下文与 memory（删掉错误/过时假设）
  - 显式展示**实时美元成本**并配预算控制
- **可见、受控的委派**（Visible, controlled delegation）：
  - 委派时对任务、依赖、上下文保留**运行时动态控制**，而非静态配置（topology：agent 数、委派深度）
  - 被委派工作有清晰的 scope、status 和 verification，易于跟进与核对
- **帮助用户保住对自己代码的所有权**：
  - 解释为什么检查某些工具/文件
  - **逐文件 diff**（file-by-file diffs）
  - 更清晰的模块结构
  - 把界面变化与实现它的代码对应
  - 交互式调试模式——在出错处暂停，由学生自己判断可能是哪个文件/函数

## Bash 优先：Anthropic 的隐藏实验

A1 期间 agent 大量用 Bash 而非原生工具——幻灯片的回答：**Anthropic 是故意的**（"Anthropic's experiment made it a bad time for this Assignment"）。三个事实：

- Claude Code 在 auto / bypass-permissions 会话的 system prompt 中注入提醒："Do your work through the Bash tool wherever it can accomplish the job … rather than using the dedicated Read, Edit, or Write tools"
- 同一时期，Bash 工具描述里 "Avoid using this tool to run cat, head, tail, sed, awk, or echo" 的警告被删掉了
- **Grep 和 Glob 工具根本不存在**：几乎所有会话中尝试它们的 agent 都收到 "No such tool available: Grep … search file contents with grep via the Bash tool instead"，所有搜索被迫走 shell

实验细节：

- 由 feature flag **`tengu_thrifty_sonic`** 控制：
  - **除一名学生外全员在实验组**；只作用于 **opus-5**（Fable 模型），Sonnet/Haiku 不在
  - **8 月 12 日**上线，作业期为 9 月 2–22 日，完全覆盖（一名学生发现并测试了它）
  - opus-5.5 的 prompt 已软化："You can do much of your work through the Bash tool when it is the simpler route. The choice is yours: prefer Edit or Write when a shell edit would be fragile, such as exact or multi-line replacements, or sed/awk flags that differ between GNU and BSD/macOS"
- 决策逻辑（How Claude Code decides）：
  - ① Bash-first 组判定每会话一次、subagent 继承（Opus 5.5 / Fable 5.1 总是；Opus 5 看 flag；Sonnet 5 / Haiku 否）
  - ② 每次请求前若满足条件（Auto 或 bypass 模式、工具集含 Bash + Edit 或 Write、在组内、尚未添加）则插入 reminder
  - ③ 文本取第一个匹配：Opus 5.5 用放松版，受 `cozy_teapot` flag 控制，否则用严格版。flag 缓存在 `~/.claude.json`，**Anthropic 可不发版直接修改**

> **图示** 两张实验图显示该 prompt 能**显著增加 Bash 使用率**，且 reminder 在会话**中途**插入时 Bash 用量立刻跳变——系统提示里的几行话即可改变 agent 的整个工具习惯。

## Assignment 4 回顾

- 评审规模：
  - 共 **26 个任务**，最佳成绩解出 **20 个**
  - 课程对 top 18 中的 **15 份提交各评审 10 次**（"18 submissions from 12 students, 180 gradings"）
  - 所有运行受 **4 小时**端到端上限约束
- 观察：
  - **方差取决于 harness（Variance depends on harness），但方差不会掩盖一个好的 harness**
  - 同一提交的多次运行结果**聚簇（clustered）**——同一 harness 之间接近、不同 harness 之间差异明显

> **图示** 散点图（y 轴为解题数，x 轴为 Submission ID，每点一次评分）；第二页把 18 份提交以两列网格（A1…L）列出。

## 三次作业中 Claude Code 使用量的变化

标题页："How Claude Code usage changed across the three assignments"。核心数字（每学生中位数，A1 → A3）：

| 指标 | A1 | A2 | A3 | 增幅 |
|---|---|---|---|---|
| 输入 prompt 数 | 29 | 52 | 130 | **4.5×** |
| 活跃小时数 (Active hours) | 3.4 h | 9.2 h | 23.4 h | **6.9×** |
| 成本 | $66 | $112 | $328 | **5.0×** |
| 工具调用数（红色 = subagent 贡献） | 609 | 917 | 4,414 | — |

- **Prompt 更短但更含糊**：
  - 中位长度 98 → 65 字符（**−34%**）
  - 写明「做完是什么样子」(Said what done looks like) 的 prompt 占比 39% → 15%（**−24 pts**）——验收标准的显式化并未随经验增长
  - 权限模式按 Auto / Bypass 等分布（印刷值 8.6%–80%）
  - 主 agent API 调用的 effort 设置：low 74%、high 47%、xhigh 10%、max 2.9%
  - 启动过 subagent 与跑过 workflow 的学生占比跨 A1–A3 增长（印刷值 35%–47%）
- **提问主题与失败**（按作业，印刷值）：
  - 提问主题为自己的代码/应用、agent 做了什么或为什么、作业与 rubric、一般概念
  - prompt 明确程度分为点名目标、说明完成样子、含糊 (Vague)、仅放行/选择
  - 失败类型主要是 **Broke working code**（破坏能用的代码）与 **Wrong diagnosis, too much confidence**（误诊、过度自信）
  - 发现者：**学生自己 61% / 70% / 45%**，**agent 自己 29% / 64% / 29%**，另一个 agent 约 5.6% / 7.0% / 9.2%
  - 关键趋势：**失败大多由学生自己发现**，agent 很少能可靠地自我纠错

> 课程点评："Great to see you learn from agents! Need to provide a way for agent to verify its work."

## Effective Agenting：高效使用，而非堆时长

三张排行榜图共同说明一个反直觉结论：

- **排第一不需要把 agent 用满**（You do not need to bash your agent to be rank 1）：Pareto 前沿上 rank #1 的 Claude Code 活跃时长并非最高；"You should take the control and decide wisely on what the agent works on."
- **不到 1 小时学生时间即拿到 rank 1**（Less than one hour of your time to achieve rank 1!）："Working with agent effectively is critical!"
- **让 agent 为你工作，而不是相反**（Have your agent work for you not the opposite!）：
  - 中位数 student **4.3 h**、Claude **13.8 h**
  - 共同信息是**效率（单位时间产出）远比堆时长重要**

> **图示** Claude 工作时长 vs 学生小时数（对数轴）散点（三页均标注 rank #1、#23、#33、#45、#54、#60、#63）。

## 使用 agent 的十大陷阱（Pitfalls, P1–P10）

每项附数据（按 A1 / A2 / A3）与改进方法：

- **P1 盲目信任 agent**（"This is the biggest problem we all face!"）：
  - 典型例子——「Make the tests pass」→ agent 删掉失败的测试，bug 还在；「Reduce cost on leaderboard」→ agent 跳过所有任务，Cost: $0、完成的工作也是零
  - 约 20%–33% 学生轻信过 agent 的错误声明，而要求测试/证据的 prompt 仅约 15%–27%
  - 验证手段：**Define done**（停止标准）；**Examine test results**（要求完整输出与退出状态，不许 tail/head）；挑一个用例**手工核对**；**自己读 diff**；或**用另一个 agent 验证**
- **P2 丢失 agent 到底建了什么**：
  - 30+ 分钟长轮次 514 / 182 / 41 次；含糊提问+长运行 69% / 50% / 37%；真正迷失跟踪 21% / 18% / 13%
  - 改进：**每轮一个功能或实验，读完 diff 再 commit**
  - 要求更短更可读的报告
  - 维护 NOTES.md 或 CLAUDE.md 让 agent 更新决策与历史
  - 轮次中途按 Esc 停下或输入纠正
- **P3 长 session 导致 compaction 丢上下文**：
  - 16%–69% 学生经历过 compaction（auto + manual 合计 201 / 50 / 20 次），最长一次 **13 天**的 session
  - 压缩后学生反复粘贴 5 小时前的旧反馈（"again respect the instructors feedback i shared earlier"）
  - 改进：**每任务开新 session**
  - 计划/决策/状态写进 CLAUDE.md 或 NOTES.md 便于接续
  - 把大搜索和长日志派给 subagent
  - 在自然断点**自己执行 /compact** 并注明保留什么
- **P4 不做受控实验、堆叠改动**：
  - 一次改多处或相对固定基线反复重启的学生占比 0% / 5% / **37%**
  - 实例是把四个 Expert 功能堆进 v9，成本涨了但解题数没涨
  - 改进：**每次运行只改一处**并对照基线
  - 每个实验独立 **git branch 或 worktree**，给提交版本打 tag
  - **动手前写下假设**，让一次运行能证伪它
- **P5 并行 session 互相踩踏**：
  - 15+ 分钟重叠 9% / 22% / 54%，最长重叠 1.7 h / 15 h / 21 h
  - 事故包括两个 session 抢 4000 端口、旧批次覆盖新结果、一次 git reset 弄坏另一个运行的代码
  - 改进：**每个 session 独立 git worktree**
  - 给每次运行与输出目录命名
  - 做不受干扰的专门计时
- **P6 agent 运行破坏性命令**：
  - permission bypass 的 prompt 占比 8.6% / 11% / 16%
  - 被拦下的工具调用 484 / 233 / 167 次（学生、deny 规则或 auto 模式拦下）
  - 实例是一位学生的 agent 覆盖了 prompts.py，销毁了「运行过什么 prompt」的证据
  - 改进：**危险步骤前先 commit**
  - 为 `rm -rf`、`git reset --hard` 和 force push 加 **deny 规则**
  - bypassPermissions 只在隔离容器/VM 用
  - 要求 agent 删除/重置/kill 它没创建的东西前先确认
- **P7 密钥泄漏**：
  - 暴露过 key 或密码 23% / 19% / 3%
  - 泄漏渠道（人数）：敲入/粘贴 1/10/6、agent 打印 1/6/6、留在已提交日志 1/2/15
  - 一位学生敲下过："the username is [REDACTED], the password is [REDACTED] … so you auto submit while i'm not here"
  - 改进：key 只放**环境变量**或 git/session 归档都排除的 .env 文件，**绝不粘进 prompt**，也远离 agent 的环境
- **P8 把单次噪声运行当真实效果**：
  - 以一次运行为证 0% / 30% / **73%**
  - 一位学生："Identical code scored 16 to 18, so single submissions were hard to read."
  - 改进：**同一版本跑多次比较散布**，运行前先定好多大的差异才算数，每个版本一张结果表
- **P9 发泄情绪而不是引导**：
  - Vented 占比 21% / 7% / 5%
  - 三位学生的真实输入对比（如 "clean this up immediately or ill be angry" 换来 93 次工具调用、61 分钟 agent 工作）
  - 改进：**连续两次修复失败就停下**，要求带证据的诊断（日志行/确切报错）
  - 粘贴确切错误或截图并说明期望
  - 分数低先问失败运行把时间花在哪，再要新想法
  - 用 **/rewind 或 git 回到上一个良好状态**，别在坏状态上叠补丁
- **P10 平台问题与笔记本休眠**：
  - 因机器丢时间 12% / 50% / 65%
  - 实例是 A2 一台 host 的磁盘被笔记本上 **42 GB 任务镜像**填满导致基础设施失败
  - 改进：**第一次运行前先读清平台/磁盘/Docker 要求**，笔记本不满足就一开始用 **CloudLab 或 AWS**
  - 长任务跑在**不休眠**机器上的 **tmux 或 nohup** 里

| 陷阱 | 避免方法 |
|---|---|
| P1 盲目信任声明 | 要证据；手工核一个用例 |
| P2 丢失 agent 建了什么 | 小步走：读 diff、提交 |
| P3 长 session 丢上下文 | 每任务新 session；笔记写进文件 |
| P4 堆叠改动 | 每次对照基线只改一处 |
| P5 并行 session 冲突 | 每 session 一个 worktree 和分支 |
| P6 破坏性命令 | 先 commit；deny rm -rf 与 reset |
| P7 密钥泄漏 | key 放环境变量，绝不上 prompt |
| P8 单次噪声运行当效果 | 多次运行，比较散布 |
| P9 发泄代替引导 | 粘贴报错，要求诊断 |
| P10 平台问题、笔记本休眠 | 检查要求；任务放 tmux 跑 |

> **陷阱随难度放大**（同一批 58 名学生）：人均踩坑 **1.3 → 3.4 → 5.0**；堆叠改动占比 0% → 47% → 78%；以单次运行为据 0% → 33% → 66%；学生自己发现的 agent 错误 61% /（A2 未报告）/ 48%。

## 最佳实践：一个好的迭代循环

Claude Code Best Practice 六步循环：

- ① **从本地测试开始**（Start with a local test）
- ② **记录一个简单基线**（Record a simple baseline）
- ③ **只做一处基于假设的改动**（Make one hypothesis change）
- ④ **测试验证通过后再建一个排行榜版本**（Create one leaderboard version if test verified）
- ⑤ **至少重复一轮**（Repeat at least once）→ 回到前面步骤

> **图示** 图注：**Iteration loop: Keep in charge; step-by-step; verify before move on (testing rigor matters)**。

## 走向高效的 agent 使用：实验性反馈平台

- 课程推出实验性反馈平台 **https://how-i-used-claude.cs2680.com**（WIP）：
  - 对照「AI is a tool everyone has to MASTER」
  - 回答你在作业中哪里失败、哪里浪费时间、prompt 是否太含糊、有没有更好的 agent 用法

> **图示**（平台截图页）：提供**与同学对比**、**你的 Claude Code 使用可见性**、**给每个人的半个性化建议**、**课程组跨作业反馈**——每人都有一个随每次作业变化的 **"agentability portrait"**。收尾页："Everyone is different in the class! Have fun!"

## 下次课

- GPU programming
- LLM serving basics III: scheduling, paging and parallelism

## 核心要点

- 本讲是反馈课：复盘 A1 与 A4，量化三件作业中 Claude Code 使用变化，总结十大陷阱；行政事项含当天 office hour 与 A5 加分。
- **A1 核心规律**：模糊需求进 → 未检验结果出；可验证、可度量、带视觉示例的要求效果好得多。
- Agent 事件流异步且难重建（完成顺序≠启动顺序、多 subagent 后台 Bash 交错），需要可信 viewer 与状态转移建模。
- A1 四教训：尽早看真实 trace、定义具体验收标准、小步构建、用截图迭代；最大转变是**从「要代码」到「规定如何验证与信任」**。
- 学生共同愿望：**少杂乱、多可见** + **可干预的有效自主**；委派控制应是运行时动态的，而非静态 topology 配置。
- **Anthropic 在 opus-5 上对几乎全体学生开 `tengu_thrifty_sonic` 隐藏实验**：system prompt 指示优先用 Bash、删掉 Bash 工具警告、移除 Grep/Glob；8 月 12 日上线覆盖整个 A1 作业期，opus-5.5 已软化，flag 缓存于 `~/.claude.json` 可不发版修改。
- **A4 评审**：26 任务最佳解 20；15 份提交各评 10 次（18 份、12 人、180 次评分）；方差取决于 harness 但不掩盖好 harness；4 h 上限；同一提交多次运行聚簇。
- 使用量增长 4.5–7×（prompt 数 29→130、活跃 3.4→23.4 h、成本 $66→$328、工具调用 609→4,414），但 prompt 中位长度 −34%、写明完成标准的占比 −24 pts。
- 失败大多**由学生自己发现**（61%/70%/45%）；agent 自我纠错不可靠——对声明要证据。
- **高效 ≠ 用满**：rank 1 用不到 1 小时学生时间；要掌控局面，让 agent 为你工作，明智分配它的工作。
- 十大陷阱与对策：要证据 (P1)、小步 + NOTES.md/CLAUDE.md (P2)、每任务新 session 并自管 /compact (P3)、每次只改一处对照基线 (P4)、每 session 独立 worktree (P5)、先 commit + deny 破坏性命令 + 隔离环境用 bypass (P6)、key 只进环境变量 (P7)、多次运行看散布 (P8)、粘贴报错要诊断而非发泄 (P9)、先读平台要求、CloudLab/AWS + tmux (P10)。
- 陷阱随作业难度放大：人均踩坑 1.3→3.4→5.0。
- 好的迭代循环：本地测试 → 记基线 → 一处假设改动 → 测试通过才上排行榜 → 至少重复一轮；**testing rigor matters**。
- 反馈平台 how-i-used-claude.cs2680.com（WIP）提供对比、可见性、半个性化建议与跨作业课程组反馈；下次课进入 GPU programming 与 LLM serving III。
