"""Staged patch rollouts, gap plan 84-28 task 2: which cards offer Cancel and what the Cancel dialog says.

Real MongoDB (skips without one). Rollouts are written straight into the collections the controller owns.

Value: protects=PTCH-04 / D-16 / T-84-78: the server decides Cancel and Resume (the browser infers nothing); a running
rollout offers Cancel with a sentence saying nothing is reverted; a rollout whose Cancel is settling offers neither
Resume nor a second Cancel; fails_when=canCancel is false for a running rollout, true for a finished one or while a
cancel is settling, canResume is true while it settles, or the note shows on a halted rollout;
no_claim=the HTTP routes (test_patch_rollout_cancel_running.py) and the dialog (src/__tests__).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops.rollout import messages
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.test_patch_rollout_views import MANAGER, NOW, VIEWER, _env, card, host, prepare, ring, seed  # noqa: F401

REQUEST = {"by": {"id": "u1", "name": "Ann"}, "at": NOW}
HALTED = {"code": "canary_failed", "ring": 0, "text": "t"}


async def test_a_running_rollout_offers_cancel_with_the_note_and_never_resume(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db)
    got = await card(mongo_db)
    assert got["canCancel"] is True and got["canResume"] is False
    assert got["cancelNote"] == messages.CANCEL_NOTE_RUNNING and "nothing is reverted" in got["cancelNote"]


async def test_a_rollout_whose_cancel_is_settling_offers_neither_cancel_nor_resume(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, cancelRequested=REQUEST)
    got = await card(mongo_db)
    assert got["canCancel"] is False and got["canResume"] is False and got["cancelNote"] is None
    await seed(mongo_db, "r2", status="halted", rings=[ring(0, "Canary", "halted")], cancelRequested=REQUEST,
               hosts=[host("a1", 0, "failed", failureMessage="m")], haltReason=HALTED)
    halted = await card(mongo_db, "r2")
    assert halted["canResume"] is False and halted["canCancel"] is False


async def test_a_rollout_whose_cancel_is_settling_says_who_asked_and_when(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, cancelRequested=REQUEST)
    got = await card(mongo_db)
    assert got["cancelling"] is True and got["cancelRequestedBy"] == "Ann" and got["cancelRequestedAt"]
    assert got["cancellingNote"] == "Cancel requested by Ann. It ends when the installs in progress finish."
    await seed(mongo_db, "r2", cancelRequested={"by": {"id": "u1"}, "at": NOW})
    nameless = await card(mongo_db, "r2")
    assert nameless["cancelRequestedBy"] is None and nameless["cancellingNote"] == messages.CANCELLING_NOTE["anon"]
    await seed(mongo_db, "r3")
    plain = await card(mongo_db, "r3")
    assert plain["cancelling"] is False and plain["cancellingNote"] is None and plain["cancelRequestedAt"] is None


async def test_a_halted_rollout_keeps_its_buttons_and_has_no_note(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, status="halted", rings=[ring(0, "Canary", "halted")],
               hosts=[host("a1", 0, "failed", failureMessage="m")], haltReason=HALTED)
    got = await card(mongo_db)
    assert got["canResume"] is True and got["canCancel"] is True and got["cancelNote"] is None


async def test_a_finished_rollout_and_a_viewer_are_offered_no_cancel(mongo_db):
    await prepare(mongo_db)
    await seed(mongo_db, status="completed")
    assert (await card(mongo_db))["canCancel"] is False
    await seed(mongo_db, "r2")
    assert (await card(mongo_db, "r2", caller=VIEWER))["canCancel"] is False
