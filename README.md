## 幻灯片

原始幻灯片 PDF 经讲师许可收录在本仓库。

| 讲次 | PDF | 中文笔记 |
|---|---|---|
| 1. 课程导论 | [1_intro.pdf](1_intro.pdf) | [notes/1_intro.md](notes/1_intro.md) — prefill 算力受限 vs decode 带宽受限；Agent 是"新计算机"，真正优化目标是 $/successful task |
| 2. 用户视角的智能体 I | [2_agent_use_1.pdf](2_agent_use_1.pdf) | [notes/2_agent_use_1.md](notes/2_agent_use_1.md) — agentic loop 四步；记忆(CLAUDE.md/auto memory)把一次性指令变长期惯例；Skill/MCP/Hook/Plugin 四种扩展机制 |
| 3. 用户视角的智能体 II | [3_agent_use_2.pdf](3_agent_use_2.pdf) | [notes/3_agent_use_2.md](notes/3_agent_use_2.md) — Superpowers/Caveman 两个案例；手工并行/subagent/team/dynamic workflow 四条规模化路径；不确定性是核心主题 |
| 4. 智能体设计 I | [4_agent_design_1.pdf](4_agent_design_1.pdf) | [notes/4_agent_design_1.md](notes/4_agent_design_1.md) — Agent = Model × Harness；ReAct 三要素；上下文四杠杆(Admission/Offloading/Transformation/Compaction)按无损到有损排序 |
| 5. 智能体设计 II | [5_agent_design_2.pdf](5_agent_design_2.pdf) | [notes/5_agent_design_2.md](notes/5_agent_design_2.md) — 三张图(控制/任务/通信)刻画八种架构；任务分解六轴八要素；多智能体继承分布式系统六大难题，A2A 与 MCP 两个协议分层叠加 |
| 6. 智能体设计 III | [6_agent_design_3.pdf](6_agent_design_3.pdf) | [notes/6_agent_design_3.md](notes/6_agent_design_3.md) — 记忆六阶段流水线(写/格式/后端/检索/反思/遗忘)；可靠性从误差复合出发，故障分五层(spec/harness/model/tool/env)，为失败而设计 |
| 7. 智能体设计 IV | [7_agent_design_4.pdf](7_agent_design_4.pdf) | [notes/7_agent_design_4.md](notes/7_agent_design_4.md) — 组件级 vs 端到端评测；八大基准(GAIA/BFCL/WebArena/OSWorld/SWE-bench/τ-bench/Terminal-Bench/TheAgentCompany)对比；数据泄漏四层与基准快速饱和 |
| 8. 智能体设计 V | [8_agent_design_5.pdf](8_agent_design_5.pdf) | [notes/8_agent_design_5.md](notes/8_agent_design_5.md) — 成本分解公式(用户×会话×轮次×步数×token×单价)逐项压缩；三种架构(单体/模块化/微内核)对比；优化是"跑→度量→改一件事→复评"的循环 |
| 作业 3 | [8_assignment3.pdf](8_assignment3.pdf) | [notes/8_assignment3.md](notes/8_assignment3.md) — 26 任务、三档模型路由；时间(35 min/evaluate, 4 h 总计)与成本(每天 $30)双重限制；按解题数/每题成本/每题时间三维天际线排名 |
| 9. LLM 服务基础 I | [9_llm_serving_basics_1.pdf](9_llm_serving_basics_1.pdf) | [notes/9_llm_serving_basics_1.md](notes/9_llm_serving_basics_1.md) — 请求六阶段(Tokenize→Schedule→Prefill→Decode→Detokenize→Stream)；Llama 3 系统估算(权重 141 GB/KV 320 KB/token)；MoE 解耦内存与算力 |
| 10a. LLM 服务基础 IIa | [10_llm_serving_basics_2a.pdf](10_llm_serving_basics_2a.pdf) | [notes/10_llm_serving_basics_2a.md](notes/10_llm_serving_basics_2a.md) — GPU 是吞吐机器，SIMT 按单线程编程，Roofline 脊点(H200 206 FLOP/B)分隔内存/计算受限；decode 强度≈1 FLOP/B 只跑峰值 0.5% |
| 10b. LLM 服务基础 IIb | [10_llm_serving_basics_2b.pdf](10_llm_serving_basics_2b.pdf) | [notes/10_llm_serving_basics_2b.md](notes/10_llm_serving_basics_2b.md) — MFU/MBU 双指标剖析；kernel 优化(融合/FlashAttention/持久 kernel/Split-KV/CUDA Graphs/PDL)；跨 GPU 通信(Flux/DeepEP) |
| 11. LLM 服务基础 III | [11_llm_serving_basics_3.pdf](11_llm_serving_basics_3.pdf) | [notes/11_llm_serving_basics_3.md](notes/11_llm_serving_basics_3.md) — 连续批处理与选择性批处理；调度(FCFS/chunked prefill/PD 分离/SJF)；PagedAttention 与前缀缓存；五种并行(DP/TP/PP/EP/SP)及通信代价 |
| 作业 4 | [assignment4.pdf](assignment4.pdf) | [notes/assignment4.md](notes/assignment4.md) — 自持 SGLang serving 引擎作为 Agent 后端，先度量后优化，一次只改一个方案，禁止换模型；评分 = 端到端时间 + 解出任务数 |
| 作业反馈讲次 | [feedback_assignment.pdf](feedback_assignment.pdf) | [notes/feedback_assignment.md](notes/feedback_assignment.md) — Claude Code 使用量增长 4.5–7×，失败多由学生自己发现；十大陷阱(P1–P10)与六步迭代循环(本地测试→基线→一处改动→验证→复评) |
