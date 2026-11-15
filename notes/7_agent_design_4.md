# 第7讲：智能体设计 IV（评测）

> 原讲次：Agent Design IV: Evaluation · Juncheng Yang · Harvard CS2680 Modern AI Systems: Agents and System Optimizations

## 本讲概览

本讲系统回答一个核心问题：如何评测一个 agent 的能力？我们从评测的两个层级切入——针对智能体内部组件（planning、tool use、memory 等）的 component-level evaluation 与针对整体智能体的 end-to-end evaluation。随后梳理了基准测试从 2018 年以前的窄任务（Penn Treebank、SQuAD）到 2023–2026 年大规模、更真实场景（GDPval、BrowseComp、Terminal-Bench、ARC-AGI-3）的演化史，并讨论了评测指标（perplexity、pass@k、pass^k、成本、延迟）。本讲对八个代表性基准逐一深入剖析：GAIA、BFCL、WebArena、OSWorld、SWE-bench、τ-bench、Terminal-Bench 与 TheAgentCompany。最后讨论 agent 评测的核心挑战——跨整个智能体栈的数据泄漏、单轮交互偏置、非确定性、不受惩罚的副作用与快速饱和，并给出 Assignment 3 基于能力/成本/速度的 Pareto 前沿评分方法。

## 课程事务（Logistics）

- 本周四 15:30 office hour，地点 SEC 4.308。
- 最终项目海报展示（poster presentation）：12 月 7 日 9:00–13:00；若时间不合适，请在**本周结束前**联系课程组。
- Assignment 2 本周日截止（建议尽早开始）。

关于 Claude Code session log 的提交要求：

