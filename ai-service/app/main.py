from datetime import date, timedelta

import structlog
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import ValidationError

from app.config import settings
from app.models import ChatwootWebhookEvent
from app.workflows.classify import process_incoming_message
from app.workflows.reporting import build_report_summary, fetch_report_data

logger = structlog.get_logger(__name__)

app = FastAPI(title="ai-service", description="AI orchestration layer for the support platform")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhooks/chatwoot")
async def chatwoot_webhook(request: Request, secret: str | None = Query(default=None)) -> dict:
    if settings.ai_webhook_shared_secret:
        if secret != settings.ai_webhook_shared_secret:
            raise HTTPException(status_code=401, detail="invalid webhook secret")
    else:
        logger.warning("webhook_secret_not_configured")

    body = await request.json()
    try:
        event = ChatwootWebhookEvent.model_validate(body)
    except ValidationError:
        # Chatwoot sends other event types and shapes this service doesn't subscribe to or
        # care about; a shape mismatch is not an error worth a retry.
        return {"status": "ignored", "reason": "unrecognized_payload"}

    if not event.is_actionable_player_message or event.conversation_id is None or event.id is None:
        return {"status": "ignored"}

    result = await process_incoming_message(event.conversation_id, event.id)
    return result


@app.get("/reports/summary")
async def reports_summary(
    since: str | None = Query(default=None, description="ISO date, defaults to 7 days ago"),
    until: str | None = Query(default=None, description="ISO date, defaults to today"),
    raw: bool = Query(default=False, description="Skip the Claude summarisation step"),
) -> dict:
    since = since or (date.today() - timedelta(days=7)).isoformat()
    until = until or date.today().isoformat()

    if raw:
        return {"data": await fetch_report_data(since, until)}
    return await build_report_summary(since, until)
