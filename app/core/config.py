from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str

    # ── Account 1: Worker line ───────────────────────────────────────────────
    agent_worker_inbound_id: str
    agent_worker_inbound_api_key: str
    agent_worker_inbound_from_phone: str = ""

    agent_worker_job_offer_id: str
    agent_worker_job_offer_api_key: str

    # ── Account 2: Customer line ─────────────────────────────────────────────
    agent_customer_inbound_id: str
    agent_customer_inbound_api_key: str
    agent_customer_inbound_from_phone: str = ""

    agent_customer_pairing_id: str
    agent_customer_pairing_api_key: str

    agent_customer_feedback_id: str
    agent_customer_feedback_api_key: str

    # ── Bolna ─────────────────────────────────────────────────────────────────
    bolna_base_url: str = "https://api.bolna.ai"

    # ── Job queue ─────────────────────────────────────────────────────────────
    job_poll_interval_seconds: int = 15


settings = Settings()


# ─────────────────────────────────────────────────────────────────────────────
# AGENT_CONFIG
#
# Single source of truth for agent routing. Maps agent_id → config dict.
# Each agent has:
#   - line     : "worker" or "customer"
#   - purpose  : "inbound" | "job_offer" | "pairing" | "feedback"
#   - api_key  : Bolna API key for the account this agent belongs to
#   - from_phone : Phone number to use when placing outbound calls
# ─────────────────────────────────────────────────────────────────────────────

AGENT_CONFIG: dict[str, dict] = {
    settings.agent_worker_inbound_id: {
        "line": "worker",
        "purpose": "inbound",
        "agent_id": settings.agent_worker_inbound_id,
        "api_key": settings.agent_worker_inbound_api_key,
        "from_phone": settings.agent_worker_inbound_from_phone,
    },
    settings.agent_worker_job_offer_id: {
        "line": "worker",
        "purpose": "job_offer",
        "agent_id": settings.agent_worker_job_offer_id,
        "api_key": settings.agent_worker_job_offer_api_key,
        "from_phone": settings.agent_worker_inbound_from_phone,  # shared
    },
    settings.agent_customer_inbound_id: {
        "line": "customer",
        "purpose": "inbound",
        "agent_id": settings.agent_customer_inbound_id,
        "api_key": settings.agent_customer_inbound_api_key,
        "from_phone": settings.agent_customer_inbound_from_phone,
    },
    settings.agent_customer_pairing_id: {
        "line": "customer",
        "purpose": "pairing",
        "agent_id": settings.agent_customer_pairing_id,
        "api_key": settings.agent_customer_pairing_api_key,
        "from_phone": settings.agent_customer_inbound_from_phone,  # shared
    },
    settings.agent_customer_feedback_id: {
        "line": "customer",
        "purpose": "feedback",
        "agent_id": settings.agent_customer_feedback_id,
        "api_key": settings.agent_customer_feedback_api_key,
        "from_phone": settings.agent_customer_inbound_from_phone,  # shared
    },
}


def get_agent_id_by_purpose(line: str, purpose: str) -> str:
    """Look up an agent_id for placing outbound calls."""
    for cfg in AGENT_CONFIG.values():
        if cfg["line"] == line and cfg["purpose"] == purpose:
            return cfg["agent_id"]
    raise ValueError(f"No agent configured for line={line} purpose={purpose}")


def get_agent_config(agent_id: str) -> dict:
    """Get the config dict for an agent_id. Returns empty dict if unknown."""
    return AGENT_CONFIG.get(agent_id, {})
