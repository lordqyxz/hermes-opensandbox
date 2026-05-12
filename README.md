# hermes-open-sandbox

OpenSandbox execution backend for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Run Hermes terminal and file tools inside secure, isolated [OpenSandbox](https://github.com/alibaba/OpenSandbox) containers instead of your local machine.

## Quick Start

```bash
# 1. Install the package
pip install hermes-open-sandbox opensandbox

# 2. Patch Hermes to register the backend
hermes-opensandbox-setup

# 3. Configure
hermes config set terminal.backend opensandbox
export OPENSANDBOX_DOMAIN=your-server:8080
export OPENSANDBOX_API_KEY=sk-xxx

# 4. Restart Hermes and use it
hermes
```

## How It Works

```
Hermes Agent
  └─ tools/terminal_tool.py  ──→  _create_environment("opensandbox")
                                      │
                                      ▼
                              tools/environments/opensandbox.py
                                      │
                                      ▼
                              hermes_opensandbox.environment
                              (OpenSandboxEnvironment)
                                      │
                                      ▼
                              opensandbox.SandboxSync
                              (OpenSandbox Python SDK)
                                      │
                                      ▼
                              ┌─────────────────────┐
                              │  OpenSandbox Server  │
                              │  (Docker containers)  │
                              └─────────────────────┘
```

## Supported Images

Any Docker image that includes `bash`:

- `python:3.11`
- `nikolaik/python-nodejs:python3.11-nodejs20` (default, includes Node.js)
- `ubuntu:22.04`
- Custom images from your registry

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENSANDBOX_DOMAIN` | `localhost:8080` | OpenSandbox server address |
| `OPENSANDBOX_API_KEY` | (none) | Authentication key |
| `OPENSANDBOX_IMAGE` | `nikolaik/python-nodejs:python3.11-nodejs20` | Container image |

## Manual Uninstall

```bash
# Remove the wrapper
rm ~/.hermes/hermes-agent/tools/environments/opensandbox.py

# Restore backups
mv ~/.hermes/hermes-agent/tools/terminal_tool.py.bak ~/.hermes/hermes-agent/tools/terminal_tool.py
mv ~/.hermes/hermes-agent/agent/prompt_builder.py.bak ~/.hermes/hermes-agent/agent/prompt_builder.py
```

## License

MIT
