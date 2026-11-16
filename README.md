# CS2680 幻灯片摘要

本仓库是对哈佛 CS2680《Modern AI Systems: Agents and System Optimizations》(Modern AI 系统:智能体与系统优化,主讲:Juncheng Yang)课程幻灯片的个人学习笔记。

- [CS2680-学习材料.md](CS2680-学习材料.md) — 完整中文学习笔记:14 周路线、五个作业、Part I/II 核心概念速记、全栈技术层级图、mads/ 参照实现说明、学习路线建议
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
