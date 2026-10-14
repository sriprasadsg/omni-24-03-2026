"""In-memory stand-ins for the audit ledger's chain collections (spec C5), for tests
whose hand-built mock databases only model audit_logs."""


class _Result:
    def __init__(self, modified_count=0):
        self.modified_count = modified_count


class ChainHeads:
    """audit_chain_heads with the compare-and-swap the ledger relies on."""

    def __init__(self):
        self.heads = {}

    async def find_one(self, flt, *args, **kwargs):
        head = self.heads.get(flt.get("tenantId"))
        return dict(head) if head else None

    async def update_one(self, flt, update, *args, **kwargs):
        head = self.heads.get(flt.get("tenantId"))
        if head and head["seq"] == flt.get("seq"):
            head.update(update["$set"])
            return _Result(1)
        return _Result(0)

    async def insert_one(self, doc, *args, **kwargs):
        self.heads[doc["tenantId"]] = dict(doc)
        return _Result()


class NoCheckpoints:
    async def find_one(self, *args, **kwargs):
        return None


def install(db):
    """Give a mock database the chain collections; returns it."""
    db.audit_chain_heads = ChainHeads()
    db.audit_chain_checkpoints = NoCheckpoints()
    return db
