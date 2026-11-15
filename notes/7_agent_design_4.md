# 第 7 讲：智能体设计 IV(评测)

> **Agent Design IV: Evaluation** · Harvard CS2680 · 讲师 Juncheng Yang
> 原始幻灯片:[7_agent_design_4.pdf](../7_agent_design_4.pdf)

## 本讲概览

本讲系统回答"如何评测一个 agent 的能力"：从组件级评测 (component-level evaluation) 与端到端评测 (end-to-end evaluation) 两个层级切入，梳理基准测试五代演化史与评测指标（pass@k、pass^k、成本、延迟）。随后逐一剖析 GAIA、BFCL、WebArena、OSWorld、SWE-bench、τ-bench、Terminal-Bench、TheAgentCompany 八个代表性基准。最后讨论贯穿整个智能体栈的数据泄漏、单轮交互偏置、成本/延迟/非确定性/安全等核心挑战，以及基准快速饱和的现状。

## 课程事务 (Logistics)

- 周四 15:30 office hour（SEC 4.308）；最终项目海报展示 12 月 7 日 9:00–13:00（时间不合适请在**本周结束前**联系课程组）；Assignment 2 本周日截止。
- Assignment 2 需打包完整 Claude Code session log（`~/.claude/projects/` 等，缺失部分会扣分）；**绝对不要篡改 session log**（视为学术诚信违规，有 3 名学生因试图抹除历史被点名）。今日主题：Agent evaluation 与 Cost-effective agents。

## 评测框架：层级、指标与评测循环

- 评测分两层：**组件级**评估智能体内部组件（planning、task decomposition、memory 的抽取/整合/检索、tool use 的发现/选择/参数化、error recovery），回答"哪个环节弱"；**端到端**评估整体智能体，指标为 **success rate**（任务是否完成）、**cost**（每任务花费）、**latency**（完成耗时）。
- **指标**：早期基准用 perplexity（留出文本上指数化的平均负对数似然，越低越好）、accuracy/F1、preference/win rate；能力指标 **pass@k** = k 次采样中至少一次通过，**pass^k** = k 次全部通过（由 τ-bench 引入）；成本目前主要计 LLM（漏掉工具调用、缓存 miss），延迟覆盖整条链路而非只算 LLM。
- **通用评测循环**：任务间 `reset_to_task_initial_state` → budget 内循环 `observe()` → `agent(task_instruction, observation, history, tools)` → `execute(action)` → 由 `task_evaluator` 对最终答案、最终环境状态、轨迹打分。各基准的差异正在于"环境"与"评测器"的不同。

## 基准演化史 (A Bit of History)

| 时期 | 代表基准 | 主题 |
|---|---|---|
| 2018 前 | Penn Treebank、WikiText、LAMBADA、SQuAD | 语言建模、窄任务 |
| 2018–2019 | GLUE、SuperGLUE、ARC、HellaSwag、WinoGrande | 迁移学习、通用 NLU |
| 2020–2022 | MMLU、BIG-bench、GSM8K、MATH、HumanEval、TruthfulQA、HELM | 基础模型能力 |
| 2023–2024 | MT-Bench、Chatbot Arena、AlpacaEval、IFEval、LongBench、MMMU、GPQA、AgentBench、WebArena、GAIA、SWE-bench、OSWorld、τ-bench | Agent 与工具使用、上下文、多模态 |
| 2024–2025 | MMLU-Pro、LiveBench、LiveCodeBench、MMMU-Pro、FrontierMath、Humanity's Last Exam | 难度、鲁棒性、时效性 |
| 2025–2026 | GDPval、BrowseComp、Terminal-Bench、ARC-AGI-3… | 更大范围、更模糊指令、更真实场景、更新的题目 |

## 评测目标 (Evaluation Objectives)

| 评测目标 | 代表基准 | 成功的含义 |
|---|---|---|
| 预测文本 (Predict text) | PTB, WikiText | 对观测到的文本赋予高概率 |
| 产生正确答案 (Produce a correct answer) | MMLU, GSM8K, GPQA, HLE | 与已知答案匹配 |
| 产生受偏好的回答 (Produce a preferred response) | Arena, AlpacaEval, MT-Bench | 获得人类或模型评审的有利判断 |
| 产生可运行的代码 (Produce functioning code) | HumanEval, LiveCodeBench, SWE-bench | 通过可执行测试 |
| 完成交互式任务 (Complete an interactive task) | WebArena, OSWorld, τ-bench, Terminal-Bench | 达到所需的环境状态 |

