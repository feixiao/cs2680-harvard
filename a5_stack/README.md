# a5_stack — Mads-Stack 评测基础设施 (CS2680 A5)

Terminal-Bench 夹具 + Mads-Stack (Mads-Loop 驱动) Agent, 已建立,
已冒烟测试, 并运行: 首次全栈套件在 1.5 B 大脑上实测 1/5 (20%) —
全路径端到端已验证 ([首次全栈运行](#首次全栈运行-measured-2026-11-16-112-min))。

## 就绪组件

| 部分 | 状态 |
|---|---|
| Docker 守护进程 | Docker Desktop 4.96.1 / 引擎 **29.9.2** (aarch64, **16 CPU, 7.75 GB RAM** — 低于 16 GB 上限, 保持原样)。通过 `open -a Docker` 启动。 |
| `.venv` | Homebrew **Python 3.14.7**, **terminal-bench 0.2.18** (PyPI 最新版) + 依赖。CLI 为 `tb` (0.2.x 将旧 `tbench` 改名); `.venv/bin/tbench` 兼容 shim 转发到 `tb`。 |
| 任务目录 | `terminal-bench-core` **v0.1.1** (启动集: 按注册表的 65 个任务; 稀疏克隆 `terminal-bench-core/tasks/` 包含该分支全部 86 个目录)。 |
| 精选镜像 | 拉取 3 个基础镜像 + 预构建 5 个小任务镜像 = **~1.9 GB 总计** (≤10 GB 预算)。全部通过 shell 启动验证。 |
| Agent | `harness_stub.py` — `MadsStackAgent`, terminal-bench 的 `BaseAgent` 由 `a2_loop/madsloop` 运行时驱动。冒烟: **通过** (hello-world 沙箱中一次真实命令往返, 7 秒)。 |

### Docker 资源
Docker Desktop VM: 16 CPU / 7.75 GB RAM (本机默认; 主机有 128 GB —
如果全栈阶段需要更大任务的余量, 在 Docker Desktop → 设置 → 资源中提高 RAM 上限, **≤16 GB** 按资源预算; LM Studio + mlx-lm 引擎占用主机约 30–40 GB)。

### 任务目录
- 数据集: `terminal-bench-core==0.1.1` (简单手工任务) 已本地检出到 `terminal-bench-core/tasks/` — 使用 `--dataset-path` 避免重新下载 (本机网络慢; 650 MB 镜像拉取耗时 ~35 分钟)。
- terminal-bench 注册表 (通过 `tb datasets list` 获取) 还提供适配器数据集 — `swebench-verified`, `swesmith`, `appworld-*`, `mlebench-lite`, `quixbugs`, `usaco`, `algotune`, `aider-polyglot` — 全部 `head` 版本, 全部比核心集重得多。
- 精选小任务 (简单 bash/python, 无 ML/数据科学):
  `hello-world`, `count-dataset-tokens`, `grid-pattern-transform`,
  `organization-json-generator`, `fix-permissions`.
  小 VM 运行避免: `train-fasttext`, `eval-mteb`, `hf-model-inference`,
  `pytorch-model-cli`, `cartpole-rl-training`, `chess-best-move`, `qemu-*`,
  `build-*`, `swe-bench-*`, `solana-data`, `reshard-c4-data`, `intrusion-detection`.

### 精选镜像 (全部启动验证: shell + tmux + asciinema)
| 镜像 | 大小 | 被谁使用 |
|---|---|---|
| `ghcr.io/laude-institute/t-bench/python-3-13:latest` | 265 MB | hello-world, count-dataset-tokens, grid-pattern-transform, org-json-generator (及大多数 python 任务) |
| `ghcr.io/laude-institute/t-bench/ubuntu-24-04:latest` | 206 MB | fix-permissions (及其他 bash 任务) |
| `ubuntu:latest` | 181 MB | git-multibranch |
| `tb__hello-world__client:latest` | 265 MB | 预构建任务镜像 |
| `tb__count-dataset-tokens__client:latest` | 265 MB | 预构建任务镜像 |
| `tb__grid-pattern-transform__client:latest` | 265 MB | 预构建任务镜像 |
| `tb__organization-json-generator__client:latest` | 285 MB | 预构建任务镜像 |
| `tb__fix-permissions__client:latest` | 206 MB | 预构建任务镜像 |

`tb__*` 名称正是夹具在运行时计算的名称
(`tb__<task_id>__client`), 所以运行可使用 `--no-rebuild` 并立即开始。
重建其中任何一项: `a5_stack/build_curated.sh` (在 ~15 秒内重建全部 5 项)。

## 夹具契约 (3 句话)
terminal-bench 0.2.18 通过
`BaseAgent.perform_task(instruction, session, logging_dir)` 驱动 Agent 执行
任务, 其中 `session` 是包装任务 Docker 容器的 `TmuxSession`: Agent 以
`session.send_keys([cmd, "Enter"], block=True)` 发送输入 (等待 `tmux wait -S done` 标记), 并通过
`session.get_incremental_output()` / `capture_pane()` 读取结果。夹具通过
`--agent-import-path module.path:ClassName` 和
`--agent-kwarg key=value` 从 CLI 实例化 Agent, 然后在执行器线程下运行 `perform_task`
在 `asyncio.wait_for(task.max_agent_timeout_sec)` 内, 之后在新生成的会话中执行
任务的 `run-tests.sh` 并解析面板以判定 resolved/not。
`MadsStackAgent` 通过运行 Mads-Loop `Agent`
(OpenAI 聊天循环: 重试/退避, 滑动上下文, 死循环检测) 履行该接口, 其唯一暴露的工具是 `bash`, 从主机重定向到 tmux 会话 — 模型因此对容器自身的终端执行操作, 用量 token 映射到 `AgentResult`。

## 全栈阶段运行什么

前提: A4 引擎在
`http://localhost:8081/v1` 上提供 OpenAI 聊天补全 — 通过 `a4_serve/serve.sh` 启动 (补丁服务器:
`/metrics` + 并发崩溃修复, 使 Agent 的并发请求安全)。

运行单个任务:
```bash
cd /Users/fx/wk/github/cs2680-harvard        # sys.path 上的仓库根以导入路径
export PYTHONPATH=$PWD
a5_stack/.venv/bin/tbench run \
  --dataset-path a5_stack/terminal-bench-core/tasks \
  --task-id hello-world \
  --agent-import-path a5_stack.harness_stub:MadsStackAgent \
  --agent-kwarg base_url=http://localhost:8081/v1 \
  --agent-kwarg model=<a4 模型名> \
  --no-rebuild --no-cleanup \
  --output-path a5_stack/runs
```
运行套件 (5 个精选任务):
```bash
a5_stack/.venv/bin/tbench run \
  --dataset-path a5_stack/terminal-bench-core/tasks \
  --task-id hello-world --task-id count-dataset-tokens \
  --task-id grid-pattern-transform --task-id organization-json-generator \
  --task-id fix-permissions \
  --agent-import-path a5_stack.harness_stub:MadsStackAgent \
  --agent-kwarg base_url=http://localhost:8081/v1 \
  --agent-kwarg model=<a4 模型名> \
  --no-rebuild --no-cleanup --n-concurrent 1 \
  --output-path a5_stack/runs
```
无需 LLM 的夹具健康检查:
```bash
a5_stack/.venv/bin/tbench run --dataset-path a5_stack/terminal-bench-core/tasks \
  --task-id hello-world --agent-name oracle --no-rebuild --no-cleanup --output-path a5_stack/runs
```
使用 `--no-cleanup` 保留预构建镜像 (`--cleanup` 以 `compose down --rmi all` 删除镜像)。

## 首次全栈运行 (2026-11-16 实测, 11.2 分钟)

5 个精选任务, 真实 Docker 沙箱, A2 运行时驱动 Agent,
1.5 B 引擎作为大脑, `n-concurrent 1`:

| 任务 | 结果 |
|---|---|
| `hello-world` | **resolved** — 1.5 B 模型在沙箱中端到端完成任务 |
| `count-dataset-tokens` | unresolved (测试超时) |
| `grid-pattern-transform` | unresolved (测试超时) |
| `fix-permissions` | unresolved (测试超时) |
| `organization-json-generator` | unresolved (测试超时) |

**准确率 1/5 (20%)。** 诚实解读: 这是 *1.5 B* 模型 —
地板, 不是栈的天花板。hello-world 证明了全路径畅通 (模型 → Mads-Loop 重试/上下文循环 → tmux 终端 → 真实 shell → 任务测试 → 判定)。其余四个需要能遵循多步 shell 指令的模型; 通过 `--agent-kwarg` 将大脑换为 35 B MoE (或 27 B) 是下一个实验 — 夹具、镜像和 Agent 全部与模型无关。运行输出: `runs/2026-11-16__17-23-22/`
(`results.json` + 每任务目录 + `run.log`)。

## 全栈阶段必须关闭的缺口
1. **A4 引擎在 :8081 上运行**, 使用真实模型名 — 设置
   `--agent-kwarg model=...` (环境变量 `MADS_MODEL` 也有效; 默认
   `qwen3.8-27b-splash`)。
2. **文件工具**: 存根仅暴露 `bash` (文件工具会触及主机文件系统, 而非容器)。扩展 `TerminalToolExecutor` 以通过会话路由 read/write/edit/glob/grep — 仅 bash 已解决文件任务。
3. **内存预算**: 7.75 GB VM; 保持 `--n-concurrent 1` 并停留在
   精选小任务上, 除非提高 Docker Desktop RAM (≤16 GB)。
4. 如果你 ever 执行 `pip install --force-reinstall terminal-bench`, Python
   3.14 兼容补丁在下次 `tbench` 调用时自动重新应用 (见下文)。

## Python 3.14 陷阱 (已修复, 已文档化)
terminal-bench 0.2.18 在
`terminal_bench/cli/tb/{runs,datasets}.py` 中定义了名为 `list` 的 CLI 命令函数。Python 3.14 (PEP 649) 在模块全局中惰性求值
注解, 所以同一模块中其他命令的 `list[str] | None` 失败 typer 的解析: 每次 `tb` 调用以
`TypeError: 'function' object is not subscriptable` 死亡。`a5_stack/patch_terminal_bench.py`
重命名了阴影函数 (子命令名称通过显式
`name="list"` 保留), 并由 `.venv/bin/tbench` shim 幂等应用。
(没有更新的 PyPI 版本修复它; 0.2.18 是当前版本)。

## 文件
- `harness_stub.py` — `MadsStackAgent` + `TerminalToolExecutor` + `smoke()`
  (`python harness_stub.py smoke [--task X] [--rebuild]`)。
- `build_curated.sh` — 重建 5 个精选任务镜像。
- `patch_terminal_bench.py` — 幂等 3.14 兼容补丁 (由 shim 调用)。
- `terminal-bench-core/` — v0.1.1 数据集分支的稀疏克隆
  (tasks/, git-忽略; 重新获取: `git clone --filter=blob:none --sparse
  -b v0.1.1 https://github.com/laude-institute/terminal-bench-core` +
  `git sparse-checkout set tasks`)。
- `.venv/` — Python 3.14 环境; `bin/tb`, `bin/terminal-bench`, `bin/tbench` (shim)。
