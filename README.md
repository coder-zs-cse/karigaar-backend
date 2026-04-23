# Karigaar Backend

> Urban Company on Phone -> UrbanCall

> Voice AI marketplace connecting customers to skilled workers in Hyderabad — powered by Bolna AI voice agents.

**🌐 Landing Site:** [github.com/coder-zs-cse/karigaar-landing](https://github.com/coder-zs-cse/karigaar-landing)

---

## What is Karigaar?

Karigaar is a phone-first marketplace where blue-collar workers (electricians, plumbers, painters, and 17 more trades) register by calling one number, customers post jobs by calling another, and the system automatically matches, pairs, and collects feedback — all through natural Hinglish voice conversations. No app download. No smartphone required.

<img width="2156" height="3062" alt="urbancall_system_sequence_diagram" src="https://github.com/user-attachments/assets/b201bf73-e613-40ea-b4a7-170b48c27eb6" />

**How it works:** A customer in Madhapur calls and says "mujhe electrician chahiye, fan nahi chal raha." Within minutes, Karigaar finds a nearby electrician, calls them to offer the job, and once accepted, calls the customer back with the worker's number. After the job is done, Karigaar calls the customer again to collect detailed feedback on punctuality, behavior, and quality.

Zero human intervention. Fully automated. Two phone numbers. Five AI agents.

---

## Architecture

### 5 specialized Bolna voice agents across 2 accounts

```
┌─────────────────────────────────────────────────────────────┐
│                     WORKER LINE (Account 1)                 │
│                                                             │
│  ☎ Inbound ──► Agent 1: Arjun                              │
│                Registration + queries + job completion      │
│                                                             │
│  📞 Outbound ──► Agent 2: Arjun — Job Offer                │
│                  "Madhapur mein electrician ka kaam hai"     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   CUSTOMER LINE (Account 2)                 │
│                                                             │
│  ☎ Inbound ──► Agent 3: Priya                              │
│                Job posting + status + queries               │
│                                                             │
│  📞 Outbound ──► Agent 4: Priya — Pairing                  │
│                  "Worker mil gaya, number note karo"         │
│                                                             │
│  📞 Outbound ──► Agent 5: Priya — Feedback                 │
│                  "Rating do — punctuality, behavior, quality"│
└─────────────────────────────────────────────────────────────┘
```

### End-to-end call flow

```
Worker calls ─► Agent 1 ─► Backend saves worker
                                │
Customer calls ─► Agent 3 ─► Backend saves job (searching_worker)
                                │
                    Job queue polls every 15s
                                │
                    Backend ─► Agent 2 ─► calls worker with job offer
                                │
                         Worker accepts
                                │
                    Backend ─► Agent 4 ─► calls customer with worker's number
                                │
                      Worker completes job
                                │
              Worker calls Agent 1 ─► "kaam ho gaya"
                                │
                    Backend ─► Agent 5 ─► calls customer for feedback
                                │
                         Job completed ✓
```

### System design

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│   Bolna AI   │────►│  FastAPI Backend  │────►│  PostgreSQL  │
│  (5 agents)  │◄────│                   │◄────│              │
└──────────────┘     │  • /webhook/bolna │     │  • workers   │
                     │  • /caller-context│     │  • customers │
  GET /caller-context│  • /health        │     │  • jobs      │
  before each call   │                   │     │  • call_logs │
                     │  Job queue (async) │     └──────────────┘
  POST /webhook      │  polls every 15s  │
  after each call    └──────────────────┘
```

---

## 20 supported trades

Electrician, plumber, painter, mason, locksmith, carpenter, AC technician, tile worker, welder, CCTV installer, pest control, cleaning service, waterproofing, false ceiling, appliance repair, geyser repair, glass fabricator, solar installer, civil work, interior texture.

---

## Tech stack

- **Runtime:** Python, FastAPI
- **Database:** PostgreSQL
- **Voice AI:** Bolna AI (LLM + TTS + STT orchestration)
- **TTS:** ElevenLabs (Hinglish voices)
- **STT:** Deepgram Nova-3
- **LLM:** GPT-4.1 Mini
- **Hosting:** Render

---

## Project structure

```
karigaar-backend/
├── app/
│   ├── main.py                          # FastAPI app + lifespan
│   ├── core/
│   │   └── config.py                    # Settings + AGENT_CONFIG (5 agents)
│   ├── db/
│   │   └── database.py                  # Sync SQLAlchemy engine (pg8000)
│   ├── models/
│   │   ├── worker.py                    # 20 trades, availability enum
│   │   ├── customer.py
│   │   ├── job.py                       # Status lifecycle, feedback fields
│   │   └── call_log.py                  # 1 row per call, incremental upsert
│   ├── schemas/
│   │   ├── webhook.py                   # Bolna webhook payload
│   │   └── context.py                   # Inbound caller-context responses
│   ├── routers/
│   │   ├── webhook.py                   # POST /webhook/bolna
│   │   └── caller_context.py            # GET /caller-context
│   └── services/
│       ├── bolna_client.py              # Outbound call trigger (line + purpose)
│       ├── webhook_processor.py         # Per-agent handlers, idempotent
│       ├── caller_context_service.py    # DB lookup → scenario + variables
│       └── job_queue.py                 # Background poller for job matching
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/karigaar-backend.git
cd karigaar-backend

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Fill in DATABASE_URL and all agent IDs/keys

uvicorn app.main:app --reload
```

API docs at `http://localhost:8000/docs`

---

## Environment variables

```env
DATABASE_URL=postgresql+pg8000://user:pass@host:5432/karigaar

# Account 1 — Worker line
AGENT_WORKER_INBOUND_ID=...
AGENT_WORKER_INBOUND_API_KEY=...
AGENT_WORKER_INBOUND_FROM_PHONE=+1XXXXXXXXXX
AGENT_WORKER_JOB_OFFER_ID=...
AGENT_WORKER_JOB_OFFER_API_KEY=...

# Account 2 — Customer line
AGENT_CUSTOMER_INBOUND_ID=...
AGENT_CUSTOMER_INBOUND_API_KEY=...
AGENT_CUSTOMER_INBOUND_FROM_PHONE=+1XXXXXXXXXX
AGENT_CUSTOMER_PAIRING_ID=...
AGENT_CUSTOMER_PAIRING_API_KEY=...
AGENT_CUSTOMER_FEEDBACK_ID=...
AGENT_CUSTOMER_FEEDBACK_API_KEY=...

BOLNA_BASE_URL=https://api.bolna.ai
JOB_POLL_INTERVAL_SECONDS=15
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook/bolna` | Receives post-call webhooks from all 5 agents |
| `GET` | `/caller-context` | Pre-call prompt variables (inbound agents only) |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

---

## Webhook design

Every Bolna call generates multiple webhook events. The backend handles them incrementally:

- **One row per call** in `call_logs` (unique on `bolna_call_id`)
- Each event merges into the existing row — only non-null fields overwrite
- Raw payloads append to an `events` JSONB column (audit trail)
- DB mutations on `workers`, `customers`, `jobs` apply exactly once per call, gated by a `processed` flag
- Dispatch is by `(agent_line, agent_purpose)` — each of the 5 agents has its own handler

---

## Job lifecycle

```
searching_worker ──► worker_offered ──► paired_active ──► worker_marked_complete ──► completed
       │                    │                │                                           
       ▼                    ▼                ▼                                           
   cancelled           (declined →      cancelled                                       
                    back to searching)                                                   
```

---

## Locality matching

All 200+ Hyderabad localities are embedded in the LLM extraction prompt. The agent never reads them out — the list is used only by the extraction LLM to canonicalize spoken input (e.g., "Madyapur" → "Madhapur", "Goolchibowli" → "Gachibowli"). This prevents fuzzy-match drift in the database.

---

## Deploying to Render

1. Push to GitHub
2. Create a PostgreSQL database on Render (free tier)
3. Create a Web Service pointing to this repo
4. Set the start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add all environment variables
6. Update Bolna dashboard with the live webhook and caller-context URLs

---

## Related

**🌐 Landing Site:** [github.com/coder-zs-cse/karigaar-landing](https://github.com/coder-zs-cse/karigaar-landing)

## License

MIT
