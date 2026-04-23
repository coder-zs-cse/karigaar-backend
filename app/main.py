"""
UrbanCall — FastAPI backend entry point.

Run with:
    uvicorn app.main:app --reload
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db
from app.routers import caller_context, webhook
from app.services.job_queue import run_job_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UrbanCall starting up…")
    init_db()  # sync — runs once at startup
    logger.info("Database ready.")

    job_queue_task = asyncio.create_task(run_job_queue())
    logger.info("Job queue poller started.")

    yield

    job_queue_task.cancel()
    try:
        await job_queue_task
    except asyncio.CancelledError:
        pass
    logger.info("UrbanCall shut down cleanly.")


app = FastAPI(
    title="UrbanCall API",
    description="Voice AI marketplace connecting customers to blue-collar workers in Hyderabad.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router)
app.include_router(caller_context.router)


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "service": "urbancall"}
