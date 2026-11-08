"""The tray-to-server contract of the service desk's "My tickets" window (Phase 85, UI-SPEC section 8).

FROZEN once an agent carrying the tray window is published (D-05). The tray script
(agent-install/omni-agent-rs/scripts/tray_icon.ps1) ships inside the agent, so a route or field renamed
afterwards strands every installed tray on the old shape. Add a field only if the old tray ignores it.
tests/test_service_desk_tray_contract.py pins every value below literally, so a change is a visible test
diff. 85-10 tests the tray script against this module and 85-19 tests the routes against it.

Three rules the contract rests on:

* Every display string the tray shows comes from the server (status words, headings, notices, the footer
  line), so a copy change needs no agent release. Only the fixed window labels live in the script.
* The routes are authenticated with the agent key and project the ticket: the tray never sees drafts,
  staff-only comments or hand-off reasons.
* The Windows user name the tray reports (``user``) is soft scoping between people who share one computer,
  never a security boundary (D-34). The footnote says what is shown and does not claim it is private.

Stdlib only; the module imports nothing from service_desk/__init__.py.
"""

# ---------------------------------------------------------------- routes

ROUTES = {
    "create": "/api/agents/{agent_id}/tray/tickets",
    "list": "/api/agents/{agent_id}/tray/tickets",
    "confirm": "/api/agents/{agent_id}/tray/tickets/{ticket_id}/confirm",
    "help": "/api/agents/{agent_id}/tray/tickets/{ticket_id}/help",
    "article": "/api/agents/{agent_id}/tray/tickets/{ticket_id}/articles/{article_id}",
}

METHODS = {
    "create": "POST",
    "list": "GET",
    "confirm": "POST",
    "help": "POST",
    "article": "GET",
}

# ---------------------------------------------------------------- the capability claim

# The tray lists this in ``client.features`` when it creates a ticket. A ticket created without it (an older
# tray) never gets a posted answer, only a draft, because that tray cannot show one (D-05).
FEATURE_MY_TICKETS = "my_tickets"

# ---------------------------------------------------------------- the Raise a Ticket templates

TEMPLATE_IDS = ("install_software", "access_request", "report_issue", "hardware_request",
                "security_concern", "custom")

# How the desk treats a ticket raised from each template (D-02, D-23): "fulfilment" and "account_access" and
# "security" always go to a person; "eligible" tickets may get an answer.
TEMPLATE_CLASS = {
    "install_software": "fulfilment",
    "access_request": "account_access",
    "report_issue": "eligible",
    "hardware_request": "fulfilment",
    "security_concern": "security",
    "custom": "eligible",
}

# The title prefixes the current tray puts on a ticket. An older tray sends no ``template``; the server
# recognises the template from the prefix.
LEGACY_TITLE_PREFIXES = {
    "Software Install Request: ": "install_software",
    "Access Request: ": "access_request",
    "Issue: ": "report_issue",
    "Hardware Request: ": "hardware_request",
    "Security Concern: ": "security_concern",
}

# ---------------------------------------------------------------- limits

LIST_LIMIT = 20            # tickets in the list, newest first
LIST_DAYS = 60             # only tickets from the last 60 days
NOTE_MAX = 500             # characters in the optional "I still need help" note
TITLE_MAX = 200            # characters in a ticket title

# ---------------------------------------------------------------- timings

POLL_FAST_SECONDS = 30            # check every 30 seconds ...
POLL_FAST_WINDOW_SECONDS = 180    # ... for 3 minutes after the user raises a ticket
POLL_SLOW_SECONDS = 300           # then every 5 minutes while the user has an open ticket from this computer
REQUEST_TIMEOUT_SECONDS = 10      # every tray request uses -TimeoutSec 10

# ---------------------------------------------------------------- field names

USER_PARAM = "user"        # the Windows user name; a query parameter on list and article, a body field elsewhere

# POST create: request body.
CREATE_FIELDS = ("title", "description", "type", "priority", "template", "endpoint_info", "client")
CLIENT_FIELDS = ("features", "version")

# GET list: response body.
LIST_RESPONSE_FIELDS = ("tickets", "user", "display")
TICKET_FIELDS = ("id", "number", "title", "status", "statusText", "canConfirm", "canHelp", "reasonLine",
                 "entries", "answerIds", "updatedAt")
ENTRY_FIELDS = ("kind", "at", "heading", "text", "citations")
ENTRY_KINDS = ("answer", "reply", "you", "withdrawn", "notice")
CITATION_FIELDS = ("articleId", "title")
DISPLAY_FIELDS = ("footnote", "footer", "empty")

# GET article: response body.
ARTICLE_FIELDS = ("title", "content", "available")

# POST confirm and POST help: request body.
CONFIRM_FIELDS = ("user",)
HELP_FIELDS = ("user", "text")
