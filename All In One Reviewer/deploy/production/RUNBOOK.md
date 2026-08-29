# AndyHub Phase 6 production cutover

This runbook is for a human operator. None of these commands should be run by an automation agent against production. The target is the existing free-tier VM only: `andy-reviewer-server` (`34.134.184.11`) in project `project-312aa934-7212-437b-b62`, zone `us-central1-a`. Do not create or resize any cloud resource.

The runtime has four containers with hard limits totaling 640 MB: worker 384 MB, API 128 MB, web 96 MB, and proxy 32 MB. Docker adds about 80 MB. The installer adds a persistent 2 GB swapfile, but swap is only a pressure valve. It is not permission to run Streamlit and the new stack together.

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

```bash
sudo chown root:root /etc/andyhub/groq_api_key
```

```bash
sudo chmod 0600 /etc/andyhub/groq_api_key
```

Confirm metadata only. Do not read the file back:

```bash
sudo stat -c '%U %G %a %s bytes' /etc/andyhub/groq_api_key
```

The size must be greater than zero and the mode must be `600`.

## 6. Prepare the Cloudflare dashboard, but do not change it yet

Open Cloudflare Zero Trust in a browser and navigate to **Networks > Tunnels > andyhub-tunnel > Edit > Public Hostname / Published application routes**. Locate the `andyhub.org` route. The connector remains the existing token-mode `cloudflared.service`.

Keep this page open. Do **not** change the route while Streamlit is still the active runtime. The one required cutover edit is:

- From: `http://localhost:8501`
- To: `http://localhost:8080`

Do not create a tunnel, replace the token, add a local Cloudflare config file, or alter DNS.

## 7. Run the local cutover

Make sure nobody is generating a deck. The command disables and stops supervised Streamlit first because both runtimes cannot fit in 954 MB, builds and starts the constrained stack, then checks proxy, web, API, and container health. Disabling Streamlit prevents both runtimes from starting after a VM reboot. Any error, timeout, Ctrl+C, or termination signal after Streamlit stop triggers an automatic rollback attempt that re-enables Streamlit.

```bash
cd "/home/andreipamesa20/School-Works/All In One Reviewer"
sudo ./deploy/production/cutover.sh
```

Do not edit Cloudflare if the script exits nonzero. Confirm the automatic rollback:

```bash
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
```

If the script succeeds, verify the local proxy once more:

```bash
sudo systemctl is-enabled streamlit.service
```

The expected result is `disabled` while the container stack is active.

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/proxy-health
```

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/health
```

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/api/v1/health
```

## 8. Change the Cloudflare route, then verify publicly

Only after all local checks pass, change the `andyhub.org` service in the open Cloudflare dashboard from `http://localhost:8501` to `http://localhost:8080` and save it. Do not restart `cloudflared`; token-mode ingress is delivered from the dashboard.

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

If `cutover.sh` fails before the Cloudflare edit, it automatically attempts to stop the containers and restore Streamlit on port 8501. Leave the dashboard route unchanged and verify `https://andyhub.org`.

If the dashboard has already been changed, or any acceptance check fails, run the rollback command immediately:

```bash
sudo ./deploy/production/rollback.sh
```

Then change the Cloudflare `andyhub.org` service back to `http://localhost:8501`, save it, and verify:

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
