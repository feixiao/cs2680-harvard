# mads — 参照实现

确定性、纯 CPU 模拟的 "Mads 全栈"：prompt → Agent Loop → 调度/批处理 → 分页 KV → 记账。无网络、无墙钟、无真实模型；同一输入两次运行逐字节一致（固定种子 token 流 + 模拟时钟）。五个课程作业各对应一个模块。

## 模块

| 文件 | 对应作业 | 作用 |
|---|---|---|
| `lens.py` | Mads-Lens | 逐任务记账：token / 缓存命中 / 成本 / 延迟 / 重试 / KV 高水位，`Lens.summary()` 汇总 |
| `agent_loop.py` | Mads-Loop | 手写 Agent Runtime：结构化工具调用、上下文窗口（滑动丢弃 / 压缩）、瞬时错误重试退避、退出判定。`AgentConfig` 是全栈旋钮总入口 |
| `opt.py` | Mads-Opt | 优化策略层：`baseline_config()` 优化后的全栈配置 + `route_by_step` 路由策略 |
| `scheduler.py` | Mads-Serve / Stack | 32 GB GPU 模拟：事件驱动 continuous batching、FIFO prefill（张量并行切分）、投机解码（0.5B draft，8 token 窗口 / 95% 接受率）、GPU 驻留管理 |
| `kv_cache.py` | Mads-Serve | 分页 KV 缓存（16 token/block，内容寻址前缀复用，超预算 FIFO 驱逐） |
| `workload.py` | 评测 | 16 个确定性任务（固定种子，5–14 步工具计划），`make_tasks(16, seed=42)` |
| `agent.py` | Mads-Loop/Serve | 工作负载驱动 `run_workload()`：准入控制，请求完成即时决策，工具 I/O 与退避挂共享时钟，与 GPU 工作并行 |
| `models.py` / `simclock.py` / `llm.py` | 基础 | 三模型一草稿的规格表 / 模拟时钟 / 确定性伪 LLM |

依赖：仅 Python 3 标准库。

## 运行

基准（打印 METRIC 行，16/16 任务完成否则非零退出）：

```bash
bash autoresearch.sh        # 或 python3 bench/run_bench.py
```

当前输出（`baseline_config` 优化后的全栈）：

```
METRIC e2e_latency_s=15.505        # 模拟总耗时（主指标，越低越好）
METRIC total_cost_usd=0.0331
METRIC total_tokens=413879
METRIC cache_hit_rate=0.7565       # 内容寻址前缀复用命中 76%
METRIC tasks_completed=16          # 正确性门
METRIC retries=7
METRIC peak_kv_mb=5667.2
```

作为库用（换配置跑同一负载）：

```python
from mads import make_tasks, run_workload, AgentConfig

metrics, lens = run_workload(make_tasks(16, seed=42), AgentConfig())  # 朴素基线
print(metrics["e2e_latency_s"], metrics["total_cost_usd"])
```

## 优化杠杆（`AgentConfig` 旋钮，照课程顺序）

1. **路由** `router`：每步改由本地 starter（3B）服务，比 expert API 便宜 30x、快 6.6x；`resident=["starter", "draft"]` 把权重内存腾给 KV 预算。
2. **前缀复用** `prefix_reuse=True`：相邻步共享稳定前缀，prefill 只为新增 token 付费（课程数据：97.6% 的 token 是缓存读）。
3. **压缩** `compaction=True` + `keep_recent=2` + `prefix_budget`：上下文压到最小的稳定前缀，砍掉 68% 的 token。
4. **并发** `concurrency=16` + `parallel_tools=True`：16 任务同时推进，工具调用并行。
5. **投机解码** `speculative=True`：0.5B draft 一次 prefill、8 token 窗口、95% 接受率，decode 摊薄。
6. **张量并行** `tp_size=8`：prefill 按 token 工作量切到 8 卡。

朴素基线（`AgentConfig()` 默认）→ 优化全栈：e2e 1738.5 s → 15.5 s（112x），成本 $4.48 → $0.033（135x）。

更细的讲解见 [`../CS2680-学习材料.md` 第七节](../CS2680-学习材料.md)。
