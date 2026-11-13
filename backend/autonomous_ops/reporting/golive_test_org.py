"""Skeleton for the go-live test organization mark (Phase 86, 86-14, D-23); behavior follows the RED commit."""


class AlreadyMarked(Exception):
    def __init__(self, current):
        super().__init__("a test organization is already marked")
        self.current = current


async def current(db):
    raise NotImplementedError


async def mark(db, tenant_id, tenant_name, actor, now):
    raise NotImplementedError


async def clear(db, tenant_id):
    raise NotImplementedError
