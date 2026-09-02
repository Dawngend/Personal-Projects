#!/usr/bin/env bash
# Restarts AndyHub production containers that Docker has marked unhealthy.
#
# Why this exists: every service in compose.production.yaml carries both a
# healthcheck and `restart: unless-stopped`, which reads as if the two
# cooperate. They do not. Docker's restart policy reacts to a process EXIT and
# ignores health status entirely, so a wedged-but-alive container stays
# unhealthy forever with nothing acting on it and nothing reporting it. That
# was the one unaddressed critical from the overnight audit.
#
# Alerting is journald only by design: it needs no credentials on the VM.
# `journalctl -u andyhub-watchdog` is the record. Every restart logs at
# warning and every give-up at error, so a future alerting path only has to
# watch this unit's priority levels.
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPOSE_FILE="${SCRIPT_DIR}/compose.production.yaml"
readonly COMPOSE_PROJECT="andyhub-production"
readonly SERVICES=(api worker web proxy)

# Same lock cutover.sh and rollback.sh take. A deploy stops containers on
# purpose; without this the watchdog would race it and restart containers out
# from under a cutover, or "recover" a stack that rollback.sh is deliberately
# tearing down.
readonly LOCK_FILE=/run/lock/andyhub-cutover.lock

# STATE_DIRECTORY is set by systemd (StateDirectory=andyhub-watchdog). The
# fallback keeps the script runnable by hand for testing.
readonly STATE_DIR="${STATE_DIRECTORY:-/var/lib/andyhub-watchdog}"

# A container that comes back unhealthy this many times running is not going to
# be fixed by another restart. Stop and stay loud rather than restart-looping a
# broken image forever.
readonly MAX_CONSECUTIVE_RESTARTS="${ANDYHUB_WATCHDOG_MAX_RESTARTS:-3}"

log() {
    printf '[andyhub-watchdog] %s\n' "$*"
}

err() {
    printf '[andyhub-watchdog] %s\n' "$*" >&2
}

compose() {
    docker compose --project-name "${COMPOSE_PROJECT}" --file "${COMPOSE_FILE}" "$@"
}

restart_count() {
    local file="${STATE_DIR}/${1}.restarts"
    [[ -r ${file} ]] && cat "${file}" || printf '0'
}

set_restart_count() {
    local service="$1" count="$2"
    printf '%s' "${count}" > "${STATE_DIR}/${service}.restarts"
}

main() {
    mkdir -p "${STATE_DIR}"

    exec 9>"${LOCK_FILE}"
    if ! flock --nonblock 9; then
        log "a cutover or rollback holds ${LOCK_FILE}; skipping this pass"
        return 0
    fi

    local service container_id health count

    for service in "${SERVICES[@]}"; do
        container_id="$(compose ps --quiet "${service}" 2>/dev/null || true)"
        if [[ -z ${container_id} ]]; then
            # The whole stack is down, or this service was never created.
            # Deliberately NOT `compose up`: bringing production up is a
            # deploy decision, and cutover.sh owns it.
            err "ERROR: ${service} has no container; the stack is not running. Manual intervention required."
            continue
        fi

        # A container without a healthcheck reports no Status field. Treat the
        # empty case as "nothing to judge" rather than as unhealthy.
        health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "${container_id}" 2>/dev/null || true)"

        case "${health}" in
            healthy|starting|"")
                # `starting` means still inside start_period. The worker's is
                # 180s and legitimately uses it; restarting there would create
                # exactly the boot loop this script is meant to prevent.
                count="$(restart_count "${service}")"
                if [[ ${count} != 0 ]]; then
                    log "${service} is ${health:-unmonitored} again after ${count} restart(s); clearing its counter"
                    set_restart_count "${service}" 0
                fi
                ;;
            unhealthy)
                count="$(restart_count "${service}")"
                if (( count >= MAX_CONSECUTIVE_RESTARTS )); then
                    err "ERROR: ${service} still unhealthy after ${count} consecutive restarts; giving up. Manual intervention required."
                    continue
                fi
                count=$(( count + 1 ))
                err "WARNING: ${service} is unhealthy; restarting (attempt ${count}/${MAX_CONSECUTIVE_RESTARTS})"
                set_restart_count "${service}" "${count}"
                if docker restart "${container_id}" >/dev/null; then
                    log "${service} restarted"
                else
                    err "ERROR: docker restart failed for ${service}"
                fi
                ;;
            *)
                err "ERROR: ${service} reports unexpected health status '${health}'"
                ;;
        esac
    done
}

main "$@"
