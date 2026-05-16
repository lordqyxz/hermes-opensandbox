# 方案 3：NodePort 替代 Ingress + 更新 hosts

## Context

本地 K8s 访问 `http://opensandbox.local/` 经过 Ingress 代理，比集群内部 DNS `svc.cluster.local` 慢。方案 3 通过将 Service 改为 NodePort 类型绕开 Ingress。

## 步骤

### 1. 检查当前 Service 状态

```bash
kubectl get svc -n opensandbox-system opensandbox-server -o yaml
```

确认当前 type 和 port 配置。

### 2. Patch Service 为 NodePort

```bash
kubectl patch svc opensandbox-server -n opensandbox-system \
  -p '{"spec":{"type":"NodePort","ports":[{"port":8080,"nodePort":30080,"targetPort":8080,"protocol":"TCP"}]}}'
```

### 3. 更新 /etc/hosts

确保 `opensandbox.local` 指向 localhost：
```
127.0.0.1 opensandbox.local
```

### 4. 更新 Hermes 配置

将 domain 改为直连 NodePort：
```bash
hermes config set terminal.opensandbox_domain localhost:30080
```

### 5. 验证

```bash
curl http://localhost:30080/v1/health
```

或用 Python SDK 测试连通性和性能。

## 验证方式

- 检查 Service type 已变为 NodePort
- 测试 curl 延迟对比
- 确认 Hermes 命令能正常执行
