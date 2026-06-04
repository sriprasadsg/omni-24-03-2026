# Data Export Center — New Report Modules

**Date:** 2026-06-03  
**Status:** Approved for implementation

---

## Problem

The Data Export Center in `ReportingDashboard.tsx` has export cards for Asset Inventory, Patches, Security Events, Vulnerability, SBOM, Secrets, and Compliance — but the following platform features have no export at all:

- Change Management  
- Chat (Support Chat + Endpoint Chat)  
- Agent Health  
- Audit Log  
- User Activity  
- Automation Policies  
- Cloud Security / CSPM  

**Constraint:** Do not touch any existing report section, card, or backend handler.

---

## Scope

Add **10 new ExportCards** to the Data Export Center section in `ReportingDashboard.tsx`, backed by **8 new data handlers** in `export_service.py`.

---

## Architecture

### Frontend — `components/ReportingDashboard.tsx`

Two new group blocks inserted after the existing "Asset & Patch" group, and four new cards appended to the existing "Governance & Risk" group. All existing groups and cards remain unchanged.

**New group: IT Operations**
- `Change Management` — change_id, title, type, status, risk_level, assignee, scheduled dates, rollback plan flag, created_at
- `Agent Health` — hostname, IP, platform, OS, status, last_seen, agent_version, tenant_id

**New group: Chat & Support**
- `Support Chat` — convo_id, subject, chat_type, status, initiator_name, initiator_email, initiator_role, message_count, escalated, created_at, resolved_at
- `Endpoint Chat` — session_id, agent_hostname, subject, status, initiator_id, initiator_type (admin/endpoint), message_count, escalated, escalated_by, created_at

**Expanded: Governance & Risk** (4 new cards appended, 2 existing untouched)
- `Audit Log` — event_id, action, actor, resource_type, resource_id, outcome, ip_address, tenant_id, timestamp
- `User Activity` — user_id, name, email, role, status, tenant_id, last_login, login_count (derived from audit log)
- `Automation Policies` — policy_id, name, trigger_type, action_count, enabled, last_run, run_count, tenant_id
- `Cloud Security` — finding_id, cloud_provider, account_id, severity, resource_type, resource_id, status, detected_at, tenant_id

### Backend — `backend/export_service.py`

New `_format_*` methods and new branches in `_fetch_data()`. No existing branches or methods change.

| Report type string | Collection | Format method |
|---|---|---|
| `Change Management` | `change_requests` | `_format_change` |
| `Agent Health` | `agents` | `_format_agent` (new — not same as existing asset) |
| `Support Chat` | `support_conversations` | `_format_support_chat` |
| `Endpoint Chat` | `agent_chat_sessions` | `_format_endpoint_chat` |
| `Audit Log` | `audit_logs` | `_format_audit_log` |
| `User Activity` | `users` | `_format_user_activity` |
| `Automation Policies` | `automation_policies` | `_format_automation` |
| `Cloud Security` | `cspm_findings` | `_format_cspm` |

All fetches respect existing tenant isolation: `query = {"tenantId": tenant_id}` when `tenant_id` is not None. Result limit 1 000 rows unless noted otherwise.

---

## Data Shapes

### Change Management
```
Change ID | Title | Type (standard/normal/emergency) | Status | Risk Level |
Impact Level | Assignee | Reporter | Required Approvals | CAB Votes |
Has Rollback Plan | Scheduled Start | Scheduled End | Created At | Tenant ID
```

### Agent Health
```
Agent ID | Hostname | IP Address | Platform | OS Type | OS Version |
Status | Agent Version | Last Seen | Capabilities | Tenant ID
```

### Support Chat
```
Convo ID | Subject | Chat Type | Status | Initiator Name | Initiator Email |
Initiator Role | Target User | Message Count | Escalated | Escalated By |
Created At | Resolved At | Tenant ID
```

### Endpoint Chat
```
Session ID | Agent Hostname | Subject | Status | Initiator ID | Initiator Type |
Message Count | Escalated | Escalated By | Escalation Note | Created At | Tenant ID
```

### Audit Log
```
Event ID | Action | Actor | Resource Type | Resource ID | Outcome |
IP Address | User Agent | Tenant ID | Timestamp
```

### User Activity
```
User ID | Name | Email | Role | Status | Tenant ID | Last Login | Created At
```
*(Last Login derived from the most recent audit_log entry for this user if users collection lacks it.)*

### Automation Policies
```
Policy ID | Name | Trigger Type | Actions Count | Enabled | Last Run |
Run Count | Created At | Tenant ID
```

### Cloud Security (CSPM)
```
Finding ID | Cloud Provider | Account ID | Region | Severity | Resource Type |
Resource ID | Rule ID | Status | Detected At | Remediated At | Tenant ID
```

---

## Error Handling

- Empty collection → export returns a file with header row only and a comment row "No data available".
- Unknown collection name → `_fetch_data` falls through to existing `return []`.
- Tenant isolation: Non-admins always get `query = {"tenantId": caller_tenant}`. Admins get `query = {}`.

---

## Out of Scope

- No changes to existing ExportCards, their format methods, or their `_fetch_data` branches.
- No new API endpoints (the existing `GET /api/reports/export?type=…&format=…` handles everything).
- No changes to `export_report_endpoint.py` or `ExportServicePDFMixin`.
- PDF generation uses the existing `_generate_pdf()` method — no layout customisation per module.
- No date-range filtering on export (existing limitation retained).

---

## Files Changed

| File | Change |
|---|---|
| `backend/export_service.py` | 8 new `_format_*` methods + 8 new `elif` branches in `_fetch_data` |
| `components/ReportingDashboard.tsx` | 2 new JSX group blocks + 4 new `<ExportCard>` in Governance & Risk |

Total: 2 files, ~0 deletions, ~150 additions.
