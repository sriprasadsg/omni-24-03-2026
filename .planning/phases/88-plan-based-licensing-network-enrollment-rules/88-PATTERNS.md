# Phase 88: Plan-Based Licensing & Network Enrollment Rules - Pattern Map

**Mapped:** 2026-11-10
**Files analyzed:** 22 (new + modified)
**Analogs found:** 21 / 22
All analog paths below are git-tracked except those marked (untracked baseline): `backend/machine_identity.py`, `backend/migrations/033_machine_identities.py`, `backend/tests/test_machine_identity.py` (valid per orchestrator, uncommitted).
Paths are relative to `/home/azureuser/enterprise-omni-agent-ai-platform/`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/plan_service.py` (new) | service | CRUD + atomic CAS | `backend/licensing.py` + `backend/partner_pool.py` | role-match |
| `backend/network_rules.py` (new) | service/utility | request-response | `backend/agent_allowlist.py` | role-match |
| `backend/cross_tenant.py` (new) | service | request-response, raw cross-tenant read | `backend/agent_registry_endpoints.py::_take_over_hardware_seat` + `seat_identity.hardware_match_filter` | role-match |
| `backend/screen_ceiling.py` (new) | utility | transform/validation | `backend/partner_portal_service.py::_final_screens` (extract) | exact |
| `backend/plan_endpoints.py` (new) | route | CRUD | `backend/partner_platform_endpoints.py` mounted by `backend/catalogue_mounts_partners.py` | role-match |
| `backend/catalogue_mounts_plans.py` (new) | config | mount | `backend/catalogue_mounts_partners.py` | exact |
| `backend/license_rules.py` (mod) | service | request-response | itself (`hold_reason`, `send_expiry_reminders`) | exact |
| `backend/licensing.py` (mod) | service | CRUD, atomic | itself (`update_license`, `try_claim_seat`) | exact |
| `backend/pending_agents.py` (mod) | service | event-driven decisions | itself (`approve`, `reject`, `_REASON_TEXT`, `list_not_admitted`) | exact |
| `backend/pending_agent_endpoints.py` (mod) | route | request-response | itself (`ApproveBody`) | exact |
| `backend/agent_registry_endpoints.py` (mod) | controller | request-response | itself (lines 286-316) | exact |
| `backend/agent_heartbeat_endpoints.py` (mod) | controller | request-response | itself (refuse Replaced) | exact |
| `backend/app_background_tasks.py` (mod) | job | batch | itself (`license_seat_tick`) | exact |
| `backend/seat_identity.py` (mod) | utility | transform | `hardware_match_filter` | exact |
| `backend/tenant_endpoints.py`, `tenant_docs.py`, `authentication_endpoints.py`, `payment_billing_endpoints.py`, `partner_pool.py`, `partner_portal_service.py`, `partner_platform_service.py`, `partner_store.py` (mod) | route/service | CRUD | each is its own analog; route writers through `plan_service.change_plan` | exact |
| `backend/migrations/034_plan_licensing.py` (new) | migration | batch | `backend/migrations/033_machine_identities.py` (untracked baseline) | exact |
| `backend/tests/test_plan_*.py`, `test_trial.py`, `test_network_rule.py`, `test_proxy_headers.py`, `test_cross_tenant_duplicate.py`, `test_migration_034_plans.py` (new) | test | real-Mongo | `backend/tests/test_enrollment_controls.py` + `tests/_mongo_test_db.py` | exact |
| `backend/tests/test_partner_license_writers.py` (mod) | test | AST scan | itself (add `trial`/`allowedNetworks` to `PRE_CHANGE_KEYS`) | exact |
| `components/TenantLicensePanel.tsx`, `PendingAgentsPanel.tsx`, `AddNewTenantModal.tsx`, `ManageTenantModal.tsx`, `PartnerPortal.tsx` (mod) | component | request-response | themselves | exact |
| New Super Admin Plans screen (new, frontend) | component | CRUD | `PartnerPortal.tsx` / the Partners screen | role-match |
| `shared/catalogue-access.json` (mod) | config | manifest | existing `partners` entry | exact |
| nginx / systemd unit flags (`--forwarded-allow-ips`) | config | n/a | none (see No Analog) | none |

## Pattern Assignments

### `backend/license_rules.py` - add `source_ip` and three hold rules (service, request-response)

**Analog:** same file, `hold_reason` (lines 123-145). Rules run in a fixed order; each returns a reason string. Keep this shape and insert (per research order): trial_ended after the expiry checks; cross_tenant_duplicate before the allowlist; new_network after the allowlist; sub-limits last.

```python
REASON_EXPIRED = "license_expired"            # lines 28-30: add REASON_TRIAL_ENDED = "trial_ended",
REASON_NOT_ALLOWLISTED = "not_allowlisted"    # REASON_CROSS_TENANT = "cross_tenant_duplicate", REASON_NEW_NETWORK = "new_network"