## 代表性基准 (Representative Benchmarks)

### GAIA: General AI Assistant
- 466 道人工编写的问答题（网页浏览、电子表格、PDF、图片、音频、计算），三个难度级：Level 1（≤5 步、零/一个工具）、Level 2（5–10 步、多工具，**无固定工具 API**——每个 agent 自带搜索/浏览器/Python/shell）、Level 3（任意长度、多工具，考察整个 agent 系统而非只考 LLM）。
- 只打最终答案分：`score = (1/N) Σᵢ 1[ normalize(ŷ) = normalize(y) ]`（归一化后精确匹配；示例：从电子表格找影片→查导演→报告出生地，答案 4,381）；测量推理/检索/工具选择/综合，**不测量**实际动作（发邮件、订机票、改数据库、提交表单、更新 issue）。（图示：打开网页→下载 PDF→抽取表格→搜索→运行 Python 的工具调用轨迹。）

### BFCL: Berkeley Function Calling Leaderboard
- 评测模型的工具接口是否可靠：对"订下周一波士顿→芝加哥最便宜的机票"，正确做法为 `search_flights(...)` 选出最便宜再 `book_flight(...)`；典型错误是捏造 flight_id、发出无关调用（如 `get_weather(...)`）。
- 打分：AST 或执行检查；多轮场景每轮检查状态 + 回复；V4 新增 web search 与 memory 类别。**读各类别分数，不读综合分**。

### WebArena
- 812 个任务，运行在自托管网站（Reddit、GitLab、maps、Wikipedia、电商、admin 后端）；观测 = accessibility tree（可访问性树），动作 = click / type / stop（示例：在 GitLab 创建 issue、指派给 Alex、加 documentation 标签）。
- 计分：reset snapshot → 轨迹 τ（不打分）→ 对最终状态 s_T 做功能检查（issue 查 URL/assignee，其他查元素 ID 或后端状态）→ success 1/0；WebArena-Verified（ServiceNow, 2025）移除 LLM-as-a-judge，改为对 HTTP trace 的**确定性检查**。

### OSWorld
- 369 个任务（浏览器、办公、文件、系统应用）；观测 = 屏幕截图（像素），动作 = 鼠标/键盘（示例：给电子表格加计算列、排序、另存为 result.xlsx）。
- 计分：setup → 轨迹 τ（不打分）→ 检查最终状态 s_T（单元格、公式、文件位置、设置、文件、应用配置）→ evaluator f → reward R；**OSWorld 2.0（2026）**新增 108 条跨应用长流程（常 1 小时以上、数百步），约 27 个 checkpoint 给部分分 (partial credit)。

### SWE-bench
- 修复真实仓库 issue（示例：用空索引调用库函数错误抛异常，应返回空结果并保持既有行为）：agent 经 grep 仓库 / inspect 实现与测试 / 改文件 / debug 产生 patch，apply 到仓库跑测试，判 **resolved or not**。
- 版本：**Verified**（人工校验）、**Lite**（300 任务子集）、**Multilingual**（9 种语言）、**Multimodal**（图片 issue）、**Pro**（更难、跨多文件）。

### τ-bench
- 两个交互者 + 一份政策：LLM 模拟用户 + agent（工具 + 航空数据库，API 调用真实改状态），受 airline policy 约束（如 basic economy 不可修改、改签前验证身份）；示例：用户要求把明天航班改到晚上那班。
- 打分 r = r_action × r_output：最终数据库与标注目标状态一致 = 1（**意外写入 (unintended writes) 直接判失败**）；回复包含所需信息 = 1。引入 **pass^k** = k 次独立运行**全部**成功的概率（如 4/4），刻意比 pass@k（1 次成功即可）严格，衡量可靠性 (reliability)；τ³-bench 新增修正任务、更多领域、知识检索 (knowledge retrieval) 与语音评测。

### Terminal-Bench
- 任务领域 = 端到端工作（programming、sysadmin + 服务器配置、数据处理、模型训练、安全、科学工作流），以 Docker 容器打包：`instruction.md` + `Dockerfile` → agent 在 shell 中执行（轨迹不打分）→ `tests/test.sh` 检查最终系统状态，pass/fail。
- TB 2.0 共 89 个任务 → TB 4.0 精简为 66 个（附隐藏人类参考解）；代表任务：在在线 KV 服务上新增协议（不丢饱和连接、延迟达标）。无 GUI grounding（不预测鼠标坐标），考察长程推理与系统交互，定位介于 SWE-bench 与 OSWorld 之间：

