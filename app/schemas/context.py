"""
Caller-context response schemas for the two INBOUND agents.

Bolna hits GET /caller-context before each call; the returned JSON keys
are injected into the agent prompt as {variable} references.

Only inbound agents need caller-context (they react based on DB state).
Outbound agents get their user_data directly from our backend at call time.
"""

from pydantic import BaseModel


class WorkerInboundContext(BaseModel):
    """Variables for Agent 1 (Arjun — worker inbound)."""
    scenario: str = "new_worker"
    worker_name: str = ""
    worker_type: str = ""
    worker_locality: str = ""
    # Populated only when scenario == "paired_in_progress"
    customer_phone: str = ""
    customer_name: str = ""
    service_type: str = ""
    job_description: str = ""
    job_locality: str = ""


class CustomerInboundContext(BaseModel):
    """Variables for Agent 3 (Priya — customer inbound)."""
    scenario: str = "new_customer"
    customer_name: str = ""
    customer_locality: str = ""
    service_type: str = ""
    job_description: str = ""
    # Populated when paired
    worker_name: str = ""
    worker_phone: str = ""
    worker_type: str = ""
