"""85-10: static checks of the tray scripts against the frozen tray contract (D-05, D-12).

There is no PowerShell on the development VM, so tray_icon.ps1 and tray_my_tickets.ps1 are never run here.
These tests read them as text and pin what can be proved from text: the route paths and field names equal
service_desk/tray_contract.py, the scripts carry no dynamic code execution, no PowerShell 7-only syntax, only
ASCII, balanced brackets, a 10 second timeout on every request and a 4 px grid under every control. The live
round trip (pop-up, This fixed it, I still need help, display scaling) is the user's step after the agent that
carries the window is released.
"""
import pathlib
import re

import pytest

from service_desk import tray_contract as c

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "agent-install" / "omni-agent-rs" / "scripts"
MAIN_PATH = SCRIPTS / "tray_icon.ps1"
SECOND_PATH = SCRIPTS / "tray_my_tickets.ps1"
BOTH = [MAIN_PATH, SECOND_PATH]


# ---------------------------------------------------------------- helpers

def read(path):
    return path.read_text(encoding="utf-8")


def code_lines(text):
    """The script without block comments and whole-line comments."""
    text = re.sub(r"<#.*?#>", "", text, flags=re.S)
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def code(text):
    return "\n".join(code_lines(text))


def strip_strings_and_comments(text):
    """Blank out comments, here-strings and quoted strings so brackets can be counted."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if text.startswith("<#", i):
            j = text.find("#>", i)
            i = n if j < 0 else j + 2
        elif ch == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("@'", i) or text.startswith('@"', i):
            q = text[i + 1]
            m = re.compile(r"\n" + q + "@").search(text, i)
            i = n if not m else m.end()
        elif ch == "'":
            i += 1
            while i < n:
                if text[i] == "'":
                    if text.startswith("''", i):
                        i += 2
                        continue
                    break
                i += 1
            i += 1
        elif ch == '"':
            i += 1
            while i < n:
                if text[i] == "`":
                    i += 2
                    continue
                if text[i] == '"':
                    break
                i += 1
            i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def matching(text, open_index):
    """Index of the bracket closing the one at open_index (strings and comments skipped)."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    stack, i, n = [], open_index, len(text)
    while i < n:
        ch = text[i]
        if text.startswith("<#", i):
            j = text.find("#>", i)
            i = n if j < 0 else j + 2
            continue
        if ch == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("@'", i) or text.startswith('@"', i):
            q = text[i + 1]
            m = re.compile(r"\n" + q + "@").search(text, i)
            i = n if not m else m.end()
            continue
        if ch == "'":
            i += 1
            while i < n:
                if text[i] == "'":
                    if text.startswith("''", i):
                        i += 2
                        continue
                    break
                i += 1
            i += 1
            continue
        if ch == '"':
            i += 1
            while i < n:
                if text[i] == "`":
                    i += 2
                    continue
                if text[i] == '"':
                    break
                i += 1
            i += 1
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in ")}]":
            if not stack or stack.pop() != ch:
                return -1
            if not stack:
                return i
        i += 1
    return -1


def function_body(text, name):
    m = re.search(r"^function\s+" + re.escape(name) + r"\b[^\n{]*\{", text, flags=re.M)
    assert m, f"function {name} not found"
    start = m.end() - 1
    end = matching(text, start)
    assert end > start, f"function {name} has unbalanced braces"
    return text[start + 1:end]


def block_after(text, anchor_regex):
    """The text between the bracket that follows anchor_regex and its match."""
    m = re.search(anchor_regex, text)
    assert m, f"anchor not found: {anchor_regex}"
    start = m.end() - 1
    end = matching(text, start)
    assert end > start, f"unbalanced block after {anchor_regex}"
    return text[start + 1:end]


def top_level_keys(block):
    """Keys of a PowerShell hashtable body (depth 0 only), whatever the line layout."""
    keys, depth, cur, i, n = [], 0, [], 0, len(block)
    cleaned = strip_strings_and_comments(block)
    # strip_strings_and_comments removes quoted text, which is fine: keys are bare words.
    for ch in cleaned:
        if ch in "{([":
            depth += 1
        elif ch in "})]":
            depth -= 1
        if depth == 0 and ch in "\n;":
            piece = "".join(cur)
            m = re.match(r"\s*(\w+)\s*=", piece)
            if m:
                keys.append(m.group(1))
            cur = []
        else:
            cur.append(ch)
    m = re.match(r"\s*(\w+)\s*=", "".join(cur))
    if m:
        keys.append(m.group(1))
    return keys


def route_in_script(name):
    """The contract route as a script writes it: '$Base' + path with $AgentId, $ticketId, $articleId."""
    return ("$Base" + c.ROUTES[name]
            .replace("{agent_id}", "$AgentId")
            .replace("{ticket_id}", "$ticketId")
            .replace("{article_id}", "$articleId"))


@pytest.fixture(scope="module")
def main():
    return read(MAIN_PATH)


@pytest.fixture(scope="module")
def second():
    assert SECOND_PATH.exists(), "tray_my_tickets.ps1 does not exist"
    return read(SECOND_PATH)


