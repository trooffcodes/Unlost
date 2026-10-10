# Unlost

Flask document classification and semantic search, deployed as one Vercel Python function. Documents are processed during the upload request; metadata and embeddings live in Redis. Original files are **not backed up or available for download**.

## Deploy on Vercel

1. Set the project **Root Directory to the repository root** (not `src`). Use the Flask framework preset in `vercel.json` and Python **3.12**, selected by `.python-version`. `app.py` exports the WSGI app; `requirements.txt` installs pinned dependencies. No frontend build command is needed.
2. Configure the following in Vercel Environment Variables for each deployment environment:

   | Variable | Purpose |
   | --- | --- |
   | `SECRET_KEY` | Required stable random signing key, at least 32 characters. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |
   | `REDIS_URL` or `KV_URL` | Required Redis TCP/TLS connection URL. Use `rediss://…` for hosted TLS Redis. REST URLs/tokens alone are not supported. |
   | `GEMINI_API_KEY` | Required for embeddings and metadata fallback. |
   | `ADMIN_PASSWORD` | Optional long, unique dashboard password. The dashboard is disabled when absent. Basic Auth accepts any username. |

   See `.env.example` for optional Groq, OCR and model configuration. Verify the selected model IDs are enabled for your provider account. Do not put secrets into Git or browser JavaScript. Use separate Redis databases and secrets for Preview and Production.
3. Keep Fluid Compute enabled and allow the **300-second** function duration declared in `vercel.json`. Each upload completes before responding; no background thread is expected to survive a response. Provider calls have bounded timeouts. Provider outages produce failed document status, not a false successful library entry.
4. Deploy, then check `/healthz` (Redis connectivity), `/`, and `/static/js/app.js`. Upload a small text file, confirm completed status, search for it, reload, and verify it persists. Open `/dashboard` with the configured password. Confirm an unrelated browser cannot see documents or job status. Finally clear the test data.
5. Enable Vercel Firewall/rate rules and provider billing limits for a publicly accessible deployment. Device sessions are anonymous, not accounts; clearing cookies starts a new library and quota. Do not treat the device quota as an abuse-proof billing boundary. Redis must have suitable persistence, memory capacity and backups; storage failures never fall back to Vercel `/tmp`.

No Vercel project or live provider credentials are included in this repository. Local regression tests do not replace the deployment smoke check above.

## Limits and behavior

- Vercel accepts one document per request, up to **4,000,000 bytes**; the total multipart body is capped at **4,200,000 bytes**, below Vercel's 4.5 MB function payload limit. The browser queues up to 50 files and sends them individually. ZIP uploads on Vercel can contain **one** supported file; multi-file archives require a durable queue/object-storage design before increasing this limit.
- Local development allows 15 MiB files and 50 files per request; extracted archives are capped at 30 MiB. File contents must match their extension. Nested/encrypted archives, empty files, images over 20 megapixels, encrypted PDFs and PDFs over 100 pages are rejected.
- PDF indexing reads embedded text from the first 20 pages. On Vercel, scanned PDFs use Gemini vision on the first two pages. Local development can additionally use LlamaParse and OCR.Space. Long documents may therefore have incomplete search coverage.
- A library holds up to 200 documents. Reuploading the same sanitized filename replaces its metadata. Limits are estimated credits, charged atomically before provider calls (including failed attempts), resetting after 48 hours. Searches also consume credits. Clearing a library preserves usage limits.
- Feedback is limited to 4,000 characters and a validated PNG/JPEG/WebP screenshot of at most 256 KiB. The admin response shows up to 100 users, the latest 50 events and 5 feedback entries to bound the response size; it is not an export of all retained records.
- Optional user/feedback Discord webhooks send that metadata to the configured recipient. `WEBHOOK_FILE`, when explicitly configured, also forwards original uploads to its Discord destination. `WEBHOOK_ERROR` sends generic failure notifications; exception details are not forwarded. Leave all webhooks unset unless this sharing is intended.
- Mutating HTTP requests require `X-Unlost-Request: 1`. The UI adds it automatically. No cross-origin API access is configured.

## Existing deployment migration

Back up Redis before deploying. Existing `vector_db:*`, `token_usage:*`, telemetry and feedback formats are retained. The former unsigned `device_id` cookie is deliberately **not trusted or migrated**: accepting it would let a visitor claim another device's files. Existing browsers receive a new signed session and will need to reupload their documents. Old records remain for administrator-managed retention/migration; do not reassign them based solely on a client-supplied ID. Changing `SECRET_KEY` also invalidates sessions.

If changing `GEMINI_EMBEDDING_MODEL`, reindex existing documents: vectors from different models are not compatible, even when their dimensions match. The supplied default is `gemini-embedding-001`.

## Local development and checks

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
# Fill GEMINI_API_KEY and a stable SECRET_KEY; Redis is optional locally.
.venv/bin/python app.py
```

Open `http://localhost:5000`. Without Redis, JSON storage is for one local process only; it is not a production configuration. The application refuses to start on Vercel without required configuration.

```sh
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
node --test tests/frontend.test.cjs
```

Tests use temporary local storage or an in-memory Redis protocol implementation and stub provider calls. They cover session isolation, CSRF, admin authentication, malformed payloads, upload/archive limits, concurrent storage/quota updates, storage outages, provider fallback and MIME handling, frontend escaping and sequential uploads. CI runs these checks on Python 3.12 and Node 24.
