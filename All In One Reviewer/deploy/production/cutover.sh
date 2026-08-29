#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly COMPOSE_FILE="${SCRIPT_DIR}/compose.production.yaml"
readonly COMPOSE_PROJECT="andyhub-production"
readonly PROXY_BASE_URL="http://127.0.0.1:${ANDYHUB_PRODUCTION_PORT:-8501}"
readonly APP_USER="${ANDYHUB_APP_USER:-andreipamesa20}"

streamlit_stop_started=0
cutover_succeeded=0

log() {
    printf '[andyhub-cutover] %s\n' "$*"
}

compose() {
    docker compose --project-name "${COMPOSE_PROJECT}" --file "${COMPOSE_FILE}" "$@"
}

streamlit_is_healthy() {
    curl --fail --silent --show-error --max-time 5 \
        http://127.0.0.1:8501/_stcore/health >/dev/null
}

port_8501_is_listening() {
    ss --no-header --tcp --listening 'sport = :8501' | grep -q .
}

production_stack_is_healthy() {
    local container_id health_status service

    curl --fail --silent --show-error --max-time 5 "${PROXY_BASE_URL}/proxy-health" >/dev/null 2>&1 || return 1
    curl --fail --silent --show-error --max-time 5 "${PROXY_BASE_URL}/health" >/dev/null 2>&1 || return 1
    curl --fail --silent --show-error --max-time 5 "${PROXY_BASE_URL}/api/v1/health" >/dev/null 2>&1 || return 1

    for service in api worker web proxy; do
        container_id=$(compose ps --quiet "${service}")
        [[ -n ${container_id} ]] || return 1
        health_status=$(docker inspect --format '{{.State.Health.Status}}' "${container_id}")
        [[ ${health_status} == "healthy" ]] || return 1
    done
}

stop_compose_stack() {
    local -a running_containers=()

    if compose down --remove-orphans; then
        return 0
    fi

    log "Compose down failed; stopping any running project containers by label" >&2
    mapfile -t running_containers < <(
        docker ps --quiet --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}"
    )
    if [[ ${#running_containers[@]} -gt 0 ]]; then
        docker stop "${running_containers[@]}" >/dev/null
    fi

    mapfile -t running_containers < <(
        docker ps --quiet --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}"
    )
    [[ ${#running_containers[@]} -eq 0 ]]
}

automatic_rollback() {
    local stack_status=0 streamlit_status=0

    log "automatic rollback: stopping the production Compose stack"
    stop_compose_stack || stack_status=$?
    if [[ ${stack_status} -ne 0 ]]; then
        log "CRITICAL: containers are still running; refusing to start Streamlit concurrently" >&2
        return "${stack_status}"
    fi

    log "automatic rollback: enabling and starting streamlit.service"
    systemctl enable --now streamlit.service || streamlit_status=$?

    if [[ ${streamlit_status} -eq 0 ]]; then
        for _ in {1..30}; do
            if streamlit_is_healthy; then
                log "automatic rollback succeeded; Streamlit is healthy on port 8501"
                return 0
            fi
            sleep 2
        done
    fi

    log "CRITICAL: automatic rollback was attempted but Streamlit did not become healthy" >&2
    systemctl --no-pager --full status streamlit.service >&2 || true
    return 1
}

on_exit() {
    local original_status=$1 rollback_status=0
    trap - EXIT INT TERM

    if [[ ${cutover_succeeded} -eq 0 && ${streamlit_stop_started} -eq 1 ]]; then
        automatic_rollback || rollback_status=$?
        if [[ ${rollback_status} -ne 0 ]]; then
            original_status=${rollback_status}
        fi
    fi
    exit "${original_status}"
}

trap 'on_exit $?' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ${EUID} -ne 0 ]]; then
    log "ERROR: run as root: sudo ./deploy/production/cutover.sh" >&2
    exit 1
fi

exec 9>/run/lock/andyhub-cutover.lock
if ! flock --nonblock 9; then
    log "ERROR: another AndyHub cutover or rollback is already running" >&2
    exit 1
fi

command -v docker >/dev/null 2>&1 || { log "ERROR: Docker is not installed" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { log "ERROR: curl is not installed" >&2; exit 1; }
command -v ss >/dev/null 2>&1 || { log "ERROR: ss is not installed" >&2; exit 1; }
docker compose version >/dev/null
systemctl cat streamlit.service >/dev/null
[[ -r /etc/andyhub/groq_api_key ]] || { log "ERROR: /etc/andyhub/groq_api_key is not readable" >&2; exit 1; }

for directory in Database uploads extraction_cache course_brain_db; do
    [[ -d "${APP_ROOT}/${directory}" ]] || {
        log "ERROR: required data directory is missing: ${APP_ROOT}/${directory}" >&2
        exit 1
    }
done

export ANDYHUB_APP_ROOT="${APP_ROOT}"
export ANDYHUB_UID="$(id -u "${APP_USER}")"
export ANDYHUB_GID="$(id -g "${APP_USER}")"

compose config --quiet

if production_stack_is_healthy; then
    log "the production stack is already healthy; ensuring Streamlit stays disabled"
    streamlit_stop_started=1
    systemctl disable --now streamlit.service
    cutover_succeeded=1
    exit 0
fi

if systemctl is-active --quiet streamlit.service; then
    if ! streamlit_is_healthy; then
        log "ERROR: streamlit.service is active but its health endpoint is failing; leaving it untouched" >&2
        exit 1
    fi
elif port_8501_is_listening; then
    log "ERROR: port 8501 has an unmanaged listener; leaving it untouched" >&2
    exit 1
fi

log "disabling and stopping the supervised Streamlit rollback target"
streamlit_stop_started=1
systemctl disable --now streamlit.service

for _ in {1..15}; do
    if ! port_8501_is_listening; then
        break
    fi
    sleep 1
done
if port_8501_is_listening; then
    log "ERROR: port 8501 did not become free after Streamlit stopped" >&2
    exit 1
fi

log "building and starting the 704 MB production stack"
COMPOSE_PARALLEL_LIMIT=1 compose up --detach --build --remove-orphans

log "waiting up to 7 minutes for the local proxy and its dependencies"
proxy_ready=0
for _ in {1..84}; do
    if curl --fail --silent --show-error --max-time 5 \
        "${PROXY_BASE_URL}/proxy-health" >/dev/null 2>&1; then
        proxy_ready=1
        break
    fi
    sleep 5
done
[[ ${proxy_ready} -eq 1 ]] || { log "ERROR: local proxy did not become healthy" >&2; exit 1; }

log "running final health checks through the local proxy"
curl --fail --silent --show-error --max-time 10 "${PROXY_BASE_URL}/proxy-health" >/dev/null
curl --fail --silent --show-error --max-time 10 "${PROXY_BASE_URL}/health" >/dev/null
curl --fail --silent --show-error --max-time 10 "${PROXY_BASE_URL}/api/v1/health" >/dev/null

for service in api worker web proxy; do
    container_id=$(compose ps --quiet "${service}")
    [[ -n ${container_id} ]] || { log "ERROR: ${service} container is missing" >&2; exit 1; }
    health_status=$(docker inspect --format '{{.State.Health.Status}}' "${container_id}")
    [[ ${health_status} == "healthy" ]] || {
        log "ERROR: ${service} container health is ${health_status}" >&2
        exit 1
    }
done

cutover_succeeded=1
log "local cutover succeeded; the stack is healthy at ${PROXY_BASE_URL}"
log "the Cloudflare tunnel remains unchanged on localhost:8501; run the public checks in RUNBOOK.md"
