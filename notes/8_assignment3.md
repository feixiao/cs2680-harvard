# 作业 3:MadsOpt Harness 竞赛(规格)

> 原讲次名称:*Assignment 3: MadsOpt: Harness Competition*(共 7 页规格幻灯片)

## 本讲概览

MadsOpt 是课程中的智能体 harness 竞赛:你的智能体(agent)要在一个隔离的沙箱里自动完成 26 个任务,竞赛比拼的不是"能不能做对",而是在**成本**和**速度**约束下能稳定解出多少任务。评测环境完全离线(只能访问课程 API),你通过 HTTP 与任务容器交互,由一个 Dispatcher 分发任务、回收结果。每次 `evaluate()` 有 35 分钟时限、总时长 4 小时、每次运行 $10、每天 $30 的硬性预算。提交只需上传 `src.zip`(你的智能体逻辑),排行榜按**解题数、每题成本、每题时间**三个指标构成的天际线(skyline)排名;至少解出 7 个任务才计分,达到 16 题基线后分数有 `max(81 − r, 50)` 的保护下限。最终成绩 = 排行榜 80 分 + 技术报告 10 分 + 视频 10 分。

## 竞赛框架(Framework)

- 任务与容器:**共 26 个任务,分属 3 种容器类型**(26 tasks. 3 types of containers)。任务不是直接给你的代码,而是运行在容器里的服务。
- 隔离与访问方式:你的 Agent 和任务位于**不同的容器**中,Agent 通过 **HTTP 请求**访问任务(Agent and the task are in separate containers, using HTTP requests to access the task)。这意味着你的智能体必须像一个"远程操作员"一样,通过 HTTP 接口观察任务状态、获取信息、提交工作,而不能直接读文件、改代码目录。
- 网络隔离:评测是**离线**的(offline evaluation),Agent 唯一能访问的外部地址是 **api.cs2680.com**(课程 API,用于调用模型)。沙箱里没有任意互联网访问,所有能力都必须来自课程提供的模型 API 和你自己的 harness 逻辑。

图示:第 2 页的框架图描绘了整体拓扑——左侧是你的 Agent 容器,右侧是承载任务的容器;两者之间由 HTTP 请求连接,同时 Agent 可以(也仅可以)出站到 api.cs2680.com 调用大模型。

工作流(第 3 页)是一个围绕 Dispatcher 的循环:

1. **Dispatcher 把任务信息传给你的 Agent**(Dispatcher passes the task info to your Agent)。
2. Agent 在任务上工作,产出 **patch**(Agent works on a task and generates a patch)。
3. patch 被**评测**,评测结果被发回给 Agent(the patch is evaluated with the result sent back to Agent)——Agent 可以据此迭代。
4. 并发上限:**最多同时 5 个任务**(5 task in parallel at most)。编排(orchestration)本身因此成为设计问题:如何在 5 路并行、4 小时总预算下分配任务顺序与重试策略,直接影响"每任务成本/时间"两个指标。

图示:第 3 页的流程图为 Dispatcher → Agent(产出 patch)→ 评测(结果回传 Agent)的回路。

## 限额(Limits)

竞赛的硬约束分模型档位、时间、成本三类:

- **三个模型档位:Expert、Standard、Starter**(Three models: Expert, Standard, Starter)。不同档位代表不同的能力/价格取舍,你的 harness 可以为不同任务(或同一任务的不同阶段)选择不同档位的模型,这直接对应课程中"路由与单位 token 价格"的杠杆。
- **时间限制**(Time limit):

| 限制项 | 数值 |
|---|---|
| 每次 `evaluate()` | 35 min |
| 总计 | 4 h |

- **成本限制**(Cost limit):

| 限制项 | 数值 |
|---|---|
| 每天 | $30 per day |
| 每次运行 | $10 per run |

也就是说:一次完整运行(`evaluate()` 一次)最多 35 分钟、$10;每天最多跑 3 次(4 小时与 $30 的日预算共同封顶)。这两个限制意味着"解出更多任务"和"省成本/省时间"是相互竞争的目标——这正是后面三指标天际线评分要权衡的东西。

## 代码结构(Code structure)

- `init.sh`、`package_claude_sessions.py`:**生成会话日志**(generate session logs)——课程要求披露并保留使用 AI 的会话记录,该脚本负责打包 Claude 会话日志。
- `src/`:**你的智能体逻辑**(the agent logic)。沙箱会请求把它 zip 起来,并且它是**唯一会被上传到 Leaderboard 的文件**(the sandbox requests zip it and it is the ONLY file uploaded to Leaderboard)。
- `dispatcher`、`evaluation_scripts`:Dispatcher 逻辑与评分用的测试(Dispatcher logic and tests for grading)。**排行榜上使用的是同一套代码**,因此**不要为了本地测试而修改它**(The same used on Leaderboard, do not modify it for local testing)——本地改了只会让本地结果与排行榜不一致。

