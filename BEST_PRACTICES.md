# LangChain + Langfuse + 观测云 接入最佳实践

更新时间：2026-08-04

本文基于本项目的真实验证结果整理，目标是帮助团队稳定地把 `LangChain` 运行链路上报到 `Langfuse` 兼容入口，并在 `观测云/Guance` 中完成接收与排障。

## 1. 推荐架构

推荐使用下面这层结构：

- 应用编排层：`LangChain`
- 观测接入层：`Langfuse Python SDK`
- LangChain 自动采集：`langfuse.langchain.CallbackHandler`
- 业务自定义 Span：`langfuse.start_as_current_observation(...)`
- 接收端：`Guance Langfuse 兼容入口`

这个方案的优点是：

- 保留 LangChain 原生链路结构，例如 `RunnableSequence`、`Prompt`、`Model Call`
- 可以在业务层补充会话、轮次、用户、环境等元数据
- 兼容多轮对话场景
- 不需要自己手工拼 OTLP protobuf

## 2. 官方推荐的接入方式

Langfuse 官方对 LangChain 的推荐方式是：

- 用 `CallbackHandler()` 采集 LangChain 执行链路
- 用 `Langfuse` SDK 在业务代码里创建更高层的 observation/span
- 通过 `session_id`、`user_id`、`tags`、`metadata` 增强可检索性

本项目当前实现也是按这个方式组织的：

- LangChain 自动 observation：`langfuse.langchain.CallbackHandler`
- 业务根 span：`langchain-demo-chat`
- 每轮对话 span：`langchain-demo-turn`

参考：

- Langfuse LangChain 集成：<https://langfuse.com/guides/cookbook/integration_langchain>
- Langfuse SDK / Instrumentation：<https://langfuse.com/docs/observability/sdk/instrumentation>

## 3. 配置最佳实践

### 3.1 统一使用环境变量

不要把 endpoint、key、路径写死在代码里，统一走环境变量。

最少配置：

```dotenv
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://llm-openway.guance.com
```

推荐额外配置：

```dotenv
LANGFUSE_OTLP_COMPRESSION=none
LANGFUSE_DEBUG_HTTP=0
```

说明：

- `LANGFUSE_HOST` 指向 Guance 提供的 Langfuse 兼容入口域名
- `LANGFUSE_OTLP_COMPRESSION=none` 建议作为默认值
- `LANGFUSE_DEBUG_HTTP=1` 只在排障时开启

### 3.2 明确 `.env` 与 shell 环境变量优先级

本项目使用：

```python
load_dotenv()
```

`python-dotenv` 默认 `override=False`，这意味着：

- shell 中已经存在的环境变量优先
- `.env` 只补充缺失值
- `.env` 不会覆盖你之前 `export` 的旧值

因此最佳实践是：

- 测试前先 `unset LANGFUSE_*`
- 或者开一个干净 shell 再运行
- 或者把代码改成 `load_dotenv(override=True)`，强制以 `.env` 为准

## 4. 观测模型最佳实践

建议把“会话”和“单轮请求”分层，而不是把每个模型调用都直接当成根节点。

推荐层级：

- 会话级：一个聊天 session，一个根 span
- 轮次级：每次用户输入一个子 span
- LangChain 内部执行：由 `CallbackHandler` 自动挂在当前上下文下

推荐字段：

- `session_id`：串起整场对话
- `user_id`：标识调用用户
- `tags`：如 `langchain-demo`、`provider=openai-compatible`
- `metadata`：版本、部署环境、主题、轮次、返回长度

不建议做法：

- 把所有字段都打到 resource attributes
- 在根 span 上塞完整聊天历史
- 为了“看起来全”而手工复制 LangChain 已经自动产生的 span

## 5. Guance 兼容性结论

以下结论来自 2026-08-04 的真实验证。

### 5.1 默认 OTLP traces 路径

当前 `Langfuse Python SDK` 默认会把 trace 发到：

```text
/api/public/otel/v1/traces
```

所以当 `LANGFUSE_HOST=https://llm-openway.guance.com` 时，默认请求地址是：

```text
https://llm-openway.guance.com/api/public/otel/v1/traces
```

### 5.2 非压缩请求可成功

当配置：

```dotenv
LANGFUSE_OTLP_COMPRESSION=none
```

并使用已验证可用的 Guance key 时，Guance 返回：

