#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

: "${OTEL_TRACES_EXPORTER:=otlp}"
: "${OTEL_EXPORTER_OTLP_TRACES_PROTOCOL:=http/protobuf}"
: "${OTEL_METRICS_EXPORTER:=none}"
: "${OTEL_LOGS_EXPORTER:=none}"

export OTEL_TRACES_EXPORTER
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL
export OTEL_METRICS_EXPORTER
export OTEL_LOGS_EXPORTER
export OTEL_DEBUG_HTTP=1

exec "${repo_dir}/.venv/bin/python" "${repo_dir}/otel_debug/run_otel_zero_debug.py"