async def hold_reason(db, tenant, hardware, platform, default_group_id=None) -> Optional[str]:
    raw = _raw(db)
    fresh = await raw.tenants.find_one({"id": tenant["id"]}) or tenant
    lic = licensing.license_of(fresh)
    if expired(lic):
        return REASON_EXPIRED
    if fresh.get("partnerId"):  # partner pool expiry counts for its customers (D-08)
        ...
    if lic["allowlistMode"] == "enforce" and not await agent_allowlist.matches(db, tenant["id"], hardware):
        return REASON_NOT_ALLOWLISTED
```
Add `source_ip: Optional[str] = None` parameter; skip trial/network for `tenant["id"] == "platform-admin"` (D-26). Reads use `raw = _raw(db)` (`getattr(db, "_db", db)`, line 38-39) with explicit filters.

**Reminders:** copy `send_expiry_reminders` (lines 160-196) as `send_trial_reminders` with thresholds `(7, 1)`: the atomic claim pattern is the load-bearing part:
```python
res = await raw.tenants.update_one(
    {"id": tenant["id"], "license.expiryRemindersSent": {"$nin": [threshold]}},
    {"$addToSet": {"license.expiryRemindersSent": {"$each": due}}})
if res.modified_count != 1:
    continue
await pending_agents.post_to_recipients(raw, tenant, title, message, "warning", {...})
```
Use `trial.remindersSent` instead. Wire as a step in `license_seat_tick` (`backend/app_background_tasks.py:357`): `for step in steps + [licensing.reclaim_inactive_agents, license_rules.send_expiry_reminders]:` (each step individually guarded by try/except).

---

### `backend/agent_registry_endpoints.py` - pass server-observed IP, cross-tenant and learn-network (controller)

**Analog:** same file lines 290-316 and 74-109.

```python
if seat_needed:
    hold_reason = None
    if not existing_agent:
        key_claimed = await enrollment_keys.claim_use(db, install_key)
        hold_reason = (await license_rules.hold_reason(db, tenant, hardware, data.get("platform"),
                                                       install_key.get("defaultGroupId"))
                       if key_claimed else license_rules.REASON_KEY_EXHAUSTED)
    if not existing_agent and hold_reason is None:
        try:
            replaced_id = await _take_over_hardware_seat(db, tenant["id"], hardware, agent_id)
        except _LiveDuplicate:
            hold_reason = pending_agents.REASON_DUPLICATE_HARDWARE
    ...
    elif hold_reason is None:
        claimed = await licensing.try_claim_seat(db, tenant["id"])
```
Pass `request.client.host if request.client else None` (already used at line 194 for `identity_fields`; this is the only trusted source, NOT `data["publicIp"]` and NOT X-Forwarded-For). Learn the first network only after the seat claim succeeds. In-tenant 24 h rule to mirror cross-tenant:
```python
_HARDWARE_TAKEOVER_AFTER = timedelta(hours=24)            # line 71
def _seen_within(agent, window): ...                       # lines 74-81
owner = await raw.agents.find_one({**flt, "status": {"$nin": sorted(licensing.NON_SEAT_STATUSES)}})
res = await raw.agents.update_one(
    {"id": owner["id"], "status": {"$nin": sorted(licensing.NON_SEAT_STATUSES)}},
    {"$set": {"status": "Replaced", "replacedBy": new_agent_id, "replacedAt": now}})
