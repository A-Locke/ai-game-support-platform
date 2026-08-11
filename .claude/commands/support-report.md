Answer a support-reporting question ($ARGUMENTS, e.g. "what are the main issues this week?")
using `support-mcp-server` directly -- the MCP-only mirror of `ai-service`'s
`GET /reports/summary` (`ai-service/app/workflows/reporting.py`). Keep data retrieval and
summarisation as two distinct steps, same as the Python implementation (docs/ai-workflows.md,
§C) -- don't blend guesswork into the numbers.

1. Determine a date range from $ARGUMENTS (default: the last 7 days if nothing is specified).
2. Call `get_support_statistics(since, until)` and
   `get_category_statistics(since, until, categories=[...])` (use the `SUPPORT_CATEGORIES` list
   from `.env`, or the default: `Bug, Crash, Technical, Installation, Account, Performance,
   Billing, Feature Request, Feedback, Other`).
3. Present the raw numbers first (total conversations, spam count, human-intervention count,
   per-category breakdown) as reported by the tools -- don't editorialize this part.
4. Then write a short prose summary (a paragraph plus up to 3 bullet points of notable trends)
   grounded only in the numbers from step 2 -- no fabricated detail about *why* a trend
   happened unless a conversation was actually inspected to confirm it.
