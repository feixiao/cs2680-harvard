# 作业 4：MadsServe —— 拥有自己的推理引擎（Assignment 4: MadsServe: Own the Serving Engine）

## 本讲概览

本作业的主题是 "Own the Serving Engine"：在 ATG 集群上搭建自己的 SGLang serving 引擎，把它作为之前作业中 Agent 的推理后端，对端到端性能做深入测量，找出真实 Agent 负载下的瓶颈，并基于观测结果做优化、迭代提交排行榜。核心方法论是"先度量、后优化"：作业不指定要优化什么，要求你亲自测出瓶颈再做单变量实验。

## 作业流程（Overview）

- 五步主线：搭建基础 SGLang serving 引擎 → 用自持引擎跑 Agent → 观察瓶颈 → 针对观测到的瓶颈做优化 → 提交并迭代（循环）。
- 优化对象必须是你自己测量发现的瓶颈，而非预设的"标准优化清单"。

## 基础 SGLang 搭建（Basic SGLang Setup）

- 环境在课程的 **ATG 集群**（集群共预留 80 台 RTX 4500）。
- 首次使用需完成集群初始配置，并分配一台 **RTX Pro 4500** 节点。
- SGLang 实例的具体安装与 Agent 连接方式，按 Assignment 4 官方网页说明操作（幻灯片不重复命令细节）。

## 性能测量（Measure the Performance）

- 把分配给你的**全部 25 个任务**跑一遍；注意本地任务集**与排行榜任务集不同**，本地结果仅作诊断。
- 同时记录 Agent 侧日志与引擎侧指标，SGLang 的 **/metrics 端点**很有用。
- 要求 **"dig deep into where the time goes"**：拆解端到端时间，定位时间真正花在哪里。
- 同时运行 **SGLang bench**，对比合成基准与真实 Agent 流量的趋势是否一致，并解释差异原因。

## 优化（Make Serving Efficient）

- 基于测量发现的问题列出候选方案，**一次只试一个方案（one solution at a time）**，保证性能变化可归因。
- 允许修改：
  - **Serving 引擎**：配置（configuration）与代码（code）均可改；
  - **Agent**：可以改它使用 server 的方式。
- **不允许更换模型**——这不是本作业的重点（换模型会污染系统优化效果的归因）。

## 排行榜（Leaderboard）

- 官方在**沙箱（sandbox）**中运行你的 serving 引擎。
- 评分依据：**end-to-end time（端到端时间）+ solved tasks（解出任务数）**；其余规则与作业 3 类似。
- **引擎加载时间不计入评分**。
- 截止后排行榜**立即停止接收提交**；已提交的请求会正常评分。

## Writeup 与视频（Writeup & Video）

- 目标是展示你的**理解**，而不只是"做了一些优化"。
- Writeup 必写内容：① 测量中发现的瓶颈；② 与 SGLang benchmark 对比的发现；③ 所做的改动及详细的观测数据与推理；④ 经验教训（lessons learned）。
- 视频：**3 分钟，要求真人出镜并有真实的人机交互演示**。

## 公告（Notices）

- 资源有限（80 台 RTX 4500 共享）：**同时最多使用 1 块 GPU**，请体谅其他同学。

## 核心要点

- 主题："Own the Serving Engine"——自持 SGLang 引擎作为 Agent 后端，接管整个服务层。
- 主线循环：搭引擎 → 跑 Agent → 观察瓶颈 → 优化 → 提交迭代。
- 环境：ATG 集群，分配 RTX Pro 4500 节点，具体步骤以 Assignment 4 网页为准。
- 本地跑满 25 个任务，但本地任务集 ≠ 排行榜任务集。
- 双轨测量：Agent/引擎日志（SGLang /metrics）+ SGLang bench 对比。
- 必须拆解时间去向（dig deep into where the time goes）。
- 实验纪律：一次只改一个方案。
- 可改 serving 引擎（配置+代码）和 Agent 用法；**禁止换模型**。
- 评分 = 端到端时间 + 解出任务数，沙箱运行，引擎加载时间不计。
- Writeup 四要素：瓶颈、bench 对比发现、改动+推理、教训。
- 视频：3 分钟、真人出镜、真实交互。
- 纪律：同时最多 1 块 GPU；截止后立即停止收题。
