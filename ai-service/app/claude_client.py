"""The only module in this project that imports the Anthropic SDK. Swapping Claude for another
LLM means rewriting this file and nothing else -- see docs/architecture.md#replaceability-concretely.
"""

from __future__ import annotations

import structlog
from anthropic import AsyncAnthropic
from pydantic import ValidationError

from app.config import settings
from app.knowledge import load_knowledge_excerpt
from app.models import ClassificationResult

logger = structlog.get_logger(__name__)

_CLASSIFY_TOOL_NAME = "record_classification"

_FALLBACK = ClassificationResult(
    category="Other",
    spam=False,
    requires_human=True,
    confidence=0.0,
    reason="Automatic classification failed; routed to a human as a safe default.",
    draft_response=None,
)


def _classification_tool_schema(categories: list[str]) -> dict:
    return {
        "name": _CLASSIFY_TOOL_NAME,
        "description": "Record the classification of a customer support conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": categories},
                "spam": {"type": "boolean"},
                "requires_human": {"type": "boolean"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "reason": {
                    "type": "string",
                    "description": "One or two sentences a support agent can read at a glance.",
                },
                "draft_response": {
                    "type": ["string", "null"],
                    "description": (
                        "A suggested customer-facing reply, only if requires_human is true and a "
                        "reasonable reply can be drafted from the known-issue/FAQ context "
                        "provided. Null otherwise. Never sent automatically -- always reviewed "
                        "by a human first."
                    ),
                },
            },
            "required": ["category", "spam", "requires_human", "confidence", "reason"],
        },
    }


def _build_prompt(conversation_messages: list[str]) -> str:
    transcript = "\n".join(conversation_messages) if conversation_messages else "(no messages)"
    return (
        "You are triaging a customer support conversation for a software product.\n\n"
        f"Known issues / FAQ context:\n{load_knowledge_excerpt()}\n\n"
        f"Conversation transcript (customer messages):\n{transcript}\n\n"
        "Classify this conversation by calling record_classification."
    )


async def classify_conversation(conversation_messages: list[str]) -> ClassificationResult:
    """One forced tool call per brief §5's example JSON. Never raises for a bad/missing
    model response -- degrades to _FALLBACK so a workflow always has something to act on.
    See docs/ai-workflows.md's error handling section and ADR 0001, D7."""
    # max_retries=0: retry policy is handled explicitly by the loop below (one retry, not the
    # SDK's own default backoff-and-retry-3x), so "retried once" in docs/ai-workflows.md means
    # exactly that -- two HTTP calls total, not up to eight.
    client = AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=0)
    categories = settings.categories

    for attempt in range(2):
        try:
            response = await client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1024,
                tools=[_classification_tool_schema(categories)],
                tool_choice={"type": "tool", "name": _CLASSIFY_TOOL_NAME},
                messages=[{"role": "user", "content": _build_prompt(conversation_messages)}],
            )
            break
        except Exception as exc:
            # Deliberately broad, not just anthropic.APIError: a missing/empty API key raises
            # a plain TypeError from the SDK's own request-construction code, before any HTTP
            # call happens at all, so it never reaches an APIError handler. Found live -- the
            # first real test run (no ANTHROPIC_API_KEY set) 500'd the whole webhook instead of
            # degrading to _FALLBACK as designed. From this function's contract, any failure to
            # produce a usable response means the same thing to the caller. See
            # PROJECT_JOURNAL.md, Milestone 2.
            logger.warning("claude_call_failed", attempt=attempt, error=str(exc))
            if attempt == 1:
                return _FALLBACK
    else:
        return _FALLBACK

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        logger.warning("claude_no_tool_use", stop_reason=response.stop_reason)
        return _FALLBACK

    try:
        return ClassificationResult.model_validate(tool_use.input)
    except ValidationError as exc:
        logger.warning("claude_malformed_output", error=str(exc), raw_input=tool_use.input)
        return _FALLBACK


async def summarize_report(report_data: dict) -> str:
    """A second, independent Claude call -- deliberately separate from data retrieval.
    See docs/ai-workflows.md#c-ai-generated-reporting and ADR 0001, D9."""
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize this customer support report data for a support lead, "
                        "in a short paragraph plus up to 3 bullet points of notable trends. "
                        f"Data:\n{report_data}"
                    ),
                }
            ],
        )
    except Exception as exc:
        logger.warning("claude_call_failed_report", error=str(exc))
        return "Summary unavailable (Claude API error) -- see raw data above."

    text_block = next((b for b in response.content if b.type == "text"), None)
    return text_block.text if text_block else "Summary unavailable."
