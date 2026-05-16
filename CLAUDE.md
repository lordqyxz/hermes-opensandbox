## 架构决策记录 (ADR)

所有架构决策记录在 [CHANGELOG.md](CHANGELOG.md)，每次架构选择结果追加到该文件。

## 版本管理

- 版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)：`MAJOR.MINOR.PATCH`
- 版本存储在两处，发布时需同步更新：
  - `VERSION` — 纯文本文件，CI/CD 和脚本读取
  - `pyproject.toml` — `project.version` 字段
- 发布流程：
  1. 更新 `VERSION` 和 `pyproject.toml` 中的版本号，修复bug改最后一位，更改功能改中间位置，架构重构改第一位。
  2. 更新 `CHANGELOG.md`，在顶部追加 `## v<version> (YYYY-MM-DD)` 版本条目
  3. 打 tag：`git tag -a v<version> -m "v<version>"`
  4. 推送：`git push && git push --tags`（CI 在 tag push 时自动发布到 PyPI）

## 开发信息

- 类型注解尽量不用 Any

```bash
# 安装开发依赖
pip install -e ".[dev]"

# Lint & 格式化
ruff check src/          # 代码检查
ruff format --check src/ # 格式检查

# 类型检查
pyright src/

# 构建
python -m build
```

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
hermes-open-sandbox-setup

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
grep -l "hermes-open-sandbox" ~/.hermes/hermes-agent/tools/environments/opensandbox.py
grep "opensandbox" ~/.hermes/hermes-agent/tools/terminal_tool.py | wc -l
```

### 错误分类速查

| 异常类型                     | 含义                       | 检查项                         |
| ------------------------ | ------------------------ | --------------------------- |
| `SandboxImageError`      | 镜像不可用或不兼容                | 镜像名、tag、节点缓存、bash 可用性       |
| `SandboxNetworkError`    | API 端点不可达                | domain 配置、网络连通性、k8s ingress |
| `SandboxAuthError`       | 认证失败                     | API key、Hermes config、环境变量  |
| `SandboxCreationError`   | 其他创建失败                   | 综合检查日志                      |
| `SandboxNotCreatedError` | 未调用 create() 就 execute() | 代码逻辑错误                      |

## Skill 映射表

| 语言/框架  | 代码级 skill   | 说明                                      |
| ------ | ----------- | --------------------------------------- |
| Python | python-code | Pythonic 编码风格、DDD/Clean Architecture 实现 |

## 注入机制注意事项

- 注入使用字符串标记匹配 Hermes Agent 源码，Hermes 函数重命名会导致标记失效
- `_CHECK_PATTERN` 使用正则 `return\s+\w+\(config\)` 匹配，对函数名重命名有抗性
- 每个注入点独立检测幂等（sentinel / find\_spec），避免部分注入残留被跳过
- 标记匹配失败必须记录 error/warning，不能静默跳过

## 配置流转路径

- `hermes config set terminal.<key>` → `~/.hermes/config.yaml` → `_config_to_env_sync` 映射 → 环境变量
- `terminal_tool.py` 的 `_get_env_config()` 只读环境变量，不读 config.yaml
- `opensandbox_*` 配置项不在 hermes 的 `_config_to_env_sync` 映射中，用户必须设置 `OPENSANDBOX_*` 环境变量
- `_create_environment()` 中 `cc = container_config or {}`，仅含 `container_cpu/memory/disk` 等资源 key，不含 opensandbox 配置

## 沙箱持久化模型

- 每个 Hermes session 创建一个沙箱，session 内所有命令共享同一沙箱
- `_cancel()` 为 no-op，不 kill 沙箱；被意外 kill 后 `_ensure_sandbox()` 自动重建
- `cleanup()` 在 session 退出时调用 `kill()` + `close()` 销毁沙箱
- 配置文件中的 `cpu/memory/disk` 通过 `_OPEN_BRANCH` 从 `_sandbox_cfg` 取值，确保 `OPENSANDBOX_*` 环境变量能覆盖 Hermes 的 `container_*` 默认值

## 自动续期机制

- adapter 启动 daemon 线程每 `_RENEW_INTERVAL`（900s）调用 `OpenSandboxSession.renew()`
- `renew()` 内部调用 SDK `sb.renew(timedelta(seconds=config.timeout))`，将过期时间从当前时刻后延
- session 退出时 `_stop_renew.set()` 停止续期线程
- 续期失败静默忽略（debug 日志记录）

## 资源默认值

| 参数   | 值            | 环境变量                  |
| ---- | ------------ | --------------------- |
| CPU  | 0.5          | `OPENSANDBOX_CPU`     |
| 内存   | 512Mi        | `OPENSANDBOX_MEMORY`  |
| 磁盘   | 5000Mi       | `OPENSANDBOX_DISK`    |
| 超时   | 86400s (24h) | `OPENSANDBOX_TIMEOUT` |
| 续期间隔 | 900s         | 硬编码 `_RENEW_INTERVAL` |

## Debug 模式注意事项

- `OPENSANDBOX_DEBUG=1` 时 `kill()` 和 `close()` 跳过实际操作，沙箱保留运行
- 多次 `hermes -z` 调用会在 k8s 中累积 Running 沙箱，单节点集群可能耗尽资源
- 测试完成后需手动清理：`curl -X DELETE /sandboxes/{id}` 或 `kubectl delete pod -n opensandbox`

