# ADR 0009: Customer-Facing Support Widget

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Related** | [ADR 0001, D1](0001-architecture-and-tech-stack.md) · [ADR 0005](0005-no-direct-ai-to-customer-interface.md) |

## Context

Every previous milestone tested this platform from the agent/API side. Testing "from the user
perspective" surfaced a real gap: the only configured inbox (`Player Support`, `Channel::Api`)
has no customer-facing surface at all -- it exists purely for programmatic ticket creation
(`scripts/run_demo.py`, the webhook pipeline), by design, not oversight. That raised the actual
question this ADR answers: what should a real customer-facing entry point look like, given two
options the project owner identified directly -- embed Chatwoot's live chat widget on an existing
website, or build a full customer portal (login, ticket history).

## Decision Drivers

1. **The brief scopes out a custom frontend replacing Chatwoot** (see ADR 0007's D1 discussion of
   this same constraint for the ingestion UI) -- Chatwoot already owns the support-facing
   interface question; this project's job is configuring and extending it, not replacing it.
2. **ADR 0005 still applies**: nothing here changes the no-direct-AI-to-customer-interface
   constraint. A ticket-resolved notification is a template Chatwoot itself sends when a human
   marks a conversation resolved -- not an AI-authored message reaching a customer.
3. **Stay honest about what's verified**, consistent with every other ADR here -- this
   environment has no SMTP configured and no way to script real widget-originated messages
   through the API, so some claims here are necessarily marked as configured-but-not-fully-proven
   rather than fully live-tested.

## Options evaluated

| Option | Verdict |
|---|---|
| **Full customer portal** (login, ticket history, account creation) | Rejected. Chatwoot Community Edition has no such feature to configure -- this would mean building real customer-facing infrastructure from scratch (auth, sessions, a new data-exposure surface), which is a different and much larger project than anything built so far, and runs directly into Decision Driver 1. |
| **Live chat widget on an existing website** (Option A) | **Chosen.** Native Chatwoot feature, configuration rather than a build, and the two gaps the project owner raised against it (no CAPTCHA, no resolution notification) both turned out to be addressable without a portal -- see D1-D3. |

## Decisions

### D1: A Website (Live Chat) inbox, with a pre-chat form requiring email

**Decision:** A second inbox (`Website Live Chat`, `Channel::WebWidget`, id 2) exists alongside
the original API inbox -- the two serve different purposes and both stay. Its pre-chat form is
enabled and requires an email address before a visitor can start chatting
(`pre_chat_form_options.pre_chat_fields`, `emailAddress`, `required: true`), confirmed working
live in a real browser -- the form blocks message entry until the field is filled in.

**Why:** Requiring email up front is what makes D2 possible at all -- without an address on file,
there's nothing to notify later. This is standard Chatwoot configuration, not a workaround.

**A real bug found getting here, worth recording precisely:** each `pre_chat_fields` entry has
*two* independent type-like keys that are easy to get backwards -- `field_type` marks the field as
Chatwoot's own "standard" kind (as opposed to a `contact_attribute`/`conversation_attribute`
custom field), while `type` is fed directly into the widget's FormKit renderer as the literal
input type, so it has to be a real one (`"email"`, `"text"`), not `"standard"`. Getting this
backwards (`field_type: "email", type: "standard"`, an easy mistake since "standard" reads like
the right word for describing a built-in field) doesn't error anywhere -- the API accepts and
stores it without complaint -- it just silently renders as a generic message box with no email
input at all, and a `required: true` field that can never be filled in because it never rendered
then blocks form submission forever with no visible error. Confirmed correct against Chatwoot's
own test fixture (`app/javascript/widget/mixins/specs/configMixin.spec.js`) via its public GitHub
source, not guessed twice and hoped. `scripts/configure_chatwoot.py` bakes in the corrected shape
now, not the version that shipped broken during initial testing.

### D2: Ticket-resolved notification via a native automation rule, not a custom notification system

**Decision:** An automation rule (`event_name: conversation_resolved`, scoped to inbox 2,
action `send_email_transcript`) emails the conversation transcript to the contact's address when
an agent marks their conversation resolved.

**Why:** This directly answers the "how does a customer know their ticket is fixed" gap without
inventing anything -- Chatwoot already ships a resolved-conversation event and a transcript-email
action; the work here was recognizing the built-in path existed and wiring it up, not building a
notification system.

