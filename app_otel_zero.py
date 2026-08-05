import os
from typing import Any

from dotenv import load_dotenv

from app import build_chain

load_dotenv()


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

    chain = build_chain()

    topic = os.getenv("DEMO_TOPIC", "OpenTelemetry")
    style = os.getenv("DEMO_STYLE", "回答简洁，优先给可执行建议")
    history: list[Any] = []

    print("[session] interactive chat started (otel zero-code)")
    print("[session] 通过 OTel auto-instrumentation 启动时会自动注入 LangChain OTEL instrumentation")
    print("[session] 输入 exit 或 quit 结束，输入 /clear 清空上下文\n")

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

        result = chain.invoke(
            {
                "topic": topic,
                "style": style,
                "history": history,
                "input": user_input,
            }
        )
        content = _extract_text(result)

        history.append(HumanMessage(content=user_input))
        history.append(AIMessage(content=content))

        print("\nAssistant>")
        print(content)
        print()


if __name__ == "__main__":
    main()