| | SWE-bench | Terminal-Bench | OSWorld |
|---|---|---|---|
| Agent acts by | 编辑单个仓库中的文件 | 容器内 shell 命令 | 鼠标点击与击键 |
| Agent observes | 代码与测试输出 | 终端输出 | 屏幕截图 |
| Task scope | 修一个 GitHub issue | 配置、调试、修复、构建 | 操作任意桌面应用 |
| Scored by | 仓库的测试 | 对最终系统状态的测试 | 对最终状态的检查 |

### TheAgentCompany
- 模拟一家软件公司：GitLab（代码）+ Plane（工单）+ ownCloud（文档）+ RocketChat（团队聊天）+ LLM 模拟的同事；agent 端到端完成一个职位的完整工作流（读 ticket → 问同事 → 检查仓库 → 写代码 → 跑测试 → 更新 issue → 汇报）。
- 175 个任务（software、PM、data science、HR、finance），按进度给部分分：`S_partial = 0.5 · (earned/total) + 0.5 · S_full`（4/8 未完成 → 0.25；7/8 未完成 → 0.44；8/8 完成 → 1.00）。

### 八个基准总览

环境从 web 工具/函数接口 → 自托管网站 → 完整桌面 VM → 软件仓库/终端容器 → 模拟公司；打分对象从"简短最终答案"逐步演进为"网站/后端/文件/数据库等最终环境状态 + 可执行测试"（各项细节见上文各基准小节）。

## 挑战：数据泄漏 (Data Leakage)

- **四层泄漏**（不止发生在训练阶段）：**training leakage**（任务或人工解法在训练数据里）、**eval-time leakage**（agent 联网搜到未来的修复方案）、**environment leakage**（沙箱暴露未来 commit 或隐藏测试）、**benchmark overfitting**（prompt 与 scaffold 在公开测试集上调试）。关键矛盾：agent 评测需要真实工具（可搜索的 web）⟺ 泄漏面更大。
- 现代 agent 表现 ≈ **P = f(LLM, prompt, scaffold, tools, retriever, memory, environment)**，栈上 9 个环节（base model、fine-tuning、prompt、retrieval、memory、web search、environment、scaffold、agent development）任一都可能携带基准信息——**"模型没在测试集上训练过"对 agent 评测远不够**。

## 挑战：单轮偏置、成本、可靠性与饱和

- **单轮用户 (a single user turn)**：大多数基准只给一条完全指定的指令——prompt in, final state out，用户不在回路里；而真实工作是模糊的、会被修正、会被打断。单轮打分**奖励自信猜测**：提澄清问题花步数却不赚分。改进方向：**Clarification**（目标未指定时会不会提问）、**Recovery**（中途修正后会不会重规划）、**Memory**（能否跨轮次保持约束）。
- **成本与延迟**：成功率不足——200 步花 $40 的运行 vs 12 步花 $0.30 的运行？**非确定性**：同 agent 同任务结果可能不同，单次运行分数是噪声而非信号。
- **安全与副作用**：过程中删文件、发邮件、花的钱都不受罚，照样算 pass。**指标失配**：只看结果的打分会放过侥幸/不安全的运行；轨迹匹配打分又判掉合理但路径不同的运行。
- **基准快速饱和 (Benchmarks Saturate Quickly)**：GLUE（2018）14 个月达人类水平 87.1、39 个月达专家水平 89.8；MMLU（2020）与 GPQA Diamond（2023）发布后迅速逼近满分；**SWE-bench Verified（2024）22 个月从 33% → 95%**；**ARC-AGI-2（2025）11 个月达人类平均 60**（前沿 95.0）；**ARC-AGI-3（2026）6 个月从 0.5% → 62.7%**（仍在快速演化）。饱和 (saturated) = 前沿达到人类基线，或头部模型不再拉开差距。
- MaDSys 组正建设一个基于**真实流量 (real traffic)** 的 agent 评测研究平台（每周 20+ 小时可联系参与）。

## Agent 评测仍在演化 (Still Evolving)

