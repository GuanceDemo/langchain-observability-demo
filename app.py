import base64
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

if os.getenv("LANGFUSE_HOST") and not os.getenv("LANGFUSE_BASE_URL"):
    os.environ["LANGFUSE_BASE_URL"] = os.environ["LANGFUSE_HOST"]


def _redact_headers(headers: Any) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in dict(headers).items():
        if key.lower() == "authorization":
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def _build_debug_session():
    import requests

    class DebugSession(requests.Session):
        def send(self, request, **kwargs):
            body = request.body
            body_len = len(body) if isinstance(body, (bytes, bytearray)) else 0
            print(f"[http] --> {request.method} {request.url}")
            print(f"[http] --> headers: {_redact_headers(request.headers)}")
            if body_len:
                preview = bytes(body[:32]).hex()
                print(f"[http] --> body: {body_len} bytes, hex[:32]={preview}")

            response = super().send(request, **kwargs)

            print(f"[http] <-- {response.status_code} {response.reason}")
            print(f"[http] <-- headers: {dict(response.headers)}")
            if response.content:
                text = response.text
                if len(text) > 500:
                    text = text[:500] + "...(truncated)"
                print(f"[http] <-- body: {text}")
            return response

    return DebugSession()


def _resolve_compression():
    from opentelemetry.exporter.otlp.proto.http import Compression

    value = os.getenv("LANGFUSE_OTLP_COMPRESSION", "none").strip().lower()
    mapping = {
        "none": Compression.NoCompression,
        "gzip": Compression.Gzip,
        "deflate": Compression.Deflate,
    }
    if value not in mapping:
        raise RuntimeError(
            "LANGFUSE_OTLP_COMPRESSION 仅支持 none、gzip、deflate。"
        )
    return mapping[value], value


def configure_langfuse():
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = (
        os.getenv("LANGFUSE_HOST", "").strip()
        or os.getenv("LANGFUSE_BASE_URL", "").strip()
    )
    if not public_key or not secret_key or not host:
        raise RuntimeError(
            "缺少 Langfuse 配置。请设置 LANGFUSE_PUBLIC_KEY、"
            "LANGFUSE_SECRET_KEY、LANGFUSE_HOST。"
        )

    from langfuse import Langfuse
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )

    compression, compression_name = _resolve_compression()
    debug_http = os.getenv("LANGFUSE_DEBUG_HTTP", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    traces_export_path = os.getenv(
        "LANGFUSE_OTEL_TRACES_EXPORT_PATH", "api/public/otel/v1/traces"
    ).strip("/")
    endpoint = f"{host.rstrip('/')}/{traces_export_path}"
    headers = {
        "Authorization": (
            "Basic "
            + base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode(
                "ascii"
            )
        ),
        "x-langfuse-sdk-name": "python",
        "x-langfuse-public-key": public_key,
    }
    session = _build_debug_session() if debug_http else None
    span_exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers=headers,
        compression=compression,
        session=session,
    )

    langfuse = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=host,
        span_exporter=span_exporter,
    )
    print(f"[config] langfuse host: {host}")
    print(f"[config] langfuse public key: {public_key[:8]}***")
    print(f"[config] langfuse otlp endpoint: {endpoint}")
    print(f"[config] langfuse otlp compression: {compression_name}")
    print(f"[config] langfuse debug http: {debug_http}")
    return langfuse


