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

# Verify the rollback TARGET is installable before destroying the thing we are
# rolling back from. `docker compose down` below removes all four containers
# and frees 8501; if streamlit.service turns out to be missing or unloadable we
# would already have torn down a degraded-but-serving stack and have nothing to
# fall back to. Check first, fail with the site still up.
if ! systemctl cat streamlit.service >/dev/null 2>&1; then
    log "CRITICAL: streamlit.service is not installed; refusing to tear down the container stack" >&2
    log "          install it first: sudo install -m 0644 deploy/production/streamlit.service /etc/systemd/system/" >&2
    exit 1
fi

legacy_entrypoint="${DATA_HOST_ROOT}/app.py"
legacy_python="${DATA_HOST_ROOT}/.venv/bin/python"
for required in "${legacy_entrypoint}" "${legacy_python}"; do
    if [[ ! -e ${required} ]]; then
        log "CRITICAL: the Streamlit rollback target is incomplete: ${required} is missing" >&2
        log "          refusing to tear down the container stack with no working fallback" >&2
        exit 1
    fi
done

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

    # `docker ps` failing must NOT read as "no containers are running". A wedged
    # daemon is exactly the condition that makes an operator reach for rollback,
    # and treating its error as an empty list would start Streamlit while the
    # old containers still hold port 8501.
    if ! container_ids=$(docker ps --quiet --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}"); then
        log "CRITICAL: could not query Docker for running containers; refusing to start Streamlit blind" >&2
        exit 1
    fi
    mapfile -t running_containers <<<"${container_ids}"
    if [[ ${#running_containers[@]} -gt 0 && -n ${running_containers[0]} ]]; then
        docker stop "${running_containers[@]}" >/dev/null || stack_status=$?
    fi

    if ! container_ids=$(docker ps --quiet --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}"); then
        log "CRITICAL: could not re-query Docker after stopping containers" >&2
        exit 1
    fi
    mapfile -t running_containers <<<"${container_ids}"
    if [[ ${#running_containers[@]} -gt 0 && -n ${running_containers[0]} ]]; then
        log "CRITICAL: containers are still running; refusing to start Streamlit concurrently" >&2
        exit 1
    fi
elif systemctl is-active --quiet docker.service; then
    log "CRITICAL: Docker is active but its CLI is unavailable; refusing to start Streamlit without checking containers" >&2
    exit 1
fi

# Deliberately NOT an abort. The authoritative check above already proved that
# no project container is running, so reaching this point with a nonzero
# stack_status means `docker stop` complained about something benign, typically
# a container that had already exited. Aborting here left the containers down
# AND Streamlit never started, turning a recoverable rollback into an outage.
if [[ ${stack_status} -ne 0 ]]; then
    log "note: docker stop reported ${stack_status}, but no project container is running; continuing"
fi

# Nothing should hold 8501 now. If something does, starting Streamlit would
# fail to bind and report a confusing unit error instead of the real cause.
if ss --tcp --listening --no-header "sport = :8501" 2>/dev/null | grep --quiet .; then
    log "CRITICAL: port 8501 is still held after the stack was stopped; not starting Streamlit" >&2
    ss --tcp --listening --processes "sport = :8501" >&2 || true
    exit 1
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
