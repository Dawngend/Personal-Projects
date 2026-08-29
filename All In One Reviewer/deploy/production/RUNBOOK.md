# AndyHub Phase 6 production cutover

This runbook is for a human operator. None of these commands should be run by an automation agent against production. The target is the existing free-tier VM only: `andy-reviewer-server` (`34.134.184.11`) in project `project-312aa934-7212-437b-b62`, zone `us-central1-a`. Do not create or resize any cloud resource.

The runtime has four containers with hard limits totaling 704 MB: worker 480 MB, API 128 MB, web 64 MB, and proxy 32 MB. A realistic 20-question generation measured peaks of 347.3 MiB for the worker, 81.9 MiB for the API, 40.1 MiB for the web service, and 10.4 MiB for the proxy (479.6 MiB total). Docker adds about 80 MB. The installer adds a persistent 2 GB swapfile, but swap is only a pressure valve. It is not permission to run Streamlit and the new stack together.

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

Get the commit containing this directory onto the VM using the repository's normal fast-forward-only update. Do not copy `.env` files, Cloudflare credentials, or tokens. Resolve the checkout root rather than assuming that the VM has the same monorepo layout as the desktop:

```bash
APP_ROOT="/home/andreipamesa20/School-Works/All In One Reviewer"
```

```bash
GIT_ROOT="$(git -C "${APP_ROOT}" rev-parse --show-toplevel)"
```

```bash
git -C "${GIT_ROOT}" status --short
```

Stop if the checkout has local edits that overlap the incoming commit. Update only with a fast-forward:

```bash
git -C "${GIT_ROOT}" pull --ff-only
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

## 7. Run the local cutover

Make sure nobody is generating a deck. The command disables and stops supervised Streamlit first because both runtimes cannot fit in 954 MB, waits for port 8501 to become free, then builds and starts the constrained stack on that same port. It checks proxy, web, API, and container health. Disabling Streamlit prevents both runtimes from starting after a VM reboot. Any error, timeout, Ctrl+C, or termination signal after Streamlit stop triggers an automatic rollback attempt that frees port 8501 and re-enables Streamlit.

```bash
cd "/home/andreipamesa20/School-Works/All In One Reviewer"
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