- 需打包所有相关内容（`~/.claude/projects/`（macOS/Linux）或 `C:\Users\<YourUsername>\.claude\projects\`（Windows））；缺失完整 session log 的部分会在 Assignment 2 中扣分；多上传没有坏处。
- 使用 AI 本身不扣分，但作业的部分内容必须是自己的。课上统计了 17 名学生用 Claude 帮忙写 writeup 的情况：6 人仅用于润色；少数人让 Claude 写 bullet points；7 人自己写草稿后编辑（不鼓励）、少数从别处粘贴（如 ChatGPT）；4 人几乎是 Claude 的原样输出，2 人的 writeup 里还带着 Claude Code 的 TODO。
- 写一段简短的 reflection 即可。**绝对不要篡改 session log**，这将被视为学术诚信违规：有 3 名学生试图抹除历史记录；AI 生成的文字即使不看历史也很容易识别，而完美隐藏所有历史比完成作业难得多。

今天的计划：**Agent evaluation**（智能体评测）与 **Cost-effective agents**（高性价比智能体）。

## 组件级评测 vs 端到端评测

如何评价一个 agent 的能力？课程从两个层次出发：

- **Component-level evaluation（组件级评测）**：评估智能体内部各个组件。包括 agent 内部的 **planning（规划）**、**task decomposition（任务分解）**、**memory（记忆：抽取、整合、检索）**，以及 **tool use（工具使用：发现、选择、参数化）** 和 **error recovery（错误恢复）**。
- **End-to-end evaluation（端到端评测）**：评估整个智能体完成任务的表现，对应三个核心指标：
  - **Success rate（成功率）**：任务是否完成？
  - **Cost（成本）**：每个任务花费多少？
  - **Latency（延迟）**：完成任务花了多长时间？

组件级评测回答"哪个环节弱"，端到端评测回答"整体好不好用"，两者缺一不可。本讲随后按"历史与趋势 → 指标 → 代表性基准 → 挑战"的路线展开。

## 基准测试演化史（A bit of history）

评测基准大致每两三年换代一次，每一代都试图解决上一代"被刷爆"的问题：

| 时期 | 代表基准 | 主题 |
|---|---|---|
| 2018 年之前 | Penn Treebank、WikiText、LAMBADA、SQuAD | 语言建模、窄任务 |
| 2018–2019 | GLUE、SuperGLUE、ARC、HellaSwag、WinoGrande | 迁移学习、通用 NLU |
| 2020–2022 | MMLU、BIG-bench、GSM8K、MATH、HumanEval、TruthfulQA、HELM | 基础模型能力 |
| 2023–2024 | MT-Bench、Chatbot Arena、AlpacaEval、IFEval、LongBench、MMMU、GPQA、AgentBench、WebArena、GAIA、SWE-bench、OSWorld、τ-bench | Agent 与工具使用、上下文、多模态 |
| 2024–2025 | MMLU-Pro、LiveBench、LiveCodeBench、MMMU-Pro、FrontierMath、Humanity's Last Exam | 难度、鲁棒性、时效性 |
| 2025–2026 | GDPval、BrowseComp、Terminal-Bench、ARC-AGI-3… | 更大范围、更模糊的指令、更真实的使用场景、更新的题目 |

趋势很清晰：从静态、可背诵的题目走向"活"的、更大范围、更接近真实工作流的评测。延伸阅读：https://cs2680.com/notes/agent-evaluation

## 评测目标（Evaluation Objectives）

不同评测目标对应不同的"什么叫成功"，也决定了用什么基准：

| 评测目标 | 代表基准 | 成功的含义 |
|---|---|---|
| 预测文本（Predict text） | PTB、WikiText | 对观测到的文本赋予高概率 |
| 产生正确答案（Produce a correct answer） | MMLU、GSM8K、GPQA、HLE | 与已知答案匹配 |
| 产生受偏好的回答（Produce a preferred response） | Arena、AlpacaEval、MT-Bench | 获得人类或模型评审的有利判断 |
| 产生可运行的代码（Produce functioning code） | HumanEval、LiveCodeBench、SWE-bench | 通过可执行测试 |
| 完成交互式任务（Complete an interactive task） | WebArena、OSWorld、τ-bench、Terminal-Bench | 达到所需的环境状态 |

最后一行就是本讲主角：agent 评测不再是"答对题"，而是"在可交互环境里把状态改对"。

## 评测指标（Metrics）

- **早期基准的指标**：
  - **Perplexity**：在留出文本上指数化的平均负对数似然（越低越好）。
  - **Accuracy 或 F1 score**。
  - **Preference / win rate**（偏好/胜率）。
- **Capability（能力）**：
  - **Pass@k**：k 次采样中**至少一次**通过。
  - **Pass^k**：k 次采样**全部**通过（由 τ-bench 引入，见后文）。
- **Cost（成本）**：目前主要以 LLM 调用成本计；被忽略的部分：工具调用成本及其他开销（例如 LLM 前缀缓存 cache miss 带来的额外成本）。
- **Latency / duration（延迟/耗时）**：不只是 LLM 推理时间，还包括工具、检索等整条链路的耗时。

## 基准评测循环（Benchmark Evaluation Loop）

Agent 基准的评测循环是通用的：

```python
for task in benchmark:
    environment = reset_to_task_initial_state(task)
    while not terminated and within_budget:
        observation = environment.observe()
        action = agent(task_instruction, observation, history, tools)
        environment.execute(action)
    score = task_evaluator(
        agent_final_answer, final_environment_state, trajectory)
