# CS2680 幻灯片摘要

本仓库是对哈佛 CS2680《Modern AI Systems: Agents and System Optimizations》(Modern AI 系统:智能体与系统优化,主讲:Juncheng Yang)课程幻灯片的个人学习笔记。

- 中文学习材料(课程主线、14 周路线、五个作业、全栈概念、参照实现说明):[CS2680-学习材料.md](CS2680-学习材料.md)
- 每个 PDF 对应的中文简化总结(按章节提炼要点,非逐页翻译):[notes/](notes/)
- 参照实现:`mads/` 包 —— 确定性模拟的 Mads 全栈(Agent Loop / 上下文 / 批处理 / 分页 KV / 投机解码),五个作业各对应一个模块
- 基准:`bash autoresearch.sh` 跑 16 任务工作负载并打印 METRIC 行(主指标 `e2e_latency_s`,正确性门 16/16 任务完成)

## 五个作业的真实实现(本机,2026-11-16)

| 目录 | 作业 | 交付物 | 实测结果 |
|---|---|---|---|
| `a1_lens/` | Mads-Lens | Claude Code 会话 JSONL 的只读 Web UI(纯 stdlib + 单页 SPA):工具调用轨迹、子 agent 树、错误定位、每次调用 5 类 token/成本 | 本机 `~/.claude` 会话树全量解析,`python3 a1_lens/server.py` 即起 |
| `a2_loop/` | Mads-Loop | 手写 Agent Runtime(`madsloop/`,~750 行):结构化工具调用、上下文窗口/压缩、5xx 退避重试(4xx 致命)、死循环检测、12 任务终端套件 | 12/12 全过;20% 注入故障 28/28 恢复;同模型 mlx 引擎比 LM Studio 快 2.9×、省 8.5×(前缀缓存) |
| `a3_opt/` | Mads-Opt | `experiments.py`(真实引擎消融 + `--sim` 确定性 6 点扫描)+ 技术复盘博客 `blog.md` | 路由 31× 成本、并发 9.1× 延迟、全栈 112× 延迟 / 135× 成本,成功率不降 |
| `a4_serve/` | Mads-Serve | mlx-lm 引擎 + 409 行补丁(/metrics、分页 KV 镜像、**并发 bug 根因修复**)+ 合成负载基准 + 块级前缀缓存 `kv_cache.py` | 共享前缀 TTFT 9–34.5×(N=8 312ms vs 10.8s);N=8 吞吐 +1.9×、尾部延迟 −28%;内存 18GB vs 8GB |
| `a5_stack/` | Mads-Stack | Terminal-Bench 0.2.18(修了 Python 3.14 兼容 bug)+ terminal-bench-core 65 任务集 + Mads-Loop 驱动的 `MadsStackAgent`(真实 Docker 沙箱 + tmux 终端) | 5 任务 suite 实跑 **1/5(20%)** @1.5B 脑;hello-world 全栈端到端跑通,换 35B/27B 是下一个实验 |

每个目录自带 README(架构、运行命令、实测数据)。

## 课程链接

- 课程主页:https://cs2680.com
- 备用课程域名(幻灯片页脚中显示):https://course.agentic-system.org
- 智能体评测笔记:https://cs2680.com/notes/agent-evaluation

## 幻灯片

原始幻灯片 PDF 经讲师许可收录在本仓库。