def build_chain():
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    topic = os.getenv("DEMO_TOPIC", "OpenTelemetry")
    style = os.getenv("DEMO_STYLE", "回答简洁，优先给可执行建议")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一个简洁的技术助手。"
                "默认主题偏好：{topic}。"
                "回答风格：{style}。"
                "如果用户后续切换话题，以当前用户问题为准。",
            ),
            MessagesPlaceholder("history"),
            ("human", "{input}"),
        ]
    )

    provider = os.getenv("MODEL_PROVIDER", "auto").strip().lower()

    if provider in {"openai", "compatible", "openai-compatible"} or (
        provider == "auto"
        and (os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_KEY"))
    ):
        from langchain_openai import ChatOpenAI

        model_name = os.getenv("OPENAI_MODEL", "claude-sonnet-4.5")
        base_url = os.getenv("OPENAI_BASE_URL")
        api_key = os.getenv("OPENAI_API_KEY") or "dummy-key"
        model = ChatOpenAI(
            model=model_name,
            temperature=0.2,
            base_url=base_url,
            api_key=api_key,
        )
        provider_name = "openai-compatible" if base_url else "openai"
        print(f"[config] model provider: {provider_name} ({model_name})")
        return prompt | model

    if provider == "ollama" or (provider == "auto" and os.getenv("OLLAMA_MODEL")):
        from langchain_ollama import ChatOllama

        model_name = os.getenv("OLLAMA_MODEL", "qwen3:8b")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        model = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0.2,
        )
        print(f"[config] model provider: ollama ({model_name})")
        return prompt | model

    raise RuntimeError(
        "没有可用的真实模型后端。"
        "请配置以下任意一种方式："
        "1) OpenAI-compatible: MODEL_PROVIDER=compatible, OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_API_KEY；"
        "2) Ollama: MODEL_PROVIDER=ollama, OLLAMA_MODEL, OLLAMA_BASE_URL。"
    )


def _extract_text(result: Any) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def main() -> None:
    from langchain_core.messages import AIMessage, HumanMessage
    from langfuse import propagate_attributes
    from langfuse.langchain import CallbackHandler

    langfuse = configure_langfuse()
    chain = build_chain()
    langfuse_handler = CallbackHandler()

    topic = os.getenv("DEMO_TOPIC", "OpenTelemetry")
    style = os.getenv("DEMO_STYLE", "回答简洁，优先给可执行建议")
    session_id = os.getenv("DEMO_SESSION_ID", "langchain-demo-session")
    user_id = os.getenv("DEMO_USER_ID", "demo-user")
    app_version = os.getenv("APP_VERSION", "0.1.0")
    deployment_env = os.getenv("DEPLOYMENT_ENV", "demo")
    model_provider = os.getenv("MODEL_PROVIDER", "auto")
    history: list[Any] = []

    try:
        print("[session] interactive chat started")
        print("[session] 输入 exit 或 quit 结束，输入 /clear 清空上下文\n")
        turn_index = 0

        with langfuse.start_as_current_observation(
            as_type="span",
            name="langchain-demo-chat",
            input={"topic": topic, "style": style},
        ) as chat_span:
            with propagate_attributes(
                trace_name="langchain-demo-chat",
                session_id=session_id,
                user_id=user_id,
                tags=["langchain-demo", model_provider],
                metadata={
                    "topic": topic,
                    "style": style,
                    "app_version": app_version,
                    "deployment_environment": deployment_env,
                },
            ):
                while True:
                    try:
                        user_input = input("You> ").strip()
                    except EOFError:
                        print()
                        break

                    if not user_input:
                        continue
                    if user_input.lower() in {"exit", "quit"}:
                        break
                    if user_input == "/clear":
                        history.clear()
                        print("[session] history cleared\n")
                        continue

                    turn_index += 1
                    with chat_span.start_as_current_observation(
                        as_type="span",
                        name="langchain-demo-turn",
                        input={
                            "user_input": user_input,
                            "turn_index": turn_index,
                            "history_message_count": len(history),
                        },
                        metadata={"turn_index": turn_index},
                    ) as turn_span:
                        result = chain.invoke(
                            {
                                "topic": topic,
                                "style": style,
                                "history": history,
                                "input": user_input,
                            },
                            config={"callbacks": [langfuse_handler]},
                        )
                        content = _extract_text(result)
                        turn_span.update(
                            output={"assistant": content},
                            metadata={
                                "response_length": len(content),
                                "history_message_count": len(history),
                            },
                        )

                    history.append(HumanMessage(content=user_input))
                    history.append(AIMessage(content=content))
                    print("\nAssistant>")
                    print(content)
                    print()

                chat_span.update(
                    output={
                        "message_count": len(history),
                        "turn_count": turn_index,
                    }
                )
    finally:
        langfuse.shutdown()
        print("\n[done] langfuse shutdown complete")


if __name__ == "__main__":
    main()
