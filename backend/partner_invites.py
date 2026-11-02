"""RED stub (Phase 87-06): the invite module is written in the next commit."""
INVITE_DAYS = 7
ROLE_KINDS = ("customer_admin", "partner_admin", "partner_viewer")


def normalize_email(email):
    raise NotImplementedError


async def email_in_use(db, email):
    raise NotImplementedError


async def invite(db, **kwargs):
    raise NotImplementedError


async def issue_invite(db, **kwargs):
    raise NotImplementedError


async def send_invite_email(**kwargs):
    raise NotImplementedError


async def invite_state(db, token, now=None):
    raise NotImplementedError


async def member_status(db, email, now=None):
    raise NotImplementedError


async def resend(db, **kwargs):
    raise NotImplementedError