| 讲次 | PDF | 中文笔记 |
|---|---|---|
| 1. 课程导论 | [1_intro.pdf](1_intro.pdf) | [notes/1_intro.md](notes/1_intro.md) |
| 2. 用户视角的智能体 I | [2_agent_use_1.pdf](2_agent_use_1.pdf) | [notes/2_agent_use_1.md](notes/2_agent_use_1.md) |
| 3. 用户视角的智能体 II | [3_agent_use_2.pdf](3_agent_use_2.pdf) | [notes/3_agent_use_2.md](notes/3_agent_use_2.md) |
| 4. 智能体设计 I | [4_agent_design_1.pdf](4_agent_design_1.pdf) | [notes/4_agent_design_1.md](notes/4_agent_design_1.md) |
| 5. 智能体设计 II | [5_agent_design_2.pdf](5_agent_design_2.pdf) | [notes/5_agent_design_2.md](notes/5_agent_design_2.md) |
| 6. 智能体设计 III | [6_agent_design_3.pdf](6_agent_design_3.pdf) | [notes/6_agent_design_3.md](notes/6_agent_design_3.md) |
| 7. 智能体设计 IV | [7_agent_design_4.pdf](7_agent_design_4.pdf) | [notes/7_agent_design_4.md](notes/7_agent_design_4.md) |
| 8. 智能体设计 V | [8_agent_design_5.pdf](8_agent_design_5.pdf) | [notes/8_agent_design_5.md](notes/8_agent_design_5.md) |
| 作业 3 | [8_assignment3.pdf](8_assignment3.pdf) | [notes/8_assignment3.md](notes/8_assignment3.md) |
| 9. LLM 服务基础 I | [9_llm_serving_basics_1.pdf](9_llm_serving_basics_1.pdf) | [notes/9_llm_serving_basics_1.md](notes/9_llm_serving_basics_1.md) |
| 10a. LLM 服务基础 IIa | [10_llm_serving_basics_2a.pdf](10_llm_serving_basics_2a.pdf) | [notes/10_llm_serving_basics_2a.md](notes/10_llm_serving_basics_2a.md) |
| 10b. LLM 服务基础 IIb(引介 GPU) | [10_llm_serving_basics_2b.pdf](10_llm_serving_basics_2b.pdf) | [notes/10_llm_serving_basics_2b.md](notes/10_llm_serving_basics_2b.md) |
| 11. LLM 服务基础 III | [11_llm_serving_basics_3.pdf](11_llm_serving_basics_3.pdf) | [notes/11_llm_serving_basics_3.md](notes/11_llm_serving_basics_3.md) |
| 作业 4 | [assignment4.pdf](assignment4.pdf) | [notes/assignment4.md](notes/assignment4.md) |
| 作业反馈讲次 | [feedback_assignment.pdf](feedback_assignment.pdf) | [notes/feedback_assignment.md](notes/feedback_assignment.md) |

## 1. 课程导论(50 页)

- 课程概览:先打基础(LLM、Claude Code、编码智能体),再进系统(GPU 内核、批处理与调度、KV/前缀缓存、路由、智能体服务)。
- 五个作业:(1) 为 Claude Code 做 Web UI,(2) 写一个简单编码智能体,(3) 在排行榜上优化智能体,(4) 用小模型本地服务智能体,(5) 全栈优化。
- 计分:作业 70%、项目 16%、展示 10%、课堂参与 4%、加分 10%。迟交每天扣 20%,共 4 天宽限。
- 规定:鼓励使用 AI 但必须披露,且要提交会话日志。要求线下出勤。算力为班级 HPC 集群(RTX 6000 Blackwell,SLURM)+ AWS。
- 第一部分,智能系统与传统系统的区别:异构计算、prefill(计算受限)vs decode(访存受限)、浮点非确定性、巨大的状态(权重、KV 缓存)、多 GPU 通信、可靠性、功耗。
- 第二部分,智能体:规划、行动、观察、适应。"智能体即新计算机"类比(LLM = CPU、上下文 = RAM、工具 = 外设、harness = 操作系统)。为什么智能体是系统问题。agentic 技术栈。真正的目标函数是每个成功任务的成本($/task),而不是每秒 token 数。
- 不覆盖:训练与模型架构。

## 2. 用户视角的智能体 I:Claude Code 如何工作(53 页)

- agentic 循环:收集上下文,模型提出动作,harness 执行,结果折回上下文。
- 在你敲下第一个字符之前,上下文里已经有一万多 token。代码仓库通过 grep 和 read 按需拉取,而不是整体塞进去。
- 权限模式、上下文增长与压缩(compaction)。
- 记忆:CLAUDE.md 层级结构与它该放什么、带 `paths:` frontmatter 的 `.claude/rules/`、带 MEMORY.md 索引的自动记忆,以及 `/memory`、`/context`、`/init`、`/doctor` 命令。
- 核心工具:Read、Search、Fetch、Edit/Write、Shell、Delegate。
- 扩展机制:Skill 定义"怎么做一件事",MCP 提供外部访问,Hook 在生命周期事件上强制行为,Plugin 把它们打包。含一个发布工作流示例与分类练习。
- 可选幻灯片:MCP 架构、其原语(工具、资源、提示词)、安全、网关,以及 2026-07-28 规范。

## 3. 用户视角的智能体 II:多智能体与最佳实践(72 页)

