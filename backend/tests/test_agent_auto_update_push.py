"""Auto-pushed agent_update instructions (agent_auto_update_service).

Regression: the pushed rows had no id, so the agent could never report them
done. EILT0197's 2.1.9 push sat at "sent" from 09:04 on and the dedup check
treated it as in flight, so 2.1.10 and 2.1.11 were never offered.
"""
import agent_auto_update_service as svc


class FakeInstructions:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    @staticmethod
    def _matches(row, query):
        for key, want in query.items():
            have = row.get(key)
            if isinstance(want, dict) and "$in" in want:
                if have not in want["$in"]:
                    return False
            elif have != want:
                return False
        return True

    async def find_one(self, query):
        return next((r for r in self.rows if self._matches(r, query)), None)

    async def insert_one(self, doc):
        self.rows.append(doc)


class FakeDb:
    def __init__(self, rows=None):
        self.agent_instructions = FakeInstructions(rows)


OUTDATED = {"version": "2.1.10", "platform": "Windows"}


def pushes(db):
    return [r for r in db.agent_instructions.rows if r.get("created_by") == "auto_update" and r.get("id")]


async def test_stale_push_for_an_older_version_does_not_block_the_latest():
    stale = {"agent_id": "a1", "instruction": "agent_update", "status": "sent", "created_by": "auto_update"}
    db = FakeDb([stale])
    await svc.maybe_push_update_instruction(db, "a1", OUTDATED)
    new = pushes(db)
    assert len(new) == 1
    assert new[0]["target_version"] == svc._LATEST_AGENT_VERSION


async def test_push_carries_an_id_so_the_agent_can_report_it():
    db = FakeDb()
    await svc.maybe_push_update_instruction(db, "a1", OUTDATED)
    (row,) = db.agent_instructions.rows
    assert row["id"] and row["status"] == "pending" and row["instruction"] == "agent_update"


async def test_an_in_flight_push_for_the_latest_version_is_not_repeated():
    db = FakeDb()
    await svc.maybe_push_update_instruction(db, "a1", OUTDATED)
    db.agent_instructions.rows[0]["status"] = "sent"
    await svc.maybe_push_update_instruction(db, "a1", OUTDATED)
    assert len(db.agent_instructions.rows) == 1


async def test_up_to_date_and_non_windows_agents_get_nothing():
    db = FakeDb()
    await svc.maybe_push_update_instruction(db, "a1", {"version": svc._LATEST_AGENT_VERSION, "platform": "Windows"})
    await svc.maybe_push_update_instruction(db, "a2", {"version": "2.1.10", "platform": "Linux"})
    await svc.maybe_push_update_instruction(db, "a3", {"version": "2.0.1", "platform": "Windows"})
    assert db.agent_instructions.rows == []


async def test_a_build_newer_than_the_published_one_is_not_downgraded():
    """protects=an agent installed from a fresh source build (e.g. 2.1.13 before it is
    published) is left alone; fails_when=the push fires on any version mismatch and
    "updates" it back down to the published binary."""
    major, minor, patch = svc._parse_ver(svc._LATEST_AGENT_VERSION)
    db = FakeDb()
    await svc.maybe_push_update_instruction(db, "a1", {"version": f"{major}.{minor}.{patch + 1}", "platform": "Windows"})
    await svc.maybe_push_update_instruction(db, "a2", {"version": f"{major}.{minor + 1}.0-rust", "platform": "Windows"})
    assert db.agent_instructions.rows == []
