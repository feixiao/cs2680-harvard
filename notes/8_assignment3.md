# 作业 3:MadsOpt 智能体 Harness 竞赛

## 本讲概览

MadsOpt 是一个智能体 (agent) harness 竞赛:你的 Agent 与 26 个任务分处不同容器,通过 HTTP 请求访问任务,离线评测中唯一可访问外部地址是 api.cs2680.com。Agent 在 Dispatcher 分发任务后产出 patch,patch 被评测并把结果回传给 Agent 迭代,最多 5 个任务并行。排行榜按「解题数、每解出任务成本、每解出任务时间」三指标构成天际线 (skyline) 排名。最终成绩 = 排行榜 80 分 + 技术报告 (writeup) 10 分 + 视频 10 分。

## 竞赛框架 (Framework)

- 共 26 个任务,分 3 种容器类型 (3 types of containers)。
- Agent 与任务在不同容器中,用 HTTP 请求访问任务;评测离线,只能访问 api.cs2680.com。
- 图示:框架图为 Agent 容器 ⇄ 任务容器 (HTTP),Agent 出站到 api.cs2680.com 调用模型。
- 工作流:Dispatcher 把任务信息传给你的 Agent → Agent 工作并生成 patch → patch 被评测,结果回传 Agent。
- 并发上限:最多 5 个任务并行 (5 task in parallel at most)——并行编排直接影响每任务的时间与成本。

## 限额 (Limits)

- 模型分三档:Expert、Standard、Starter,可针对不同任务/阶段做路由 (routing)。
- 时间限制:

| 限制项 | 数值 |
|---|---|
| 每次 `evaluate()` | 35 min |
| 总计 | 4 h |

- 成本限制:

| 限制项 | 数值 |
|---|---|
| 每天 | $30 per day |
| 每次运行 | $10 per run |

- 含义:一次运行 ≤ 35 分钟、$10,日预算共同封顶;「解出更多任务」与「省成本/省时间」是相互竞争的目标。

## 代码结构 (Code structure)

- `init.sh`、`package_claude_sessions.py`:生成会话日志 (session logs)。
- `src/`:你的智能体逻辑;沙箱会将其 zip 起来,是**唯一**上传到 Leaderboard 的文件。
- `dispatcher`、`evaluation_scripts`:Dispatcher 逻辑与评分测试;Leaderboard 使用同一套代码,**不要为本地测试修改** (否则本地结果与排行榜不一致)。

## 排行榜提交 (Leaderboard submission)

- 登录:Canvas 邮箱,密码 `Cs2680-<your 8-digit student ID>` (即 `Cs2680-` + 8 位学号)。
- 提交物:上传 `src.zip`。
- 提交排队逐个运行;若提交看起来不靠谱,尽快取消。
- **取消的提交同样计入统计,并消耗当日预算**——本地验证必须先于提交。
- 衡量三指标:① 解出任务数;② 每解出任务成本;③ 每解出任务时间。

## 评分规则 (Grading)

- 排名基于上述三指标的**天际线** (skyline)。
- 门槛:至少解出 7 个任务 (at least solve 7 tasks) 才有名次。
- 名次计「排在你前面的所有人」,幻灯片示例:1, 1, 1, 4, …(并列共享名次,下一位 = 前面人数 + 1)。
- 基线:解出 16 个任务。
- 分数:任一提交达到基线 → `max(81 − r, 50)`;否则 → `81 − r`(r 为天际线名次)。达到基线后名次再落后也有 50 分下限保护。
- 成绩构成:Leaderboard 80 分 + writeup 10 分 + 视频 10 分。

## 核心要点

- 26 个任务、3 种容器;Agent 与任务隔离,仅通过 HTTP 交互。
- 离线评测,唯一允许的外部访问是 api.cs2680.com。
- 流程:Dispatcher 下发任务 → Agent 产出 patch → 评测结果回传 Agent 迭代。
- 最多 5 任务并行;并行编排是时间/成本的关键杠杆。
- 模型三档:Expert / Standard / Starter。
- 时间:每次 `evaluate()` 35 min,总计 4 h;成本:每天 $30,每次运行 $10。
- 仓库三块:会话日志脚本、`src`(唯一提交物)、官方评测 (dispatcher + evaluation_scripts,不可改)。
- 登录密码 `Cs2680-<8 位学号>`;提交 `src.zip`;取消的提交仍计预算。
- 三指标:解题数、每题成本、每题时间;天际线排名。
- ≥7 题才有名次;并列名次示例 1,1,1,4,…。
- 基线 16 题:达标分数 = max(81 − r, 50),否则 81 − r。
- 总分 100 = Leaderboard 80 + writeup 10 + 视频 10。
- 策略核心:在 $10/run、35 min/evaluate 预算内优化综合效率(解题数 ÷ 成本 ÷ 时间),而非堆算力求解题数。
