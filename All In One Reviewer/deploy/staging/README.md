# AndyHub Phase 5 staging rehearsal

This stack is isolated from production by four boundaries: its Compose project is `andyhub-staging`, its data lives only under `.staging/data`, its host listener is `127.0.0.1:8081`, and its optional Cloudflare connector uses a dedicated `andyhub-staging` tunnel for `staging.andyhub.org`. No file or command here changes the `andyhub.org` production route.

## Prepare staging

1. Install Docker Engine with the Compose v2 plugin on the staging VM.
2. Copy `.env.staging.example` to `.env.staging` and keep the result untracked.
3. Create `deploy/staging/secrets/groq_api_key` containing only the staging Groq key. The file is ignored by Git and mounted as a Docker secret.
4. Pause generation writes in the current app, then make a consistent staging state copy:

   ```powershell
   .\.venv\Scripts\python.exe deploy/staging/copy_state.py --source "D:\Personal Projects\All In One Reviewer" --destination .staging/data
   ```

   On the Linux VM, use its production app root and Python executable instead. The script opens production SQLite read-only and uses SQLite's backup API, copies `uploads`, `extraction_cache`, and `course_brain_db`, writes SHA-256 hashes to `STATE_MANIFEST.json`, and never writes into the source. If staging already exists, add `--replace`; the prior copy is renamed to `.staging/data.previous-<timestamp>` instead of being deleted. Keep production generation paused while Chroma, uploads, and extraction cache are copied so those directories describe the same point in time.

## Bring up the isolated stack

From the repository root:

```bash
docker compose --env-file deploy/staging/.env.staging -f compose.staging.yaml up -d --build
```

The reverse proxy is reachable only at `http://127.0.0.1:8081`. It routes `/api/v1/*`, `/docs`, `/redoc`, and `/openapi.json` to FastAPI and everything else to Next.js. Check all services with `docker compose --env-file deploy/staging/.env.staging -f compose.staging.yaml ps`.

## Run both smoke tests as one command

```bash
docker compose --env-file deploy/staging/.env.staging -f compose.staging.yaml --profile smoke run --rm smoke
```

The smoke container checks proxy, web, API, and worker health; sends 24 concurrent workspace loads and enforces a 3-second p95; creates an image-only PPTX; runs the real Tesseract extraction path; and feeds the four OCR results through the labelled-set, symbolic-vector, and component-assignment grading paths fixed in Part 1.

## Attach the dedicated staging hostname

Create a new Cloudflare tunnel named `andyhub-staging`; do not reuse the production tunnel or its credentials. Copy `cloudflared/config.yml.example` to the ignored `cloudflared/config.yml`, replace `<STAGING_TUNNEL_UUID>`, place that tunnel's credential JSON at the ignored `cloudflared/credentials.json`, and create only the `staging.andyhub.org` DNS route for the new tunnel. Then start the connector without altering the core stack:

```bash
docker compose --env-file deploy/staging/.env.staging -f compose.staging.yaml --profile tunnel up -d tunnel
```

The committed ingress has one hostname, `staging.andyhub.org`, and points to the staging proxy over the private Compose network. Production cutover, production DNS changes, and the existing `andyhub.org` tunnel route remain Phase 6 work.

## Stop or refresh staging

Stop only this Compose project:

```bash
docker compose --env-file deploy/staging/.env.staging -f compose.staging.yaml down
```

To refresh state, stop staging, rerun `copy_state.py` with `--replace`, and bring staging up again. Never run the copy script with the production root as its destination.
