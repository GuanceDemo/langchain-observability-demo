# LangChain Observability Demo

这个仓库用于演示 `LangChain` 应用如何接入观测能力。

当前已实现的是 `Langfuse Python SDK + LangChain CallbackHandler` 方案，用于把链路上报到 Guance 的 Langfuse 兼容入口；后续可以在同一仓库中继续扩展 `LangSmith` 等其他观测接入方式。


它保留了终端多轮对话能力：

- 连续提问会保留上下文
- `/clear` 清空上下文
- `exit` / `quit` 结束会话

## 目录

- `app.py`：多轮会话 demo
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

```bash
source .venv/bin/activate
python app.py
```

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

## 实现说明

这个版本按 Langfuse 官方当前文档实现：

- LangChain 集成使用 `from langfuse.langchain import CallbackHandler`
- 业务层自定义 observation 使用 `langfuse.start_as_current_observation(...)`
- trace/session/user/tags 通过 `propagate_attributes(...)` 传播
- 脚本退出前调用 `langfuse.shutdown()`，避免短生命周期进程丢数据

## 参考文档

- Langfuse LangChain 集成：<https://langfuse.com/integrations/frameworks/langchain>
- Langfuse Instrumentation：<https://langfuse.com/docs/observability/sdk/instrumentation>