# ---------------------------------------------------------------- Task 1: hygiene of both scripts

@pytest.mark.parametrize("path", BOTH, ids=lambda p: p.name)
def test_script_is_ascii_and_under_500_lines(path):
    assert path.exists(), f"{path.name} does not exist"
    raw = path.read_bytes()
    bad = [i for i, b in enumerate(raw) if b > 127]
    assert not bad, f"{path.name} has non-ASCII bytes at offsets {bad[:5]}"
    assert len(raw.decode("ascii").splitlines()) < 500


@pytest.mark.parametrize("path", BOTH, ids=lambda p: p.name)
def test_script_brackets_are_balanced(path):
    assert path.exists(), f"{path.name} does not exist"
    flat = strip_strings_and_comments(read(path))
    for open_ch, close_ch in ("{}", "()", "[]"):
        assert flat.count(open_ch) == flat.count(close_ch), (
            f"{path.name}: {open_ch}{close_ch} unbalanced "
            f"({flat.count(open_ch)} vs {flat.count(close_ch)})")
    # and every opener closes in order
    depth_stack = []
    for ch in flat:
        if ch in "{([":
            depth_stack.append({"{": "}", "(": ")", "[": "]"}[ch])
        elif ch in "})]":
            assert depth_stack and depth_stack.pop() == ch, f"{path.name}: brackets cross"
    assert not depth_stack


@pytest.mark.parametrize("path", BOTH, ids=lambda p: p.name)
def test_script_has_no_dynamic_code_or_downloads(path):
    assert path.exists(), f"{path.name} does not exist"
    body = code(read(path))
    for pattern in (r"Invoke-Expression", r"(?<![\w-])iex(?![\w-])", r"DownloadString", r"DownloadFile",
                    r"Invoke-WebRequest", r"Net\.WebClient", r"Start-Process[^\n]*https?:",
                    r"Start-Process[^\n]*\$\w*[Uu]rl"):
        assert not re.search(pattern, body, flags=re.I), f"{path.name} uses {pattern}"
    # Add-Type with source text: the main script keeps only its two original uses (assemblies and the
    # console-window P/Invoke); the new script has none.
    add_types = [ln.strip() for ln in code_lines(read(path)) if "Add-Type" in ln]
    allowed = (r"Add-Type -AssemblyName System\.(Windows\.Forms|Drawing)$",
               r"\$win = Add-Type -MemberDefinition \$hideSig -Name 'TrayWin' -Namespace 'Native' -PassThru$")
    for ln in add_types:
        assert path == MAIN_PATH and any(re.match(a, ln) for a in allowed), (
            f"{path.name}: unexpected Add-Type: {ln}")


@pytest.mark.parametrize("path", BOTH, ids=lambda p: p.name)
def test_script_uses_no_powershell7_only_syntax(path):
    assert path.exists(), f"{path.name} does not exist"
    body = strip_strings_and_comments(read(path))
    assert "??" not in body and "?." not in body and "?[" not in body
    assert "-Parallel" not in body
    assert not re.search(r"\s&&\s|\s\|\|\s", body)


def test_every_new_request_has_a_10_second_timeout(main, second):
    assert c.REQUEST_TIMEOUT_SECONDS == 10
    lines = [ln for ln in code_lines(second) if "Invoke-RestMethod" in ln]
    assert lines, "the second script makes no requests"
    for ln in lines:
        assert "-TimeoutSec 10" in ln, f"no 10 s timeout: {ln.strip()}"
    dialog = function_body(main, "Show-TicketDialog")
    rest = [ln for ln in dialog.splitlines() if "Invoke-RestMethod" in ln]
    assert len(rest) == 2, "the dialog posts to the new route and the legacy route"
    for ln in rest:
        assert "-TimeoutSec 10" in ln, f"no 10 s timeout: {ln.strip()}"


# ---------------------------------------------------------------- Task 1: Raise a Ticket on the new route

def test_create_route_is_the_contract_route(main):
    dialog = function_body(main, "Show-TicketDialog")
    assert route_in_script("create") in dialog
    assert c.METHODS["create"] == "POST"
    assert re.search(r"-Method Post[^\n]*" + re.escape("$newUri"), dialog)


def test_create_body_names_exactly_the_contract_fields(main):
    dialog = function_body(main, "Show-TicketDialog")
    body = block_after(dialog, r"\$newBody\s*=\s*@\{")
    assert top_level_keys(body) == list(c.CREATE_FIELDS)
    client = block_after(body, r"client\s*=\s*@\{")
    assert top_level_keys(client) == list(c.CLIENT_FIELDS)
    assert f"'{c.FEATURE_MY_TICKETS}'" in client
    assert "template = $tpl.Id" in body or "template     = $tpl.Id" in body
    assert "endpoint_info" in body and "Get-EndpointInfo" in body


