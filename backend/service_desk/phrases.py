"""The fixed phrase lists the service desk matches before the model sees a ticket (D-02, D-23, D-32).

Plain phrases only: rules.py normalises each one (sanitize.normalize_for_match) and matches it as an escaped
literal with word boundaries. Nothing in a ticket is ever compiled as a pattern. The lists are pinned by
tests/fixtures/service_desk/escalation_set.jsonl, so a phrase added or removed here is a visible test diff.

Placement rules the escalation set pins:

* The rules run in a fixed order (security, billing, legal, account access, asking for a person), so a ticket
  that hits two lists always reports the earlier one. Account-compromise phrasing ("my account was hacked",
  "someone logged in as me") belongs to ACCOUNT_ACCESS (D-32); SECURITY therefore names the device and
  company cases one by one and carries no bare "hacked" or "compromised".
* "Forgot my password", "reset my password" and "change my password" are in no list (D-32): the starter
  password article answers them. Unlocks, MFA and 2FA resets, access grants, permission changes and
  suspected compromise always go to a person.
"""

SECURITY = (
    "phishing", "phished", "phish", "suspicious email", "suspicious link", "suspicious attachment",
    "suspicious message", "suspicious activity", "malware", "virus", "ransomware", "ransom", "spyware", "trojan",
    "keylogger", "botnet", "data breach", "data leak", "leaked data", "security breach", "security incident",
    "security alert", "security threat", "vulnerability", "exploit", "hacker", "hackers", "hacking attempt",
    "ddos", "infected", "my laptop was hacked", "my computer was hacked", "my pc was hacked",
    "my device was hacked", "my phone was hacked", "the server was hacked", "we were hacked",
    "we have been hacked", "we got hacked", "i was hacked", "i got hacked", "i have been hacked",
    "laptop was compromised", "computer was compromised", "pc was compromised", "device was compromised",
    "server was compromised", "network was compromised", "system was compromised", "clicked a link",
    "clicked on a link", "clicked the link", "opened an attachment", "opened a suspicious", "stolen laptop",
    "laptop was stolen", "lost my laptop", "lost laptop", "lost device", "lost my phone", "stolen phone",
    "stolen device", "scam", "scammer", "fraud", "fraudulent", "unauthorized access", "unauthorised access",
    "data theft", "stolen data", "wrong person", "wrong recipient", "files are encrypted", "encrypted my files",
    "penetration test", "pentest", "cve",
)

BILLING = (
    "invoice", "invoices", "billing", "billed", "refund", "refunds", "refunded", "charged twice",
    "double charged", "overcharged", "incorrect charge", "wrong charge", "unexpected charge", "credit card",
    "debit card", "payment", "payments", "pay my bill", "my bill", "purchase order", "receipt", "chargeback",
    "bank transfer", "wire transfer", "pricing", "price quote", "cancel my subscription",
    "cancel the subscription", "renewal cost", "budget approval", "expense claim", "reimbursement",
    "reimburse", "tax invoice", "vat",
)

LEGAL = (
    "legal", "lawyer", "lawyers", "attorney", "solicitor", "lawsuit", "sue", "suing", "subpoena", "litigation",
    "legal hold", "gdpr", "ccpa", "data subject request", "right to be forgotten", "right to erasure",
    "privacy request", "data protection officer", "dpo", "court", "court order", "copyright", "trademark",
    "nda", "non disclosure", "non-disclosure", "contract dispute", "terms of service", "cease and desist",
    "defamation", "harassment", "discrimination", "whistleblower", "regulator", "regulatory", "ediscovery",
    "e-discovery", "law enforcement", "police",
)

ACCOUNT_ACCESS = (
    # grants and permission changes
    "give me access", "giving me access", "grant me access", "grant access", "grant permission", "need access",
    "request access", "requesting access", "access request", "can i get access", "add me to", "remove access",
    "revoke access", "revoke permission", "permission", "permissions", "admin rights", "administrator rights",
    "admin access", "administrator access", "local admin", "make me an admin", "make me admin",
    "elevated access", "elevated privileges", "privileges",
    # unlocks, lockouts and disabled accounts
    "unlock my account", "unlock account", "unlock the account", "unlock my user", "locked out", "locked me out",
    "account locked", "account is locked", "account has been locked", "account lockout", "account disabled",
    "account is disabled", "account suspended", "reactivate my account", "enable my account",
    # multi-factor sign-in
    "mfa", "2fa", "two factor", "multi factor", "multifactor", "authenticator", "security key", "otp",
    # suspected compromise (D-32)
    "account was hacked", "account has been hacked", "account got hacked", "account hacked",
    "email was hacked", "my account was compromised", "account has been compromised", "account is compromised",
    "hacked", "compromised", "someone logged in", "someone else logged in", "someone is using my account",
    "someone else is using my account", "someone accessed my account", "unrecognized login",
    "unrecognised login", "unrecognized sign in", "unrecognised sign in", "unknown login", "suspicious login",
    "suspicious sign in", "password was changed by someone", "password was stolen", "password has been stolen",
    "password was leaked", "shared my password", "gave my password",
)

ASK_FOR_PERSON = (
    "talk to a human", "speak to a human", "speak with a human", "talk to a person", "speak to a person",
    "talk to a real person", "speak to a real person", "talk to an agent", "speak to an agent",
    "talk to a technician", "speak to a technician", "talk to someone", "speak to someone", "real person",
    "real human", "human agent", "live agent", "live person", "live support", "not a bot", "not talking to a bot",
    "stop the bot", "no bots", "i want a human", "i want a person", "i want an agent", "i need a human",
    "i need a person", "get me a human", "get me a person", "get me an agent", "connect me to a person",
    "connect me to a human", "connect me to an agent", "transfer me to", "put me through", "call me",
    "phone me", "ring me", "give me a call", "escalate", "escalation", "speak to your manager",
    "talk to your manager", "speak to a manager", "talk to a manager", "supervisor",
)
