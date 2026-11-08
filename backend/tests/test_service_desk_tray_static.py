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


def skip_token(text, i):
    """Index just after the comment, here-string or quoted string starting at i; None when none starts there."""
    n, ch = len(text), text[i]
    if text.startswith("<#", i):
        j = text.find("#>", i)
        return n if j < 0 else j + 2
    if ch == "#":
        j = text.find("\n", i)
        return n if j < 0 else j
    if text.startswith("@'", i) or text.startswith('@"', i):
        m = re.compile(r"\n" + text[i + 1] + "@").search(text, i)
        return n if not m else m.end()
    if ch in "'\"":
        i += 1
        while i < n:
            if ch == '"' and text[i] == "`":
                i += 2
                continue
            if text[i] == ch:
                if ch == "'" and text.startswith("''", i):
                    i += 2
                    continue
                break
            i += 1
        return i + 1
    return None


def strip_strings_and_comments(text):
    """Blank out comments, here-strings and quoted strings so brackets can be counted."""
    out, i = [], 0
    while i < len(text):
        j = skip_token(text, i)
        if j is None:
            out.append(text[i])
            i += 1
        else:
            i = j
    return "".join(out)


def matching(text, open_index):
    """Index of the bracket closing the one at open_index (strings and comments skipped)."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    stack, i = [], open_index
    while i < len(text):
        j = skip_token(text, i)
        if j is not None:
            i = j
            continue
        ch = text[i]
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
    keys, depth, cur = [], 0, []
    for ch in strip_strings_and_comments(block):   # keys are bare words, so quoted text can go
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



# ---------------------------------------------------------------- Task 2: the My tickets and article windows

def numbers_on_grid(second):
    """(line, text) of every Location, Size, ClientSize, MaximumSize and column width off the 4 px grid."""
    bad = []
    for ln in code_lines(second):
        for m in re.finditer(r"\.(?:Location|Size|MaximumSize)\s*=\s*'(\d+)\s*,\s*(\d+)'", ln):
            if any(int(g) % 4 for g in m.groups()):
                bad.append(ln.strip())
        for m in re.finditer(r"System\.Drawing\.(?:Size|Point)\(\s*(\d+)\s*,\s*(\d+)\s*\)", ln):
            if any(int(g) % 4 for g in m.groups()):
                bad.append(ln.strip())
        for m in re.finditer(r"Columns\.Add\('[^']*',\s*(\d+)\)", ln):
            if int(m.group(1)) % 4:
                bad.append(ln.strip())
    return bad


def test_both_windows_are_defined(second):
    assert "function Show-MyTickets" in second
    assert "function Show-TrayArticle" in second


def test_my_tickets_form_is_800x560_fixed_with_close_as_cancel(second):
    body = function_body(second, "Show-MyTickets")
    assert "ClientSize = New-Object System.Drawing.Size(800, 560)" in body   # 800x560
    assert "FormBorderStyle = 'FixedDialog'" in body
    assert "MaximizeBox = $false" in body and "MinimizeBox = $false" in body
    assert "StartPosition = 'CenterScreen'" in body and "TopMost = $true" in body
    assert "$f.CancelButton = $btnClose" in body
    assert "AcceptButton" not in body.replace("$f.AcceptButton = $null", "")
    assert body.index("Sync-TrayConfig") < body.index("Test-Enrolled")
    assert "[void]$f.ShowDialog()" in body


def test_every_position_and_size_is_a_multiple_of_4(second):
    assert numbers_on_grid(second) == []


def test_grid_check_catches_an_off_grid_control():
    assert numbers_on_grid("$x.Location = '12,30'") != []
    assert numbers_on_grid("$x.Size = '292,400'") == []
    assert numbers_on_grid("New-Object System.Drawing.Size(801, 560)") != []
    assert numbers_on_grid("[void]$list.Columns.Add('Title', 142)") != []


def test_my_tickets_layout_matches_ui_spec_section_8(second):
    body = function_body(second, "Show-MyTickets")
    layout = [
        ("lblList", "12,12", None), ("list", "12,32", "292,400"), ("lblFootnote", "12,436", "292,32"),
        ("lblTitle", "320,12", "456,20"), ("lblStatus", "320,36", "456,20"), ("convo", "320,56", "456,252"),
        ("lblBased", "320,312", "456,16"), ("links", "320,332", "456,44"), ("lblFooter", "320,380", "456,32"),
        ("lblNote", "320,416", "456,16"), ("note", "320,432", "456,24"),
        ("btnFixed", "320,464", "112,28"), ("btnHelp", "440,464", "132,28"),
        ("btnRefresh", "580,464", "100,28"), ("btnClose", "688,464", "88,28"),
        ("lblFeedback", "12,500", "764,40"),
    ]
    for name, loc, size in layout:
        assert re.search(r"\$%s\.Location = '%s'" % (name, loc), body), f"{name} is not at {loc}"
        if size:
            assert re.search(r"\$%s\.Size = '%s'" % (name, size), body), f"{name} is not {size}"
    assert re.search(r"Columns\.Add\('Ticket', 64\)", body)
    assert re.search(r"Columns\.Add\('Title', 140\)", body)
    assert re.search(r"Columns\.Add\('Status', 80\)", body)
    assert "MaxLength = %d" % c.NOTE_MAX in body


def test_my_tickets_fixed_labels_are_present(second):
    for label in ("Your tickets", "Based on these articles (click one to read it):",
                  "Tell IT what is still wrong (optional)", "This fixed it", "I still need help",
                  "Refresh tickets", "Close"):
        assert f"'{label}'" in second, label


def test_tab_order_and_accessible_names(second):
    body = function_body(second, "Show-MyTickets")
    order = ["list", "convo", "links", "note", "btnFixed", "btnHelp", "btnRefresh", "btnClose"]
    for index, name in enumerate(order):
        assert re.search(r"\$%s\.TabIndex = %d\b" % (name, index), body), f"{name} is not tab stop {index}"
    for name, label in (("list", "Your tickets"), ("btnFixed", "This fixed it"),
                        ("btnHelp", "I still need help"), ("btnRefresh", "Refresh tickets"),
                        ("btnClose", "Close"), ("note", "Tell IT what is still wrong (optional)")):
        assert re.search(r"\$%s\.AccessibleName = '%s'" % (name, re.escape(label)), body), name


def test_state_texts_are_present(second):
    for text in ("Loading your tickets...", "Saving...", "Couldn't load your tickets.",
                 "Couldn't send that.", "Thanks. Your ticket is marked resolved.",
                 "Sent to IT. A person will take over.", "Choose Raise a Ticket in the tray menu.",
                 "This article is no longer available.", "Based on: "):
        assert text in second, text
    for colour in ("DimGray", "ForestGreen", "Firebrick"):
        assert f"'{colour}'" in second
    assert "$dp.empty" in second and "$dp.footnote" in second and "$dp.footer" in second


def test_window_never_claims_privacy(second):
    assert "privat" not in second.lower()
    assert "Showing tickets you raised from this computer as" in second   # only the fallback when the server sent none


def test_confirm_help_and_article_routes_are_the_contract_routes(second):
    for name in ("confirm", "help", "article"):
        assert route_in_script(name) in second, name
    assert c.METHODS["confirm"] == c.METHODS["help"] == "POST" and c.METHODS["article"] == "GET"
    assert second.count(f"?{c.USER_PARAM}=") >= 2   # the list and the article
    payloads = [block_after(second[m.start():], r"@\{") for m in re.finditer(r"\$payload\s*=\s*@\{", second)]
    assert [top_level_keys(p) for p in payloads] == [list(c.CONFIRM_FIELDS), list(c.HELP_FIELDS)]
    assert "Substring(0, %d)" % c.NOTE_MAX in second


def test_response_fields_read_by_the_windows_are_in_the_contract(second):
    reads = {
        "tk": (set(c.TICKET_FIELDS), set(c.TICKET_FIELDS) - {"updatedAt"}),
        "en": (set(c.ENTRY_FIELDS), set(c.ENTRY_FIELDS)),
        "ci": (set(c.CITATION_FIELDS), set(c.CITATION_FIELDS)),
        "dp": (set(c.DISPLAY_FIELDS), set(c.DISPLAY_FIELDS)),
        "ar": (set(c.ARTICLE_FIELDS), set(c.ARTICLE_FIELDS)),
        "lr": (set(c.LIST_RESPONSE_FIELDS), {"tickets", "display"}),
    }
    for var, (allowed, required) in reads.items():
        used = set(re.findall(r"\$" + var + r"\.(\w+)", code(second)))
        assert used <= allowed, f"${var} reads {sorted(used - allowed)} which the contract does not have"
        assert required <= used, f"${var} never reads {sorted(required - used)}"


def test_article_window_matches_ui_spec(second):
    body = function_body(second, "Show-TrayArticle")
    assert "ClientSize = New-Object System.Drawing.Size(520, 432)" in body
    assert "'Article - '" in body or '"Article - ' in body
    for needle in ("$box.Location = '12,12'", "$box.Size = '480,340'", "$btnClose.Location = '412,364'",
                   "$btnClose.Size = '80,28'", "ReadOnly = $true", "$f.CancelButton = $btnClose",
                   "TopMost = $true", "FormBorderStyle = 'FixedDialog'"):
        assert needle in body, needle
    assert body.index("Sync-TrayConfig") < body.index("Test-Enrolled")


def test_citations_open_the_article_window_not_a_browser(second):
    assert "LinkClicked" in second and "Show-TrayArticle" in second
    assert "Start-Process" not in second


def test_requests_send_the_utf8_body_the_server_expects(second):
    posts = [ln for ln in code_lines(second) if "-Method Post" in ln]
    assert len(posts) == 1
    assert "charset=utf-8" in posts[0] and "GetBytes(" in posts[0]
