#!/usr/bin/env bash
set -uo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
# The Phase 6 code checkout and the host's live data are permanently separate.
readonly DATA_HOST_ROOT="${ANDYHUB_DATA_HOST_ROOT:-/home/andreipamesa20/School-Works/All In One Reviewer}"
readonly COMPOSE_FILE="${SCRIPT_DIR}/compose.production.yaml"
readonly COMPOSE_PROJECT="andyhub-production"
readonly APP_USER="${ANDYHUB_APP_USER:-andreipamesa20}"

log() {
    printf '[andyhub-rollback] %s\n' "$*"
}

if [[ ${EUID} -ne 0 ]]; then
    log "ERROR: run as root: sudo ./deploy/production/rollback.sh" >&2
    exit 1
fi

exec 9>/run/lock/andyhub-cutover.lock
if ! flock --nonblock 9; then
    log "ERROR: another AndyHub cutover or rollback is already running" >&2
    exit 1
fi

export ANDYHUB_DATA_HOST_ROOT="${DATA_HOST_ROOT}"
export ANDYHUB_UID="$(id -u "${APP_USER}")"
export ANDYHUB_GID="$(id -g "${APP_USER}")"

stack_status=0
if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
        log "stopping the production Compose stack without deleting application data"
        if ! docker compose --project-name "${COMPOSE_PROJECT}" --file "${COMPOSE_FILE}" \
            down --remove-orphans; then
            log "Compose down failed; using the project-label fallback" >&2
        fi
    else
        log "Docker Compose is unavailable; using the project-label fallback" >&2
    fi

    mapfile -t running_containers < <(
        docker ps --quiet --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}"
    )
    if [[ ${#running_containers[@]} -gt 0 ]]; then
        docker stop "${running_containers[@]}" >/dev/null || stack_status=$?
    fi
    mapfile -t running_containers < <(
        docker ps --quiet --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}"
    )
    if [[ ${#running_containers[@]} -gt 0 ]]; then
        log "CRITICAL: containers are still running; refusing to start Streamlit concurrently" >&2
        exit 1
    fi
elif systemctl is-active --quiet docker.service; then
    log "CRITICAL: Docker is active but its CLI is unavailable; refusing to start Streamlit without checking containers" >&2
    exit 1
fi

if [[ ${stack_status} -ne 0 ]]; then
    log "CRITICAL: the production containers could not be stopped" >&2
    exit "${stack_status}"
fi

log "enabling and starting streamlit.service"
if ! systemctl enable --now streamlit.service; then
    log "CRITICAL: streamlit.service failed to start" >&2
    systemctl --no-pager --full status streamlit.service >&2 || true
    exit 1
fi

for _ in {1..30}; do
    if curl --fail --silent --show-error --max-time 5 \
        http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
        log "rollback succeeded; Streamlit is healthy on port 8501"
        exit 0
    fi
    sleep 2
done

log "CRITICAL: rollback was attempted but Streamlit did not become healthy" >&2
systemctl --no-pager --full status streamlit.service >&2 || true
exit 1
