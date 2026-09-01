# AndyHub Phase 6 production cutover

This runbook is for a human operator. None of these commands should be run by an automation agent against production. The target is the existing free-tier VM only: `andy-reviewer-server` (`34.134.184.11`) in project `project-312aa934-7212-437b-b62`, zone `us-central1-a`. Do not create or resize any cloud resource.

The runtime has four containers with hard limits totaling 704 MB: worker 480 MB, API 128 MB, web 64 MB, and proxy 32 MB. A realistic 20-question generation measured peaks of 347.3 MiB for the worker, 81.9 MiB for the API, 40.1 MiB for the web service, and 10.4 MiB for the proxy (479.6 MiB total). Docker adds about 80 MB. The installer adds a persistent 2 GB swapfile, but swap is only a pressure valve. It is not permission to run Streamlit and the new stack together.

## 0. Verify the commit is on origin

From the workstation, compare local `HEAD` with `origin/main`:

```powershell
git -C "D:/Personal Projects" rev-parse HEAD
```

```powershell
git -C "D:/Personal Projects" ls-remote origin main
```

Fetch the remote commit without changing the workstation branch, then prove that the deploy directory exists in that exact remote tree:

```powershell
git -C "D:/Personal Projects" fetch origin main
```

```powershell
git -C "D:/Personal Projects" ls-tree -d --name-only FETCH_HEAD -- "All In One Reviewer/deploy/production"
```

The last command must print `All In One Reviewer/deploy/production`. Stop if it prints nothing, or if the commit containing the intended production changes is only in local `HEAD`. The VM can receive only commits that are on `origin`; a local-only commit cannot be pulled or cloned there.

## 1. Connect to the VM

The gcloud syntax must be checked locally before the connection command is used.

- **Step 1**: Syntax Validation via `gcloud help compute ssh`
- **Step 2**: Parameter Verification (confirming required and optional flags, and explicitly checking if the `--dry-run` or `--validate-only` flag is supported)
- **Step 3**: Dry-Run Command Proposal (If `--dry-run` or `--validate-only` is supported, there MUST be a `--dry-run` or `--validate-only` invocation before the next step.)
- **Step 4**: Command Proposal & Authorization (If the command is on the "Prohibited Operations" denylist, state that autonomous execution is forbidden, and the user MUST be explicitly asked for authorization to proceed. If the command is NOT on the denylist, propose or proceed with execution, while following *ALL* "Execution Constraints" below.)

Run each command separately. The verified leaf help shows that `--dry-run` is supported.

```powershell
gcloud help compute ssh
```

```powershell
gcloud compute ssh andreipamesa20@andy-reviewer-server --dry-run --quiet --project=project-312aa934-7212-437b-b62 --zone=us-central1-a
```

Inspect the printed native SSH command. It must name `andy-reviewer-server` in `us-central1-a`. Then connect:

```powershell
gcloud compute ssh andreipamesa20@andy-reviewer-server --quiet --project=project-312aa934-7212-437b-b62 --zone=us-central1-a
```

`gcloud compute ssh` is not on the prohibited-operations list. This runbook does not authorize any other GCP command.

## 2. Stage the files without touching the running process

Get the commit containing this directory from `Dawngend/Personal-Projects`, not `Dawngend/School-Works`. The School-Works checkout contains the legacy Streamlit app and does not contain this deployment stack. Do not copy `.env` files, Cloudflare credentials, or tokens.

```bash
LEGACY_ROOT="/home/andreipamesa20/School-Works/All In One Reviewer"   # legacy Streamlit, rollback target, DO NOT DELETE
APP_ROOT="/home/andreipamesa20/Personal-Projects/All In One Reviewer" # new stack
PERSONAL_PROJECTS_ROOT="/home/andreipamesa20/Personal-Projects"
```