```
For cross-tenant retire, do NOT set `replacedBy` (cross-tenant reference leak, research Q5). Also store `sourceIp` on admitted agents; line 339 `machine_identity.remember(db, tenant["id"], agent_seat_key, agent_id, hostname)` is the end-of-register hook (`remember` must also run on approve).

---

### `backend/cross_tenant.py` (service, raw cross-tenant read)

**Analog:** `backend/seat_identity.py` lines 94-104 plus `_take_over_hardware_seat`.
```python
def hardware_match_filter(tenant_id, hardware):
    terms = []
    if hardware.get("serialNumber"):
        terms.append({"hardware.serialNumber": hardware["serialNumber"]})
    if hardware.get("smbiosUuid"):
        terms.append({"hardware.smbiosUuid": hardware["smbiosUuid"]})
    if not terms:
        return None   # a MAC alone never counts (D-35)
    return {"tenantId": tenant_id, "$or": terms}
```
Add `hardware_match_other_tenants_filter(hardware, exclude_tenant_id)` with `{"tenantId": {"$ne": exclude_tenant_id}}`. Query on `getattr(db, "_db", db)` (tenant wrapper would scope otherwise). Seat-holding status: `licensing.NON_SEAT_STATUSES = frozenset({"Pending","Rejected","Inactive","Decommissioned","Replaced","Uninstalled"})` (licensing.py:25). Retire follow-up: `licensing.release_seats(db, A_tenant)`, `authentication_service.revoke_agent_tokens(db, agent_id, reason)`, `pending_agents.forget_status`. Reuse `_seen_within` (move to a shared helper rather than import a private from the endpoint module).

---

### `backend/network_rules.py` (service, request-response)

**Analog:** `backend/agent_allowlist.py` structure: module docstring stating the rule, `_raw(db)`, `class EntryError(ValueError)`, `normalize_entry(...)` raising with a short message naming the bad value, `add` / `remove` returning docs/bools.
```python
def _raw(db):
    return getattr(db, "_db", db)

class EntryError(ValueError):
    pass

def normalize_entry(serial=None, uuid_value=None, mac=None, note=None):
    ...
        normalized = norm(value)
        if not normalized:
            raise EntryError(f"invalid {field}: {str(value)[:64]!r}")
```
Difference: networks are embedded on `tenants.allowedNetworks` (cap 100), not a collection. Atomic learn uses the `try_claim_seat` style conditional update (licensing.py:91-98):
```python
res = await raw.tenants.update_one(
    {"id": tenant_id, "allowedNetworks.0": {"$exists": False}},
    {"$push": {"allowedNetworks": entry}})
learned = res.modified_count == 1
```
Use stdlib `ipaddress`; unwrap `ipv4_mapped`; CIDR widening floor IPv4 /24, IPv6 /48 (D-42); must contain the observed IP. Never read X-Forwarded-For.

---

### `backend/screen_ceiling.py` (utility, validation)

**Analog:** `backend/partner_portal_service.py` lines 51-87 (extract verbatim, generalize to a list of allowed sets):
```python
def _allowed(partner_doc):
    ceiling = _ceiling(partner_doc)
    base = set(tenant_features.SWITCHABLE) if "all" in ceiling else set(ceiling)
    return base | set(tenant_features.START_FEATURES)

def _final_screens(partner_doc, submitted, current):
    allowed = _allowed(partner_doc)
    kept = [s for s in dict.fromkeys(current) if s not in allowed]
    known = set(tenant_features.SWITCHABLE) | set(tenant_features.START_FEATURES) | set(kept)
    known.discard(tenant_features.ALL_FEATURES)
    ...
        raise PartnerError(422, "invalid_screen", ...)
        raise PartnerError(422, "screen_outside_ceiling", f"{_label(value)} is not one of the screens you can sell.", screen=value)
    final = list(dict.fromkeys([*wanted, *kept, *tenant_features.START_FEATURES]))
    ... raise PartnerError(422, "missing_parent", ...)
