# UrbanCall Backend

Voice AI marketplace connecting customers to blue-collar workers in Hyderabad.
Built on FastAPI + PostgreSQL + Bolna AI voice agents.

## Architecture

**5 specialized Bolna agents across 2 accounts:**

| Line | Inbound (1 per line) | Outbound (multiple) |
|---|---|---|
| **Worker (Account 1)** | Arjun | Arjun — Job Offer |
| **Customer (Account 2)** | Priya | Priya — Pairing, Priya — Feedback |

Each agent has its own `agent_id` and tightly scoped extractions. Our backend
routes webhook events and outbound calls based on `(line, purpose)` pairs in
`AGENT_CONFIG`.

## Setup

```bash
git clone <repo>
cd urbancall

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Fill in DATABASE_URL and all 10 agent_id / api_key values

uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/webhook/bolna` | Receives all post-call webhooks from all 5 agents |
| GET | `/caller-context` | Pre-call prompt variables (inbound agents only) |
| GET | `/health` | Health check |

## Project Structure

```
urbancall/
├── app/
│   ├── main.py
│   ├── core/
│   │   └── config.py              — Settings + AGENT_CONFIG map (5 agents)
│   ├── db/
│   │   └── database.py            — sync SQLAlchemy engine (pg8000)
│   ├── models/
│   │   ├── worker.py
│   │   ├── customer.py
│   │   ├── job.py                 — now tracks declined_worker_ids
│   │   └── call_log.py            — 1 row per call, incrementally updated
│   ├── schemas/
│   │   ├── webhook.py             — raw Bolna payload
│   │   └── context.py             — Worker/Customer inbound contexts
│   ├── routers/
│   │   ├── webhook.py
│   │   └── caller_context.py
│   └── services/
│       ├── bolna_client.py        — outbound call trigger (by line+purpose)
│       ├── webhook_processor.py   — per-agent handlers, idempotent
│       ├── caller_context_service.py
│       └── job_queue.py           — polls searching_worker jobs
├── .env.example
├── requirements.txt
└── README.md
```

## Webhook Idempotency

- One row per `bolna_call_id` in `call_logs`.
- Each webhook event merges into the existing row (only non-null fields overwrite).
- Raw payloads appended to `events` JSONB column (audit trail).
- DB mutations on `workers`/`customers`/`jobs` apply exactly once per call,
  gated by a `processed` flag.
