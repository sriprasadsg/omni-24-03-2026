import pytest

from backend.program_service import (
    create_program,
    get_program,
    list_programs,
    update_controls,
    delete_program,
)


class MockInsertResult:
    def __init__(self, inserted_id=None):
        self.inserted_id = inserted_id


class MockDeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class MockUpdateResult:
    def __init__(self, modified_count):
        self.modified_count = modified_count


class MockCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return self.documents


class MockCollection:
    def __init__(self):
        self.documents = []

    async def insert_one(self, doc):
        stored = dict(doc)
        stored["_id"] = "mock-id"
        self.documents.append(stored)
        return MockInsertResult("mock-id")

    async def find_one(self, query, projection=None):
        for doc in self.documents:
            if all(doc.get(k) == v for k, v in query.items()):
                result = dict(doc)
                result.pop("_id", None)
                return result
        return None

    def find(self, query, projection=None):
        results = []

        for doc in self.documents:
            matched = True

            for key, value in query.items():
                if isinstance(value, dict) and "$in" in value:
                    if doc.get(key) not in value["$in"]:
                        matched = False
                        break
                elif doc.get(key) != value:
                    matched = False
                    break

            if matched:
                result = dict(doc)
                result.pop("_id", None)
                results.append(result)

        return MockCursor(results)

    async def update_one(self, query, update):
        for doc in self.documents:
            if all(doc.get(k) == v for k, v in query.items()):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return MockUpdateResult(1)

        return MockUpdateResult(0)

    async def delete_one(self, query):
        for index, doc in enumerate(self.documents):
            if all(doc.get(k) == v for k, v in query.items()):
                self.documents.pop(index)
                return MockDeleteResult(1)

        return MockDeleteResult(0)


class MockDatabase:
    def __init__(self):
        self.programs = MockCollection()
        self.asset_compliance = MockCollection()


class MockDBWrapper:
    def __init__(self):
        self._db = MockDatabase()


@pytest.fixture
def db():
    return MockDBWrapper()


@pytest.mark.asyncio
async def test_create_program(db):
    program = await create_program(
        db,
        "tenant-test",
        {
            "name": "Access Control",
            "description": "Access control compliance",
            "framework_id": "ISO27001",
            "owner": "security",
            "control_ids": ["C1", "C2"],
        },
    )

    assert program["name"] == "Access Control"
    assert program["tenantId"] == "tenant-test"
    assert program["control_ids"] == ["C1", "C2"]
    assert "id" in program


@pytest.mark.asyncio
async def test_get_program_with_rollup(db):
    program = await create_program(
        db,
        "tenant-test",
        {
            "name": "Access Control",
            "control_ids": ["C1", "C2"],
        },
    )

    await db._db.asset_compliance.insert_one(
        {
            "controlId": "C1",
            "tenantId": "tenant-test",
            "status": "Compliant",
            "lastUpdated": "2026-08-21T00:00:00+00:00",
        }
    )

    await db._db.asset_compliance.insert_one(
        {
            "controlId": "C2",
            "tenantId": "tenant-test",
            "status": "Non-Compliant",
            "lastUpdated": "2026-08-21T00:00:00+00:00",
        }
    )

    result = await get_program(
        db,
        program["id"],
        "tenant-test",
    )

    assert result is not None
    assert result["status_rollup"]["total"] == 2
    assert result["status_rollup"]["passing"] == 1
    assert result["status_rollup"]["failing"] == 1
    assert result["status_rollup"]["status"] == "at_risk"


@pytest.mark.asyncio
async def test_program_rollup_compliant(db):
    program = await create_program(
        db,
        "tenant-test",
        {
            "name": "Access Control",
            "control_ids": ["C1", "C2"],
        },
    )

    for control_id in ["C1", "C2"]:
        await db._db.asset_compliance.insert_one(
            {
                "controlId": control_id,
                "tenantId": "tenant-test",
                "status": "Compliant",
                "lastUpdated": "2026-08-21T00:00:00+00:00",
            }
        )

    result = await get_program(
        db,
        program["id"],
        "tenant-test",
    )

    assert result["status_rollup"]["total"] == 2
    assert result["status_rollup"]["passing"] == 2
    assert result["status_rollup"]["failing"] == 0
    assert result["status_rollup"]["not_assessed"] == 0
    assert result["status_rollup"]["status"] == "compliant"


@pytest.mark.asyncio
async def test_program_not_assessed(db):
    program = await create_program(
        db,
        "tenant-test",
        {
            "name": "Access Control",
            "control_ids": ["C1", "C2"],
        },
    )

    result = await get_program(
        db,
        program["id"],
        "tenant-test",
    )

    assert result["status_rollup"]["total"] == 2
    assert result["status_rollup"]["passing"] == 0
    assert result["status_rollup"]["failing"] == 0
    assert result["status_rollup"]["not_assessed"] == 2
    assert result["status_rollup"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_controls(db):
    program = await create_program(
        db,
        "tenant-test",
        {
            "name": "Access Control",
            "control_ids": ["C1", "C2"],
        },
    )

    updated = await update_controls(
        db,
        program["id"],
        "tenant-test",
        ["C3"],
        ["C1"],
    )

    assert updated is not None
    assert set(updated["control_ids"]) == {"C2", "C3"}


@pytest.mark.asyncio
async def test_list_programs(db):
    await create_program(
        db,
        "tenant-test",
        {
            "name": "Program A",
            "control_ids": [],
        },
    )

    await create_program(
        db,
        "tenant-test",
        {
            "name": "Program B",
            "control_ids": [],
        },
    )

    programs = await list_programs(db, "tenant-test")

    assert len(programs) == 2
    assert all("status_rollup" in p for p in programs)


@pytest.mark.asyncio
async def test_delete_program(db):
    program = await create_program(
        db,
        "tenant-test",
        {
            "name": "Access Control",
            "control_ids": [],
        },
    )

    deleted = await delete_program(
        db,
        program["id"],
        "tenant-test",
    )

    assert deleted is True

    result = await get_program(
        db,
        program["id"],
        "tenant-test",
    )

    assert result is None


@pytest.mark.asyncio
async def test_tenant_isolation(db):
    program = await create_program(
        db,
        "tenant-a",
        {
            "name": "Tenant A Program",
            "control_ids": [],
        },
    )

    result = await get_program(
        db,
        program["id"],
        "tenant-b",
    )

    assert result is None