These roots are permanently different after the Phase 6 move: `LEGACY_ROOT` holds the live production **data**, while `APP_ROOT` holds the new stack's **code**. Do not move the bind sources into the Personal-Projects checkout or point the data-root override at `APP_ROOT`.

For a first-time checkout, clone `Personal-Projects` into the path above:

```bash
if [[ ! -e "${PERSONAL_PROJECTS_ROOT}" ]]; then
    git clone --branch main --single-branch https://github.com/Dawngend/Personal-Projects.git "${PERSONAL_PROJECTS_ROOT}"
fi
```

If the checkout already exists, inspect it first:

```bash
if [[ -d "${PERSONAL_PROJECTS_ROOT}/.git" ]]; then
    git -C "${PERSONAL_PROJECTS_ROOT}" status --short
else
    echo "ERROR: ${PERSONAL_PROJECTS_ROOT} exists but is not a Git checkout" >&2
    false
fi
```

Stop if the checkout has local edits that overlap the incoming commit. Update only with a fast-forward:

```bash
git -C "${PERSONAL_PROJECTS_ROOT}" pull --ff-only
```

Confirm that these files exist:

```bash
ls -l "${APP_ROOT}/deploy/production"
```

Move into the app root for the remaining commands:

```bash
cd "${APP_ROOT}"
```

Make the scripts executable. This changes only repository file modes:

```bash
chmod 0755 deploy/production/install_docker.sh deploy/production/cutover.sh deploy/production/rollback.sh
```

Check free space before downloading packages and images:

```bash
df -h /
```

Abort if the root filesystem has less than 6 GB free. Do not attach a disk or resize the VM.

## 3. Install Docker and the 2 GB swapfile

```bash
sudo ./deploy/production/install_docker.sh
```

Verify the result:

```bash
sudo docker version
```

```bash
sudo docker compose version
```

```bash
swapon --show
```

The installer is safe to re-run. If `/swapfile` already exists with a different size or is not a swapfile, it aborts instead of overwriting it.

## 4. Install and prove the supervised Streamlit rollback target

Install the unit without starting a second Streamlit process:

