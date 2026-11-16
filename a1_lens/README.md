# a1_lens — Mads-Lens: Claude Code 会话的可信 Web UI (CS2680 A1)

只读可视化工具，读取 Claude Code 的本地会话日志
(`~/.claude/projects/**/*.jsonl`)。它渲染真实事件流——
工具调用（含输入/返回）、子 Agent 线程、报错、以及每次调用的
token 与费用——以可浏览、实时滚动的 Web 应用呈现。无需框架，无需
CDN，无需写入：纯 Python 标准库服务器 + 单页静态 SPA。

## 架构

```
~/.claude/projects/<目录>/<会话>.jsonl  (+ <sid>/subagents/*.jsonl)
        │  (只读，mtime 驱动重解析)
        ▼
lens_parser.py     JSONL → 会话图：线程 → 步骤，工具-结果
                   配对，错误分类，用量归因，
                   子 Agent 嵌套，token/费用聚合
        │
        ▼
lens_cost.py       模型名标准化 (claude-* / lmstudio/* /
                   antigravity/* / <合成>) + 价格表 → 5 类费用
                   组件 (输入 / 输出 / 缓存命中 / 缓存创建 / 思考); 未知模型 → 0 并设置
                   `price_unknown` 标志，绝不伪造数字
        │
        ▼
server.py          标准库 ThreadingHTTPServer:
                   GET /api/sessions            列表 (最新优先，摘要
                                                字段 + 子 Agent 计数)
                   GET /api/session/<id>        完整解析图
                   GET /api/session/<id>/tail?after=N   增量步骤
                   GET /                        static/ (index/app/style)
        │
        ▼
static/            单页客户端：会话列表 → 步骤时间线
                   (颜色编码：工具 / 报错 / 思考 / 元数据),
                   每步 token + 费用标签，报错原因，子 Agent
                   树，实时滚动
```

保持可信的设计原则：

- **绝不伪造**: 用量为零的步骤费用为零；未知模型显示"未定价"（徽章 + 提示框），本地模型显示 "$0 (本地)"。UI 从不编造美元数字。
- **错误类型化**: `is_error` 工具结果和助手报错文本由
  `detect_tool_error` / `detect_assist_error` 检测，截断为 160 字符原因，以
  独立的错误样式渲染——第三方 API 调用失败在会话加载时立即可见。
- **只读 + 增量**: 服务器仅读取；实时滚动通过
  `after=<seq>` 轮询新行实现，运行中的会话无需重解析即可更新，
  已关闭的会话仅解析一次 (mtime 驱动)。

## 运行

```sh
cd a1_lens
python3 server.py --port 8787 --root ~/.claude/projects   # Python 3.9+ 可用
# → http://localhost:8787
```

无需 pip 安装。已在本机会话上验证：API 返回真实的 `~/.claude/projects`
目录树 (会话列表含 token/费用/报错/子 Agent 摘要字段；每个会话的步骤图；
增量滚动)。

## 文件

| 文件 | 作用 |
|---|---|
| `lens_parser.py` | 解析器: `discover_sessions`, `session_graph`, 按 JSONL 记录类型构建步骤, 工具-结果配对, 费用归因, 子 Agent 导入 |
| `lens_cost.py` | `PRICES` 表 (Claude Opus/Sonnet/Haiku 4.x, 网关, 本地), `normalize_model`, `price_for`, `cost_for_usage` (5 类组件) |
| `server.py` | 标准库 HTTP 服务器 + 三条 API 路由 + 静态文件服务 |
| `static/index.html`, `app.js`, `style.css` | 前端 UI |

## 它展示什么 (课程要求的四项内容)

1. **实时工具调用轨迹** — 每个助手步骤的工具调用 (名称 + 美化输入) 和配对结果 (截断预览，展开后全文)；时间戳与每步 token。
2. **子 Agent 树** — `Task` 生成的子 Agent 作为嵌套线程出现在生成步骤下方；会话列表显示子 Agent 计数。
3. **错误定位** — 报错在失败步骤处内联渲染，含检测到的原因；会话列表携带报错计数。
4. **每次调用的 token 与费用** — 每步和每个会话的五类费用组件，未定价/本地模型标记而非猜测。