| 维度 | 早期评测 | 当前前沿 |
|---|---|---|
| 评测对象 (Objective evaluated) | 基座模型 | 模型 + prompt + 工具 + agent harness |
| 交互 (Interaction) | 静态、单轮 | 有状态、长程 (stateful and long-horizon) |
| 判分者 (Grader) | 精确匹配或似然 | 测试、环境状态、人类或评审模型 |
| 数据集 (Dataset) | 固定、公开 | 新鲜、隐藏、动态、抗污染 |
| 主要指标 (Main metric) | 平均准确率 | 任务成功之外，还看效率、可靠性、质量、成本、延迟 |
| 核心关注 (Primary concern) | 跨样本泛化 | 真实约束与安全要求下的鲁棒完成 |

## Assignment 3 与下讲预告

- **Assignment 3** 按三个指标评分：Capability（越高越好）、Cost 与 Speed（越低越好）；若 A 在任一指标不劣于 B 且至少一项更优则 **A dominates B**，不被支配者（Rank 1）构成 **Pareto 前沿**；真实世界的 agent 还有更多维度要考虑。
- **下讲**：cost-effective agent、case study、不同类型的 agent (different types of agents)、智能体框架 (agentic frameworks)。

## 核心要点

- 评测分两层：component-level（planning、task decomposition、memory、tool use、error recovery）回答"哪个环节弱"，end-to-end（success rate、cost、latency）回答"整体好不好用"。
- 基准史五代：窄任务 → NLU 套件 → 基础模型能力 → agent/工具/多模态 → 难度/鲁棒性/时效 → 更大范围更真实（GDPval、BrowseComp、Terminal-Bench、ARC-AGI-3）；趋势是从静态可背诵的题目走向"活"的真实工作流。
- 五种评测目标各对应不同基准与"成功"定义；agent 评测的成功 = **达到所需环境状态**（而非答对题）。
- 通用评测循环 = reset 环境 → budget 内 observe/act/execute → evaluator 对最终答案/最终状态/轨迹打分；不同基准的差异在于"环境"与"评测器"。
- 指标演进：perplexity / accuracy / F1 / win rate → **pass@k**（k 次至少一次过）与 **pass^k**（k 次全过，τ-bench 引入）；成本目前只计 LLM（漏掉工具调用、缓存 miss），延迟是整条链路。
- 基准谱系：**GAIA**（466 题、3 级难度、无固定工具 API、只打归一化最终答案，考"研究"不考"动作"）；**BFCL**（AST/执行检查工具调用，多轮查状态+回复，V4 加 web search 与 memory，看类别分）；**WebArena**（812 任务、accessibility tree 观测，查最终状态，Verified 用确定性 HTTP trace 检查替代 LLM-as-a-judge）；**OSWorld**（369 任务、像素观测+鼠标键盘，查最终文件/应用/系统状态，2.0 加 108 条长流程、约 27 个 checkpoint）；**SWE-bench**（issue → patch → 跑测试判 resolved，衍生 Verified/Lite/Multilingual/Multimodal/Pro）；**Terminal-Bench**（Docker 打包 + 最终系统状态测试，89 → 66 任务，无 GUI grounding，介于 SWE-bench 与 OSWorld 之间）。
- **τ-bench**：模拟用户 + 受政策约束的 agent + 真实可变数据库；r = r_action × r_output，意外写入即失败；**pass^k 要求 k 次独立运行全部成功**，刻意比 pass@k 严格以衡量可靠性；τ³-bench 扩展领域、知识检索与语音。**TheAgentCompany**：五系统模拟公司 + LLM 同事，175 个跨职位任务，部分分 S_partial = 0.5·(earned/total) + 0.5·S_full。
- **数据泄漏有 4 层**（training / eval-time / environment / benchmark overfitting），且因 P = f(LLM, prompt, scaffold, tools, retriever, memory, environment)，栈上 9 个环节任一都可能含基准信息——"没在测试集上训练"远不够。
- **单轮偏置**：无用户回路，奖励自信猜测、惩罚澄清提问；改进方向 = Clarification / Recovery / Memory。
- 成功率之外还看：**成本与延迟**（$40/200 步 vs $0.30/12 步）、**非确定性**（单次分数是噪声）、**安全与副作用**（不受罚）、**指标失配**（结果打分 vs 轨迹匹配）。
- **饱和极快**：SWE-bench Verified 22 个月 33%→95%、ARC-AGI-2 11 个月达人类平均、ARC-AGI-3 6 个月 0.5%→62.7%；评测整体从"基座模型 + 静态单轮 + 精确匹配 + 固定公开数据"演化为"整套 harness + 有状态长程 + 测试/状态/评审 + 动态抗污染数据"；Assignment 3 用 Capability/Cost/Speed 三维 Pareto 前沿评分。
