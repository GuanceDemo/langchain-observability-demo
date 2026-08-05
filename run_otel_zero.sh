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

if [ "${OTEL_DEBUG_HTTP:-}" = "1" ] || [ "${OTEL_DEBUG_HTTP:-}" = "true" ] || [ "${OTEL_DEBUG_HTTP:-}" = "yes" ] || [ "${OTEL_DEBUG_HTTP:-}" = "on" ]; then
  if [ -n "${PYTHONPATH:-}" ]; then
    export PYTHONPATH="${repo_dir}/otel_debug:${PYTHONPATH}"
  else
    export PYTHONPATH="${repo_dir}/otel_debug"
  fi
fi

exec "${repo_dir}/.venv/bin/opentelemetry-instrument" "${repo_dir}/.venv/bin/python" "${repo_dir}/app_otel_zero.py"
