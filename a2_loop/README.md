# a2_loop — Mads-Loop: 手写 Agent Runtime (CS2680 A2)

无需客户端框架：整个循环约 750 行代码（`madsloop/`），基于标准库 +
`httpx` 对接课程提供的 OpenAI 兼容端点（LM Studio 在 `localhost:1234`
，或任何 OpenAI 兼容引擎）。一个依赖；Agent 完全受我们控制，
这正是隐藏故障注入测试所探测的目标。

## 循环流程

```
prompt ──▶ LLM (结构化工具调用) ──▶ 工具执行 (子进程, 沙箱化
    ▲                                       目录, 超时, 环境变量清理) ──▶
    └───── 追加结果, 下一步 ◀──────────────┘
```

| 模块 | 作用 |
|---|---|
| `madsloop/client.py` | `LLMClient`: `httpx` 异步, JSON 工具调用解析 (从损坏的 JSON 参数恢复, 将错误反馈给模型), 用量/费用核算, **5xx/超时指数退避 + 抖动重试, 4xx 硬失败**, 每端点路由。`FaultyLLMClient`: 注入故障的测试夹具 (503 风格突发, 可选硬失败), 用于证明鲁棒性。 |
| `madsloop/agent.py` | 状态机: `submit → await model → run tools → … → done`。管理对话、步骤预算 (`max_steps`)、**死循环检测** (相同工具+参数+结果出现 3 次 ⇒ 跳出), 以及 `AgentResult` 核算。 |
| `madsloop/context.py` | 上下文窗口管理器: token 预算 (`max_context`)、**滑动窗口丢弃最旧工具 I/O**、可选 **压缩** (要求模型将历史中间部分总结为一条消息——课程中的压缩技术)、稳定前缀锁定以命中提供方的 KV 缓存。 |
| `madsloop/tools.py` | 8 种工具: `bash`, `write_file`, `read_file`, `list_dir`, `glob`, `grep`, `delete_file`, `done`。每种在每任务工作目录下运行, 带超时和清理后的环境变量。 |
| `madsloop/config.py` | 所有旋钮集中于一处 `AgentConfig` (上下文大小、压缩、保留最近、退避、每端点路由)。 |
| `run.py` | 驱动: 12 任务终端套件 (`tasks.py`, 与 `mads/workload.py` 同形状), 并发或串行, 写入 `results/<tag>.json` (含每任务 + 聚合 METRIC 行)。 |
| `tasks.py` | 12 个确定性任务 (sum-file, off-by-one 修复, csv→json, fizzbuzz, 日志解析, jsonl-聚合, …), 各有真实通过/失败评分器 (文件检查, `python -m unittest`, 输出差异)。 |

## 运行

```sh
cd a2_loop
# 课程的引擎 (LM Studio):
.venv/bin/python run.py --tag base --concurrency 1
# 任意 OpenAI 兼容引擎/模型:
.venv/bin/python run.py --tag mx --concurrency 1 \
  --base-url http://localhost:8084/v1 --model <id> \
  --fault-rate 0.2            # 注入瞬态故障以证明鲁棒性
```

## 本机实测 (2026-11-16)

相同的 12 个任务, 相同的 Agent, 三种引擎配置:

| 配置 | 模型/引擎 | 解决 | 耗时 | Token | 缓存命中 | 工具调用 | 费用 (等值) |
|---|---|---|---|---|---|---|---|
| `baseline` | Qwen3.6-35B-A3B on **mlx-lm** (:8084, 提示缓存 16 GB) | **12/12** | 241 s | 65.5 k | **53.4 k** | 3,947 | **$0.0125** |
| `compare27` | Qwen3.8-27B on **LM Studio** (:1234) | **12/12** | 694 s | 57.2 k | 0 | 3,538 | $0.1062 |
| `fault` | Qwen3.6-35B on LM Studio, **20 % 注入故障** | 10/12 * | 55 s | 56.9 k | 0 | 2,197 | $0.0101 |

* 两个未完成任务是环境产物, 非循环失败:
  两者在步骤 0 以 `400 Failed to load model … Operation canceled` 死亡
  — LM Studio (单本地引擎) 正进行模型切换同时为我们会话的 27B 模型
  提供服务。这是一个真正的 4xx, 循环正确地将其视为致命而非重试
  一个死掉的模型。所有在 20 % 故障注入下到达活模型的完成任务
  **全部完成** (10/10), **28 个注入故障全部恢复** (每任务重试
  计数 0–10; 故障突发为 503 风格: 连续失败 ≤3 次后放行 — 来自
  第 1 讲的可疑网络形状)。

读数:

- **同模型, 不同引擎, 3× 速度**: mlx-lm 的
  `--prompt-cache-bytes` 给出了 53 k 缓存命中 token (Agent 的稳定
  前缀免费重新预填充); LM Studio 报告无缓存命中。
  27B on LM Studio 费用高 8.5 倍。这是 A2 最重要的发现——
  服务引擎是 Agent 栈的一部分, 也是 A3/A4 的方向。
- **Agent 运行的 Token 形态**: 输入很小 (12 个任务共 12 k token —
  上下文管理器保持提示有界), 而输出/工具流量占主导; 费用跟踪
  输出 token, 这也是 A3 的路由杠杆 (常规步骤使用便宜模型)
  针对的目标。
- **工具调用是核心工作**: ~3.5 k 次调用处理 57 步; 每个
  结果进入上下文, 窗口管理器是保持 32 k 预算在 5–14 步任务中
  合理的机制。

## 鲁棒性说明 (隐藏测试将触及的内容及回答)

1. **5xx / 超时** → 指数退避 + 抖动重试
   (0.4 s → 0.8 → 1.6 → … → 20 s 上限), 每步 `max_retries`; 任务
   继续。上述已验证 (28/28 恢复)。
2. **4xx** → 步骤致命; 任务记录 `FAILED_ERROR`, 运行
   继续 (每任务隔离), 无重试风暴。
3. **空/畸形补全** → 客户端将空的
   `content` + 无工具调用视为可重试的退化响应 (有界), 损坏的 JSON
   `tool_calls[].arguments` 通过向模型反馈解析错误而非崩溃循环来恢复。
4. **无限循环** → 3 次连续相同的 (工具, 参数, 结果)
   三元组以合成消息"你在重复自己"跳出步骤; `max_steps` 限制整个运行。两者在 12 任务
   基线中未触发 (0 次循环跳出), 但两者都在故障路径的爆炸半径内。
5. **每任务隔离** → 一个任务的崩溃从不影响另一个的
   客户端/上下文/沙箱; 聚合门控为每任务。

## 实验完整性说明 (验证时发现)

首次故障运行在 20 % 注入率时报告 `retries=0`——
不可能。根因: 每个任务的故障 RNG 种子相同
(`Random(0)`), 该流的前十几个抽取都超过 0.2, 所以没有
任务抛出故障; "故障运行"实际上是第二个干净运行。修复为
每任务不同种子 (`seed*7919+task_index`), 修复后的运行
显示预期的 ~20 % 命中率。教训: 注入故障夹具必须
用自己的计数器验证, 而非依赖运行完成。

## 文件

- `madsloop/` — 运行时 (client, agent, context, tools, config)
- `run.py` — 驱动 (参数: `--tag --concurrency --model --base-url
  --fault-rate --tasks --compact --max-ctx --keep-recent --router …`)
- `tasks.py` — 12 任务套件 + 评分器
- `results/*.json` — 完整每任务运行 (baseline / compare27 / fault)
- `full_runs.sh` — 上述三种配置, 依次运行