```
`partner_portal_service` then calls the extracted function (`create_customer` line 107: `features = _final_screens(partner_doc, enabled_features or [], current=[])`). Keep error class `partner_pool.PartnerError`. Per D-40: partner path uses plan ∩ partner ceiling; Super Admin path (`tenant_endpoints.update_tenant`, currently unvalidated) uses plan only. Keep screens already on ("kept", D-28).

---

### `backend/pending_agents.py` (service, decisions)

**Analog:** same file. Lockstep edits for the 3 new reasons:
- `_REASON_TEXT` (lines 255-261) and `reason_text` (264-267); `_REFUSAL_TEXT` (lines 156-162, older builds show the raw code otherwise):
```python
_REASON_TEXT = {
    REASON_SEAT_LIMIT: "the tenant has no free agent seat",
    REASON_DUPLICATE_HARDWARE: "...",
    "license_expired": "the tenant's agent license has expired",
}
```
Add `"trial_ended": "the free trial has ended"`, `new_network`, `cross_tenant_duplicate` (unnamed text per D-36).
- `approve` (394-441): by reason, `new_network` adds the network (optional `widenTo`) before `try_claim_seat`; `cross_tenant_duplicate` retires A then claims B; re-run cross-tenant for other reasons (Pitfall 6). Direct-tenant raise (lines 417-419) must also set `license.seatOverride`; these `license.maxAgents` writes are on the drift-guard allowlist (`pending_agents.py`).
- `reject` (459): extend the no-denylist condition: `agent.get("pendingReason") != REASON_DUPLICATE_HARDWARE` to include `cross_tenant_duplicate`.
- `post_to_recipients` (294-300) sends identical text to platform and tenant; add a variant sending the named text to `PLATFORM_TENANT_ID` and the unnamed text to the tenant (use `_post_in_app` twice, tenant gets `{**metadata, "audience": TENANT_ADMIN_AUDIENCE}`).
- `list_not_admitted` (472-482): projection `{"_id": 0, "agentSecretHash": 0, "uninstallProtection": 0}`; add `crossTenant: 0` for non-platform callers.
- Audit via `_audit(...)` (367-374, `audit_service.log_action_async`).

`backend/pending_agent_endpoints.py`: `class ApproveBody(BaseModel)` (line 83) gains `widenTo: Optional[str] = None`; `_require_decider` (line 46) already restricts decisions.

---

### `backend/licensing.py` (service, atomic CRUD) - the only home for `license.maxAgents` writes

**Analog:** same file. New `apply_plan_seats` / `set_seat_override` follow `update_license` (134-161) and `try_claim_seat` (91-98).
```python
changes["license.maxAgents"] = max_agents
changes["maxAgents"] = max_agents  # legacy readers, one release
await _raw(db).tenants.update_one({"id": tenant_id}, {"$set": changes})
```
Bulk plan edit must exclude partner customers, platform and overrides:
`{"subscriptionTier": plan, "type": {"$ne": "partner"}, "partnerId": {"$exists": False}, "id": {"$ne": "platform-admin"}, "license.seatOverride": {"$exists": False}}`. Drift guard: `backend/tests/test_partner_license_writers.py` (`SEAT_WRITER_ALLOWLIST = {"licensing.py","partner_pool.py","tenant_docs.py","pending_agents.py","authentication_endpoints.py"}`); a new module writing seats must be added deliberately, so put seat writes in `licensing.py`.

---

### `backend/plan_service.py` (service, CAS)

**Analog:** `backend/partner_pool.py` `change_allotment` compare-and-set style and `licensing.py`. `change_plan(db, tenant_id, new_plan, actor, via)`: one `update_one` filtered on the old `subscriptionTier`; then `audit_ledger.event("plan.changed", ...)` (+ `partner_store.audit(...)` for partner actors) and a tenant-admin notice via `pending_agents._post_in_app(..., {**metadata, "audience": "tenant_admins"})`. Plans read via raw handle `db._db` (a new collection through the wrapper would get `tenantId` injected). Plan keys: `"Free","Pro","Enterprise","Custom"` (as in `billing_service.SUBSCRIPTION_LIMITS`, `feature_flags.TIER_ORDER`). Callers to route through it: `tenant_endpoints.create_tenant/update_tenant`, `authentication_endpoints.py` sign-up (~406), `payment_billing_endpoints.py` (~76, ~181), `tenant_docs.build_tenant_doc`, `tenant_signup_endpoints.approve_signup`.

---

### `backend/plan_endpoints.py` + `backend/catalogue_mounts_plans.py` (route, CRUD)

**Analog:** `backend/catalogue_mounts_partners.py` (all 33 lines):
```python
from catalogue_guards import catalogue_guard
PARTNERS_GUARD = catalogue_guard("partners", read=("manage:partners",), write=("manage:partners",))
MOUNTS = {("partner_platform_endpoints", "router"): PARTNERS_GUARD}
```
Create `PLANS_GUARD = catalogue_guard("plans", read=(<SuperAdmin-only perm>,), write=(...))`, add the screen to `shared/catalogue-access.json`; tests `test_catalogue_route_parity`, `test_catalogue_manifest`, `_route_walk.py` fail on drift (a Phase 87 slice test, `test_catalogue_slice_partners`, is the model).

---

### `backend/migrations/034_plan_licensing.py` (migration, batch)

**Analog:** `backend/migrations/033_machine_identities.py` (untracked baseline; tracked style model `migrations/032_service_desk.py`).
```python
DESCRIPTION = "..."
logger = logging.getLogger(__name__)

