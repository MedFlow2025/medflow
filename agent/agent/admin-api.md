# MedFlow Admin API

Admin API 用于跨用户查看和维护当前 worker 节点上的推理服务实例、Benchmark 任务和功能测试任务。

## 启用接口

`agent/config/agent.yaml` 中需要启用管理员接口：

```yaml
ADMIN:
  ENABLED: true
```

启动 `inference_agent.py` 前设置访问令牌：

```bash
export MEDFLOW_ADMIN_TOKEN='admin'
```

以下示例统一使用：

```bash
export ADMIN_URL='http://127.0.0.1:9999'
export ADMIN_TOKEN='admin'
```

命令使用 `jq` 格式化 JSON 响应，请先确认已经安装：

```bash
jq --version
```

所有请求都需要 Bearer Token：

```bash
-H "Authorization: Bearer ${ADMIN_TOKEN}"
```

## 操作规则

- `GET .../preview`：重新检查目标并返回计划执行的操作，不停止任务。
- `POST .../apply`：再次检查目标的最新状态，然后执行操作并记录审计。
- `apply` 不会直接复用旧的 preview 结果，避免资源状态变化后误操作。
- 停止推理实例前，如果仍有关联的 Benchmark 或功能测试在运行，接口会拒绝停止。
- `starting`、`running` 和 `degraded` 实例会保留端口租约。
- `stopped` 和 `failed` 实例只有在确认无所属或不明残留后才释放端口。

## 清理异常资源

预览清理操作：

```bash
curl --fail-with-body \
  "${ADMIN_URL}/admin/cleanup/preview" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

确认执行：

```bash
curl --fail-with-body -X POST \
  "${ADMIN_URL}/admin/cleanup/apply" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

清理结果中的端口归属字段：

- `owned_ports`：仍由该实例监听，可由 cleanup 安全清理。
- `reused_ports`：已被其他实例复用，不会终止对应进程。
- `unverified_ports`：无法确认进程归属，保持 `degraded` 并阻止自动清理。
- `closed_ports`：当前未监听，可以释放租约。

## 推理服务实例

查看最近 20 个实例：

```bash
curl --fail-with-body \
  "${ADMIN_URL}/admin/services?limit=20" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

只查看运行中的实例：

```bash
curl --fail-with-body \
  "${ADMIN_URL}/admin/services?status=running&limit=20" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

预览停止操作：

```bash
INSTANCE_ID='<instance_id>'
curl --fail-with-body \
  "${ADMIN_URL}/admin/services/${INSTANCE_ID}/stop/preview" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

确认停止实例：

```bash
INSTANCE_ID='<instance_id>'
curl --fail-with-body -X POST \
  "${ADMIN_URL}/admin/services/${INSTANCE_ID}/stop/apply" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

## Benchmark 任务

查看最近 20 个任务：

```bash
curl --fail-with-body \
  "${ADMIN_URL}/admin/benchmarks?limit=20" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

按状态或服务实例筛选：

```bash
curl --fail-with-body \
  "${ADMIN_URL}/admin/benchmarks?status=running" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .

INSTANCE_ID='<instance_id>'
curl --fail-with-body \
  "${ADMIN_URL}/admin/benchmarks?instance_id=${INSTANCE_ID}" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

预览停止操作：

```bash
JOB_ID='<job_id>'
curl --fail-with-body \
  "${ADMIN_URL}/admin/benchmarks/${JOB_ID}/stop/preview" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

确认停止任务：

```bash
JOB_ID='<job_id>'
curl --fail-with-body -X POST \
  "${ADMIN_URL}/admin/benchmarks/${JOB_ID}/stop/apply" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

## 功能测试任务

查看最近 20 个任务：

```bash
curl --fail-with-body \
  "${ADMIN_URL}/admin/tests?limit=20" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

按状态或服务实例筛选：

```bash
curl --fail-with-body \
  "${ADMIN_URL}/admin/tests?status=running" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .

INSTANCE_ID='<instance_id>'
curl --fail-with-body \
  "${ADMIN_URL}/admin/tests?instance_id=${INSTANCE_ID}" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

预览停止操作：

```bash
TEST_RUN_ID='<test_run_id>'
curl --fail-with-body \
  "${ADMIN_URL}/admin/tests/${TEST_RUN_ID}/stop/preview" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

确认停止任务：

```bash
TEST_RUN_ID='<test_run_id>'
curl --fail-with-body -X POST \
  "${ADMIN_URL}/admin/tests/${TEST_RUN_ID}/stop/apply" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  | jq .
```

## 返回与审计

- 返回字段 `operation` 为 `preview` 或 `apply`。
- `status=blocked` 表示存在运行中的关联任务或其他安全限制。
- `status=not_found` 表示目标 ID 不存在。
- 执行成功后，响应中的 `audit_file` 是本次管理员操作的审计记录路径。
