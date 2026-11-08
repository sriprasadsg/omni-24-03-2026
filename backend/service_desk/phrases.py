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

# ---------------------------------------------------------------- the English check (D-20, D-35)
#
# Small word sets for rules.is_english, pinned by tests/fixtures/service_desk/language_set.jsonl. English
# evidence is plain function words and English IT vocabulary; "no", "a", "in", "me", "do", "as", "os", "um" and
# every other word the languages share with English are deliberately left out of both sides, as are bare
# acronyms such as "vpn", so a one-word acronym can never decide the language. Diacritics are stripped before
# matching, so the words below are written without them.

ENGLISH_WORDS = (
    "the", "and", "or", "but", "if", "because", "is", "are", "was", "were", "be", "been", "am", "have", "has",
    "had", "does", "did", "doesnt", "dont", "didnt", "isnt", "arent", "cant", "cannot", "couldnt", "wont", "will",
    "would", "should", "can", "could", "may", "might", "must", "not", "never", "to", "of", "for", "from", "with",
    "without", "by", "about", "after", "before", "when", "while", "where", "what", "which", "who", "how", "why",
    "this", "that", "these", "those", "there", "here", "please", "help", "need", "needs", "want", "wants", "get",
    "got", "keep", "keeps", "every", "again", "very", "too", "also", "still", "just", "only", "some", "any", "all",
    "more", "new", "old", "slow", "slowly", "fast", "today", "yesterday", "morning", "last", "night", "week",
    "time", "back", "off", "out", "up", "over", "under", "open", "opens", "close", "start", "starts", "stop",
    "stops", "stopped", "work", "works", "working", "worked", "fix", "fixed", "change", "changed", "use", "using",
    "used", "try", "tried", "trying", "see", "seen", "find", "found", "show", "shows", "showing", "say", "says",
    "tell", "give", "take", "make", "go", "goes", "going", "my", "your", "our", "their", "his", "her", "you", "we",
    "they", "he", "she", "it", "its", "i", "ive", "im", "something", "nothing", "everything", "anyone",
    "someone", "everyone", "able", "unable", "like", "than", "then", "much", "many", "few", "own",
    "printer", "printers", "printing", "print", "prints", "scanner", "laptop", "laptops", "computer", "computers",
    "pc", "monitor", "monitors", "screen", "keyboard", "mouse", "headset", "phone", "battery", "charger", "cable",
    "network", "connect", "connects", "connecting", "connected", "connection", "disconnect", "disconnects",
    "disconnecting", "disconnected", "login", "log", "sign", "signin", "signed", "password", "account", "email",
    "emails", "mail", "mailbox", "attachment", "attachments", "file", "files", "folder", "folders", "drive",
    "backup", "backups", "update", "updates", "updated", "install", "installed", "installing", "software", "app",
    "application", "website", "web", "page", "browser", "server", "down", "offline", "online", "error", "errors",
    "crash", "crashes", "crashing", "crashed", "freeze", "freezes", "freezing", "frozen", "broken", "jammed",
    "failed", "fails", "failing", "fail", "issue", "issues", "problem", "problems", "flickering", "blank", "black",
    "sound", "audio", "video", "call", "calls", "meeting", "room", "office", "home", "floor", "shared", "guest",
    "setup", "guide", "reset", "restart", "reboot", "turn", "turns", "large", "big", "small", "volume", "signal",
    "echo", "echoes", "drain", "drains", "ticket", "support", "access", "slowly", "loading", "load", "loads",
    "responding", "response", "respond", "download", "upload", "uploads", "downloads", "send", "sending",
    "receive", "receiving", "message", "messages", "wireless", "device", "devices", "system", "service",
    "services", "link", "button", "click", "clicking", "type", "typing", "windows", "program", "programs",
)

SPANISH_WORDS = (
    "el", "los", "las", "un", "una", "unos", "unas", "del", "que", "por", "para", "con", "pero", "como", "mi",
    "mis", "tu", "su", "se", "es", "esta", "esto", "estoy", "estamos", "funciona", "funcionan", "imprime",
    "impresora", "ordenador", "computadora", "contrasena", "correo", "conectar", "conecta", "conectarme",
    "puedo", "puede", "necesito", "ayuda", "desde", "casa", "muy", "lento", "lenta", "pantalla", "teclado",
    "raton", "cuenta", "iniciar", "sesion", "ya", "mas", "tengo", "tiene", "nada", "cuando", "donde", "porque",
    "favor", "hola", "gracias", "ayer", "hoy", "ahora", "otra", "sigue", "falla", "fallo",
)

FRENCH_WORDS = (
    "le", "la", "les", "une", "des", "du", "de", "et", "est", "sont", "pas", "ne", "je", "nous", "vous", "mon",
    "ma", "mes", "ton", "notre", "votre", "ce", "cette", "ces", "qui", "pour", "avec", "sans", "dans", "sur",
    "mais", "ordinateur", "imprimante", "ecran", "clavier", "souris", "mot", "passe", "marche", "fonctionne",
    "connecter", "connexion", "reseau", "demarre", "depuis", "matin", "salle", "reunion", "probleme", "besoin",
    "aide", "imprimer", "impossible", "peux", "peut", "trop", "lent", "tres", "bonjour", "merci", "compte",
    "courriel", "fichier", "aujourd", "hier", "toujours", "encore",
)

GERMAN_WORDS = (
    "der", "das", "dem", "des", "ein", "eine", "einen", "einem", "ich", "mein", "meine", "mir", "mich", "wir",
    "sie", "nicht", "kein", "keine", "und", "oder", "aber", "mit", "ohne", "ist", "sind", "kann", "konnen",
    "funktioniert", "drucker", "druckt", "bildschirm", "tastatur", "maus", "passwort", "netzwerk", "verbinden",
    "verbindung", "anmelden", "anmeldung", "fehler", "hilfe", "brauche", "mehr", "noch", "auch", "sehr",
    "langsam", "schwarz", "bleibt", "wieder", "heute", "gestern", "rechner", "bitte", "funktionieren",
)

PORTUGUESE_WORDS = (
    "uma", "uns", "umas", "da", "das", "na", "nas", "nos", "sem", "mas", "meu", "minha", "meus", "minhas",
    "seu", "sua", "nao", "estou", "funcionando", "impressora", "computador", "rede", "senha", "conta", "acessar",
    "acesso", "consigo", "preciso", "ajuda", "muito", "lento", "tela", "obrigado", "ainda", "hoje", "ontem",
    "esta", "problema", "conectar", "imprime", "funciona", "voce", "nosso", "nossa",
)

ITALIAN_WORDS = (
    "il", "lo", "gli", "uno", "della", "dei", "delle", "di", "senza", "mio", "miei", "tuo", "suo", "non", "sono",
    "stampante", "schermo", "tastiera", "rete", "funziona", "funzionare", "riesco", "collegarmi", "collegare",
    "connettere", "accedere", "aiuto", "ho", "molto", "lento", "oggi", "ieri", "stamattina", "grazie",
    "buongiorno", "ancora", "stampa", "stampare", "alla", "nella", "sul", "problema",
)
