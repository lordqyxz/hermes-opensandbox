## Context

两个问题需要修复：

1. **注入点数量统计错误**: CLAUDE.md 声称 5 个注入点，实际 6 个（`terminal_tool.py` 有 3 个，不是 2 个）。需合并 `patch_terminal_tool` 中的 #1（插入 elif 分支）和 #2（替换错误消息）为单次替换，降到 5 个。
2. **镜像硬编码**: `_OPEN_BRANCH` 模板中 image/domain/api_key 默认值直接硬编码，与 `config.py` 中的 `DEFAULT_*` 常量重复定义。应通过 `SandboxConfig.from_env()` 统一管理默认值。

## 变更列表

### 1. `cli.py` — 合并 injection point #1 + #2，并消除硬编码默认值

**合并策略**: 将 `_OPEN_BRANCH` 插入 + 错误消息替换合并为一次 `else:` 块整体替换。匹配目标改为整个 `else: raise ValueError(...)` 块。

**去硬编码策略**: `_OPEN_BRANCH` 中不再 `os.getenv("OPENSANDBOX_IMAGE", "nikolaik/...")`，改用 `SandboxConfig.from_env(image=cc.get(...), ...)` 获取配置，默认值由 `config.py` 统一管理。

### 2. `CLAUDE.md` — 更新注入点描述

terminal_tool.py: 3 → 2（合并后），总注入点: 6 → 5。

## 受影响文件

| 文件 | 变更 |
|------|------|
| `src/hermes_opensandbox/cli.py` | 合并 marker、更新 `_OPEN_BRANCH` 模板 |
| `CLAUDE.md` | 注入点统计对齐实际 |

## 验证

1. `python -m hermes_opensandbox.cli` （需要存在 `~/.hermes/hermes-agent/` 目录才能完整运行，但导入和执行路径不会报错）
2. `python -c "import hermes_opensandbox; print(hermes_opensandbox.__all__)"` — 确认包可正常导入
3. 检查 `SandboxConfig.from_env()` 返回的默认值与模板中原硬编码值一致
