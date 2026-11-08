"""85-02 Task 3: the frozen tray-to-server contract (D-05).

Every value is pinned literally. A route or field changed after an agent carrying the tray window is
published strands every installed tray, so a change here must show up as a deliberate test diff.
"""
from service_desk import tray_contract as c


def test_routes_and_methods():
    assert c.ROUTES == {
        "create": "/api/agents/{agent_id}/tray/tickets",
        "list": "/api/agents/{agent_id}/tray/tickets",
        "confirm": "/api/agents/{agent_id}/tray/tickets/{ticket_id}/confirm",
        "help": "/api/agents/{agent_id}/tray/tickets/{ticket_id}/help",
        "article": "/api/agents/{agent_id}/tray/tickets/{ticket_id}/articles/{article_id}",
    }
    assert c.METHODS == {"create": "POST", "list": "GET", "confirm": "POST", "help": "POST", "article": "GET"}
    assert set(c.METHODS) == set(c.ROUTES)


def test_template_ids_classes_and_legacy_prefixes():
    assert c.TEMPLATE_IDS == ("install_software", "access_request", "report_issue", "hardware_request",
                              "security_concern", "custom")
    assert c.TEMPLATE_CLASS == {
        "install_software": "fulfilment",
        "access_request": "account_access",
        "report_issue": "eligible",
        "hardware_request": "fulfilment",
        "security_concern": "security",
        "custom": "eligible",
    }
    assert set(c.TEMPLATE_CLASS) == set(c.TEMPLATE_IDS)
    assert c.LEGACY_TITLE_PREFIXES == {
        "Software Install Request: ": "install_software",
        "Access Request: ": "access_request",
        "Issue: ": "report_issue",
        "Hardware Request: ": "hardware_request",
        "Security Concern: ": "security_concern",
    }
    assert len(c.LEGACY_TITLE_PREFIXES) == 5
    assert set(c.LEGACY_TITLE_PREFIXES.values()) <= set(c.TEMPLATE_IDS)


def test_the_feature_claim_limits_and_timings():
    assert c.FEATURE_MY_TICKETS == "my_tickets"
    assert (c.LIST_LIMIT, c.LIST_DAYS, c.NOTE_MAX, c.TITLE_MAX) == (20, 60, 500, 200)
    assert (c.POLL_FAST_SECONDS, c.POLL_FAST_WINDOW_SECONDS, c.POLL_SLOW_SECONDS) == (30, 180, 300)
    assert c.REQUEST_TIMEOUT_SECONDS == 10


def test_request_field_names():
    assert c.USER_PARAM == "user"
    assert c.CREATE_FIELDS == ("title", "description", "type", "priority", "template", "endpoint_info", "client")
    assert c.CLIENT_FIELDS == ("features", "version")
    assert c.CONFIRM_FIELDS == ("user",)
    assert c.HELP_FIELDS == ("user", "text")


def test_response_field_names():
    assert c.LIST_RESPONSE_FIELDS == ("tickets", "user", "display")
    assert c.TICKET_FIELDS == ("id", "number", "title", "status", "statusText", "canConfirm", "canHelp",
                               "reasonLine", "entries", "answerIds", "updatedAt")
    assert c.ENTRY_FIELDS == ("kind", "at", "heading", "text", "citations")
    assert c.ENTRY_KINDS == ("answer", "reply", "you", "withdrawn", "notice")
    assert c.CITATION_FIELDS == ("articleId", "title")
    assert c.DISPLAY_FIELDS == ("footnote", "footer", "empty")
    assert c.ARTICLE_FIELDS == ("title", "content", "available")


def test_no_ticket_field_can_leak_a_staff_only_value():
    # The projection has no field for a draft or a staff-only comment; reasonLine is the requester-safe line
    # from TRAY_REASON_LINES, never a hand-off reason (T-85-06).
    leaky = ("draft", "staff", "internal", "comment")
    for name in c.TICKET_FIELDS + c.ENTRY_FIELDS + c.ARTICLE_FIELDS:
        assert not any(word in name.lower() for word in leaky), name


def test_the_route_placeholders_match_the_names_a_handler_uses():
    for name, path in c.ROUTES.items():
        assert path.startswith("/api/agents/{agent_id}/tray/tickets")
        assert ("{ticket_id}" in path) == (name in ("confirm", "help", "article"))
    assert c.ROUTES["article"].endswith("/articles/{article_id}")


def test_the_module_is_self_contained():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(c))
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert imports == [], "tray_contract.py must import nothing"