- 案例:Superpowers 插件(九个 skill 加一个 SessionStart 引导 hook)与 Caveman 插件(skill、命令、hook、MCP,以及一个压缩工具输出的本地代理)。
- 规模化:git worktree 并行智能体、子智能体(内置/自定义/嵌套)、智能体团队、动态工作流、`/goal` 与 `/loop`。
- 案例:16 个智能体协作造了一个 C 编译器,花了约 2 万美元,靠 Git 协调。
- "编程 3.0"与 Karpathy 的 Software 3.0。不确定性是核心主题,所以要让周围的系统可靠。
- Codex 使用报告(2026 年 6 月与 9 月):委派任务持续增长,一个人跑很多智能体,委派阶梯。
- 可选幻灯片:CLI 编码智能体综述。

## 4. 智能体设计 I:上下文管理与工具设计(56 页)

- ReAct 循环与代码里的智能体循环。
- 搜索工具对比:grep/glob、语义索引、外部信号、LSP。
- 编辑工具对比:整文件重写、统一 diff、查找/替换、AST 编辑。
- shell 工具的风险,与工具设计最佳实践。
- 提示词工程:零样本、少样本、角色、思维链、思维树、自一致、提示词链、元提示。
- 上下文工程:上下文是有限资源。四种控制手段:准入、卸载、变换、压缩。五种失效方式:投毒、分心、混淆、冲突、漂移。
- 智能体 = 模型 × Harness:只改 harness 就把 SWE-bench 准确率大约翻倍。

## 5. 智能体设计 II:多智能体系统(46 页)

- 每个设计背后的三张图:控制图、任务图、通信图。
- 八种架构:主管-工人、层级、流水线/DAG、黑板、委员会、市场、群体、动态拓扑。真实系统都是混合体。
- 任务分解:切什么、粒度权衡、静态 vs 动态分解、常见失败(重叠、空隙、隐藏依赖、落后者)。
- 通信:介质、通道、消息格式(结构化控制字段 + 自然语言内容)。
- 多智能体系统继承分布式系统的问题,如幂等与部分失败。
- A2A 协议(智能体卡片、任务、任务生命周期)与 MCP 对比。
- 设计原则:单智能体往往就够用。

## 6. 智能体设计 III:记忆与可靠性(31 页)

- 记忆管线:写或跳过、编码、存储、检索、反思、遗忘。
- 格式(原始情节、摘要、结构化状态、知识图谱)与后端(文件、键值、向量、图数据库)。
- 有效时间(valid time)与出处、记忆归属、专用记忆系统(Mem0、Graphiti、supermemory)。
- 记忆失效模式与基准(LoCoMo、LongMemEval、BEAM)。
- 可靠性:单步 95% 成功率,50 步的运行只有约 8% 能全程无错完成。
- 故障来源:任务规格、harness、模型、工具、环境。各配一张"失败-修复"表,最后汇总"为失败而设计"。

## 7. 智能体设计 IV:评测(37 页)

- 组件级 vs 端到端评测、基准演进史、指标(pass@k vs pass^k、成本、延迟)。
- 基准深潜:GAIA、BFCL、WebArena、OSWorld、SWE-bench、τ-bench、Terminal-Bench、TheAgentCompany。
- 挑战:贯穿整个智能体栈的数据泄漏、单轮偏差、非确定性、不受惩罚的副作用、基准快速饱和。
- 作业 3 按能力、成本、速度的 Pareto 天际线计分。

## 8. 智能体设计 V:高性价比智能体(54 页)

- 成本 = 用户数 × 会话数 × 轮数 × 步数 × token 数 × 单位价格。
- 班级使用数据:约 97.6% 的 token 是缓存读,主智能体单步中位数 20–30 万 token。
- 杠杆:减少轮数、批量步骤、更精简的上下文、更短的输出(effort 档位)、更低的单位 token 价格(缓存、批处理、路由)。
- 预算与停止规则,以及何时根本不用 LLM。
- 速度:关键路径、编排、并行、投机动作(PASTE、SPORK)。
- harness 架构:单体、模块化、微内核。
- 八个 harness 对比:Claude Code、Codex CLI、DeepSeek Harness、OpenCode、Pi、oh-my-pi、OpenClaw、Hermes Agent。

## 作业 3:MadsOpt Harness 竞赛(7 页)

- 26 个任务,跨 3 种容器类型。智能体通过 HTTP 到达每个任务,除课程 API 外全程离线运行。
- 限额:三档模型(Expert、Standard、Starter),每次 `evaluate()` 35 分钟、总计 4 小时,每次 $10、每天 $30。
- 排行榜只上传 `src.zip`。
- 排名是求解任务数、每任务成本、每任务时间的天际线。至少解出 7 个任务,基线是 16 个。
- 分数:若任一提交达到基线则为 `max(81 − r, 50)`,否则 `81 − r`。排行榜占 80 分、技术报告 10 分、视频 10 分。
