"""Autonomous Ops daily digest (Phase 86, plan 86-05, ACTV-04, D-01..D-04).

Value: protects=each organization's admins get one honest digest a day (what ran, what was undone, what waits
for approval, and, kept apart, what shadow mode would have done), only they can read it, and a restart, a
second worker or a failing mail server never makes it a second one; fails_when=a count or section differs from
the screen, a simulation item is counted as ran, the notice reaches on-call, the platform feed or a reader the
tenant_admins audience does not admit, a quiet day sends something, or one day sends twice; no_claim=real mail
(email_service.send_email is always a mock), the live database and the live backend.

Real-MongoDB cases use the throwaway database of tests/_mongo_test_db.py (set MONGO_TEST_URL, MONGODB_URL and
MONGO_URI to a private mongod; never the live one) and are never skipped.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-the-digest")

from autonomous_ops.reporting import digest_text as text
from autonomous_ops.reporting.digest_text import DigestItem, Group

UTC = timezone.utc
MORE = "Showing the first 10 of {n}. The rest are on the Autonomous Ops screen."
CLOSING = "Open Autonomous Ops in the sidebar to see everything."


def item(n, *, at=None, action="Block IP address", target="203.0.113.7", rule="sweep:block_ip", command="block_ip"):
    return DigestItem(id=f"AO-{n:03d}", at=at or datetime(2026, 11, 12, 6, 12, tzinfo=UTC), action_label=action,
                      target=target, rule_id=rule, command=command)


# ================================================================== task 1: the pure text

def test_counts_line_always_carries_all_three_counts():
    assert text.counts_line(12, 2, 3) == "Last 24 hours: 12 ran, 2 undone, 3 waiting for your approval."
    assert text.counts_line(1, 1, 1) == "Last 24 hours: 1 ran, 1 undone, 1 waiting for your approval."
    assert text.counts_line(0, 0, 0) == "Last 24 hours: 0 ran, 0 undone, 0 waiting for your approval."


def test_simulation_line_says_nothing_was_carried_out():
    assert text.simulation_line(7) == "Simulation (shadow mode): 7 would have been done. Nothing was carried out."


def test_a_section_is_cut_at_ten_items_with_the_overflow_sentence():
    lines = text.section_lines("Ran", [item(n) for n in range(12)])
    assert lines[0] == "Ran (12)"
    assert len([line for line in lines if line.startswith("- ")]) == 10
    assert lines[-1] == MORE.format(n=12)
    assert lines[1] == "- Block IP address on 203.0.113.7. Rule: Block an address two sources agree on. 06:12 UTC"


def test_a_short_section_has_no_overflow_sentence_and_a_total_larger_than_the_listed_items_still_cuts():
    assert MORE.format(n=3) not in text.section_lines("Ran", [item(n) for n in range(3)])
    lines = text.section_lines("Ran", [item(n) for n in range(10)], total=14)
    assert lines[0] == "Ran (14)" and lines[-1] == MORE.format(n=14)


def test_an_item_without_a_target_leaves_the_target_out():
    line = text.section_lines("Ran", [item(1, target=None)])[1]
    assert line.startswith("- Block IP address. Rule: ")


def test_a_200_character_target_is_cut_to_80_characters_with_an_ellipsis():
    line = text.section_lines("Ran", [item(1, target="h" * 200)])[1]
    shown = line[len("- Block IP address on "):line.index(". Rule:")]
    assert len(shown) == 80 and shown.endswith("…") and shown[:-1] == "h" * 79


def test_a_target_with_line_breaks_stays_on_one_line():
    line = text.section_lines("Ran", [item(1, target="host\r\nBcc: x\nmore")])[1]
    assert "\n" not in line and "\r" not in line and "host Bcc: x more" in line


def test_the_simulation_section_is_introduced_and_its_items_say_would_have():
    lines = text.section_lines("Simulation: would have done", [item(1), item(2, command="isolate_host", target="WS-014", at=datetime(2026, 11, 12, 5, 0, tzinfo=UTC))],
                               simulation=True)
    assert lines[0] == "Simulation: would have done (2)"
    assert lines[1] == "Shadow mode is on. Nothing below was carried out."
    assert lines[2].startswith("- Would have blocked 203.0.113.7. Rule: ")
    assert lines[3].startswith("- Would have isolated WS-014. Rule: ")


def test_every_simulation_verb_reads_as_a_past_tense_phrase_and_unknown_commands_fall_back():
    cases = {"quarantine_file": "Would have quarantined a file on H.", "restart_service": "Would have restarted a service on H.",
             "kill_process": "Would have stopped a process on H.", "install_patches": "Would have installed patches on H.",
             "reboot_host": "Would have restarted H.", "ticket_answer": "Would have answered ticket H."}
    for command, expected in cases.items():
        got = text.section_lines("S", [item(1, command=command, target="H")], simulation=True)[2]
        assert got.startswith(f"- {expected} Rule: "), (command, got)
    fallback = text.section_lines("S", [item(1, command="rotate_key", action="Rotate key", target="H")], simulation=True)[2]
    assert fallback.startswith("- Would have run rotate key on H. Rule: ")


def test_the_notice_lists_sections_in_order_and_leaves_empty_ones_out():
    body = text.notice_text(Group(2, [item(1), item(2)]), Group(0, []), Group(1, [item(3, action="Install patches")]),
                            Group(3, [item(4), item(5), item(6)]))
    lines = body.split("\n")
    assert lines[0] == "Last 24 hours: 2 ran, 0 undone, 1 waiting for your approval."
    assert lines[1] == "Simulation (shadow mode): 3 would have been done. Nothing was carried out."
    assert lines[2] == ""
    headings = [line for line in lines if line.endswith(")") and not line.startswith("-") and " (" in line
                and not line.startswith("Simulation (")]
    assert headings == ["Ran (2)", "Waiting for your approval (1)", "Simulation: would have done (3)"]
    assert "Undone" not in body
    assert lines[-1] == CLOSING and lines[-2] == ""


def test_the_notice_has_no_simulation_line_when_there_are_no_simulation_items():
    body = text.notice_text(Group(1, [item(1)]), Group(0, []), Group(0, []), Group(0, []))
    lines = body.split("\n")
    assert lines[0].startswith("Last 24 hours: 1 ran, 0 undone, 0 waiting")
    assert lines[1] == "" and lines[2] == "Ran (1)"
    assert "Simulation" not in body


def test_a_simulation_only_day_reads_zero_ran_zero_undone_zero_waiting_then_the_simulation():
    body = text.notice_text(Group(0, []), Group(0, []), Group(0, []), Group(2, [item(1), item(2)]))
    lines = body.split("\n")
    assert lines[0] == "Last 24 hours: 0 ran, 0 undone, 0 waiting for your approval."
    assert lines[1].startswith("Simulation (shadow mode): 2 would have been done.")
    assert "Ran (" not in body and "Simulation: would have done (2)" in body


def test_the_notice_title_and_a_plain_list_of_items_is_accepted_as_a_group():
    assert text.notice_title() == "Autonomous Ops daily digest"
    body = text.notice_text([item(1)], [], [], [])
    assert "Ran (1)" in body


def test_items_are_listed_newest_first_with_ties_by_id_descending():
    a = item(1, at=datetime(2026, 11, 12, 5, 0, tzinfo=UTC))
    b = item(2, at=datetime(2026, 11, 12, 6, 0, tzinfo=UTC))
    c = item(3, at=datetime(2026, 11, 12, 6, 0, tzinfo=UTC))
    lines = text.section_lines("Ran", [a, b, c])
    assert [line[-9:] for line in lines[1:]] == ["06:00 UTC", "06:00 UTC", "05:00 UTC"]
    ids_in_order = [i.id for i in sorted([a, b, c], key=lambda i: (i.at, i.id), reverse=True)]
    assert ids_in_order == ["AO-003", "AO-002", "AO-001"]


def test_the_time_is_the_utc_clock_of_the_item():
    from datetime import timedelta
    plus5 = timezone(timedelta(hours=5))
    line = text.section_lines("Ran", [item(1, at=datetime(2026, 11, 12, 10, 30, tzinfo=plus5))])[1]
    assert line.endswith("05:30 UTC")


def test_the_subject_strips_line_breaks_from_the_organization_name():
    subject = text.email_subject("Acme\r\nBcc: x", 12, 2, 3)
    assert "\r" not in subject and "\n" not in subject
    assert subject == "Autonomous Ops daily digest for Acme Bcc: x: 12 ran, 2 undone, 3 waiting"


def test_the_email_text_follows_the_agreed_shape():
    sections = (Group(12, [item(n) for n in range(10)]), Group(0, []), Group(1, [item(20, action="Install patches", target="WS-1")]),
                Group(1, [item(30, command="isolate_host", target="WS-014")]))
    body = text.email_text("Acme", "2026-11-12", sections, "https://app.example")
    lines = body.split("\n")
    assert lines[0] == "Autonomous Ops daily digest for Acme"
    assert lines[1] == "The last 24 hours, up to 07:00 UTC on 12 Nov 2026."
    assert lines[2] == "" and lines[3] == "12 ran, 0 undone, 1 waiting for your approval."
    assert lines[4] == "" and lines[5] == "Ran (12)"
    assert MORE.format(n=12) in lines
    assert "Waiting for your approval (1)" in lines and "Simulation: would have done (1)" in lines
    assert "See everything: https://app.example" in lines
    assert lines[-2] == ""
    assert lines[-1] == ("You get this because you are an administrator of Acme. It is sent once a day, and only on days "
                         "when something ran, was undone, is waiting for approval or would have been done in shadow mode.")
    assert body.index("Ran (12)") < body.index("Waiting for your approval (1)") < body.index("Simulation: would have done")


def test_the_email_html_carries_the_same_words_in_order_with_every_server_string_escaped():
    evil = '<script>alert(1)</script> & "x"'
    sections = (Group(1, [item(1, target=evil)]), Group(0, []), Group(0, []), Group(1, [item(2, target=evil)]))
    html_body = text.email_html("A<b>cme", "2026-11-12", sections, 'https://app.example/?a=1&b="2"')
    assert "<script>" not in html_body and "<b>cme" not in html_body and "<img" not in html_body
    assert "&lt;script&gt;" in html_body and "A&lt;b&gt;cme" in html_body and "&amp;" in html_body
    order = ["Autonomous Ops daily digest for", "The last 24 hours, up to 07:00 UTC on 12 Nov 2026.", "1 ran, 0 undone, 0 waiting",
             "Ran (1)", "Simulation: would have done (1)", "Shadow mode is on. Nothing below was carried out.",
             "See everything", "You get this because you are an administrator of"]
    positions = [html_body.index(words) for words in order]
    assert positions == sorted(positions)


def test_a_digest_of_long_targets_and_rule_names_stays_bounded():
    long_item = lambda n: item(n, target="t" * 500, rule="x" * 500)  # noqa: E731
    group = Group(10, [long_item(n) for n in range(10)])
    body = text.notice_text(group, group, group, group)
    assert len(body) < 20000
    assert all(len(line) < 700 for line in body.split("\n"))


# ================================================================== task 2: one organization

import asyncio  # noqa: E402
import uuid  # noqa: E402
from datetime import timedelta  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import email_service as email_module  # noqa: E402
import notification_audience  # noqa: E402
from autonomous_ops.reporting import DIGESTS, digest  # noqa: E402
from tests._mongo_test_db import mongo_db  # noqa: E402,F401  (fixture)

DAY = "2026-11-12"
NOW = datetime(2026, 11, 12, 7, 5, tzinfo=UTC)
FRONTEND = "https://app.example"
SMTP = {"smtpHost": "smtp.example", "smtpPasswordEncrypted": "x"}


def _at(h, m=0, s=0, *, day=12):
    return datetime(2026, 11, day, h, m, s, tzinfo=UTC)


async def seed(db, tenant, command, state, *, finished=None, created=None, kind="security", rule=None, target=None,
               expires=None, inputs=None):
    """One decision row with the fields the digest reads (terminal rows carry finishedAt)."""
    row = {"id": "AO-" + uuid.uuid4().hex, "tenantId": tenant, "kind": kind, "command": command, "state": state,
           "reason": {"ruleId": rule or f"sweep:{command}", "inputs": inputs or {}}, "target": target or "203.0.113.7",
           "createdAt": created or _at(3), "finishedAt": finished}
    if expires:
        row["approval"] = {"expiresAt": expires}
    await db.autonomy_actions.insert_one(row)
    return row


@pytest.fixture
def world(mongo_db, monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    return mongo_db


async def _ready(db, *tenants):
    await digest.ensure_indexes(db)
    for tenant in tenants:
        await db.tenants.replace_one({"id": tenant}, {"id": tenant, "name": tenant.title(), "enabledFeatures": ["view:autonomous_ops"]},
                                     upsert=True)


async def _notices(db, tenant):
    return [n async for n in db.notifications.find({"tenantId": tenant}, {"_id": 0})]


def _mail(*, smtp=SMTP, send=None):
    """Patch the mail path: the smtp lookup and email_service.send_email (nothing real is sent)."""
    mock = send or AsyncMock(return_value={"success": True})
    return mock, [patch("auth_password_reset_endpoints._resolve_smtp_config", AsyncMock(return_value=smtp)),
                  patch("database.get_database", lambda: MagicMock()),
                  patch.object(email_module.email_service, "send_email", mock)]


async def _with_mail(coro_factory, *, smtp=SMTP, send=None, patches=()):
    mock, ps = _mail(smtp=smtp, send=send)
    for p in list(ps) + list(patches):
        p.start()
    try:
        return mock, await coro_factory()
    finally:
        for p in list(ps) + list(patches):
            p.stop()


def test_the_window_is_the_24_hours_before_07_00_utc_of_the_day():
    assert digest.window(DAY) == (_at(7, day=11), _at(7))


async def test_a_row_finished_exactly_at_07_00_belongs_to_the_next_digest(world):
    await _ready(world, "t1")
    inside = await seed(world, "t1", "block_ip", "executed", finished=_at(6, 59, 59))
    await seed(world, "t1", "block_ip", "executed", finished=_at(7, 0, 0))
    edge = await seed(world, "t1", "block_ip", "executed", finished=_at(7, 0, 0, day=11))
    ran, undone, waiting, simulation = await digest.gather(world, "t1", DAY, NOW)
    assert ran.total == 2 and sorted(i.id for i in ran.items) == sorted([inside["id"], edge["id"]])
    assert (undone.total, waiting.total, simulation.total) == (0, 0, 0)


async def test_the_digest_counts_the_organizations_rows_and_stores_one_notice_for_its_admins(world):
    await _ready(world, "t1", "t2")
    for _ in range(2):
        await seed(world, "t1", "block_ip", "executed", finished=_at(5))
    await seed(world, "t1", "isolate_host", "undone", finished=_at(6))
    await seed(world, "t1", "install_patches", "awaiting_approval", expires=NOW + timedelta(hours=1))
    for _ in range(3):
        await seed(world, "t1", "block_ip", "shadow", created=_at(4))
    await seed(world, "t1", "block_ip", "recorded", kind="control", finished=_at(5))
    await seed(world, "t1", "block_ip", "recorded", kind="platform_health", finished=_at(5))
    await seed(world, "t2", "block_ip", "executed", finished=_at(5))
    assert await digest.send_for_tenant(world, "t1", DAY, NOW) == "sent"
    notices = await _notices(world, "t1")
    assert len(notices) == 1
    lines = notices[0]["message"].split("\n")
    assert lines[0] == "Last 24 hours: 2 ran, 1 undone, 1 waiting for your approval."
    assert lines[1] == "Simulation (shadow mode): 3 would have been done. Nothing was carried out."
    assert notices[0]["title"] == "Autonomous Ops daily digest" and notices[0]["severity"] == "info"
    meta = notices[0]["metadata"]
    assert meta["source"] == "autonomous_ops" and meta["event"] == "autonomous_ops.daily_digest"
    assert meta["audience"] == "tenant_admins" and meta["day"] == DAY
    assert meta["counts"] == {"ran": 2, "undone": 1, "waiting": 1, "simulation": 3}
    assert "Ran (3)" not in notices[0]["message"]            # PROH-86-02: simulation is never counted as ran
    assert [n async for n in world.notifications.find({"tenantId": "platform-admin"})] == []
    assert await world.oncall_outbox.count_documents({}) == 0   # PROH-86-01: nothing pages on-call
    assert await _notices(world, "t2") == []
    claim = await world[DIGESTS].find_one({"tenantId": "t1", "day": DAY})
    assert claim["state"] == "sent" and claim["counts"] == meta["counts"] and claim["sentAt"]


async def test_the_notice_is_read_only_by_users_the_tenant_admins_audience_admits(world):
    await _ready(world, "t1")
    await seed(world, "t1", "block_ip", "executed", finished=_at(5))
    await digest.send_for_tenant(world, "t1", DAY, NOW)

    async def readable(perms):
        with patch.object(notification_audience.rbac_service, "get_user_permissions", AsyncMock(return_value=perms)), \
                patch.object(notification_audience, "is_ticket_staff", AsyncMock(return_value=False)):
            query = await notification_audience.reader_filter(MagicMock(username="u", email="u@x.io"), "t1")
        return await world.notifications.count_documents(query)

    assert await readable(["view:overview"]) == 0
    assert await readable(["manage:agents"]) == 1
    assert await readable(["*"]) == 1


async def test_a_simulation_only_day_sends_the_digest_with_zero_counts(world):
    await _ready(world, "t1")
    await seed(world, "t1", "block_ip", "shadow", created=_at(4))
    await seed(world, "t1", "isolate_host", "shadow", created=_at(5))
    assert await digest.send_for_tenant(world, "t1", DAY, NOW) == "sent"
    lines = (await _notices(world, "t1"))[0]["message"].split("\n")
    assert lines[0] == "Last 24 hours: 0 ran, 0 undone, 0 waiting for your approval."
    assert lines[1].startswith("Simulation (shadow mode): 2 would have been done.")


async def test_a_day_with_nothing_or_only_failed_and_refused_rows_is_quiet(world):
    await _ready(world, "t1", "t2")
    await seed(world, "t2", "block_ip", "failed", finished=_at(5))
    await seed(world, "t2", "block_ip", "refused", finished=_at(5))
    await seed(world, "t2", "block_ip", "shadow", created=_at(3, day=10))   # before the window
    for tenant in ("t1", "t2"):
        assert await digest.send_for_tenant(world, tenant, DAY, NOW) == "quiet"
        assert await _notices(world, tenant) == []
        assert (await world[DIGESTS].find_one({"tenantId": tenant, "day": DAY}))["state"] == "quiet"


async def test_a_second_call_for_the_same_day_sends_nothing(world):
    await _ready(world, "t1")
    await seed(world, "t1", "block_ip", "executed", finished=_at(5))
    assert await digest.send_for_tenant(world, "t1", DAY, NOW) == "sent"
    assert await digest.send_for_tenant(world, "t1", DAY, NOW) == "already_claimed"
    first, second = await asyncio.gather(digest.send_for_tenant(world, "t1", "2026-11-13", NOW + timedelta(days=1)),
                                         digest.send_for_tenant(world, "t1", "2026-11-13", NOW + timedelta(days=1)))
    assert sorted([first, second]) == ["already_claimed", "quiet"]
    assert len(await _notices(world, "t1")) == 1


async def test_waiting_is_the_screens_needs_your_decision_set(world):
    await _ready(world, "t1")
    live = NOW + timedelta(hours=1)
    await seed(world, "t1", "install_patches", "awaiting_approval", expires=live)
    await seed(world, "t1", "install_patches", "awaiting_approval", expires=NOW - timedelta(minutes=1))   # expired
    await seed(world, "t1", "ticket_answer", "awaiting_approval", expires=live, inputs={"suggestionOnly": True})
    _, _, waiting, _ = await digest.gather(world, "t1", DAY, NOW)
    assert waiting.total == 1


async def test_items_are_newest_first_cut_at_ten_with_the_total_kept(world):
    await _ready(world, "t1")
    for n in range(12):
        await seed(world, "t1", "block_ip", "executed", finished=_at(1, n), target=f"198.51.100.{n}")
    await digest.send_for_tenant(world, "t1", DAY, NOW)
    lines = (await _notices(world, "t1"))[0]["message"].split("\n")
    start = lines.index("Ran (12)")
    assert lines[start + 1].endswith("01:11 UTC") and lines[start + 10].endswith("01:02 UTC")
    assert lines[start + 11] == MORE.format(n=12)


async def test_long_targets_are_cut_in_the_stored_notice(world):
    await _ready(world, "t1")
    for n in range(10):
        await seed(world, "t1", "block_ip", "executed", finished=_at(1, n), target="x" * 400, rule="rule:" + "y" * 300)
    await digest.send_for_tenant(world, "t1", DAY, NOW)
    message = (await _notices(world, "t1"))[0]["message"]
    assert "x" * 81 not in message and len(message) < 8000


async def test_a_failed_read_releases_the_claim_so_the_day_is_not_lost(world):
    await _ready(world, "t1")
    with patch.object(digest, "gather", AsyncMock(side_effect=RuntimeError("down"))):
        with pytest.raises(RuntimeError):
            await digest.send_for_tenant(world, "t1", DAY, NOW)
    assert await world[DIGESTS].count_documents({"tenantId": "t1"}) == 0


async def _admins(db):
    await db.users.insert_many([
        {"email": "a1@x.io", "tenantId": "t1", "role": "Tenant Admin", "status": "Active"},
        {"email": "a2@x.io", "tenantId": "t1", "role": "admin", "status": "Active"},
        {"email": "gone@x.io", "tenantId": "t1", "role": "admin", "status": "Inactive"},
        {"email": "v@x.io", "tenantId": "t1", "role": "Viewer", "status": "Active"},
        {"email": "other@x.io", "tenantId": "t2", "role": "admin", "status": "Active"}])


async def test_email_goes_to_the_tenant_admins_only_with_the_digest_subject(world, monkeypatch):
    await _ready(world, "t1")
    await _admins(world)
    await seed(world, "t1", "block_ip", "executed", finished=_at(5))
    monkeypatch.setenv("FRONTEND_URL", FRONTEND + "/")
    send, _ = await _with_mail(lambda: digest.send_for_tenant(world, "t1", DAY, NOW))
    assert send.await_count == 2
    assert sorted(c.kwargs["to_email"] for c in send.await_args_list) == ["a1@x.io", "a2@x.io"]
    first = send.await_args_list[0].kwargs
    assert first["subject"] == "Autonomous Ops daily digest for T1: 1 ran, 0 undone, 0 waiting"
    assert "See everything: https://app.example" in first["body_text"] and "<p>" in first["body_html"]
    assert first["smtp_config"] == SMTP
    claim = await world[DIGESTS].find_one({"tenantId": "t1", "day": DAY})
    assert claim["state"] == "sent" and claim["email"] == {"sent": 2, "failed": 0}


@pytest.mark.parametrize("how", ["raises", "refused", "hangs"])
async def test_a_failing_email_never_blocks_the_notice(world, monkeypatch, how):
    await _ready(world, "t1")
    await _admins(world)
    await seed(world, "t1", "block_ip", "executed", finished=_at(5))
    monkeypatch.setenv("FRONTEND_URL", FRONTEND)

    async def hang(**_):
        await asyncio.sleep(60)

    send = {"raises": AsyncMock(side_effect=RuntimeError("smtp down")), "refused": AsyncMock(return_value={"success": False}),
            "hangs": AsyncMock(side_effect=hang)}[how]
    _, result = await _with_mail(lambda: digest.send_for_tenant(world, "t1", DAY, NOW), send=send,
                                 patches=[patch.object(digest, "EMAIL_TIMEOUT", 0.05)])
    assert result == "sent" and len(await _notices(world, "t1")) == 1
    assert (await world[DIGESTS].find_one({"tenantId": "t1", "day": DAY}))["email"] == {"sent": 0, "failed": 2}


@pytest.mark.parametrize("frontend,smtp", [("", SMTP), ("app.example", SMTP), (FRONTEND, None)])
async def test_no_email_without_an_http_link_base_or_a_mail_configuration(world, monkeypatch, frontend, smtp):
    await _ready(world, "t1")
    await _admins(world)
    await seed(world, "t1", "block_ip", "executed", finished=_at(5))
    monkeypatch.setenv("FRONTEND_URL", frontend)
    send, result = await _with_mail(lambda: digest.send_for_tenant(world, "t1", DAY, NOW), smtp=smtp)
    assert result == "sent" and send.await_count == 0 and len(await _notices(world, "t1")) == 1


async def test_the_organization_name_loses_line_breaks_in_the_subject(world, monkeypatch):
    await _ready(world, "t1")
    await world.tenants.update_one({"id": "t1"}, {"$set": {"name": "Acme\r\nBcc: x"}})
    await _admins(world)
    await seed(world, "t1", "block_ip", "executed", finished=_at(5))
    monkeypatch.setenv("FRONTEND_URL", FRONTEND)
    send, _ = await _with_mail(lambda: digest.send_for_tenant(world, "t1", DAY, NOW))
    subject = send.await_args_list[0].kwargs["subject"]
    assert "\r" not in subject and "\n" not in subject and "Acme Bcc: x" in subject
