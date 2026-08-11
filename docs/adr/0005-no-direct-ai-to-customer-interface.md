# ADR 0005: No Direct AI-to-Customer Interface, Ever

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Related** | [ADR 0001, D4](0001-architecture-and-tech-stack.md#d4-draft-customer-facing-responses-are-stored-as-private-chatwoot-notes-not-a-bespoke-entity) · [ai-workflows.md](../ai-workflows.md#d-human-escalation--draft-response) |

## Context

The originating brief already required that AI-generated responses never send automatically
(§3.D, §10) — implemented from the start via ADR 0001, D4 (drafts are private Chatwoot notes, a
human copies them into a real reply). That was scoped as a *v1* constraint, phrased in terms of
"not in this version." The project owner then stated explicitly that under EU legislation, an
AI-generated message can never reach a customer without either a competent person approving it
first, or the message being clearly labeled as AI-generated — and asked to rule out *any*
workflow where the AI interfaces with the customer directly, permanently, not just for now. This
generally tracks the EU AI Act's transparency obligations (informing people when they're
interacting with an AI system / labeling AI-generated content) and human-oversight requirements
for AI systems — recorded here as the project owner's compliance direction, not as independent
legal advice from this project.

This ADR upgrades that from "current scope" to a permanent architectural boundary, and rules out
a specific feature direction (confidence-gated auto-send) that was under discussion before this
constraint was stated explicitly.

## Decision

**No component in this project will ever send an AI-generated message directly to a customer,
regardless of confidence score, category, or any other signal — real or self-reported.** This is
not a v1 limitation to be revisited later; it is a permanent boundary.

Concretely:

- `create_draft_response` (mcp-server) continues to write a private, agent-only Chatwoot note. It
  will never be extended with a "send directly" mode, no matter how that might be gated.
- **"Confidence-gated automation"** — auto-sending an AI draft once some confidence threshold is
  crossed — is permanently out of scope, not merely deprioritized. This was under active
  discussion (see PROJECT_JOURNAL.md) as a possible future extension before this ADR; it is
  removed from consideration entirely, independent of whether "confidence" is ever made a real,
  computed signal rather than an LLM self-report (see the confidence-accuracy discussion in
  PROJECT_JOURNAL.md, Milestone 7) — a *real* confidence score would not change this decision.
- Any future extension that touches customer-facing communication (e.g. a future multilingual
  drafting feature) inherits this constraint automatically: draft only, human sends, no exceptions.

## Why

1. **Direct instruction from the project owner**, citing EU legal obligations around AI
   transparency and human oversight of AI-generated content reaching real people.
2. **Consistent with the architecture's own existing bias.** Every AI action in this project
   already lands as a tag, a custom attribute, or a private note — nothing has ever had a code
   path to speak to a customer directly. This ADR closes off that possibility as a *design
   direction*, not just documents current behavior.
3. **A calibrated confidence score wouldn't fix the actual concern.** Even if grounding's
   confidence were made fully real and well-calibrated (a live discussion at the time of this
   ADR), gating an automatic send on it would still remove the human decision the legal
   requirement exists to preserve. The fix for "confidence isn't real" is transparency to the
   human reviewer (surface the real signal so they decide faster); it is not a justification for
   removing the human.

## Consequences

**Positive:** One fewer category of future feature to evaluate case-by-case — "does this send to
the customer automatically?" is now a hard no across the board, not a judgment call per proposal.

**Negative / accepted trade-offs:** Rules out a real product capability (faster, cheaper
resolution for high-confidence, low-risk tickets) that some support platforms do offer. Accepted
deliberately as the cost of the compliance posture the project owner directed.
