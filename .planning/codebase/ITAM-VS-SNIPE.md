# ITAM Console vs Snipe-IT Feature Comparison

Generated: 2026-08-12

## Executive Summary
The ITAM Console implements ~30-40% of Snipe-IT's feature surface. Core asset lifecycle (check-out/in, audit, labels) is functional; enterprise/ITIL-grade features are largely absent.

---

## Feature-by-Feature Comparison

### 1. Assets & Lifecycle
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| Asset CRUD | ✅ Full | ✅ Partial (hostname, tag, status, tenant) | Partial |
| Asset Models (separate from manufacturer) | ✅ | ❌ | Missing |
| Custom Fields on Assets | ✅ | ❌ | Missing |
| Check-out / Check-in | ✅ | ✅ | Present |
| Audit Trail (history of changes) | ✅ | ❌ (only `markAssetAudited`) | Missing |
| Asset Labels (QR/Barcode/Sheet) | ✅ | ✅ | Present |
| Bulk Actions | ✅ | ❌ | Missing |
| CSV Import/Export | ✅ | ❌ | Missing |
| Requestable Assets / Approval Workflow | ✅ | ❌ | Missing |
| Accessories/Consumables Assignment | ✅ | ✅ Partial | Partial |
| Components (parts) | ✅ | ✅ Basic | Partial |
| Depreciation / Book Value | ✅ | ✅ Fetch only | Partial |
| Warranty Tracking + Alerts | ✅ | ✅ Fetch only | Partial |
| Maintenance Scheduling | ✅ | ❌ | Missing |
| File Attachments | ✅ | ❌ | Missing |
| Asset Statuses (deployable, deployed, archived, etc.) | ✅ | ✅ | Present |

### 2. Catalog / Reference Data
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| Manufacturers | ✅ | ✅ | Present |
| Categories | ✅ | ✅ | Present |
| Locations | ✅ | ✅ | Present |
| Suppliers | ✅ | ❌ | Missing |
| Companies | ✅ | ❌ | Missing |
| Departments | ✅ | ❌ | Missing |
| Custom Dropdowns/Fields | ✅ | ❌ | Missing |

### 3. Users & Permissions
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| User Management (CRUD) | ✅ | ❌ | Missing |
| Employee/Group/Manager Hierarchy | ✅ | ❌ | Missing |
| LDAP / Active Directory / SAML / SSO | ✅ | ❌ | Missing |
| Roles & Permissions (admin, user, etc.) | ✅ | ❌ (only `isSuperAdminView`) | Missing |
| Personal Access Tokens (API) | ✅ | ❌ | Missing |
| Two-Factor Authentication | ✅ | ❌ | Missing |

### 4. Licenses & Consumables
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| Software Licenses (seats, expiry) | ✅ | ✅ Basic | Partial |
| License Assignment to Users/Assets | ✅ | ✅ Basic | Partial |
| Consumables (quantity, min-qty alerts) | ✅ | ✅ Basic | Partial |
| Component Assignment | ✅ | ✅ Basic | Partial |

### 5. Finance & Procurement
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| Purchase Orders / Costs | ✅ | ❌ | Missing |
| Vendor/Supplier Management | ✅ | ❌ | Missing |
| Depreciation Methods (straight-line, etc.) | ✅ | ❌ | Missing |
| Budget Tracking | ✅ | ❌ | Missing |

### 6. Compliance & Security
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| Compliance Frameworks | ✅ | ✅ Basic | Partial |
| Evidence Upload | ✅ | ✅ Basic | Partial |
| Audit Log / Activity Feed | ✅ | ❌ | Missing |
| Security Scanning Integration | ✅ | ❌ | Missing |

### 7. Reporting & Analytics
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| Report Builder (custom reports) | ✅ | ❌ | Missing |
| Pre-built Reports (asset value, check-out, etc.) | ✅ | ❌ | Missing |
| Export (PDF, CSV, Excel) | ✅ | ❌ | Missing |
| Dashboard / KPIs | ✅ | ❌ | Missing |

### 8. Notifications & Alerts
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| Email Alerts (warranty, check-in due, etc.) | ✅ | ❌ | Missing |
| Slack/Webhook Integrations | ✅ | ❌ | Missing |
| In-app Notifications | ✅ | ❌ | Missing |
| Scheduled Reports | ✅ | ❌ | Missing |

### 9. API & Integrations
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| REST API (full CRUD) | ✅ | ❌ (backend only?) | Unknown |
| Webhooks | ✅ | ❌ | Missing |
| Third-party Integrations (Jira, ServiceNow, etc.) | ✅ | ❌ | Missing |

### 10. Settings & Customization
| Feature | Snipe-IT | ITAM Console | Status |
|---------|----------|--------------|--------|
| Global Settings UI | ✅ | ❌ | Missing |
| Custom Fields (global) | ✅ | ❌ | Missing |
| Branding / Logo / Theme | ✅ | ❌ | Missing |
| Localization / Translations | ✅ | ❌ | Missing |

---

## Gap Summary

| Priority | Gap Area | Effort |
|----------|----------|--------|
| High | User Management + Auth (LDAP/SSO) | Large |
| High | Custom Fields on Assets | Medium |
| High | Audit Trail / Activity Log | Medium |
| High | Bulk Import/Export (CSV) | Medium |
| High | Reports & Dashboard | Medium-Large |
| Medium | Maintenance/Warranty Alerts + Notifications | Medium |
| Medium | Requestable Assets / Approval Workflow | Medium |
| Medium | Depreciation Modeling | Small-Medium |
| Low | Suppliers / Companies / Departments | Small |
| Low | API Tokens / Webhooks / 3rd Party Integrations | Large |

---

## Suggested Phases (High-Level)

| Phase | Focus | Key Deliverables |
|-------|-------|------------------|
| P1 | User Mgmt + Auth | User CRUD, roles, LDAP/SSO, API tokens |
| P2 | Custom Fields + Audit Trail | Custom field engine, change history |
| P3 | Reports & Dashboard | Report builder, pre-built reports, KPIs |
| P4 | Alerts & Notifications | Email/Slack, scheduled checks |
| P5 | Procurement & Depreciation | POs, suppliers, depreciation schedules |
| P6 | Approval Workflows | Requestable assets, multi-step approval |

---

## Next Steps

1. **Pick a priority gap** (e.g., "User Management", "Custom Fields", "Reports")
2. **Run proper phase discussion**: `/gsd-discuss-phase <N>` where N is a new milestone phase number
3. **Or run a full roadmap update**: `/gsd-new-milestone` to plan multi-phase ITAM roadmap