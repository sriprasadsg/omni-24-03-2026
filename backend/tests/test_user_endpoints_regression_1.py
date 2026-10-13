"""
Regression: ISSUE-003 — user create/update/delete audit entries invisible to the tenant
Found by /qa on 2026-10-13
Report: .gstack/qa-reports/run-20261013T151919Z/qa-report-127.0.0.1-2026-10-13.md

Live repro: a super admin created a tenant admin in "QA Tenant"; the only audit entry
was {action, actor, target, tenant_id, timestamp}. GET /api/audit-logs filters on
tenantId, so the tenant's own admin saw "No audit logs found".

Value: protects=a user.created entry written by user_endpoints is returned by the
audit reader's tenant-scoped query with actor/resource fields; fails_when=_audit
writes its own actor/target/tenant_id shape that get_logs never matches;
why_new=no test covers user_endpoints audit writes; seam=none;
no_claim=Mongo query semantics and the DB wrapper's tenant override (an in-memory
fake audit_logs collection stands in for Mongo). Hermetic: no Mongo.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import audit_service
import user_endpoints


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=-1):
        self.docs = sorted(self.docs, key=lambda d: d.get(key, ""), reverse=direction == -1)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, length=None):
        return [{k: v for k, v in d.items() if k != "_id"} for d in self.docs][:length]


class _AuditLogs:
    def __init__(self):
        self.docs = []

    @staticmethod
    def _match(doc, flt):
        return all(doc.get(k) == v for k, v in (flt or {}).items())

    async def find_one(self, flt=None, *_a, sort=None, **_k):
        hits = [d for d in self.docs if self._match(d, flt)]
        if sort:
            key, direction = sort[0]
            hits.sort(key=lambda d: d.get(key, ""), reverse=direction == -1)
        return hits[0] if hits else None

    async def insert_one(self, doc, *_a, **_k):
        self.docs.append(dict(doc))

    def find(self, flt=None, *_a, **_k):
        return _Cursor([d for d in self.docs if self._match(d, flt)])


class _DB:
    def __init__(self):
        self.audit_logs = _AuditLogs()


async def test_user_created_audit_entry_is_visible_to_its_tenant():
    db = _DB()
    with patch.object(audit_service, "get_database", return_value=db), \
            patch.object(user_endpoints, "get_database", return_value=db, create=True):
        await user_endpoints._audit(db, "user.created", "qa-super@qa.omni.test",
                                    "new-admin@qa.omni.test", "tenant-a")
        logs = await audit_service.get_audit_service().get_logs(tenant_id="tenant-a")

    assert len(logs) == 1, db.audit_logs.docs
    entry = logs[0]
    assert entry["action"] == "user.created"
    assert entry["userName"] == "qa-super@qa.omni.test"
    assert entry["resourceType"] == "user"
    assert entry["resourceId"] == "new-admin@qa.omni.test"
    assert entry["tenantId"] == "tenant-a"
    assert entry.get("hash"), "entry must join the tenant's hash chain"
