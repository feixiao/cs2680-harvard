# a3_opt — Mads-Opt: 端到端优化 + 技术复盘 (CS2680 A3)

优化 A2 运行时 (`a2_loop/madsloop`) 并报告。两个组件, 一个故事:

| 文件 | 作用 |
|---|---|
| `blog.md` | **交付物** — 技术复盘: 真实 E0 测量 (引擎 + 前缀缓存: 8.5× 成本 / 2.9× 延迟, 12/12), 确定性 6 点杠杆扫描 (E1–E5: 路由 31× 成本, 并发 9.1× 延迟, 全栈 112×/135×, 成功率不变), 发现, 以及单台 Mac 无法测量的内容。 |
| `experiments.py` | 测试夹具。`--sim` 运行确定性 `mads/` 扫描 (无需引擎, 字节一致); 无此标志时运行真实引擎消融 E1–E5 (需两个引擎同时运行)。 |
| `engines.sh` | 引擎集群控制: `engines.sh status|up|down` 管理 mlx-lm 1.5 B (:8082) 和 35 B (:8084) 服务器, 含课程的前缀缓存标志。 |

从完整状态运行全部复盘:

```sh
a2_loop/.venv/bin/python a3_opt/experiments.py --sim   # 模拟扫描, 秒级
a2_loop/.venv/bin/python a3_opt/experiments.py E1 E2 E5   # 真实消融, ~1 小时
```

真实消融的引擎前提 (experiments.py 通过 `engines_up` 检查): 1.5 B @8082 (`engines.sh start`), 35 B @8084 (`a4_serve/serve.sh` 或 `a3_opt/engines.sh start`), 27 B @1234 (LM Studio)。一次只运行一个引擎可保持测量清晰; 35 B @8084 服务器必须使用**补丁版** mlx-lm (a4_serve), 否则 N>1 解码会崩溃 (见 A4)。

`blog.md` 中的数字来自 2026-11-16 本机 (128 GB Apple Silicon, LM Studio 27 B + 两个 mlx-lm 服务器); 绝对费用使用公开列表价格, 因为本地引擎费用 $0。