```text
HTTP 200 OK
```

### 5.3 gzip 压缩请求当前会失败

当配置：

```dotenv
LANGFUSE_OTLP_COMPRESSION=gzip
```

同一组可用 key 的请求返回：

```json
{"error_code":"kodo.protobufError"}
```

这说明至少在当前入口上：

- Guance 能接收非压缩 protobuf
- Guance 当前不接受 gzip 压缩后的 Langfuse OTLP protobuf body

因此建议：

```dotenv
LANGFUSE_OTLP_COMPRESSION=none
```

作为生产和测试默认值。

## 6. Key 使用最佳实践

不要混用不同系统的 key。

常见错误：

- 用标准 Langfuse Cloud 的 `pk-lf-... / sk-lf-...`
- 但把 host 指向 `https://llm-openway.guance.com`

这种组合很容易导致：

- `400 Bad Request`
- `appid/token 不匹配`
- 服务端无法识别当前 key 对应的应用

正确做法是：

- `LANGFUSE_HOST` 用 Guance 域名
- `LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY` 也必须使用 Guance 为该入口生成的同一组凭据

## 7. 调试最佳实践

### 7.1 排障时打开 HTTP 调试

排障建议临时开启：

```dotenv
LANGFUSE_DEBUG_HTTP=1
```

这样终端会打印：

- 请求 URL
- 请求头
- 响应头
- 响应体

重点检查：

- `Content-Type` 是否为 `application/x-protobuf`
- 是否出现 `Content-Encoding: gzip`
- 响应体里的 `error_code` 是什么

### 7.2 先做“最小上报测试”，再测完整对话

不要一上来就用完整应用排障。先做最小 span 验证，排除模型侧干扰：

```bash
python - <<'PY'
from app import configure_langfuse

langfuse = configure_langfuse()
with langfuse.start_as_current_observation(
    as_type="span",
    name="langfuse-connectivity-check",
    input={"ping": "guance"},
) as span:
    span.update(output={"status": "ok"})
langfuse.shutdown()
PY
```

如果最小上报失败，再去看：

- key 是否匹配
- host 是否正确
- 是否开启了压缩
- 服务端返回的 `error_code`

### 7.3 区分“模型成功”和“上报失败”

如果终端里：

- `Assistant` 正常回复了
- 但同时出现 `Failed to export span batch code: 400`

那么问题通常是：

- 模型调用成功
- 观测上报失败

不要把这两类问题混在一起排查。

## 8. 推荐测试流程

建议同事按下面顺序测试。

### 步骤 1：安装依赖

```bash
cd /path/to/langchain-guance-otel-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 步骤 2：准备配置

```bash
cp .env.example .env
```

`.env` 至少包含：

```dotenv
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://llm-openway.guance.com
LANGFUSE_OTLP_COMPRESSION=none
LANGFUSE_DEBUG_HTTP=1
```

### 步骤 3：先跑最小上报验证

成功预期：

- 请求发到 `/api/public/otel/v1/traces`
- 没有 `Content-Encoding: gzip`
- 返回 `200 OK`

### 步骤 4：再跑完整对话 demo

```bash
python app.py
```

如果模型正常返回，但 trace 上报失败，优先看 `LANGFUSE_DEBUG_HTTP` 打出来的响应体。

## 9. 生产使用建议

- 默认关闭 HTTP 调试，避免日志过多
- 默认关闭压缩兼容风险，固定 `LANGFUSE_OTLP_COMPRESSION=none`
- 不要在日志里打印完整 `Authorization`、`secret key`
- 用 `session_id`、`user_id`、`tags` 组织检索，不要把大段正文堆到 metadata
- 先在最小测试脚本验证 key/host，再接入真实业务流量

## 10. 本项目建议结论

对于这个 demo，建议采用下面这组默认策略：

```dotenv
LANGFUSE_HOST=https://llm-openway.guance.com
LANGFUSE_OTLP_COMPRESSION=none
LANGFUSE_DEBUG_HTTP=0
```

排障时改成：

```dotenv
LANGFUSE_DEBUG_HTTP=1
```

如果你们团队经常因为 shell 残留环境变量导致配置混乱，建议把：

```python
load_dotenv()
```

改成：

```python
load_dotenv(override=True)
```

前提是你们明确希望 `.env` 始终覆盖当前 shell 的旧值。