```bash
sudo install -m 0644 deploy/production/streamlit.service /etc/systemd/system/streamlit.service
```

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl enable streamlit.service
```

Validate the unit and inspect the current bare process:

```bash
sudo systemd-analyze verify /etc/systemd/system/streamlit.service
```

```bash
pgrep -u andreipamesa20 -af 'streamlit run app.py --server.port 8501 --server.address 0.0.0.0'
```

The process listing must show exactly the known Streamlit command. Record its PID, then stop only that PID gracefully:

```bash
sudo kill -INT <STREAMLIT_PID>
```

Start the same command under systemd and verify it before continuing:

```bash
sudo systemctl start streamlit.service
```

```bash
sudo systemctl --no-pager --full status streamlit.service
```

```bash
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
```

If this check fails, do not proceed. Review `sudo journalctl -u streamlit.service -n 100 --no-pager` and restore Streamlit first.

## 5. Create the API secret file without printing it

The Compose stack does not read the Cloudflare token. Leave `/etc/cloudflared/cloudflared.env` and `cloudflared.service` unchanged.

```bash
sudo install -d -m 0700 -o root -g root /etc/andyhub
```

Use an interactive editor to place only the existing Groq API key in the file. Do not use `echo`, command history, logs, or the terminal screen to display it:

```bash
sudoedit /etc/andyhub/groq_api_key
```

The secret must be owned by the **application user**, not by root. Compose bind-mounts this file into the container with its own ownership, and the containers run as that user. A `root:root` file is unreadable to them: the API then reports `generator: unconfigured`, its health endpoint returns 503 indefinitely, and the cutover fails waiting on that dependency while every other check looks correct. A rehearsal reproduced exactly this.

```bash
sudo chown andreipamesa20:andreipamesa20 /etc/andyhub/groq_api_key
```

```bash
sudo chmod 0600 /etc/andyhub/groq_api_key
```

The directory must also be traversable by that user. A `0700` mode on `/etc/andyhub` blocks access before the file's own mode is ever consulted:

```bash
sudo chmod 0711 /etc/andyhub
```

Confirm metadata only. Do not read the file back:

```bash
sudo stat -c '%U %G %a %s bytes' /etc/andyhub/groq_api_key
```

The size must be greater than zero, the mode must be `600`, and the owner must be `andreipamesa20`.

Then confirm the container user can actually read it. This is the check that matters, and the one a root shell cannot perform for you, because root can read the file regardless:

```bash
sudo runuser -u andreipamesa20 -- test -r /etc/andyhub/groq_api_key && echo readable
```

It must print `readable`. `cutover.sh` performs this same test and refuses to start if it fails.

## 6. Confirm the fixed port handoff

The existing token-mode Cloudflare tunnel already sends `andyhub.org` to `localhost:8501`. The production proxy publishes on that same loopback port after Streamlit releases it. The tunnel configuration, dashboard ingress, token file, service, and DNS are never touched during cutover or rollback. No Cloudflare dashboard access is needed.

Confirm that the supervised Streamlit process is the only listener on port 8501:

```bash
sudo ss --tcp --listening --processes 'sport = :8501'
```

Stop if this shows any listener other than the expected Streamlit process. `cutover.sh` performs the same preflight and aborts before stopping Streamlit if port 8501 has an unmanaged listener.

## 6b. Back up production state before cutover

Make sure nobody is generating a deck or using the study session. Resolve the live source paths from the API bind mounts in `compose.production.yaml`; do not assume that they live under the new checkout. The Compose defaults intentionally point at `LEGACY_ROOT`, which is the live Streamlit state and rollback target.

The VM does not have the `sqlite3` command-line client, and its EOL Ubuntu package archives are not a reliable installation source. Do not add it as a cutover dependency. `/usr/bin/python3` is already present and exposes SQLite's C-level online backup API through the standard-library `sqlite3` module.

`repositories.py` enables WAL mode, so copying or tarring the live `reviewer.db` file can omit committed WAL transactions or capture an inconsistent page. The block below opens the source read-only, calls `Connection.backup()` to include committed WAL contents safely even with a concurrent writer, and refuses to create an archive unless the resulting snapshot returns exactly `ok` from `PRAGMA integrity_check`.

Run this block as one command. It fails if any required mount or source is missing, writes the timestamped archive outside every Git checkout, and prints its path and byte size:

```bash
(
    set -Eeuo pipefail

    COMPOSE_BIND_SOURCES="$(
        sudo env -u ANDYHUB_DATA_HOST_ROOT docker compose \
            --file "${APP_ROOT}/deploy/production/compose.production.yaml" \
            config --format json |
        python3 -c '
import json
import sys

config = json.load(sys.stdin)
binds = {
    volume["target"]: volume["source"]
    for volume in config["services"]["api"]["volumes"]
    if volume.get("type") == "bind"
}
for target in (
    "/data/Database",
    "/data/uploads",
    "/data/extraction_cache",
    "/data/course_brain_db",
):
    print(binds[target])
'
    )"

    mapfile -t LIVE_PATHS <<<"${COMPOSE_BIND_SOURCES}"
    [[ ${#LIVE_PATHS[@]} -eq 4 ]]

    DATABASE_PATH="$(realpath -e "${LIVE_PATHS[0]}/reviewer.db")"
    UPLOADS_PATH="$(realpath -e "${LIVE_PATHS[1]}")"
    EXTRACTION_CACHE_PATH="$(realpath -e "${LIVE_PATHS[2]}")"
    COURSE_BRAIN_PATH="$(realpath -e "${LIVE_PATHS[3]}")"
    [[ -f "${DATABASE_PATH}" ]]
    [[ "$(basename "${UPLOADS_PATH}")" == "uploads" ]]
    [[ "$(basename "${EXTRACTION_CACHE_PATH}")" == "extraction_cache" ]]
    [[ "$(basename "${COURSE_BRAIN_PATH}")" == "course_brain_db" ]]

    BACKUP_ROOT="/home/andreipamesa20/andyhub-backups"
    BACKUP_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    BACKUP_ARCHIVE="${BACKUP_ROOT}/andyhub-production-${BACKUP_TIMESTAMP}.tar.gz"
    BACKUP_PARTIAL="${BACKUP_ARCHIVE}.partial"
    sudo install -d -m 0700 "${BACKUP_ROOT}"

    BACKUP_STAGING="$(
        sudo mktemp --directory \
            --tmpdir="${BACKUP_ROOT}" \
            ".andyhub-backup-${BACKUP_TIMESTAMP}.XXXXXX"
    )"
    [[ "${BACKUP_STAGING}" == "${BACKUP_ROOT}/.andyhub-backup-${BACKUP_TIMESTAMP}."* ]]
    sudo chmod 0700 "${BACKUP_STAGING}"
    trap 'sudo rm -rf -- "${BACKUP_STAGING}"; sudo rm -f -- "${BACKUP_PARTIAL}"' EXIT
    sudo install -d -m 0700 "${BACKUP_STAGING}/Database"
    SQLITE_SNAPSHOT="${BACKUP_STAGING}/Database/reviewer.db"

    [[ -x /usr/bin/python3 ]] || {
        echo "ERROR: /usr/bin/python3 is required for the SQLite backup" >&2
        exit 1
    }
    sudo /usr/bin/python3 - "${DATABASE_PATH}" "${SQLITE_SNAPSHOT}" <<'PY'
import sqlite3
import sys

source, staging = sys.argv[1:3]
src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
dst = sqlite3.connect(staging)
try:
    with dst:
        src.backup(dst)
    row = dst.execute("PRAGMA integrity_check").fetchone()[0]
finally:
    dst.close()
    src.close()
if row != "ok":
    print(f"snapshot integrity_check returned: {row}", file=sys.stderr)
sys.exit(0 if row == "ok" else 1)
PY

    sudo tar --create --gzip --file "${BACKUP_PARTIAL}" \
        --directory "${BACKUP_STAGING}" "Database/reviewer.db" \
        --directory "$(dirname "${UPLOADS_PATH}")" "uploads" \
        --directory "$(dirname "${EXTRACTION_CACHE_PATH}")" "extraction_cache" \
        --directory "$(dirname "${COURSE_BRAIN_PATH}")" "course_brain_db"
    sudo mv -- "${BACKUP_PARTIAL}" "${BACKUP_ARCHIVE}"

    printf 'Backup archive: %s\n' "${BACKUP_ARCHIVE}"
    sudo stat --format 'Archive size: %s bytes' "${BACKUP_ARCHIVE}"
)
```

The subshell must exit successfully and print a nonzero archive size. Do not proceed with cutover if this step fails. If production data is later corrupted, use the restore procedure in section 9b. `rollback.sh` cannot restore data.

## 7. Run the local cutover

Make sure nobody is generating a deck. The command disables and stops supervised Streamlit first because both runtimes cannot fit in 954 MB, waits for port 8501 to become free, then builds and starts the constrained stack on that same port. It checks proxy, web, API, and container health. Disabling Streamlit prevents both runtimes from starting after a VM reboot. Any error, timeout, Ctrl+C, or termination signal after Streamlit stop triggers an automatic rollback attempt that frees port 8501 and re-enables Streamlit.

```bash
cd "${APP_ROOT}" # new Personal-Projects stack; the legacy service remains at LEGACY_ROOT for rollback
sudo ./deploy/production/cutover.sh
```

If the script exits nonzero, confirm the automatic rollback. The unchanged tunnel continues using port 8501:

```bash
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
```

If the script succeeds, verify the local proxy once more:

```bash
sudo systemctl is-enabled streamlit.service
```

The expected result is `disabled` while the container stack is active.

```bash
curl --fail --silent --show-error http://127.0.0.1:8501/proxy-health
```

```bash
curl --fail --silent --show-error http://127.0.0.1:8501/health
```

```bash
curl --fail --silent --show-error http://127.0.0.1:8501/api/v1/health
```

## 8. Verify publicly

The tunnel keeps forwarding to `localhost:8501`, which is now owned by the production proxy. Do not open or edit the Cloudflare dashboard and do not restart `cloudflared`.

From a separate terminal or device, verify all three paths:

```bash
curl --fail --silent --show-error https://andyhub.org/health
```

```bash
curl --fail --silent --show-error https://andyhub.org/api/v1/health
```

```bash
curl --fail --silent --show-error --output /dev/null https://andyhub.org/
```

Then complete the desktop and mobile acceptance pass: upload a mixed document, generate a deck, complete every card type, reload the workspace, and confirm the deck and quiz state persist.

Monitor memory and restarts during one real generation:

```bash
free -h
```

```bash
sudo docker stats --no-stream
```

```bash
sudo docker compose --project-name andyhub-production --file deploy/production/compose.production.yaml ps
```

```bash
sudo docker compose --project-name andyhub-production --file deploy/production/compose.production.yaml logs --tail 100
```

Never run `docker compose down -v`. Application state is bind-mounted from the existing `Database`, `uploads`, `extraction_cache`, and `course_brain_db` directories.

## 9. Abort or roll back

If `cutover.sh` fails, it automatically attempts to stop the containers and restore Streamlit on port 8501. The unchanged tunnel follows the restored service automatically. Verify `https://andyhub.org`.

Rollback changes which runtime is serving. It does not restore the database, uploads, extraction cache, or course memory. If any of those are corrupted, follow section 9b instead of treating `rollback.sh` as data recovery.

If any acceptance check fails, run the rollback command immediately:

```bash
sudo ./deploy/production/rollback.sh
```

No Cloudflare action is required before or after rollback. Verify the restored Streamlit endpoint:

```bash
curl --fail --silent --show-error https://andyhub.org/_stcore/health
```

The rollback command re-enables `streamlit.service`, so a VM reboot continues to restore the legacy runtime rather than the stopped container stack.

If the rollback command reports that Streamlit is not healthy, inspect:

```bash
sudo systemctl --no-pager --full status streamlit.service
```

```bash
sudo journalctl -u streamlit.service -n 100 --no-pager
```

Do not delete containers, images, data directories, the swapfile, the Cloudflare unit, or either secret file while diagnosing. The rollback script is idempotent and safe to run again.

## 9b. Restore production data from a backup archive

This is the **only recovery path from production data corruption**. `rollback.sh` restores the legacy service, not the data. A restore replaces the database, uploads, extraction cache, and course memory, so select the archive deliberately and keep the automatic pre-restore quarantine until the restored runtime has passed acceptance.

List the available archives outside the repositories:

```bash
BACKUP_ROOT="/home/andreipamesa20/andyhub-backups"
sudo find "${BACKUP_ROOT}" -maxdepth 1 -type f \
    -name 'andyhub-production-*.tar.gz' \
    -printf '%TY-%Tm-%Td %TH:%TM:%TS %s bytes %p\n' | sort
```

Set the exact archive selected from that output, then confirm its contents before stopping anything:

```bash
RESTORE_ARCHIVE="/home/andreipamesa20/andyhub-backups/andyhub-production-YYYYMMDDTHHMMSSZ.tar.gz"
sudo test -f "${RESTORE_ARCHIVE}"
sudo tar --list --gzip --file "${RESTORE_ARCHIVE}"
```

The listing must contain `Database/reviewer.db`, `uploads/`, `extraction_cache/`, and `course_brain_db/`. Run the following block as one command. It resolves the destinations from the same Compose bind mounts used in section 6b, validates the archived database before replacing anything, stops whichever runtime is serving, preserves the displaced state in a timestamped quarantine, verifies the installed database, and restarts the same runtime:

```bash
(
    set -Eeuo pipefail

    [[ -f "${RESTORE_ARCHIVE}" ]]
    [[ -x /usr/bin/python3 ]] || {
        echo "ERROR: /usr/bin/python3 is required for SQLite verification" >&2
        exit 1
    }

    verify_sqlite_integrity() {
        local database_path=$1
        sudo /usr/bin/python3 - "${database_path}" <<'PY'
import sqlite3
import sys

database_path = sys.argv[1]
database = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
try:
    row = database.execute("PRAGMA integrity_check").fetchone()[0]
finally:
    database.close()
if row != "ok":
    print(f"integrity_check returned: {row}", file=sys.stderr)
sys.exit(0 if row == "ok" else 1)
PY
    }

    COMPOSE_BIND_SOURCES="$(
        sudo env -u ANDYHUB_DATA_HOST_ROOT docker compose \
            --file "${APP_ROOT}/deploy/production/compose.production.yaml" \
            config --format json |
        python3 -c '
import json
import sys

config = json.load(sys.stdin)
binds = {
    volume["target"]: volume["source"]
    for volume in config["services"]["api"]["volumes"]
    if volume.get("type") == "bind"
}
for target in (
    "/data/Database",
    "/data/uploads",
    "/data/extraction_cache",
    "/data/course_brain_db",
):
    print(binds[target])
'
    )"

    mapfile -t LIVE_PATHS <<<"${COMPOSE_BIND_SOURCES}"
    [[ ${#LIVE_PATHS[@]} -eq 4 ]]

    DATABASE_PATH="$(realpath -e "${LIVE_PATHS[0]}/reviewer.db")"
    UPLOADS_PATH="$(realpath -e "${LIVE_PATHS[1]}")"
    EXTRACTION_CACHE_PATH="$(realpath -e "${LIVE_PATHS[2]}")"
    COURSE_BRAIN_PATH="$(realpath -e "${LIVE_PATHS[3]}")"

    RESTORE_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    RESTORE_STAGING="$(
        sudo mktemp --directory \
            --tmpdir="${BACKUP_ROOT}" \
            ".andyhub-restore-${RESTORE_TIMESTAMP}.XXXXXX"
    )"
    [[ "${RESTORE_STAGING}" == "${BACKUP_ROOT}/.andyhub-restore-${RESTORE_TIMESTAMP}."* ]]
    sudo chmod 0700 "${RESTORE_STAGING}"
    sudo tar --extract --gzip --file "${RESTORE_ARCHIVE}" \
        --directory "${RESTORE_STAGING}"

    [[ -f "${RESTORE_STAGING}/Database/reviewer.db" ]]
    [[ -d "${RESTORE_STAGING}/uploads" ]]
    [[ -d "${RESTORE_STAGING}/extraction_cache" ]]
    [[ -d "${RESTORE_STAGING}/course_brain_db" ]]

    verify_sqlite_integrity \
        "${RESTORE_STAGING}/Database/reviewer.db"

    STREAMLIT_WAS_ACTIVE=0
    STACK_WAS_ACTIVE=0
    if sudo systemctl is-active --quiet streamlit.service; then
        STREAMLIT_WAS_ACTIVE=1
    fi
    if sudo docker ps --quiet \
        --filter 'label=com.docker.compose.project=andyhub-production' |
        grep -q .; then
        STACK_WAS_ACTIVE=1
    fi
    if [[ $((STREAMLIT_WAS_ACTIVE + STACK_WAS_ACTIVE)) -ne 1 ]]; then
        echo "ERROR: expected exactly one serving runtime; nothing was changed" >&2
        exit 1
    fi

    if [[ ${STACK_WAS_ACTIVE} -eq 1 ]]; then
        sudo docker compose --project-name andyhub-production \
            --file "${APP_ROOT}/deploy/production/compose.production.yaml" \
            down --remove-orphans
    else
        sudo systemctl stop streamlit.service
    fi

    PRE_RESTORE_ROOT="${BACKUP_ROOT}/pre-restore-${RESTORE_TIMESTAMP}"
    sudo install -d -m 0700 "${PRE_RESTORE_ROOT}"
    DATABASE_UID="$(sudo stat --format '%u' "${DATABASE_PATH}")"
    DATABASE_GID="$(sudo stat --format '%g' "${DATABASE_PATH}")"
    DATABASE_MODE="$(sudo stat --format '%a' "${DATABASE_PATH}")"

    sudo mv -- "${DATABASE_PATH}" "${PRE_RESTORE_ROOT}/reviewer.db"
    for suffix in -wal -shm -journal; do
        if [[ -e "${DATABASE_PATH}${suffix}" ]]; then
            sudo mv -- "${DATABASE_PATH}${suffix}" \
                "${PRE_RESTORE_ROOT}/reviewer.db${suffix}"
        fi
    done
    sudo mv -- "${UPLOADS_PATH}" "${PRE_RESTORE_ROOT}/uploads"
    sudo mv -- "${EXTRACTION_CACHE_PATH}" \
        "${PRE_RESTORE_ROOT}/extraction_cache"
    sudo mv -- "${COURSE_BRAIN_PATH}" \
        "${PRE_RESTORE_ROOT}/course_brain_db"

    sudo install -m "${DATABASE_MODE}" \
        -o "${DATABASE_UID}" -g "${DATABASE_GID}" \
        "${RESTORE_STAGING}/Database/reviewer.db" "${DATABASE_PATH}"
    sudo mv -- "${RESTORE_STAGING}/uploads" "${UPLOADS_PATH}"
    sudo mv -- "${RESTORE_STAGING}/extraction_cache" \
        "${EXTRACTION_CACHE_PATH}"
    sudo mv -- "${RESTORE_STAGING}/course_brain_db" \
        "${COURSE_BRAIN_PATH}"

    verify_sqlite_integrity "${DATABASE_PATH}"

    if [[ ${STREAMLIT_WAS_ACTIVE} -eq 1 ]]; then
        sudo systemctl enable --now streamlit.service
        curl --fail --silent --show-error \
            http://127.0.0.1:8501/_stcore/health
    else
        APP_UID="$(id -u andreipamesa20)"
        APP_GID="$(id -g andreipamesa20)"
        sudo env -u ANDYHUB_DATA_HOST_ROOT \
            ANDYHUB_UID="${APP_UID}" ANDYHUB_GID="${APP_GID}" \
            docker compose --project-name andyhub-production \
            --file "${APP_ROOT}/deploy/production/compose.production.yaml" \
            up --detach --remove-orphans

        RESTORE_HEALTHY=0
        for _ in {1..84}; do
            if curl --fail --silent --show-error --max-time 5 \
                http://127.0.0.1:8501/api/v1/health >/dev/null 2>&1; then
                RESTORE_HEALTHY=1
                break
            fi
            sleep 5
        done
        [[ ${RESTORE_HEALTHY} -eq 1 ]]
        curl --fail --silent --show-error \
            http://127.0.0.1:8501/proxy-health
        curl --fail --silent --show-error \
            http://127.0.0.1:8501/api/v1/health
    fi

    printf 'Restore completed. Pre-restore state retained at: %s\n' \
        "${PRE_RESTORE_ROOT}"
)
```

If the block fails after stopping the runtime, leave the runtime stopped and inspect the printed error. Do not delete the `pre-restore-*` quarantine. It is the recoverable copy of the state that was displaced during the restore.
