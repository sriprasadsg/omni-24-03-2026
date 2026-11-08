"""The four starter IT articles of the service desk, and the builder that copies them into a tenant (D-28, D-29, D-36).

The platform writes the starters; each tenant gets its own editable copies when an admin presses
"Add starter IT articles" on the Knowledge Base screen. This module is the single source of the starter
text: the Knowledge Base route, the retrieval tests and the output checks all load it.

Content rules (D-36, T-85-07), pinned by tests:

* generic: no product or vendor name, no operating system name;
* no URL, www. host, email address or phone number, so an output check can never allow a foreign link
  from a starter;
* the first line tells the admin to adapt the article, and placeholders such as "your company's VPN app"
  show what to edit;
* the password article covers only the self-service how-to; unlocks, MFA resets and access changes go to
  a person (D-32).

Stdlib only.
"""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Tuple, Union

FIRST_LINE = "Edit this article to match your organization before you rely on it."
MAX_CONTENT_CHARS = 20000

_PASSWORD_RESET = FIRST_LINE + """

How to reset your own password

If you forgot your password, or you want to change it, you can reset it yourself. This is the password
reset how-to for your sign-in to your company's systems.

1. Open your company's sign-in page.
2. Choose "Forgot password" below the password box.
3. Enter your work user name and follow the steps on the screen. A reset link or a one-time code is sent
   to the contact details your company has on file for you.
4. Choose a new password that follows your company's password rules. A long phrase is better than a short
   word with symbols.
5. Sign in with the new password. If a device keeps asking for the old password, sign out of it and sign
   in again.

If the reset link or code does not arrive, wait a few minutes and check your spam folder before you try
again.

What this article does not cover

An account that is locked, a lost or replaced phone for multi-factor sign-in (an MFA reset), and any
change to what you can access have to be done by a person. Choose "I still need help" and a person from
IT will take over. Never share your password or a one-time code with anyone, including IT.
"""

_VPN = FIRST_LINE + """

Fixing a VPN connection that will not connect or keeps dropping

Use these steps when your company's VPN app cannot connect, says the connection failed, or disconnects
while you work from home or another network.

1. Check that your internet connection works: open any public web page. If it does not load, fix your
   home network first (restart the router, move closer to it, or switch to a wired connection).
2. Close your company's VPN app completely and open it again.
3. Sign in with your work user name and password. If it asks for a one-time code, enter the current code.
4. Choose the server or location your company tells you to use, then connect.
5. If it still fails, restart your computer and try again once.
6. Try another network, for example a phone hotspot. If it connects there, the problem is your home or
   public network, not your account.

Tips
- Do not run two VPN apps at the same time.
- Public places sometimes block VPN connections. Try the phone hotspot.
- Keep your company's VPN app up to date; your company may publish the newest version on its software
  page.

If none of this works, choose "I still need help" and write down the exact message your VPN app shows.
"""

_PRINTER = FIRST_LINE + """

Fixing a printer that will not print

Use these steps when a print job does not come out, the printer shows as offline, or the job is stuck in
the queue.

1. Look at the printer itself. Check that it is on, has paper and toner or ink, and shows no error on its
   display. Clear any paper jam shown on the display.
2. Check that you chose your company's printer for this job and not another one. Open the print dialog
   and pick the printer again.
3. Open the print queue on your computer and look for your job. If it is stuck, cancel the job and print
   again.
4. If the printer shows as offline, turn the printer off, wait 30 seconds, and turn it on again. Then
   print a single page.
5. Make sure your computer is on your company's network or connected to the VPN when you print to an
   office printer from home.
6. Restart your computer if the queue still will not clear.

Printing from a phone or tablet: use the print option of the app and pick your company's printer from the
list. If the printer is missing, you are probably on the wrong network.

If the printer still does not respond, choose "I still need help" and say which printer it is (the name
or the label on the printer) and what its display shows.
"""

_AGENT_TRAY = FIRST_LINE + """

Using the IT support tray app on your computer

Your company's IT support agent runs on your computer and shows a small icon in the tray, next to the
clock. Right-click the icon to open its menu.

Raise a Ticket
1. Right-click the tray icon, choose "Raise a Ticket", then pick a request type, for example
   "Report an Issue".
2. Write a short title and describe what is wrong in a few sentences.
3. Choose Submit. The window tells you the ticket number.

My tickets
1. Right-click the tray icon and choose "My tickets".
2. Select a ticket in the list to read its status and any reply from IT.
3. If an answer from IT support appears, a pop-up near the clock tells you. Click it to read the answer.
4. Choose "This fixed it" if the answer solved the problem. The ticket is marked resolved.
5. Choose "I still need help" if it did not. You can add a short note first. A person from IT will take
   over.

Checking that the agent is working
1. Left-click the tray icon, or right-click it and choose "Agent Status", to see the agent status.
2. If the status says the agent is not connected, check your internet connection and your company's
   network or VPN, then wait a minute and look again.
3. If the tray icon is missing, restart your computer. If it is still missing, choose "I still need
   help" on a ticket raised from another device, or ask your company's IT contact.
"""

# (key, title, content, tags). Order is the order in the dialog copy: password reset, VPN, printer, agent tray app.
STARTERS: Tuple[Dict[str, Any], ...] = (
    {"key": "password_reset", "title": "How to reset your own password",
     "content": _PASSWORD_RESET, "tags": ["helpdesk", "starter", "password"]},
    {"key": "vpn", "title": "Fixing a VPN connection that will not connect",
     "content": _VPN, "tags": ["helpdesk", "starter", "vpn"]},
    {"key": "printer", "title": "Fixing a printer that will not print",
     "content": _PRINTER, "tags": ["helpdesk", "starter", "printer"]},
    {"key": "agent_tray", "title": "Using the IT support tray app",
     "content": _AGENT_TRAY, "tags": ["helpdesk", "starter", "agent", "tray"]},
)


def _iso(now: Union[datetime, date, str, None]) -> str:
    if isinstance(now, str):
        return now
    if now is None:
        return datetime.utcnow().isoformat()
    return now.isoformat()


def copy_docs(tenant_id: str, actor: Dict[str, Any], now: Union[datetime, str, None] = None) -> List[Dict[str, Any]]:
    """The four starters as tenant-scoped ``knowledge_docs`` documents, ready to insert.

    Each carries ``helpdesk`` True and ``starterKey`` so the route can tell which starters a tenant already
    has. A tenant id that is empty or "global" is refused: a starter copy is always the tenant's own and
    the shared reference documents are never written here.
    """
    tenant = (tenant_id or "").strip() if isinstance(tenant_id, str) else ""
    if not tenant or tenant == "global":
        raise ValueError("A starter copy needs a real tenant id")
    stamp = _iso(now)
    author = ((actor or {}).get("name") or (actor or {}).get("username") or "system")
    return [{
        "id": "kb-" + uuid.uuid4().hex[:12],
        "tenantId": tenant,
        "title": starter["title"],
        "content": starter["content"],
        "tags": list(starter["tags"]),
        "source": "starter",
        "helpdesk": True,
        "starterKey": starter["key"],
        "createdBy": author,
        "createdAt": stamp,
        "updatedAt": stamp,
    } for starter in STARTERS]
