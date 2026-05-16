## v0.3.0 (2026-05-16)

- 新增 PVC (PersistentVolumeClaim) 挂载支持，可挂载 JuiceFS 等 k8s 存储卷
- 新增 OSSFS (阿里云 OSS) 挂载支持
- 新增 `subPath` 和 `readOnly` 字段支持，适用于所有后端 (host/pvc/ossfs)
- 新增 `OPENSANDBOX_VOLUMES` 环境变量，JSON 数组格式配置复杂挂载
- 移除 `DEFAULT_MOUNTS` 本地 hostPath 默认挂载（`$HOME`、`/tmp`、`/var/folders`）
- 修复注入机制 bug：sentinel 检测导致模板参数更新不生效
  - sentinel 改为版本号标记格式：`# --- hermes-opensandbox backend v0.3.0 (auto-patched) ---`
  - setup 时对比已注入版本与当前包版本，版本不同自动替换注入块
  - 兼容旧版无版本号 sentinel，自动升级为新格式
- `_backup_and_write()` 增加 `PermissionError` 容错处理

## v0.2.1 (2026-05-16)

- 新增 YAML 配置文件支持：`~/.hermes/opensandbox.yaml`（与 Hermes `config.yaml` 同级）
- 新增 `OPENSANDBOX_CONFIG` 环境变量，可指定自定义配置文件路径
- 新增 `SandboxConfig.from_file()` 类方法，从 YAML 文件加载配置
- 配置优先级链：`overrides` > `OPENSANDBOX_*` 环境变量 > 配置文件 > 代码默认值
- 无配置文件时行为不变，完全向后兼容
- 新增 `pyyaml>=6.0` 依赖
- 修复 `__version__` 与 VERSION/pyproject.toml 不同步的问题

## v0.1.3 (2026-05-12)

- 沙箱改为 session 级持久化：每个 session 仅创建一个沙箱，session 退出才销毁
- 新增后台自动续期线程，每 15 分钟调用 OpenSandbox `renew` API 延长沙箱生命周期
- 降低默认资源配置：CPU 0.5→1.0、内存 5000→256MB、磁盘 51200→5000MB
- `create_opensandbox_module` 改为始终覆盖，确保部署最新 adapter 模板

## v0.1.2 (2026-05-12)

- 修复 `_OPEN_BRANCH` 中 `timeout` 被 Hermes 调用参数覆盖导致沙箱过早关闭的 bug
- 修复 `mounts` 未传递给 adapter 导致宿主机路径挂载失效、文件读取失败的 bug
- 新增 `OPENSANDBOX_TIMEOUT` 环境变量支持

## v0.1.1 (2026-05-12)

- Sandbox 生命周期默认值从 300s 提升至 86400s (24h)，解决自动关闭过快问题
- HTTP `request_timeout` 与 sandbox 生命周期 `timeout` 分离，前者固定 60s

## 架构决策记录 (ADR)

### ADR-1: 2026-05-12 — hermes-open-sandbox 重构

- **项目类型**: Python Library + CLI 混合
- **架构模式**: Clean Architecture 简化版（SDK 封装与 Hermes 适配彻底分离）
- **核心实体/组件**:
  - `SandboxConfig` — 配置值对象 (config.py)，包含 image、domain、api_key、cwd、timeout、cpu、memory、disk、task_id、mounts、debug
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

### ADR-6: 2026-05-12 — 宿主机路径挂载

- 通过 SDK `volumes` 参数挂载宿主机路径到沙箱，`mountPath` 与 `host_path` 一致保证路径透明
- 默认挂载 `$HOME`、`/tmp`、`/var/folders`（macOS）
- 可通过 `OPENSANDBOX_MOUNTS` 环境变量自定义（格式: `host:mount,host:mount`）
- OpenSandbox server 的 `allowed_host_paths` 需包含所有挂载路径前缀

### ADR-7: 2026-05-12 — Debug 模式

- `SandboxConfig.debug` 控制沙箱是否在会话结束时自动销毁
- 通过 `OPENSANDBOX_DEBUG=1`（或 `true`/`yes`）启用
- `kill()` 和 `close()` 在 debug 模式下记录日志并跳过实际操作
- 所有清理路径统一响应：`cleanup()`、context manager `__exit__`、手动 `kill()`/`close()`、`_cancel()` 回调