async def up(db: AsyncIOMotorDatabase) -> None:
    import machine_identity
    await machine_identity.ensure_indexes(db)
    ...
        res = await db[...].update_one(filter, {"$setOnInsert": {...}}, upsert=True)
    logger.info("migration 033: %d machine identities recorded", recorded)
```
Copy: `DESCRIPTION`, `async def up(db)`, idempotent `$setOnInsert`/`$exists` guards, lazy in-function imports, log line with counts. Do here: seed `plans` (4 docs, generated screen seed 19/69/120, D-46), D-18 seats (record `license.maxAgentsBeforePlans` first; partner customers and platform untouched, D-41), trial record (Free: now + 14 days; paid: `consumed`), `allowedNetworks` from `publicIp` (valid global only, `source: "migrated"`), sparse indexes `agents.hardware.serialNumber` and `agents.hardware.smbiosUuid` (sparse, NOT partial; research probe). A second `up()` must be a no-op.

---

### Tests (real-Mongo)

**Analog:** `backend/tests/test_enrollment_controls.py` + `backend/tests/_mongo_test_db.py` (`mongo_db` fixture: throwaway `omni_test_<hex>` DB, skips if mongod unreachable). Module docstring convention: `Value: protects=... fails_when=... no_claim=...`; harness:
```python
async def _register(db, hostname, key=REG_KEY, hardware=None, **body):
    with _register_patches(db):
        return await _register_unpatched(hostname, key, hardware, **body)
```
(`_register_patches` patches `reg.get_database`, `reg.limiter.enabled=False`, `invalidate_cache`, stubs `finops_service`.) Request is built with client `("203.0.113.7", 5555)`; new network tests vary that. Move `_register`/two-tenant setup to a shared helper (do not import from another test). Proxy-headers test: wrap a trivial ASGI app in `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1,::1")`. Reminder test model: `test_expiry_reminders_go_out_once_per_threshold`. `tests/test_machine_identity.py` (untracked baseline) for machine-id interplay.

---

### Frontend

