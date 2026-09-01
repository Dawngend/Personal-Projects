#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
# The Phase 6 code checkout and the host's live data are permanently separate.
readonly DATA_HOST_ROOT="${ANDYHUB_DATA_HOST_ROOT:-/home/andreipamesa20/School-Works/All In One Reviewer}"
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

readonly LOCK_FILE=/run/lock/andyhub-cutover.lock
exec 9>"${LOCK_FILE}"
if ! flock --nonblock 9; then
    # fd 9 is inherited by every child, so a killed cutover whose `docker
    # compose` child survived still holds this lock with nothing meaningfully
    # running. That happened on 2026-09-01 and presented as a flat refusal
    # with no way to tell a real concurrent run from a leftover, so name the
    # holder instead of guessing.
    log "ERROR: another AndyHub cutover or rollback holds ${LOCK_FILE}" >&2
    holder="$(cat "${LOCK_FILE}" 2>/dev/null || true)"
    if [[ -n ${holder} ]]; then
        log "       lock record: ${holder}" >&2
    fi
    if command -v lsof >/dev/null 2>&1; then
        log "       processes holding it:" >&2
        lsof -t "${LOCK_FILE}" 2>/dev/null | while read -r holder_pid; do
            log "         PID ${holder_pid}: $(tr '\0' ' ' < "/proc/${holder_pid}/cmdline" 2>/dev/null | cut -c1-120)" >&2
        done
    else
        log "       inspect with: sudo lsof ${LOCK_FILE}" >&2
    fi
    log "       If this is a leftover from an interrupted run, kill those PIDs" >&2
    log "       explicitly (not with pkill -f, which matches your own shell)." >&2
    exit 1
fi
printf 'pid=%s started=%s cmd=%s\n' "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$0" >&9 || true

command -v docker >/dev/null 2>&1 || { log "ERROR: Docker is not installed" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { log "ERROR: curl is not installed" >&2; exit 1; }
command -v ss >/dev/null 2>&1 || { log "ERROR: ss is not installed" >&2; exit 1; }
docker compose version >/dev/null
systemctl cat streamlit.service >/dev/null
[[ -s /etc/andyhub/groq_api_key ]] || { log "ERROR: /etc/andyhub/groq_api_key is missing or empty" >&2; exit 1; }

# Readable BY THE CONTAINER USER, not by root. This script runs as root, so a
# plain [[ -r ]] test always passes and proves nothing. Compose bind-mounts the
# secret with its own ownership, so a root:root 0600 file leaves the api unable
# to read its key: it reports generator "unconfigured", health returns 503
# forever, and the cutover fails waiting on that dependency. A rehearsal hit
# exactly this while every static check passed.
if ! runuser -u "${APP_USER}" -- test -r /etc/andyhub/groq_api_key; then
    log "ERROR: ${APP_USER} cannot read /etc/andyhub/groq_api_key" >&2
    log "       the container runs as that user and needs read access; fix with:" >&2
    log "       sudo chown ${APP_USER}:${APP_USER} /etc/andyhub/groq_api_key" >&2
    log "       sudo chmod 0600 /etc/andyhub/groq_api_key" >&2
    log "       sudo chmod 0711 /etc/andyhub" >&2
    exit 1
fi

for directory in Database uploads extraction_cache course_brain_db; do
    [[ -d "${DATA_HOST_ROOT}/${directory}" ]] || {
        log "ERROR: required data directory is missing: ${DATA_HOST_ROOT}/${directory} (code root: ${APP_ROOT}; data root: ${DATA_HOST_ROOT})" >&2
        exit 1
    }
done

export ANDYHUB_DATA_HOST_ROOT="${DATA_HOST_ROOT}"
export ANDYHUB_UID="$(id -u "${APP_USER}")"
export ANDYHUB_GID="$(id -g "${APP_USER}")"

# This VM's disk is IOPS-throttled hard enough that building here is not
# viable: a 2026-09-01 attempt sat at 77% iowait and had not finished the
# first application image after 20 minutes, with Streamlit already stopped.
# Build elsewhere, load the images, and set ANDYHUB_SKIP_BUILD=1 so the
# cutover only starts containers. Verify the images BEFORE stopping
# Streamlit, so a missing image costs nothing instead of an outage.
readonly SKIP_BUILD="${ANDYHUB_SKIP_BUILD:-0}"
readonly PULL_IMAGES="${ANDYHUB_PULL:-0}"
readonly IMAGE_TAG="${ANDYHUB_IMAGE_TAG:-phase6-production}"
readonly API_IMAGE="${ANDYHUB_API_IMAGE:-andyhub-api:${IMAGE_TAG}}"
readonly WEB_IMAGE="${ANDYHUB_WEB_IMAGE:-andyhub-web:${IMAGE_TAG}}"
export ANDYHUB_API_IMAGE="${API_IMAGE}"
export ANDYHUB_WEB_IMAGE="${WEB_IMAGE}"

if [[ ${SKIP_BUILD} == "1" ]]; then
    if [[ ${PULL_IMAGES} == "1" ]]; then
        log "pulling ${API_IMAGE} and ${WEB_IMAGE} from their registry"
        compose pull --quiet api web || {
            log "ERROR: could not pull the application images." >&2
            log "       If they are private, authenticate first: docker login ghcr.io" >&2
            exit 1
        }
    fi
    for image in "${API_IMAGE}" "${WEB_IMAGE}"; do
        docker image inspect "${image}" >/dev/null 2>&1 || {
            log "ERROR: ANDYHUB_SKIP_BUILD=1 but ${image} is not present locally." >&2
            log "       Either set ANDYHUB_PULL=1 to fetch it, or load it from a tarball:" >&2
            log "         # on a machine with a fast disk:" >&2
            log "         docker save ${API_IMAGE} ${WEB_IMAGE} -o images.tar" >&2
            log "         # copy images.tar to this VM, then:" >&2
            log "         sudo docker load --input images.tar" >&2
            exit 1
        }
    done
    log "using pre-built images (ANDYHUB_SKIP_BUILD=1); no build will run here"
fi

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

if [[ ${SKIP_BUILD} == "1" ]]; then
    log "starting the 704 MB production stack from pre-loaded images"
    COMPOSE_PARALLEL_LIMIT=1 compose up --detach --no-build --remove-orphans
else
    log "building and starting the 704 MB production stack"
    COMPOSE_PARALLEL_LIMIT=1 compose up --detach --build --remove-orphans
fi

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