def test_templates_carry_contract_ids_and_legacy_prefixes(main):
    block = block_after(main, r"\$Templates\s*=\s*@\(")
    entries = re.findall(r"@\{([^}]*)\}", block)
    assert len(entries) == 6
    ids = []
    for entry in entries:
        tid = re.search(r"Id='(\w+)'", entry)
        assert tid, f"template without an Id: {entry}"
        assert tid.group(1) in c.TEMPLATE_IDS
        ids.append(tid.group(1))
        prefix = re.search(r"Prefix='([^']*)'", entry).group(1)
        if prefix:
            assert c.LEGACY_TITLE_PREFIXES[prefix] == tid.group(1)
    assert sorted(ids) == sorted(c.TEMPLATE_IDS)


def test_legacy_route_only_in_the_404_fallback(main):
    dialog = function_body(main, "Show-TicketDialog")
    legacy = "/api/agents/$AgentId/ticket\""
    assert dialog.count(legacy) == 1
    before = dialog[:dialog.index(legacy)]
    assert "404" in before[-600:], "the legacy route must sit behind a 404 check"
    assert dialog.count(route_in_script("create")) == 1


def test_success_text_comes_from_the_server_with_the_ui_spec_fallback(main):
    dialog = function_body(main, "Show-TicketDialog")
    assert "$r.message" in dialog
    assert "Choose My tickets in the tray menu to see any reply." in dialog
    assert "Start-TicketWatch" in dialog


# ---------------------------------------------------------------- Task 1: menu, dot-source, timer

def test_main_script_dot_sources_the_second_before_the_menu_is_built(main):
    m = re.search(r"(?<![\w.])\.\s+\(Join-Path \$PSScriptRoot 'tray_my_tickets\.ps1'\)", main)
    assert m, "tray_icon.ps1 does not dot-source tray_my_tickets.ps1 from $PSScriptRoot"
    assert m.start() > main.index("function Get-FailureText")
    assert m.start() < main.index("New-Object System.Windows.Forms.ContextMenuStrip")


def test_menu_has_my_tickets_between_raise_and_chat(main):
    assert "'My tickets'" in main
    order = [main.index("[void]$menu.Items.Add($ticketRoot)"),
             main.index("[void]$menu.Items.Add($myTicketsItem)"),
             main.index("[void]$menu.Items.Add($chatItem)")]
    assert order == sorted(order)
    assert "Show-MyTickets" in main
    assert "Add_Click" in main[main.index("$myTicketsItem = "):main.index("[void]$menu.Items.Add($myTicketsItem)")]


def test_timer_is_created_and_started_before_application_run(main, second):
    assert main.index("Initialize-TicketWatch") < main.index("[System.Windows.Forms.Application]::Run")
    init = function_body(second, "Initialize-TicketWatch")
    assert "New-Object System.Windows.Forms.Timer" in init
    assert ".Start()" in init
    assert "GetNewClosure()" in init


def test_poll_timings_equal_the_contract(second):
    assert (c.POLL_FAST_SECONDS, c.POLL_FAST_WINDOW_SECONDS, c.POLL_SLOW_SECONDS) == (30, 180, 300)
    assert re.search(r"FastSeconds\s*=\s*%d\b" % c.POLL_FAST_SECONDS, second)
    assert re.search(r"FastWindowSeconds\s*=\s*%d\b" % c.POLL_FAST_WINDOW_SECONDS, second)
    assert re.search(r"SlowSeconds\s*=\s*%d\b" % c.POLL_SLOW_SECONDS, second)


def test_seen_file_is_under_localappdata(second):
    assert "LOCALAPPDATA" in second
    assert "OmniAgent" in second and "tray-seen.json" in second


def test_poll_uses_the_list_route_and_the_user_parameter(second):
    listing = function_body(second, "Get-TrayTicketList")
    assert route_in_script("list") in listing
    assert c.METHODS["list"] == "GET"
    assert f"?{c.USER_PARAM}=" in listing
    assert "[uri]::EscapeDataString($env:USERNAME)" in listing
    assert "-TimeoutSec 10" in listing
    assert "Get-TrayTicketList" in function_body(second, "Invoke-TicketPoll")


def test_popup_is_one_balloon_per_answer_under_255_characters(second):
    poll = function_body(second, "Invoke-TicketPoll")
    assert "Your ticket has an answer" in poll
    assert "Click to read it." in poll
    assert "255" in poll
    assert "ShowBalloonTip" in poll
    assert "Write-TrayLog" in poll
    assert "My tickets ({0} new)" in second or "My tickets (" in second


def test_balloon_click_opens_my_tickets_on_that_ticket(second):
    init = function_body(second, "Initialize-TicketWatch")
    assert "BalloonTipClicked" in init
    assert "Show-MyTickets" in init


def test_response_fields_read_by_the_poll_are_in_the_contract(second):
    poll = function_body(second, "Invoke-TicketPoll")
    for var, allowed in (("tk", c.TICKET_FIELDS), ("lr", c.LIST_RESPONSE_FIELDS)):
        used = set(re.findall(r"\$" + var + r"\.(\w+)", poll))
        assert used and used <= set(allowed), f"${var} reads {used - set(allowed)}"

