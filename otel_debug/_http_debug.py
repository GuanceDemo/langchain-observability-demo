import os


def _enabled() -> bool:
    return os.getenv("OTEL_DEBUG_HTTP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _redact_headers(headers):
    redacted = {}
    for key, value in dict(headers).items():
        if key.lower() == "authorization":
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def install() -> None:
    if not _enabled():
        return

    import requests

    if getattr(requests.Session.send, "__module__", "") == __name__:
        return

    _original_send = requests.Session.send

    def _send(self, request, **kwargs):
        body = request.body
        body_len = len(body) if isinstance(body, (bytes, bytearray)) else 0
        print("[otel-debug] requests hook enabled")
        print(f"[http] --> {request.method} {request.url}")
        print(f"[http] --> headers: {_redact_headers(request.headers)}")
        if body_len:
            preview = bytes(body[:32]).hex()
            print(f"[http] --> body: {body_len} bytes, hex[:32]={preview}")

        response = _original_send(self, request, **kwargs)

        print(f"[http] <-- {response.status_code} {response.reason}")
        print(f"[http] <-- headers: {dict(response.headers)}")
        if response.content:
            text = response.text
            if len(text) > 500:
                text = text[:500] + "...(truncated)"
            print(f"[http] <-- body: {text}")
        return response

    requests.Session.send = _send
