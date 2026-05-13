# Plan: Fix Hermes execute_code Tool Broken by hermes-opensandbox

## Context

安装 `hermes-opensandbox` 后，`execute_code` 工具可能损坏。根因在 `cli.py` 中注入 `terminal_tool.py` 的代码片段有两处关键错误。

---

## 发现的问题

### Bug 1 (关键): `_CHECK_MARKER` 与实际代码不匹配 → opensandbox 需求检查静默未注入

**位置**: `cli.py` 第 49-51 行，`_CHECK_MARKER` 字符串

Marker:
```python
elif env_type == "vercel_sandbox":
            return check_vercel_sandbox()
```

`terminal_tool.py` (第 2235-2236 行) 实际代码:
```python
elif env_type == "vercel_sandbox":
            return _check_vercel_sandbox_requirements(config)
```

函数名不同 → 字符串匹配失败 → opensandbox 需求检查**静默未注入**。当 `check_environment_requirements()` 被调用且 env_type 为 "opensandbox" 时,落入 else 分支,返回 "Unknown TERMINAL_ENV" 错误。

### Bug 2 (关键): opensandbox elif 分支通过 `cc.get()` 获取配置,但 `cc` 来自不包含这些 key 的 `container_config`

**位置**: `cli.py` 第 158-175 行,`_OPEN_BRANCH` 字符串

```python
_sandbox_cfg = _SandboxConfig.from_env(
    image=cc.get("opensandbox_image"),
    domain=cc.get("opensandbox_domain"),
    api_key=cc.get("opensandbox_api_key"),
)
```

`cc` 定义为 `cc = container_config or {}`。`container_config` 只包含 `container_cpu/memory/disk` 等资源 key,**不包含** opensandbox 配置。因此 overrides 全为 `None`,配置回退到 `from_env()` 的 env var fallback。

**注意**: 如果用户已设 `OPENSANDBOX_IMAGE/DOMAIN/API_KEY` 环境变量(按 CLAUDE.md 文档要求),此 bug 不产生影响。但如果用户只通过 `hermes config set terminal.opensandbox_*` 配置(写入 config.yaml 但未同步到 env var,因 opensandbox key 不在 hermes 的 `_config_to_env_sync` 映射中),则会使用错误的默认值(`localhost:8080`),导致 sandbox 创建失败。

---

## 修复方案

### 修复 1: 更正 `_CHECK_MARKER` 匹配字符串

**文件**: `src/hermes_opensandbox/cli.py`

```python
# 旧:
_CHECK_MARKER = '''\
        elif env_type == "vercel_sandbox":
            return check_vercel_sandbox()'''

# 新:
_CHECK_MARKER = '''\
        elif env_type == "vercel_sandbox":
            return _check_vercel_sandbox_requirements(config)'''
```

同步更新 `_CHECK_REPLACEMENT`:
```python
_CHECK_REPLACEMENT = '''\
        elif env_type == "opensandbox":
            import importlib.util
            return importlib.util.find_spec("opensandbox") is not None
        elif env_type == "vercel_sandbox":
            return _check_vercel_sandbox_requirements(config)'''
```

### 修复 2: 去掉 opensandbox elif 分支中的冗余覆盖 → 直接调用 `from_env()`

**文件**: `src/hermes_opensandbox/cli.py`

`_OPEN_BRANCH` 中:
```python
# 旧:
_sandbox_cfg = _SandboxConfig.from_env(
    image=cc.get("opensandbox_image"),
    domain=cc.get("opensandbox_domain"),
    api_key=cc.get("opensandbox_api_key"),
)

# 新: from_env() 原生就读取 OPENSANDBOX_* 环境变量,无需冗余覆盖
_sandbox_cfg = _SandboxConfig.from_env()
```

### 修复 3: 为 `_CHECK_MARKER` 替换添加失败日志

**文件**: `src/hermes_opensandbox/cli.py`

```python
if _CHECK_MARKER in content:
    ...
else:
    logger.warning("Cannot find requirement-check insertion point in terminal_tool.py")
```

---

## 涉及文件

| 文件 | 操作 |
|------|------|
| `src/hermes_opensandbox/cli.py` | 修改 `_CHECK_MARKER`、`_CHECK_REPLACEMENT`、`_OPEN_BRANCH`、`patch_terminal_tool()` |

---

## 验证步骤

1. 从备份恢复 `terminal_tool.py`: `cp ~/.hermes/hermes-agent/tools/terminal_tool.py.bak ~/.hermes/hermes-agent/tools/terminal_tool.py`
2. 运行 `python -m hermes_opensandbox.cli` 或 `hermes-opensandbox-setup`
3. 确认三处 opensandbox 注入点都存在:
   ```bash
   grep -n "opensandbox" ~/.hermes/hermes-agent/tools/terminal_tool.py
   # 应出现: require check 区 + elif branch + error message
   ```
4. 设置 env 测试 execute_code:
   ```bash
   TERMINAL_ENV=opensandbox python -c "
   from tools.code_execution_tool import check_sandbox_requirements
   print('requirements OK:', check_sandbox_requirements())
   "
   ```
5. `ruff check src/` 确保无 lint 错误