- `components/PendingAgentsPanel.tsx`: `REASONS` map and `reasonText` get the three reasons; approve dialog gets `widenTo` input for `new_network`; named view only for platform user.
- `components/TenantLicensePanel.tsx` + `GET /api/tenants/{id}/license` (`licensing.license_summary`, lines 164+): add plan, `seatOverride` flag, `allowedNetworks`, trial days left.
- `components/AddNewTenantModal.tsx:12`: default `'Enterprise'` to `'Free'`.
- Partner portal: add `plan`, `trialEndsAt` to `partner_store.CUSTOMER_FIELDS` (pinned by a test).
- Tests: vitest `src/__tests__/PendingAgentsPanel.test.tsx`, `PartnerPortal.test.tsx`, `SidebarTenantSwitches.test.tsx`; new `PlansScreen.test.tsx`.

## Shared Patterns

### Raw handle with explicit filters
**Source:** `backend/licensing.py:28`, `license_rules.py:38-39`, `agent_allowlist.py:24-25`
**Apply to:** every new module touching `tenants`, `agents`, `plans`.
```python
def _raw(db):
    return getattr(db, "_db", db)
```

### Atomic conditional update (no read-then-write)
**Source:** `backend/licensing.py:91-98` (`try_claim_seat`), `license_rules.py:182-186` (reminder claim)
**Apply to:** learn-first-network, trial reminders, retire-cross-tenant-agent (`status $nin NON_SEAT_STATUSES` guard), change_plan CAS.

### Hold reasons as strings plus Pending flow
**Source:** `license_rules.py:28-30`, `pending_agents.py:33-34,155-162,255-267`
**Apply to:** `trial_ended`, `new_network`, `cross_tenant_duplicate` in backend text maps, UI `REASONS`, `alert_payload`.

### Never cut off enrolled agents
`hold_reason` is called only `if not existing_agent`; heartbeat only claims seats. New rules must not re-check enrolled agents (D-01, D-05). Exception: heartbeat must refuse `Replaced` (agent_heartbeat_endpoints.py ~88-96, plus token revocation).

### Tenant-leak control (D-36)
Tenant-facing output (notice, Pending list, ledger, 403 text) contains no other organization's name; named text goes to `PLATFORM_TENANT_ID` feed and platform ledger only. Test both feeds/lists/ledgers.

### Audit and notices
`audit_ledger.event(...)`, `partner_store.audit(...)`, `pending_agents._audit` (audit_service), `pending_agents._post_in_app` with `audience: tenant_admins` (see `notification_audience`).

### Server-observed IP only
`request.client.host` (uvicorn ProxyHeadersMiddleware trusts only 127.0.0.1/::1; nginx `/api` appends `$remote_addr`). Test that `license_rules`/`network_rules` never read `X-Forwarded-For`.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| systemd unit / `start-all-services.sh` `--forwarded-allow-ips 127.0.0.1` pin | config | n/a | Deployment config; not in tracked Python; research assumption A1, generator unverified; planner should check the script before editing (restarts are the user's action) |
| Plans screen frontend | component | CRUD | Closest is the Partners/PartnerPortal screens (role-match only) |
| Cross-tenant platform-only name projection | service | n/a | No existing platform-only field projection pattern beyond `list_not_admitted` projection dict |

## Metadata

**Analog search scope:** `backend/` top-level modules, `backend/migrations/`, `backend/tests/`, catalogue mounts, `components/` (names from research)
**Files read:** license_rules, licensing (86-175), pending_agents (255-483), agent_allowlist (1-70), agent_registry_endpoints (70-110, 286-316), seat_identity (80-104), partner_portal_service (1-110), catalogue_mounts_partners, migrations/033, tests/_mongo_test_db and test_enrollment_controls (excerpts), app_background_tasks (338-362)
**Tracked-source check:** `git ls-files` confirmed tracked: license_rules, licensing, agent_allowlist, pending_agents, seat_identity, partner_portal_service, partner_platform_service, catalogue_mounts_partners, agent_registry_endpoints, pending_agent_endpoints, app_background_tasks, migrations/032, tests/_mongo_test_db, tests/test_enrollment_controls. No `.gsd/capabilities` mirror paths used.
**Pattern extraction date:** 2026-11-10
