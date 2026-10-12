#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
LOCAL_ENV_FILE="${SCRIPT_DIR}/local_env.sh"

if [ -f "${LOCAL_ENV_FILE}" ]; then
    # Load untracked local secrets and proxy settings.
    # shellcheck disable=SC1090
    source "${LOCAL_ENV_FILE}"
fi

AI_BACKEND="${AI_BACKEND:-local}"
case "${AI_BACKEND}" in
  deepseek)
    AI_PROVIDER="${AI_PROVIDER:-deepseek}"
    DEEPSEEK_URL="${DEEPSEEK_URL:-https://api.deepseek.com/chat/completions}"
    DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com}"
    DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-v4-pro}"
    AI_BASE_URL="${AI_BASE_URL:-${DEEPSEEK_URL}}"
    AI_API_KEY="${AI_API_KEY:-${DEEPSEEK_API_KEY:-}}"
    AI_MODEL="${AI_MODEL:-${DEEPSEEK_MODEL}}"
    ;;
  local)
    CODEX_PROXY_URL="${CODEX_PROXY_URL:-http://127.0.0.1:8787/v1/chat/completions}"
    CODEX_PROXY_BASE_URL="${CODEX_PROXY_BASE_URL:-${CODEX_PROXY_URL%/chat/completions}}"
    AI_PROVIDER="${AI_PROVIDER:-openai}"
    OPENAI_URL="${OPENAI_URL:-${CODEX_PROXY_URL}}"
    OPENAI_BASE_URL="${OPENAI_BASE_URL:-${CODEX_PROXY_BASE_URL}}"
    OPENAI_API_KEY="${OPENAI_API_KEY:-${CODEX_PROXY_API_KEY:-codex-proxy}}"
    OPENAI_MODEL="${OPENAI_MODEL:-gpt-6-astra}"
    AI_BASE_URL="${AI_BASE_URL:-${OPENAI_URL}}"
    AI_API_KEY="${AI_API_KEY:-${OPENAI_API_KEY}}"
    AI_MODEL="${AI_MODEL:-${OPENAI_MODEL}}"
    ;;
  *)
    printf '%s\n' "AI_BACKEND must be 'local' or 'deepseek'." >&2
    exit 1
    ;;
esac

if [ "${AI_BACKEND}" = "deepseek" ] && [ -z "${AI_API_KEY}" ]; then
    printf '%s\n' "DEEPSEEK_API_KEY or AI_API_KEY is required when AI_BACKEND=deepseek." >&2
    exit 1
fi

if [ -n "${LOCAL_HTTP_PROXY:-}" ]; then
    export HTTP_PROXY="${HTTP_PROXY:-${LOCAL_HTTP_PROXY}}"
    export HTTPS_PROXY="${HTTPS_PROXY:-${LOCAL_HTTP_PROXY}}"
    export http_proxy="${http_proxy:-${LOCAL_HTTP_PROXY}}"
    export https_proxy="${https_proxy:-${LOCAL_HTTP_PROXY}}"
fi

export AI_BACKEND AI_PROVIDER AI_BASE_URL AI_API_KEY AI_MODEL
export OPENAI_URL OPENAI_BASE_URL OPENAI_API_KEY OPENAI_MODEL
export CODEX_PROXY_URL CODEX_PROXY_BASE_URL
export DEEPSEEK_URL DEEPSEEK_BASE_URL DEEPSEEK_MODEL

cd "${PROJECT_ROOT}"
exec python3 "${SCRIPT_DIR}/download_paper.py" \
    --extractor hybrid \
    --timeout "${DOWNLOAD_PAPER_TIMEOUT:-1800}" \
    --workers "${DOWNLOAD_PAPER_WORKERS:-1}" \
    --google-scholar-cdp-url "${GOOGLE_SCHOLAR_CDP_URL:-http://127.0.0.1:9222}" \
    "$@"
