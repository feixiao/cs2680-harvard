# a4_serve — Mads-Serve: 可测量的开源 LLM 服务引擎 (CS2680 A4)

课程作业的目标是 **RTX-4500 集群上的 SGLang** — 本机无法触及。本目录是本地等效方案: 一个开源引擎
(**mlx-lm** 在 Apple Metal 上), 其三项服务旋钮 — 连续批处理、分块预填充、KV 缓存前缀复用 — 我们可以调节和测量。相同的概念, 相同的测量; 课程的集群只是以 venv 形式存在于本机。

## 组件

| 组件 | 作用 |
|---|---|
| `serve.sh` | 一键启动端口 **8081** 的引擎, 含文档化、可环境变量覆盖的标志集; 应用服务器补丁; `--stop` 终止。 |
| `bench_synth.py` | OpenAI 兼容合成负载客户端 (标准库)。套件 **A** = 16 条提示共享 ~4k-token 前缀 + ~100-token 尾部; 套件 **B** = 随机长度 100–4k, 输出 50–200。运行 N = 1, 4, 8 (串行/并发); 记录每请求 TTFT、TPOT、e2e、token、`cached_tokens`; 打印 `METRIC key=value` 行。 |
| `metrics.py` | 轮询引擎 `/metrics` (由补丁添加) 并汇总: 批处理大小分布、队列深度、KV 字节/峰值、缓存命中/未命中 + 跳过 token、预填充 vs 解码 token 率。 |
| `kv_cache.py` | 课程更细粒度的前缀缓存, 生产形态: 内容寻址 **16-token 块** 带链式 CRC32 哈希, LRU + 引用计数驱逐, `match_prefix` / `register` / `stats`。 |
| `patches/mlx-lm-metrics.diff` | 上游贡献: 对 `mlx_lm/server.py` 的 409 行补丁 (由 `serve.sh` 自动重新应用;  survives venv 重装)。 |
| `run_baseline.sh` | 运行完整矩阵: 复用 {on,off} × 套件 {A,B} × N {1,4,8}, 每次用 `metrics.py` 采样; 全部写入 `results/`。 |
| `results/` | 实测基线 (`baseline.md` + 机器输出)。 |

## 服务器补丁 (三项贡献)

1. **`/metrics` 端点** (Prometheus 文本格式): 按类型分组的提示缓存条目/字节, 缓存命中/未命中/跳过 token 计数器, 在飞和排队请求仪表, 提示/解码 token 和时间计数器, 活跃 KV 和峰值内存。
2. **分页前缀缓存镜像**: 每个请求的 token 前缀送入
   `kv_cache.PagedKVCache` (Main 模块), 其块级统计暴露为 `mlx_lm_paged_kv_*` — 课程的分页设计在引擎内置 trie 缓存旁实时运行。
3. **一个真实的并发 bug 修复** (根因 + 纵深防御):
   `_generate` 的批处理结果分发使用 `del batch_results[uid]`, 但 `uid` 来自缓存保存循环的**陈旧值**, 所以两个并发请求可能崩溃整个生成线程 (`KeyError: <uid>`; 每个后续请求得到 `404 generation thread died`)。在根处修复 (`del batch_results[r.uid]`), **且**两个分发循环现在使用 `batch_results.get(r.uid)` 加日志跳过, 因此任何分发路径都无法杀死线程。没有它, 基线中 N=4/8 的点在任何原版 mlx-lm 服务器上都无法运行。

## 引擎及其旋钮

模型: `mlx-community/Qwen2.5-1.5B-Instruct-4bit` (从磁盘复用,
`/Users/Shared/LLM_Models` — 840 MB, 秒级加载)。选择 1.5B 而非课程建议的 8B: HF 下载速度约 3.4 MB/s (8B Q8_0 需 ~45 分钟), 且 1.5B 足够快, 所有 12 个基准点可在数分钟内完成, 包括解码绑定的并发点。用 `MODEL=...` 替换。
**GPU 证明**: 每个响应中的 `system_fingerprint` 是
`...Mach-O-applegpu_g16s` (`applegpu` = Apple Metal GPU; `/metrics` 中的 `mx.get_peak_memory` 跟踪 MLX 设备分配)。

`serve.sh` 标志 (可环境变量覆盖; 每项在脚本中文档化):