图示:第 5 页的目录结构图把仓库分为三块——脚本(`init.sh`、`package_claude_sessions.py`)、你的代码(`src`,唯一提交物)、官方评测(`dispatcher` + `evaluation_scripts`,只读)。

## 排行榜提交(Leaderboard submission)

- **登录**:用你在 Canvas 上的邮箱登录,密码为 `Cs2680-<your 8-digit student ID>`(即 `Cs2680-` 加上你的 8 位学号)。
- **提交物**:上传 **`src.zip`**(Submit the src.zip)。
- **队列机制**:提交是**排队逐个运行**的(submission is measured in queue at a time);**如果某个提交看起来不靠谱,请尽快取消**(please cancel a submission if it does not look promising)。
- **取消也有代价**:**被取消的提交同样计入统计,并消耗当日预算**(Cancelled submission also counts, and consumes the daily budget)。所以"提交前在本地跑通"比"提交后再取消"重要得多——取消不能省钱,只能止血时间。
- **排行榜衡量三个指标**(The submission is measured by):
  1. 解出的任务数(the number of tasks solved)
  2. 每个解出任务的成本(the cost per solved task)
  3. 每个解出任务的时间(the time per solved task)

## 评分规则(Grading)

- **天际线排名**:排名基于上述**三个指标构成的天际线**(Skyline with the three metrics)——即课程评测讲次中讲到的 Pareto 天际线:一个提交若在所有指标上都不劣于另一个,则排在它前面,排名体现的是"解题数 × 单位成本 × 单位时间"的综合效率,而不是单纯的解题数。
- **门槛**:**至少解出 7 个任务**才有名次(at least solve 7 tasks)。
- **名次计数方式**:名次**计算排在你前面的所有人**("The rank counts everyone ahead of it"),幻灯片给出的例子是 **1, 1, 1, 4, …** —— 即并列者共享名次,其后的人的名次等于其前面人数加一(3 人并列第一,则下一位是第 4 名)。
- **基线**:**解出 16 个任务**为基线(a baseline of solving 16 tasks)。
- **分数公式**:

  - 如果你的**任一提交**达到基线(解出 ≥ 16 个任务):分数 = **max(81 − r, 50)**;
  - 否则:分数 = **81 − r**。

  其中 r 是你的天际线名次。基线保护的含义:达到基线后,即使名次落后于第 31 名,分数也不低于 50 分;未达基线则名次每落后一名扣 1 分,无下限保护。
- **成绩构成**:**排行榜占 80 分,技术报告(writeup)10 分,视频 10 分**(Leaderboard accounts for 80, with another 10 for the writeup and 10 [for the video])。

图示:第 7 页用一张表把评分规则汇总成:天际线三指标 → 7 题门槛 → 并列名次示例(1,1,1,4,…)→ 16 题基线 → `max(81 − r, 50)` / `81 − r` 分支 → 80/10/10 的权重分配。

## 核心要点

- 26 个任务、3 种容器类型;Agent 与任务分处不同容器,仅能通过 HTTP 请求访问任务。
- 评测全程离线,唯一允许的外部访问是课程 API:api.cs2680.com。
- 工作流:Dispatcher 下发任务信息 → Agent 产出 patch → patch 被评测、结果回传 Agent 迭代。
- 最多 5 个任务并行——并行编排是直接影响每任务时间与成本的杠杆。
- 模型分三档:Expert、Standard、Starter,可按任务/阶段路由。
- 时间限制:每次 `evaluate()` 35 分钟,总计 4 小时。
- 成本限制:每天 $30,每次运行 $10。
- 仓库分三块:会话日志脚本(`init.sh`、`package_claude_sessions.py`)、智能体逻辑 `src`、官方评测 `dispatcher` + `evaluation_scripts`。
- `src.zip` 是上传到 Leaderboard 的唯一文件。
- 排行榜与本地使用同一套 dispatcher 和 evaluation_scripts,不要为本地测试修改它们。
- 排行榜登录:Canvas 邮箱 + 密码 `Cs2680-<8 位学号>`。
- 提交排队运行;看起来不靠谱的提交要尽快取消。
- 被取消的提交同样计入,并消耗当日 $30 预算——本地验证先于提交。
- 排行榜三指标:解出任务数、每解出任务成本、每解出任务时间。
- 排名取三指标的天际线(Pareto skyline)。
- 至少解出 7 个任务才有名次;并列名次示例 1, 1, 1, 4, …(名次 = 前面人数 + 1)。
- 基线 = 解出 16 个任务;达到基线则分数 = max(81 − r, 50),否则 = 81 − r。
- 最终成绩 = 排行榜 80 分 + 技术报告 10 分 + 视频 10 分。
- 策略含义:在 $10/run、35 min/evaluate 的预算内,优化"解出任务数 ÷ 单位成本 ÷ 单位时间"的综合效率,而不是无脑堆算力追求解题数。
