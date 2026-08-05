# LangChain Observability Demo

这个仓库用于演示 `LangChain` 应用如何接入观测能力。

当前已实现两种方案：

- `Langfuse Python SDK + LangChain CallbackHandler`
- `OpenTelemetry LangChain auto-instrumentation（zero-code）`

两种方案都可以把链路上报到 Guance 的 Langfuse 兼容入口；后续可以在同一仓库中继续扩展 `LangSmith` 等其他观测接入方式。


它保留了终端多轮对话能力：

- 连续提问会保留上下文
- `/clear` 清空上下文
- `exit` / `quit` 结束会话

## 目录

- `app.py`：Langfuse 版多轮会话 demo
- `app_otel_zero.py`：零业务埋点版 LangChain demo，配合 `opentelemetry-instrument` 启动
- `run_otel_zero.sh`：zero-code 启动脚本，只使用 `OTEL_*` 上报参数
- `.env.example`：环境变量模板
- `requirements.txt`：依赖

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Langfuse 配置

至少需要这三个变量：

```dotenv
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
LANGFUSE_HOST=https://llm-openway.guance.com
```

代码会自动把 `LANGFUSE_HOST` 映射成 SDK 可用的 `LANGFUSE_BASE_URL`。

如果你怀疑 Guance/Kodo 不接受压缩后的 OTLP body，可以显式关闭压缩并打开 HTTP 调试：

```dotenv
LANGFUSE_OTLP_COMPRESSION=none
LANGFUSE_DEBUG_HTTP=1
```

其中：

- `LANGFUSE_OTLP_COMPRESSION` 支持 `none`、`gzip`、`deflate`，默认是 `none`
- `LANGFUSE_DEBUG_HTTP=1` 时会打印请求头、响应头和响应体，便于确认是否出现了 `Content-Encoding: gzip`

## OTEL 配置

`run_otel_zero.sh` 和 `run_otel_zero_debug.sh` 使用标准 `OTEL_*` 环境变量。

脚本在你没有显式设置时，会自动补这几个缺省值：

- `OTEL_TRACES_EXPORTER=otlp`
- `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf`
- `OTEL_METRICS_EXPORTER=none`
- `OTEL_LOGS_EXPORTER=none`

这样做的原因是：当前 demo 只安装了 OTLP HTTP exporter，如果让 auto-instrumentation 走默认 `grpc`，会报 `Requested component 'otlp_proto_grpc' not found`。

如果你要把 traces 发到观测云 OTEL LLM 入口，推荐这样配置：

```dotenv
OTEL_SERVICE_NAME=langchain-observability-demo
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://llm-openway.guance.com/v1/write/otel-llm
OTEL_EXPORTER_OTLP_HEADERS=To-Headless=true,X-Token=<agent_token>
OTEL_RESOURCE_ATTRIBUTES=agent_id=<agent_id>,agent_name=langchain-otel,agent_runtime=langchain
```

其中：

- `OTEL_EXPORTER_OTLP_HEADERS` 要用 `key=value`，不要写成 `key:value`
- `OTEL_RESOURCE_ATTRIBUTES` 要用英文逗号 `,`，不要用中文逗号 `，`
- 当前 demo 默认只验证 traces，上报成败看 `run_otel_zero_debug.sh` 的 HTTP 输出

## 模型配置

### 方式 A：OpenAI-compatible 网关

```dotenv
MODEL_PROVIDER=compatible
OPENAI_BASE_URL=http://43.98.191.89:8317/v1
OPENAI_API_KEY=your_gateway_key
OPENAI_MODEL=claude-sonnet-4.5
```

我本地实测这个网关下，`claude-sonnet-4.5` 能跑通 `langchain_openai`。

### 方式 B：Ollama

```dotenv
MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
```

## 运行

### 方式 A：Langfuse 版

```bash
source .venv/bin/activate
python app.py
```

### 方式 B：OTEL zero-code / auto-instrumentation 版

```bash
chmod +x run_otel_zero.sh
./run_otel_zero.sh
```

这条方式的特点是：

- `app_otel_zero.py` 本身不显式调用 OTEL API
- 启动时通过 `opentelemetry-instrument` 自动注入 LangChain instrumentation
- `run_otel_zero.sh` 只负责启动，环境变量需要你自行注入

如果你要看 OTLP 请求头、响应头和状态码，使用调试启动脚本：

```bash
chmod +x run_otel_zero_debug.sh
./run_otel_zero_debug.sh
```

这个脚本会自动打开项目里的 HTTP 调试钩子，用于确认上报成功还是失败。

只验证 Langfuse OTLP 上报链路时，不依赖真实 LLM 也可以直接跑一个最小脚本：

```bash
source .venv/bin/activate
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

这条验证的重点是看控制台输出里：

- 请求头是否没有 `Content-Encoding`
- `Content-Type` 是否为 `application/x-protobuf`
- Guance 返回的具体 HTTP 状态码和错误体

只验证 OTEL zero-code 上报链路时，直接运行：

```bash
./run_otel_zero.sh
```

启动后：

- 输入普通问题：继续当前会话
- 输入 `/clear`：清空历史上下文
- 输入 `exit` 或 `quit`：退出

## 观测结构

当前脚本会在 Langfuse 中形成这层结构：

- `langchain-demo-chat`
- `langchain-demo-turn`
- LangChain 自动捕获的子 observation，例如 prompt / model call

其中：

- `session_id` 用来把整场对话串起来
- `user_id` 用来标识用户
- `tags` 默认会带上 `langchain-demo` 和当前 `MODEL_PROVIDER`

`app_otel_zero.py` 更接近 zero-code 场景：

- 应用代码里没有显式 `TracerProvider` / `OTLPSpanExporter` 初始化
- LangChain instrumentation 由 `opentelemetry-instrument` 自动注入
- 主要用于验证“零业务埋点”情况下的自动链路采集效果

## 实现说明

`app.py` 按 Langfuse 官方当前文档实现：

- LangChain 集成使用 `from langfuse.langchain import CallbackHandler`
- 业务层自定义 observation 使用 `langfuse.start_as_current_observation(...)`
- trace/session/user/tags 通过 `propagate_attributes(...)` 传播
- 脚本退出前调用 `langfuse.shutdown()`，避免短生命周期进程丢数据

`app_otel_zero.py` 和 `run_otel_zero.sh` 用于 zero-code 方式：

- 业务脚本只保留 LangChain 调用逻辑
- OTEL 配置和注入都放在启动命令层
- 更适合验证 auto-instrumentation 的真实效果

## 参考文档

- Langfuse LangChain 集成：<https://langfuse.com/integrations/frameworks/langchain>
- Langfuse Instrumentation：<https://langfuse.com/docs/observability/sdk/instrumentation>
- OpenTelemetry Python LangChain instrumentation：<https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation-genai/opentelemetry-instrumentation-langchain>
