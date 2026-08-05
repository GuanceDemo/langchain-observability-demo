from pathlib import Path
import sys

from _http_debug import install


def main() -> None:
    repo_dir = Path(__file__).resolve().parents[1]
    if str(repo_dir) not in sys.path:
        sys.path.insert(0, str(repo_dir))

    install()

    from opentelemetry.instrumentation.auto_instrumentation import initialize

    initialize()

    from app_otel_zero import main as app_main

    app_main()


if __name__ == "__main__":
    main()
