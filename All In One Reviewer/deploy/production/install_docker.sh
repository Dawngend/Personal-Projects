#!/usr/bin/env bash
set -Eeuo pipefail

readonly SWAP_FILE="/swapfile"
readonly SWAP_BYTES=2147483648
readonly DOCKER_REPOSITORY_FILE="/etc/apt/sources.list.d/docker.list"
readonly DOCKER_KEYRING="/etc/apt/keyrings/docker.asc"

log() {
    printf '[andyhub-install] %s\n' "$*"
}

fail() {
    printf '[andyhub-install] ERROR: %s\n' "$*" >&2
    exit 1
}

if [[ ${EUID} -ne 0 ]]; then
    fail "run this script as root: sudo ./deploy/production/install_docker.sh"
fi

if [[ ! -r /etc/os-release ]]; then
    fail "/etc/os-release is missing"
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ ${ID:-} != "ubuntu" ]]; then
    fail "this installer supports Ubuntu only (found ${ID:-unknown})"
fi

install_swap() {
    local available_bytes current_size

    if [[ -e ${SWAP_FILE} ]]; then
        if [[ ! -f ${SWAP_FILE} ]]; then
            fail "${SWAP_FILE} exists but is not a regular file; refusing to replace it"
        fi
        current_size=$(stat --format='%s' "${SWAP_FILE}")
        if [[ ${current_size} -ne ${SWAP_BYTES} ]]; then
            fail "${SWAP_FILE} already exists with ${current_size} bytes; refusing to resize it destructively"
        fi
    else
        available_bytes=$(df --output=avail --block-size=1 / | tail -n 1 | tr -d ' ')
        if [[ ${available_bytes} -lt $((SWAP_BYTES + 1073741824)) ]]; then
            fail "less than 3 GB is free on /; refusing to risk filling the filesystem"
        fi
        log "creating a 2 GB swapfile"
        if ! fallocate --length 2G "${SWAP_FILE}"; then
            rm -f "${SWAP_FILE}"
            dd if=/dev/zero of="${SWAP_FILE}" bs=1M count=2048 status=progress
        fi
        chmod 0600 "${SWAP_FILE}"
        mkswap "${SWAP_FILE}" >/dev/null
    fi

    chmod 0600 "${SWAP_FILE}"
    if ! blkid -p -s TYPE -o value "${SWAP_FILE}" 2>/dev/null | grep -Fxq swap; then
        fail "${SWAP_FILE} exists but is not initialized as swap; refusing to overwrite it"
    fi

    if ! swapon --noheadings --show=NAME | grep -Fxq "${SWAP_FILE}"; then
        log "enabling ${SWAP_FILE}"
        swapon "${SWAP_FILE}"
    fi

    if ! grep -Eq '^/swapfile[[:space:]]+none[[:space:]]+swap[[:space:]]' /etc/fstab; then
        printf '%s\n' '/swapfile none swap sw 0 0' >> /etc/fstab
    fi

    printf '%s\n' 'vm.swappiness=10' > /etc/sysctl.d/99-andyhub-swap.conf
    sysctl --load=/etc/sysctl.d/99-andyhub-swap.conf >/dev/null
}

install_docker() {
    local architecture codename repository_line docker_user

    if command -v docker >/dev/null 2>&1 \
        && docker compose version >/dev/null 2>&1 \
        && systemctl cat docker.service >/dev/null 2>&1; then
        log "Docker Engine and Compose v2 are already installed"
    else
        architecture=$(dpkg --print-architecture)
        codename=${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}
        [[ -n ${codename} ]] || fail "could not determine the Ubuntu codename"

        log "installing Docker Engine and Compose v2 from Docker's Ubuntu repository"
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install --yes ca-certificates curl
        install -m 0755 -d /etc/apt/keyrings
        curl --fail --silent --show-error --location \
            https://download.docker.com/linux/ubuntu/gpg \
            --output "${DOCKER_KEYRING}.tmp"
        chmod 0644 "${DOCKER_KEYRING}.tmp"
        mv -f "${DOCKER_KEYRING}.tmp" "${DOCKER_KEYRING}"

        repository_line="deb [arch=${architecture} signed-by=${DOCKER_KEYRING}] https://download.docker.com/linux/ubuntu ${codename} stable"
        printf '%s\n' "${repository_line}" > "${DOCKER_REPOSITORY_FILE}"
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install --yes \
            docker-ce \
            docker-ce-cli \
            containerd.io \
            docker-buildx-plugin \
            docker-compose-plugin
    fi

    if ! command -v curl >/dev/null 2>&1; then
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install --yes ca-certificates curl
    fi

    systemctl enable --now docker
    docker version >/dev/null
    docker compose version >/dev/null

    docker_user=${DOCKER_USER:-${SUDO_USER:-andreipamesa20}}
    if id "${docker_user}" >/dev/null 2>&1 && ! id -nG "${docker_user}" | tr ' ' '\n' | grep -Fxq docker; then
        usermod --append --groups docker "${docker_user}"
        log "added ${docker_user} to the docker group; a new login is required before non-root Docker use"
    fi
}

install_swap
install_docker

log "installation complete"
swapon --show --bytes
docker --version
docker compose version
