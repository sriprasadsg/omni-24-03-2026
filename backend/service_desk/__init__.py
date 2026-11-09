"""The first-line service desk (Phase 85): every desk constant, declared once.

Stdlib only, so any module (the ticket hooks, the tests, the structural checks) can import it
without pulling in a database or a model client. Limits cite the locked decisions in
85-CONTEXT.md: D-01 (only a person raising a ticket gets an attempt), D-03 (Drafts only by
default), D-15 (the model is local and loopback only), D-25 (desk breaker), D-30 (desk rate
limit). The desk reads and writes through the raw Mongo handle with an explicit tenantId and
never uses the ambient tenant ContextVar. Nothing under autonomous_ops imports this package.
"""
from datetime import timedelta

# ---------------------------------------------------------------- names

DISPATCHER_NAME = "service_desk"        # gate.ActionRequest.dispatcher (desk_gate.DISPATCHER holds the same string)
KIND = "servicedesk"                    # the ledger row kind
COMMAND_ANSWER = "ticket_answer"
COMMAND_WITHDRAW = "ticket_withdraw"
COMMAND_HANDOFF = "ticket_handoff"

# ---------------------------------------------------------------- settings and who raised the ticket

MODES = ("off", "drafts", "post")
DEFAULT_MODE = "drafts"                 # D-03: nothing stored means Drafts only

RAISED_VIA = ("portal", "portal_agent", "tray", "automation")
PERSON_RAISED = ("portal", "portal_agent", "tray")     # D-01: only these get an attempt

ELIGIBLE_TYPES = ("task", "bug", "incident")

# ---------------------------------------------------------------- comments

VISIBILITY = ("staff", "requester")
COMMENT_KINDS = ("ai_answer", "ai_draft", "staff_note", "handoff_notice", "withdrawn_notice", "requester_reply")

# ---------------------------------------------------------------- reason codes

HANDOFF_REASONS = (
    "no_article", "security_topic", "billing_topic", "legal_topic", "account_access", "asked_for_person",
    "tenant_word", "critical_priority", "fulfilment_request", "type_not_answered", "not_english", "empty_ticket",
    "service_desk_offline", "service_desk_busy", "output_check_failed", "did_not_help", "no_reply_to_ai_answer",
    "answer_withdrawn", "desk_stopped",
)
GAP_REASONS = ("no_article", "not_english")
DRAFT_REASONS = (
    "level_suggest", "shadow", "mode_drafts", "desk_rate_limit", "stopped", "desk_breaker", "no_tray_window",
    "settings_unreadable",
)

# ---------------------------------------------------------------- the queue

JOB_STATES = ("pending", "ready", "running", "done", "dropped")
QUEUE_DEADLINE = timedelta(minutes=10)
TENANT_QUEUE_CAP = 10
GLOBAL_QUEUE_CAP = 30

# ---------------------------------------------------------------- limits

DESK_RATE_LIMIT = 20                    # D-30: automatic desk answers per rolling hour
DESK_BREAKER_THRESHOLD = 3              # D-25: withdrawn answers in 24 hours
DESK_BREAKER_WINDOW = timedelta(hours=24)
RETURN_WORKING_DAYS = 3

TITLE_CAP = 200
DESCRIPTION_CAP = 1500
GAP_TEXT_CAP = 300
ANSWER_MAX_CHARS = 900
ANSWER_MAX_LINES = 8
MAX_CANDIDATES = 300
MAX_CITED = 3
ARTICLE_TEXT_CAP = 4000
HELPDESK_CONTENT_MAX = 20000
WORDS_MAX = 50
WORD_MIN = 2
WORD_MAX = 40

# ---------------------------------------------------------------- the local model (D-15, DESK-04)

OLLAMA_URL_ENV = "SERVICE_DESK_OLLAMA_URL"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
MODEL_ENV = "SERVICE_DESK_MODEL"
DEFAULT_MODEL = "llama3.2:3b"
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")

NUM_PREDICT = 220
NUM_CTX = 4096
KEEP_ALIVE = "30m"
PROBE_TIMEOUT_SECONDS = 2
PROBE_CACHE_SECONDS = 15
CALL_TIMEOUT_MIN = 45
CALL_TIMEOUT_MAX = 300
DEFAULT_CALL_TIMEOUT = 120
DEFAULT_PREFILL_TPS = 10
DEFAULT_GEN_TPS = 3
DEFAULT_LOAD_SECONDS = 20

# ---------------------------------------------------------------- the worker

WORKER_LOCK = "service_desk_worker"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
POLL_SECONDS = 5

SYSTEM_AUTHOR = "Service desk"
