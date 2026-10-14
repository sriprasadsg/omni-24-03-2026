"""The compliance framework catalogue as each tenant may see it.

``compliance_frameworks`` holds the platform catalogue (no tenantId) plus frameworks a
tenant created (tenantId set). Through the database wrapper a customer tenant's request
reads and writes only the catalogue frameworks the tenant purchased and its own (see
compliance_purchases.visible_filter); the platform context and work without a tenant
context (startup, background jobs) see everything. Raw handles (``db._db``) bypass this.

find() and aggregate() are synchronous in Motor, but the tenant's purchases need a
database read, so they return a cursor that resolves the filter when it is first read
(``to_list`` or ``async for``); chained sort/limit/skip calls are replayed on it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import compliance_purchases
from tenant_context import get_tenant_id


def _merge(filter_query: Optional[Dict[str, Any]], scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if scope is None:
        return filter_query or {}
    return {"$and": [filter_query, scope]} if filter_query else scope


class _DeferredCursor:
    _CHAINABLE = frozenset({"sort", "limit", "skip", "batch_size", "max_time_ms", "collation", "hint"})

    def __init__(self, open_cursor):
        self._open = open_cursor
        self._calls: List[tuple] = []

    def __getattr__(self, name):
        if name not in self._CHAINABLE:
            raise AttributeError(f"{name} is not supported on a tenant-scoped framework cursor")

        def record(*args, **kwargs):
            self._calls.append((name, args, kwargs))
            return self
        return record

    async def _cursor(self):
        cursor = await self._open()
        for name, args, kwargs in self._calls:
            cursor = getattr(cursor, name)(*args, **kwargs)
        return cursor

    async def to_list(self, length=None):
        return await (await self._cursor()).to_list(length=length)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        async for doc in await self._cursor():
            yield doc


class FrameworkScopedCollection:
    def __init__(self, collection, raw_db):
        self._collection = collection
        self._raw_db = raw_db

    async def _scope(self) -> Optional[Dict[str, Any]]:
        return await compliance_purchases.visible_filter(self._raw_db, get_tenant_id())

    def find(self, filter=None, *args, **kwargs):
        async def open_cursor():
            return self._collection.find(_merge(filter, await self._scope()), *args, **kwargs)
        return _DeferredCursor(open_cursor)

    def aggregate(self, pipeline, *args, **kwargs):
        async def open_cursor():
            scope = await self._scope()
            return self._collection.aggregate(([{"$match": scope}] if scope else []) + list(pipeline), *args, **kwargs)
        return _DeferredCursor(open_cursor)

    async def find_one(self, filter=None, *args, **kwargs):
        return await self._collection.find_one(_merge(filter, await self._scope()), *args, **kwargs)

    async def count_documents(self, filter=None, *args, **kwargs):
        return await self._collection.count_documents(_merge(filter, await self._scope()), *args, **kwargs)

    async def distinct(self, key, filter=None, *args, **kwargs):
        return await self._collection.distinct(key, _merge(filter, await self._scope()), *args, **kwargs)

    async def update_one(self, filter, update, *args, **kwargs):
        return await self._collection.update_one(_merge(filter, await self._scope()), update, *args, **kwargs)

    async def update_many(self, filter, update, *args, **kwargs):
        return await self._collection.update_many(_merge(filter, await self._scope()), update, *args, **kwargs)

    async def replace_one(self, filter, replacement, *args, **kwargs):
        return await self._collection.replace_one(_merge(filter, await self._scope()), replacement, *args, **kwargs)

    async def find_one_and_update(self, filter, update, *args, **kwargs):
        return await self._collection.find_one_and_update(_merge(filter, await self._scope()), update, *args, **kwargs)

    async def delete_one(self, filter, *args, **kwargs):
        return await self._collection.delete_one(_merge(filter, await self._scope()), *args, **kwargs)

    async def delete_many(self, filter, *args, **kwargs):
        return await self._collection.delete_many(_merge(filter, await self._scope()), *args, **kwargs)

    def _owned(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """A framework a customer tenant creates belongs to that tenant (never the catalogue)."""
        tenant_id = get_tenant_id()
        if tenant_id and tenant_id != compliance_purchases.PLATFORM_TENANT_ID:
            document["tenantId"] = tenant_id
        return document

    async def insert_one(self, document, *args, **kwargs):
        return await self._collection.insert_one(self._owned(document), *args, **kwargs)

    async def insert_many(self, documents, *args, **kwargs):
        return await self._collection.insert_many([self._owned(d) for d in documents], *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._collection, name)
