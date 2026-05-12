## 架构决策记录 (ADR)

<!-- /dev 每次架构选择结果追加到此 -->

### ADR-1: 2026-05-12 — hermes-opensandbox 重构

- **项目类型**: Python Library + CLI 混合
- **架构模式**: Clean Architecture 简化版（SDK 封装与 Hermes 适配彻底分离）
- **核心实体/组件**:
  - `SandboxConfig` — 配置值对象 (config.py)
  - `OpenSandboxSession` — 沙箱会话聚合根 (session.py)
  - `CLI Patcher` — Hermes 注入工具 (cli.py)
- **接口/契约**:
  - `OpenSandboxSession` 零 Hermes 依赖，可独立使用
  - Thin adapter（`tools/environments/opensandbox.py`）由 CLI 自动生成到 Hermes 安装目录
  - 5 个注入点：terminal_tool.py (2: elif分支+错误消息, check_requirements) + prompt_builder.py (2: frozenset, fallback描述) + opensandbox.py (1: thin adapter)

### ADR-2: 2026-05-12 — 错误分类体系

- 新增异常层级: `SandboxError` → `SandboxCreationError` → `SandboxImageError` / `SandboxNetworkError` / `SandboxAuthError`
- `create()` 中捕获 SDK 原生异常（`SandboxReadyTimeoutException`, `SandboxApiException`, `httpx.ConnectError`, `SandboxInternalException`）并映射为分类异常
- Thin adapter 中 catch `SandboxCreationError` 让子类异常直接传播至 Hermes，AI 可通过异常类名识别错误类别

### ADR-3: 2026-05-12 — Plugin 系统 vs Patching

- Hermes plugin 系统不支持替换 terminal 执行后端（provider 类型仅限 Memory/Context Engine）
- `pre_tool_call` 只能拦截不能替换执行逻辑；`register_tool` 只能新增工具
- **结论**: Patching 是 Hermes 架构限制下的最小侵入方案

### ADR-4: 2026-05-12 — 文件传输机制

- 文件传入沙箱通过 shell heredoc 完成（`BaseEnvironment._embed_stdin_heredoc()`）
- Thin adapter 设置 `_stdin_mode = "heredoc"`，命令字符串中已包含完整 heredoc
- SDK `sb.files.write_file()` 可作为大文件/二进制文件的备用通道

### ADR-5: 2026-05-12 — 配置解析链

- 镜像/domain/api_key 不从模板硬编码，统一通过 `SandboxConfig.from_env()` 解析
- 优先级: Hermes config (`cc.get`) → 环境变量 (`OPENSANDBOX_*`) → `config.py` 默认常量
- k8s 节点无法访问 Docker Hub，镜像需本地缓存且使用非 `:latest` tag（`imagePullPolicy: IfNotPresent`）

## 安装指南

### 前置条件

1. Python 3.10+, Hermes Agent 已安装
2. OpenSandbox 服务已部署（本机 k8s 或远程）
3. 用于执行的 Docker 镜像已在节点缓存

### 安装步骤

```bash
# 1. 安装包
pip install hermes-open-sandbox opensandbox

# 2. 注入 backend（幂等，可多次执行）
hermes-opensandbox-setup

# 3. 配置 Hermes
hermes config set terminal.backend opensandbox
hermes config set terminal.opensandbox_domain <your-server:port>
hermes config set terminal.opensandbox_image <your-image:tag>

# 4. 设置 API key
export OPENSANDBOX_API_KEY=<your-key>
# 持久化: echo 'export OPENSANDBOX_API_KEY=<your-key>' >> ~/.zshrc

# 5. 确保 toolsets 包含 terminal/file/code_execution
hermes config set platform_toolsets.cli hermes-cli,terminal,file,code_execution

# 6. 重启 Hermes
```

### 镜像注意事项

- k8s 节点使用 containerd，需确保镜像已在节点缓存
- 避免使用 `:latest` tag — k8s 会尝试从 Docker Hub 拉取（`imagePullPolicy: Always`）
- 使用具体版本 tag（如 `python:3.11-slim`, `code-interpreter-sandbox:v0.1.0`）
- 若需自定义镜像，确保包含 `bash` 且兼容 execd sidecar

### 验证

```bash
# 测试 SDK 连通性
python -c "
from opensandbox.config.connection_sync import ConnectionConfigSync
from opensandbox.sync.sandbox import SandboxSync
from datetime import timedelta
conn = ConnectionConfigSync(domain='opensandbox.local', api_key='localtest')
sb = SandboxSync.create(image='code-interpreter-sandbox:v0.1.0', timeout=timedelta(seconds=120), connection_config=conn)
r = sb.commands.run('python3 --version')
print(''.join(e.text for e in r.logs.stdout).strip())
sb.kill(); sb.close()
"

# 检查 patch 状态
grep -l "hermes-opensandbox" ~/.hermes/hermes-agent/tools/environments/opensandbox.py
grep "opensandbox" ~/.hermes/hermes-agent/tools/terminal_tool.py | wc -l
```

### 错误分类速查

| 异常类型 | 含义 | 检查项 |
|----------|------|--------|
| `SandboxImageError` | 镜像不可用或不兼容 | 镜像名、tag、节点缓存、bash 可用性 |
| `SandboxNetworkError` | API 端点不可达 | domain 配置、网络连通性、k8s ingress |
| `SandboxAuthError` | 认证失败 | API key、Hermes config、环境变量 |
| `SandboxCreationError` | 其他创建失败 | 综合检查日志 |
| `SandboxNotCreatedError` | 未调用 create() 就 execute() | 代码逻辑错误 |

## Skill 映射表

| 语言/框架 | 代码级 skill | 说明 |
|-----------|-------------|------|
| Python | python-code | Pythonic 编码风格、DDD/Clean Architecture 实现 |