```

要点：环境在任务间重置到初始状态；agent 在 budget（步数/时间/成本）内循环地观察、决策、执行；最终由 `task_evaluator` 对**最终答案、最终环境状态、完整轨迹**三者之一或组合打分。不同基准的区别正是"环境"与"task_evaluator"的不同。

## GAIA: General AI Assistant

来源：Mialon et al., GAIA, arXiv 2023。问题：**助手能否研究（research）并返回正确答案？**

GAIA 包含 **466 道人工编写的问答题**，覆盖网页浏览、电子表格、PDF、图片、音频、计算等能力。分三个难度级别：

- **Level 1**：≤ 5 步、零或一个工具，答案为短答案（一个数、字符串或列表），例如 17.4 或 4,381。
- **Level 2**：5–10 步、多个工具，**无固定工具 API**——每个 agent 自带自己的搜索、浏览器、Python、shell。
- **Level 3**：任意长度、大量工具。Level 2/3 考察的是**整个 agent 系统**，而不只是 LLM。

**示例任务**：附件电子表格包含一组影片列表，找出满足两个条件的影片、查询其导演、报告导演的出生地。agent 的实际做法：打开网页 → 下载 PDF → 从表格中抽取 → 搜索 → 运行 Python，最终答案 **4,381**。（图示：一个由"打开网页、下载 PDF、抽取表格、搜索、运行 Python"串联而成的工具调用轨迹，终点框出答案 4,381。）

**打分方式**：只打最终答案分：

score = (1/N) Σᵢ 1[ normalize(ŷ) = normalize(y) ]

即对预测答案与标准答案做归一化后精确匹配。**它测量的是**：推理、检索、工具选择与综合。**它不测量**：实际动作（如发邮件、订机票、修改数据库、提交表单、更新 issue）。GAIA 因此是"研究型助手"评测：答案对就对，过程不受考。

## BFCL: Berkeley Function Calling Leaderboard

来源：Patil et al., Berkeley Function Calling Leaderboard, ICML 2025。问题：**模型的工具接口是否可靠？**

**示例 prompt**（用户："订下周一从波士顿到芝加哥最便宜的机票"）：

- **正确做法**：调用 `search_flights(origin="BOS", destination="CHI", date=...)`，选出最便宜的，再调用 `book_flight(flight_id=..., passenger_id=...)`。
- 模型常见的错误调用：凭空捏造 ID 的 `book_flight(flight_id, ...)`（应询问乘客 passenger_id）、与任务无关的 `get_weather(...)`、订票时重复调用 get_weather 等。

（图示：左侧为对话 prompt 与可用工具列表 `search_flights(...)`、`book_flight(...)`，右侧标注模型实际发出的调用，并以不同颜色区分正确调用与"捏造 ID""无关调用"等错误。）

**打分**：通过 **AST 检查或执行检查**验证调用；多轮场景下每一轮都检查状态 + 回复。V4 版本新增 **web search 与 memory** 类别。**注意**：读各类别分数即可，不要只看综合分。

## WebArena: 可自托管的 Web 工作流

来源：Zhou et al., WebArena, ICLR 2024；WebArena-Verified（ServiceNow, 2025）。问题：**agent 能否完成一个 web 工作流？**

**示例任务**："在 GitLab 中创建 issue『Update onboarding documentation』，指派给 Alex，并添加 documentation 标签。"

agent 的交互基于 **accessibility tree（可访问性树）**：灰色为观测（accessibility tree），青色为动作（click、type、stop）。轨迹示例：观测 accessibility tree → click [Create issue] → 观测 → click [Projects] → click [project] → type issue title → … → stop。（图示：一串交替出现的观测树快照与鼠标/键盘动作。）

**任务如何计分**：从 reset snapshot 出发，执行轨迹 τ，得到最终状态 s_T，被**检查（inspected）**，经 functional checks 后给出 success 1/0。即只看最终环境状态，不看轨迹。

- **812 个任务**，运行在自托管网站：Reddit、GitLab、maps、Wikipedia、电商购物站、admin 后端。
- Issue 类任务：检查最终 URL、页面内容、issue 是否存在、assignee 是否正确。
- 其他任务：对结构化输出检查 click 或 type 到了正确的元素 ID；对文本答案检查后端状态。
- 早期 WebArena 使用 **LLM-as-a-judge**，WebArena-Verified 将其移除，改为对 HTTP trace 的**确定性检查**，消除评审模型的不确定性。

## OSWorld: 操作真实计算机

来源：Xie et al., OSWorld, NeurIPS 2024；os-world.github.io。问题：**agent 能否操作一台真实的电脑？**

**示例任务**：给电子表格添加一个计算列、排序、另存为 result.xlsx。agent 的观测是**像素（screenshot）**，动作是鼠标与键盘：click LibreOffice → click 单元格 → type 公式 → … → save file。（图示：左侧为桌面截图序列，右侧标注对应的鼠标点击与键盘输入动作。）

**任务如何计分**：setup logic → 轨迹 τ（**不参与打分**）→ 检查最终状态 s_T → evaluator f → reward R。

- 共 **369 个任务**，涵盖浏览器、办公软件、文件管理、系统应用。
- 检查项包括：表格单元格、公式、文件位置、系统设置、文件、应用配置。
- **OSWorld 2.0（2026）**：跨应用工作流（cross-application workflows），108 条长流程（常常 1 小时以上、数百步），约 **27 个 checkpoint** 用于给部分分（partial credit）。

## SWE-bench: 修复真实仓库 issue

来源：Jimenez et al., 2024；OpenAI, 2024（Verified）；Deng et al., 2025；swebench.com。问题：**agent 能否修复一个真实仓库的 issue？**

**示例任务**（issue 大意：用空索引调用库函数时错误地抛出异常，应使其返回空结果，同时保持既有行为不变）。agent 的做法：grep 仓库（空结果）→ inspect implementation → inspect tests → run tests → 修改文件 → debug → run the tests → **产生 patch**。

**patch 如何打分**：apply 到仓库 → run tests → 判 **resolved or not**（补丁是否使测试通过）。

各版本：

| 版本 | 说明 |
|---|---|
| Verified | 人工校验过 |
| Lite | 300 任务子集 |
| Multilingual | 9 种编程语言 |
| Multimodal | 含图片的 issue |
| Pro | 更难、跨多文件 |

## τ-bench: 与用户对话 + 遵守政策 + 改后端状态

来源：Yao et al., τ-bench, arXiv 2024。问题：**agent 能否与用户交互、遵守政策，并正确修改后端状态？**

τ-bench 有**两个交互者 + 一份政策**：

- **Simulated user**：由 LLM 扮演客户（灰色）。
- **Agent**：调用工具 + 访问航空数据库（teal）；API 调用会**真实改变数据库状态**。
- 中间受 **airline policy** 约束，例如：basic economy 机票不能修改、查票价要解释差异、改签需先验证身份等。

**示例任务**（用户："我要把明天的航班改到晚上那班。"）：agent 查预订（get reservation）→ 向用户解释 basic economy 不可改的 fare 差异 → 询问确认（change_booking）→ 验证身份（look up / ask identity）→ 搜索航班（search flights）→ 完成改签，数据库中的 reservation 被更新。（图示：agent 与模拟用户的对话中，灰色为对用户的说话，teal 为工具调用，终点是"已更新的 DB state"。）

**打分：终态 + 一致性。** 本基准同时引入了 **pass^k**：

- 原始奖励 r = r_action × r_output：
  - **r_action = 1** 仅当最终数据库与标注的目标状态一致；**意外写入（unintended writes）直接判失败**。
  - **r_output = 1** 仅当面向用户的回复包含所需信息。
- **pass^k** = k 次独立运行同一场景**全部成功**的概率（例：4 次中 4 次成功）。而 pass@k 只需 1 次成功即可。只读调用可以不同，但副作用必须每次都正确。**pass^k 有意比 pass@k 严格得多**，衡量的是可靠性（reliability）而非"能力上限"。
- **τ³-bench**：实现已更新，包含修正过的任务、更多领域、知识检索（knowledge retrieval）与语音（voice）评测。

## Terminal-Bench: 通过 shell 完成真实任务

来源：Merrill et al., Terminal-Bench 2.0, arXiv 2026。问题：**agent 能否仅通过 shell 完成一个真实任务？**

- 任务领域是**端到端工作**而非仅仅修 repo bug：programming、sysadmin（服务器配置）、数据处理、模型训练、安全、科学计算工作流。
- **任务如何打包与打分**：任务以 **Docker 容器**为单位：`instruction.md` + `Dockerfile` → agent 在 shell 中产生**轨迹（不打分）** → 检查**最终系统状态**，由 `tests/test.sh` 测试套件判 pass 或 fail。
- **TB 2.0 有 89 个任务 → TB 4.0 精简为 66 个**；附隐藏的人类参考解（hidden human solutions）。
- **代表任务**：在一个在线 KV 服务上实现新协议：不丢饱和连接、延迟保持在要求内（no saturated connections dropped, latency held）。
- **与 SWE-bench / OSWorld 的对比**：

| | SWE-bench | Terminal-Bench | OSWorld |
|---|---|---|---|
| agent 的动作方式 | 编辑单个仓库中的文件 | 容器内 shell 命令 | 鼠标点击与击键 |
| agent 的观测 | 代码与测试输出 | 终端输出 | 屏幕截图 |
| 任务范围 | 修一个 GitHub issue | 配置、调试、修复、构建 | 操作任意桌面应用 |
| 打分方式 | 仓库测试 | 对最终系统状态的测试 | 对最终状态的检查 |

- **无 GUI grounding（No GUI grounding）**：不需要预测鼠标坐标，纯靠终端文本交互，因此更干净地考察**长程推理与系统交互**能力——定位介于 SWE-bench（纯代码）与 OSWorld（纯 GUI）之间。

## TheAgentCompany: 模拟一家软件公司

来源：Xu et al., TheAgentCompany, arXiv 2024；the-agent-company.com。问题：**能否模拟一个公司里一个完整职位的工作？**

- **公司环境**由五个自托管系统构成：**GitLab**（代码）、**Plane**（工单/tickets）、**ownCloud**（文档）、**RocketChat**（团队聊天），加上 **LLM 模拟的同事（coworkers）**。
- **一个职位、端到端**：agent 要完成一整个 job 的工作流：读 ticket（Plane）→ 询问同事（RocketChat）→ 检查仓库（GitLab）→ 写代码 → 跑测试 → 更新 issue → 汇报结果（Plane/RocketChat）。（图示：以"询问 → 检查 → 更新 → 汇报"为骨架，在各系统图标之间流转的工作流。）
- **175 个任务**，覆盖 software、PM、data science、HR、finance 等职位，采用**按进度给分（score by progress）**的部分分机制：

  S_partial = 0.5 · (earned/total) + 0.5 · S_full

  即一半分数按完成的 checkpoint 比例给，一半按是否全部完成给。示例：完成 4/8 个 checkpoint、未完成 → **0.25**；完成 7/8、未完成 → **0.44**；8/8 全部完成 → **1.00**。

## Agent 基准总览

| 基准 | agent 运行的环境 | 典型动作 | 打分对象 |
|---|---|---|---|
| GAIA | Web/文件/代码工具 | 搜索、查看文件、计算 | 简短的最终答案 |
| WebArena | 自托管网站 | 点击、输入、导航 | 网站或后端状态 |
| OSWorld | 完整桌面虚拟机 | 鼠标、键盘、应用交互 | 文件、应用状态、系统状态 |
| SWE-bench | 软件仓库 | 查看、编辑、跑测试 | 补丁通过测试 |
| BFCL | 函数/API 接口 | 结构化函数调用 | 调用、参数与产生的状态 |
| τ-bench | 客服 API 与对话 | 与用户对话、调 API | 数据库状态与回复 |
| Terminal-Bench | 隔离的终端容器 | 任意 shell 命令 | 任务专属验证测试 |
| TheAgentCompany | 模拟软件公司 | 用 web 应用、写代码、管文件、与同事交流 | 工作流 checkpoint 与最终系统状态 |

从"答一道题"到"在完整工作环境里交付结果"，打分对象从字符串匹配逐步演进为环境状态检查与可执行测试。

## Agent 评测的挑战

### 挑战一：数据泄漏——四层，且贯穿整个智能体栈

首先是四层泄漏（Data leakage，不止发生在训练阶段）：

1. **Training leakage（训练泄漏）**：任务或它的人工解法出现在训练数据里。
2. **Eval-time leakage（评测时泄漏）**：agent 联网搜索并抄到未来的修复方案。
3. **Environment leakage（环境泄漏）**：沙箱暴露了未来的 commit 或隐藏测试。
4. **Benchmark overfitting（基准过拟合）**：prompt 与 scaffold 在公开测试集上调过。

关键矛盾：**"评测 agent 需要真实工具 ⟺ 泄漏面更大"**——agent 评测要求真实工具（可搜索的 web），而基准可能正是可被搜索到的。

现代 agent 的表现可写为 **P = f(LLM, prompt, scaffold, tools, retriever, memory, environment)**，因此**栈上任何一环都可能携带基准信息**：

| 组件 | 可能的泄漏 |
|---|---|
| Base model（基座模型） | 基准例子出现在预训练数据中 |
| Fine-tuning（微调） | 基准解法被用作 agent 训练轨迹 |
| Prompt（提示词） | few-shot 例子取自测试任务 |
| Retrieval（检索） | 基准答案被索引进 RAG 语料 |
| Memory（记忆） | 存入了此前的基准尝试 |
| Web search（联网搜索） | 检索到已发布的任务解法 |
| Environment（环境） | 暴露未来 Git commit / 隐藏产物 |
| Scaffold（脚手架） | 手写的启发式规则是针对基准调的 |
| Agent development（开发过程） | 研究者反复查看测试失败并调系统 |

结论：**"模型没有在测试集上训练过"这一句话对 agent 评测远远不够**——泄漏可以发生在栈的任何一个组件里。

### 挑战二：单轮用户（A single user turn）

- 大多数基准只给 agent **一条完全指定的指令**：**prompt in, final state out——用户不在回路里（no user in the loop）**。
- 而真实工作是**模糊的、会被修改的、会被打断的**：约束缺失、任务中途修正、目标漂移。
- 单轮打分**奖励"自信地猜"**：而**提出澄清问题要花步数却拿不到分**。
- 讲中两次以 Assignment 1（用 Claude Code 的经历）来印证这种"真实交互"的差距，并展示了相应的改进方向：
  - **Clarification**：目标未指定清楚时，agent 会不会提问？
  - **Recovery**：任务中途被修正后，agent 会不会重新规划？
  - **Memory**：agent 能否跨轮次保持约束？

（图示：展示 Assignment 1 中用户与 Claude Code 多轮交互、中途改需求的实际 session 截图。）

### 挑战三：还有其他（There are more）

- **Cost and latency（成本与延迟）**：成功率不足以说明问题——一个 200 步、花 $40 的运行 vs 一个 12 步、花 $0.30 的运行，哪个更好？
- **Non-determinism（非确定性）**：同一个 agent、同一个任务，结果可能不同：单次运行（single-run）的分数是噪声，不是信号。
- **Safety and side effects（安全与副作用）**：过程中删除文件、发出邮件、花掉的钱，没有任何惩罚，照样算 pass。
- **Metrics（指标本身）**：只看结果的打分会让"碰运气的"或"不安全的"运行通过；而用轨迹匹配（trajectory matching）打分又会判掉合理但路径不同的运行。
- 课程组正在建设一个**基于真实流量（real traffic）的 agent 评测研究平台**，有兴趣且每周能投入 20 小时以上的同学可以联系 Juncheng。

### 挑战四：基准快速饱和（Benchmarks saturate quickly）

"前沿追赶有多快"：

- **GLUE（2018）**：14 个月达到人类水平（87.1），39 个月达到专家水平（89.8）；其中 PhD 专家题（69.7）用了 10 个月。
- **MMLU（2020）**：从 91.1 → 100 → 92.3 → 100 → 96.0 的爬升曲线迅速逼近满分。
- **GPQA Diamond（2023）**：曲线一路逼近 100。
- **SWE-bench Verified（2024）**：**22 个月内从 33% → 95%**。
- **ARC-AGI-2（2025）**：**11 个月达到人类平均（60）**，前沿已冲到 95.0。
- **ARC-AGI-3（2026）**：**6 个月内从 0.5% → 62.7%**（带 * 号，仍在快速演化）。

（图示：六张分数-时间曲线图，横轴 0–4 年、纵轴 0–100，每代基准发布后前沿模型快速爬升直至饱和。）

另一张时间线总图（2016 → 2025，至 Sep 2026）展示了各基准的出生与饱和节奏：SQuAD 1.1 → GLUE → SuperGLUE → ARC-AGI-1 → MMLU → MATH → HumanEval → MT-Bench → Chatbot Arena → WebArena → SWE-bench → Verified → GPQA Diamond → MMMU → OSWorld → FrontierMath → Humanity's Last Exam → ARC-AGI-2 → Terminal-Bench → GDPval → SWE-bench Pro → Remote Labor Index → ARC-AGI-3 → OSWorld 2.0，按"窄任务 → NLU 套件 → 知识与推理 → 助手 → agent"分类。**Saturated（饱和）= 前沿达到人类基线，或头部模型之间不再拉开差距。**

### Agent 评测仍在演化（总体对比）

| 维度 | 早期评测 | 当前前沿 |
|---|---|---|
| 评测对象（Objective evaluated） | 基座模型 | 模型 + prompt + 工具 + agent harness（整套系统） |
| 交互（Interaction） | 静态、单轮 | 有状态、长程（stateful and long-horizon） |
| 判分者（Grader） | 精确匹配或似然 | 测试、环境状态、人类或评审模型 |
| 数据集（Dataset） | 固定、公开 | 新鲜的、隐藏的、动态的，或感知数据污染的 |
| 主要指标（Main metric） | 平均准确率 | 除任务成功率外，还看系统效率、可靠性、质量、成本、延迟 |
| 核心关注（Primary concern） | 跨样本泛化 | 在真实约束与安全要求下的鲁棒完成 |

## Assignment 3：三个指标与 Pareto 前沿评分

Assignment 3 将对 agent 在**三个指标**上评分，其中能力（Capability）越高越好，成本（Cost）与速度（Speed）越低越好：

- **Pareto 支配关系**：若 A 在任一指标上都不比 B 差、且至少在某个指标上更好，则 **A dominates B（A 支配 B）**。
- 例：Rank 1 的 agent 能力更高、成本更低、速度更快，则它支配 Rank 2；若某 agent 只在"usability（可用性）"这类未纳入排名的维度占优、而三项指标均被支配，则落在 Rank 3。
- **Rank 1 即 Pareto 前沿（Pareto frontier）**：不被任何其他 agent 支配的解集合。（示意图中速度轴因图面原因未画出。）
- 真实世界的 agent 还有更多维度需要纳入考虑，三指标只是起点。

## 下讲预告（Next class）

- Cost-effective agent（高性价比智能体）
- Case study（案例研究）
- Different types of agents（不同类型的 agent）
- Agentic frameworks（智能体框架）

## 核心要点

- 评测分两层：**component-level**（planning、task decomposition、memory 的抽取/整合/检索、tool use 的发现/选择/参数化、error recovery）与 **end-to-end**（success rate、cost、latency）。
- 基准史五代：2018 前窄任务 → 2018–19 NLU 套件 → 2020–22 基础模型能力 → 2023–24 agent/工具/多模态 → 2024–25 难度/鲁棒性/时效 → 2025–26 更大范围、更真实（GDPval、BrowseComp、Terminal-Bench、ARC-AGI-3）。
- 五种评测目标各对应不同基准与"成功"定义；agent 评测的成功 = **达到所需环境状态**。
- 通用评测循环：reset 环境 → observe/act/execute 循环（在 budget 内）→ task_evaluator 对最终答案 + 最终状态 + 轨迹打分。
- 指标演进：perplexity / accuracy / F1 / win rate → **pass@k（k 次至少一次过）** 与 **pass^k（k 次全过，τ-bench 提出）**；成本目前只计 LLM，漏掉工具调用与前缀缓存 miss；延迟是整条链路而非只算 LLM。
- **GAIA**：466 题、3 个难度级（≤5 步/5–10 步/任意长度），无固定工具 API、只打归一化后的最终答案，考"研究"不考"动作"。
- **BFCL**（ICML 2025）：以 AST 或执行检查工具调用，多轮逐轮检查状态+回复，V4 加入 web search 与 memory；看类别分而非综合分。
- **WebArena**（ICLR 2024）：812 任务、自托管网站（Reddit/GitLab/maps/Wikipedia/电商/admin），accessibility tree 观测 + 点击输入动作，最终状态做功能检查；WebArena-Verified 用确定性 HTTP trace 检查替代 LLM-as-a-judge。
- **OSWorld**（NeurIPS 2024）：369 任务、像素观测 + 鼠标键盘动作，检查文件/应用/系统最终状态；OSWorld 2.0 提供 108 条 1 小时以上、数百步、约 27 个 checkpoint 的跨应用长流程并支持部分分。
- **SWE-bench**：issue → 补丁 → 应用仓库跑测试 → resolved or not；派生版本 Verified（人工校验）、Lite（300 任务）、Multilingual（9 语言）、Multimodal（图片 issue）、Pro（更难多文件）。
- **τ-bench**：模拟用户 + 受政策约束的 agent + 真实可变数据库；r = r_action × r_output，意外写入直接失败；**pass^k 要求 k 次独立运行全部成功**，刻意比 pass@k 严格以衡量可靠性；τ³-bench 增加更多领域、知识检索与语音评测。
- **Terminal-Bench**：Docker 容器（instruction.md + Dockerfile）+ 最终系统状态测试（tests/test.sh）；TB 2.0 89 任务 → TB 4.0 66 任务，附隐藏人类解；介于 SWE-bench 与 OSWorld 之间，无 GUI grounding，考察长程推理与系统交互。
- **TheAgentCompany**：GitLab + Plane + ownCloud + RocketChat + LLM 同事的模拟公司，175 个跨职位任务，部分分公式 S_partial = 0.5·(earned/total) + 0.5·S_full（4/8→0.25，7/8→0.44，8/8→1.00）。
- **数据泄漏有 4 层**：训练泄漏、评测时泄漏（联网搜到未来解）、环境泄漏（沙箱暴露未来 commit/隐藏测试）、基准过拟合（prompt/scaffold 在公开测试集上调试）；因为真实工具 ⟺ 更大泄漏面。
- **泄漏贯穿整个栈**：P = f(LLM, prompt, scaffold, tools, retriever, memory, environment)——9 个环节任一都可能含基准信息，"没在测试集上训练"远不够。
- **单轮偏置**：prompt in, final state out，无用户回路；真实工作模糊、会被修正、会被打断；单轮打分奖励自信猜测，澄清提问花钱不赚分；改进方向 = Clarification / Recovery / Memory。
- 成功率之外：**成本与延迟**（200 步 $40 vs 12 步 $0.30）、**非确定性**（单次分数是噪声）、**安全与副作用**（删文件、发邮件、花钱都不受罚）、**指标失配**（结果打分放过侥幸/不安全运行，轨迹匹配判掉合理路径）。
- **饱和极快**：GLUE 14 个月到人类水平；SWE-bench Verified 22 个月 33%→95%；ARC-AGI-2 11 个月达人类平均 60；ARC-AGI-3 6 个月 0.5%→62.7%；饱和 = 达到人类基线或头部模型不再区分。
- 评测演化总表：对象从基座模型 → 整套 harness；交互从静态单轮 → 有状态长程；判分从精确匹配 → 测试/状态/人/评审模型；数据从固定公开 → 新鲜/隐藏/动态/抗污染；指标从平均准确率 → 效率+可靠性+质量+成本+延迟。
- **Assignment 3**：按 Capability（高优）/ Cost（低优）/ Speed（低优）三维评分，A 在任一指标不劣于 B 且至少一项更优则 A 支配 B，不被支配者构成 Pareto 前沿（Rank 1）。
