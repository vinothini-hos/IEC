# IEC — Mailbox Module

Inbox / thread view / reply, backed by the Gmail API, built as the first
module of the larger RFQ-to-proposal workflow app.

## Scope (this pass)

- Inbox: incoming emails grouped by `thread_id`
- Thread view: all emails in a thread, chronological, incoming vs outgoing
  clearly distinguished
- Reply within a thread, or send a new email
- Sender / recipient / subject / timestamp / attachments / body
- Unread / read state (auto-marks read when a thread is opened)

Everything else in the sidebar (Proposals, Reviews, Historical Matches,
etc.) is a placeholder for later modules — not built yet.

## Stack

- Frontend: React (Vite) + react-router-dom
- Backend: FastAPI
- DB: PostgreSQL (SQLAlchemy)
- Email: Gmail API, using the OAuth client + Pub/Sub push setup
  (`gmail-notifications` topic / `gmail-notifications-sub` subscription)
  already configured in Google Cloud Console

## Setup

### 1. Database

```bash
createdb iec_mailbox
psql iec_mailbox -c "CREATE USER iec_user WITH PASSWORD 'iec_pass';"
psql iec_mailbox -c "GRANT ALL PRIVILEGES ON DATABASE iec_mailbox TO iec_user;"
```

Tables are auto-created on backend startup (see `init_db.sql` if you'd
rather run the schema manually).

### 2. Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill in DB creds + Gmail paths

mkdir -p credentials
# copy your existing Gmail OAuth client file here:
cp /path/to/your/gmail_credentials.json credentials/gmail_credentials.json
# first run will open a browser to complete the OAuth consent flow and
# write credentials/gmail_token.json — do this once, locally

uvicorn app.main:app --reload --port 8000
```

The backend syncs your inbox automatically — a background task pulls
recent threads from Gmail immediately on startup, then every
`IEC_GMAIL_POLL_INTERVAL_SECONDS` (default 30s) after that. The frontend
polls the API on the same cadence to pick up changes, so no manual command
is needed. If you want to force an immediate re-sync (e.g. right after
sending a test email), you can still run:

```bash
curl -X POST http://localhost:8000/api/threads/sync
```

For near-instant push updates instead of polling, point your Pub/Sub
subscription's push endpoint at `https://<your-domain>/api/gmail/webhook`
(use `ngrok` for local dev) — the polling loop and the webhook can run
side by side.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173`, proxying `/api` to the backend on
`:8000` (see `vite.config.js`).

## API

| Method | Path                        | Purpose                          |
|--------|-----------------------------|-----------------------------------|
| GET    | `/api/threads`              | List threads for the inbox        |
| GET    | `/api/threads/{id}`         | Full thread, chronological emails |
| POST   | `/api/threads/sync`         | Manual pull from Gmail            |
| POST   | `/api/emails/send`          | Send new email or reply           |
| PATCH  | `/api/emails/{id}/read`     | Mark read/unread                  |
| POST   | `/api/gmail/webhook`        | Pub/Sub push receiver             |

## Notes / next steps

- No login yet — this is wired as a single-user internal tool for now.
- The Pub/Sub webhook currently re-syncs the most recent threads on any
  notification rather than using `historyId` for a precise delta — fine
  for a first pass, worth tightening once volume grows.
- Attachments on mail you *receive* are downloaded from Gmail during sync
  and saved to `backend/storage/attachments/`, downloadable from the
  thread view. Attachments you send are attached to the outgoing message
  but not stored locally.