**Verification caveat, stated plainly:** this environment has no SMTP configured (confirmed by
grepping `.env` and `docker-compose.yml` for mailer settings -- nothing there), so real email
delivery cannot be observed end to end here regardless of anything else. Sending a genuine message
through the widget itself (not simulated through the agent API, which flatly refuses
`message_type: incoming` for `Channel::WebWidget` inboxes -- `"Incoming messages are only allowed
in Api inboxes"`) is now confirmed working live, D1's schema fix in hand. Whether
`send_email_transcript` actually attempts delivery when *that* real conversation gets resolved is
the one piece not independently confirmed in this environment -- check the
`chatwoot`/`chatwoot-sidekiq` container logs for mail-delivery activity after resolving a
widget-originated conversation (it'll fail to actually send without SMTP configured, but should
still show an attempt).

### D3: CAPTCHA is external to Chatwoot, documented as a reference pattern, not deployed

**Decision:** Chatwoot has no native CAPTCHA option on the live chat widget (confirmed --
Chatwoot's own spam handling is reactive: mute the conversation, block the contact, after the
fact). Since the widget is just a script tag on a page the deploying company controls, the
CAPTCHA gate belongs on that page, not in Chatwoot. `widget-demo/index.html` includes an inert,
commented-out reference implementation (gate the widget's script injection behind a Cloudflare
Turnstile challenge) rather than a live integration, since this project has no real domain to
register a Turnstile site key against.

**Why:** Building a fake CAPTCHA integration against no real site would be theater, not a real
feature -- the honest version of this decision is documenting the correct pattern precisely
enough that wiring in a real site key later is a one-line change, not a research project.

### D4: A throwaway demo page, served by its own minimal container, on an opt-out Compose profile

**Decision:** `widget-demo/index.html` is a minimal static page embedding the widget script
exactly as it would appear on a real site -- one script tag, no build step. It's served by a
dedicated `widget-demo` service (`python:3.12-alpine`, `python -m http.server`, no Dockerfile) on
port 8080, on the `demo` Compose profile -- included by default (`COMPOSE_PROFILES=demo` in
`.env.example`), removable by clearing that variable once a real deployment is embedding the same
script into its own actual website instead of using this stand-in.

**Why a real container instead of "just open the file":** found live -- opening the page directly
as `file://` left the widget bubble not rendering at all. A `file://` page is a null origin, and
the widget's calls beyond the initial script tag (fetching its config, opening a connection)
don't behave the same way from one as they do from a real HTTP origin. A dedicated container is
the smallest fix that's also honest about deployment: a real company's widget would always be
served over real HTTP by their own site, so the demo should be too, not "open this file" advice
that only coincidentally happens to work in some browsers.

**Why a profile, on by default:** this page is genuinely useful for trying the whole flow locally,
which is why it's on unless explicitly turned off -- but it's also explicitly a stand-in
(D4 above), not something a real deployment would run permanently once its own site carries the
same embed script. A Compose profile already exists for exactly this kind of "on by default,
one flag to exclude" need (`ai-service` uses the same mechanism in reverse -- off by default, one
flag to include).

### D5: Two operational gotchas hit live, worth documenting so nobody re-derives them

**Rate limiting:** Chatwoot's own `rack::attack` throttles the widget's config/conversation
endpoints. Enough back-to-back testing (automated and manual) tripped it, and the widget silently
stopped rendering entirely -- traced to the `/widget` iframe endpoint returning `429`, not a
config or code problem. The counters live in Redis under keys like
`velma:rack::attack:<id>:widget?website_token={website_token}&...`; deleting them resets the
throttle immediately rather than waiting out the window.

**Inbox config caching:** a Redis key (`alfred:idb-cache-key-account-1-inbox`) versions Chatwoot's
cached inbox config. An inbox update via the API doesn't necessarily invalidate it immediately --
after fixing D1's schema bug, the widget kept serving the *previous* (broken) config until that
key was deleted and `chatwoot`/`chatwoot-sidekiq` were restarted. Both containers are stateless
app servers (all real state lives in Postgres), so restarting either is always safe.

## Consequences (Overall)

**Positive:** A real, confirmed-working customer entry point exists using only Chatwoot's native
configuration surface -- no new frontend, no conflict with the brief's constraint against
replacing Chatwoot's own interface, and the one new service (`widget-demo`) exists purely to
demo it locally, opt-out by default rather than permanent infrastructure. The
resolution-notification gap closed via a feature that already existed, not new code. CAPTCHA has
a documented, ready-to-activate pattern for a real deployment. The exact schema bug that broke
the pre-chat form is documented precisely enough that nobody building on this needs to rediscover
it, and `configure_chatwoot.py` bakes in the corrected version.

**Negative / accepted trade-offs:** Whether `send_email_transcript` actually attempts delivery on
a genuinely resolved widget conversation remains the one unconfirmed piece in this environment --
flagged explicitly rather than assumed, consistent with ADR 0004's precedent. Real CAPTCHA
protection requires a real domain and site key this portfolio project doesn't have; the reference
implementation is correct but inert until someone deploying this for real fills that in.