| 环境变量 | 默认值 | mlx-lm 标志 | 含义 |
|---|---|---|---|
| `REUSE` | `on` | `--prompt-cache-size 64` / `0` | KV 前缀复用 A/B。引擎**无布尔开关** — 前缀缓存默认开启; size 0 在插入时驱逐每条目, 所以查询永远无法命中。 |
| `PROMPT_CACHE_SIZE` | 64 / 0 | `--prompt-cache-size` | 最大不同缓存 KV 条目数 (套件 A 保持 16 条前缀)。 |
| `PROMPT_CACHE_BYTES` | (无界) | `--prompt-cache-bytes` | 缓存 KV 的字节预算。 |
| `DECODE_CONCURRENCY` | 32 | `--decode-concurrency` | 最大并发解码数 (连续批处理宽度)。 |
| `PROMPT_CONCURRENCY` | 8 | `--prompt-concurrency` | 并行预填充的提示数。 |
| `PREFILL_STEP_SIZE` | 2048 | `--prefill-step-size` | 分块预填充块大小 (每次预填充的 token 数)。 |
| `KV_BITS` / `KV_GROUP_SIZE` | 全精度 / 64 | `--kv-bits --kv-group-size` | KV 量化 (1.5B 无需量化; 保持关闭)。 |
| `MAX_TOKENS`, `TEMP` | 512, 0.0 | `--max-tokens --temp` | 采样默认值 (基准按请求覆盖)。 |
| `WARMUP` | 1 | — | 丢弃请求, 使 Metal 内核在测量前编译。 |
| `HOST`, `PORT` | 127.0.0.1, 8081 | — | 绑定地址 (LM Studio 占用 1234; 从不触碰)。 |

## 运行

```sh
cd a4_serve
./serve.sh                  # 8081 上引擎 (复用 on); ./serve.sh --stop
.venv/bin/python bench_synth.py --suite A --reuse on --N 1,4,8
.venv/bin/python bench_synth.py --suite B --reuse off --N 4
.venv/bin/python metrics.py --duration 60 --out results/m.json --label demo
./run_baseline.sh           # 完整矩阵 -> results/
```

## 结果 (2026-11-16 本机实测)

见 `results/baseline.md` 完整表格; 关键数字:

- **KV 前缀复用是在共享前缀负载上 9–35× 的 TTFT 收益**
  (套件 A, 16 请求共享 4.06k 前缀): TTFT p50 关闭 → 开启 =
  1570 → 172 ms @ N=1 (9.1×), 3173 → 266 ms @ N=4 (11.9×),
  10777 → 312 ms @ N=8 (34.5×)。关闭的 N=8 TTFT 是纯预填充排队。
- **在随机负载上, 复用带来 ~5% 增益** (套件 B, N=1: 885 vs 834 ms —
  仅聊天模板头部匹配) — 收益集中在共享前缀, 即 Agent 模式。
- **解码是计算绑定的, 在 N≈4 停止扩展**: 总生成量
  48 → 90 → 116 tok/s (N = 1 → 4 → 8, 套件 A); 每 token TPOT
  17.8 → 37.8 → 60.2 ms。
- **内存是复用预算**: 16 × 4k-token 条目 ≈ 5.7 GB 提示
  缓存 (进程峰值 18 GB) 与关闭复用时的 3.8 GB 对比。

## 设计决策 / 注意事项

- **mlx-lm 而非 llama.cpp**: brew 安装 llama.cpp 停滞 45+ 分钟无可用二进制; mlx-lm 的 venv 秒级安装, 其 `LRUPromptCache` (trie + LRU + 字节预算) 正是课程的前缀复用机制 — *且* 它报告 `usage.prompt_tokens_details.cached_tokens` 每条请求, 这是最清晰的客户端侧复用证据。
- **关闭复用通过 size 0**: 插入时驱逐; 已验证每条请求 `cached_tokens=0` 且关闭分支所有引擎未命中。
- `paged_kv_*` 指标是*镜像* (仅 token id) — 它们报告课程分块设计*本会*跳过的内容; 不改变引擎行为。TTFT 结论使用引擎自己的缓存 (`cached_tokens`)。
- mlx 服务器无上下文大小标志; 上下文由模型配置 (32768) 和 RAM 限制。
- 确定性: 基准尾部已播种; `temperature` 每套件固定; 预期解码时序有小幅运行间漂移 (操作系统调度, 16 核 Mac 上的其他租户 — LM Studio 与本箱并发运行)。
