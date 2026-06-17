# Phase 3: Audit-Ready Export — Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 7 focus areas across backend and frontend
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/compliance_reporting_data.py` | service/data | CRUD | itself (extend) | exact |
| `backend/compliance_reporting_excel.py` | service/renderer | file-I/O | itself (extend) | exact |
| `backend/compliance_reporting_pdf.py` | service/renderer | file-I/O | itself (extend) | exact |
| `backend/compliance_reporting_service.py` | service/aggregator | CRUD | itself (extend) | exact |
| `backend/compliance_report_endpoints.py` | controller | request-response | `backend/compliance_reports_endpoints.py` | exact |
| `services/apiService.ts` | service | request-response | itself (extend) | exact |
| `components/FrameworkDetail.tsx` | component/UI | event-driven | itself (extend) | exact |

---

## Pattern Assignments

### 1. PDF Export

**Analog:** `backend/compliance_reporting_pdf.py`
**Library:** `reportlab` (SimpleDocTemplate, Table, Paragraph, Spacer, HRFlowable)

**Imports pattern** (lines 1–17):
```python
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table as PDFTable, TableStyle,
    Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from compliance_reporting_data import _build_report_data
```

**Core PDF generation pattern** (lines 42–134):
- `SimpleDocTemplate` writes directly to a filesystem path in `static/reports/`; no in-memory BytesIO used.
- Page size: `landscape(letter)` with 0.5 inch margins on all sides.
- Style hierarchy: title → subtitle → section heading → cell → header cell (all `ParagraphStyle` from `getSampleStyleSheet`).
- Tables: `PDFTable(data, colWidths=col_ws, repeatRows=1)` with `TableStyle`; rows use `Paragraph` wrappers so text wraps correctly.
- Status colour helper: `_find_status_rows(rows_data, col_idx)` returns `BACKGROUND` commands keyed on `_PDF_STATUS_COLORS` dict.
- File saved, returns `{"filename": ..., "url": f"/static/reports/{filename}", "generatedAt": ..., "rowCount": ...}`.

**Status colour map** (lines 19–28):
```python
_PDF_STATUS_COLORS = {
    "Compliant":           colors.HexColor("#C6EFCE"),
    "Partially Compliant": colors.HexColor("#FFEB9C"),
    "Non-Compliant":       colors.HexColor("#FFC7CE"),
    "Warning":             colors.HexColor("#FFEB9C"),
    "Implemented":         colors.HexColor("#C6EFCE"),
    "Not Implemented":     colors.HexColor("#FFC7CE"),
    "In Progress":         colors.HexColor("#FFEB9C"),
    "—":                   colors.white,
}
```

**Anti-pattern to avoid:** The existing PDF only covers a single framework. For Phase 3, an all-frameworks PDF will need to loop the same pattern used in `_generate_all_excel` (see Section 3).

---

### 2. Excel/XLSX Export

**Analog:** `backend/compliance_reporting_excel.py`
**Library:** `openpyxl` — `Workbook`, `Font`, `Alignment`, `PatternFill`, `Border`, `Side`

**Imports pattern** (lines 1–13):
```python
import os
import re
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

from compliance_reporting_data import _build_report_data, _overall_verdict
```

**Shared style constants** (lines 16–41):
```python
_STATUS_FILLS = { "Compliant": PatternFill(...), ... }
_STATUS_FONTS = { "Compliant": Font(color="006100"), ... }
_THIN_BORDER  = Border(left=Side(style="thin"), ...)
_HEADER_FILL  = PatternFill(start_color="366092", ...)
_HEADER_FONT  = Font(bold=True, color="FFFFFF", size=10)
_SECTION_FILL = PatternFill(start_color="1F3864", ...)
_SECTION_FONT = Font(bold=True, color="FFFFFF", size=11)
```

**Worksheet helper trio** (lines 46–75):
- `_xl_header_row(ws, headers)` — appends header row and applies `_HEADER_FILL`/`_HEADER_FONT` + centering + border.
- `_xl_auto_width(ws)` — caps column width at 55 characters.
- `_apply_status_colors(ws, row_num, col_idx, val)` — fills from `_STATUS_FILLS`/`_STATUS_FONTS`.
- `_apply_url_hyperlink(ws, row_num, url_col, raw_urls)` — first URL becomes a hyperlink, blue underline font.

**Single-framework Excel pattern** (lines 80–139):
- `wb = openpyxl.Workbook()` → `ws1 = wb.active` (title: "Asset Summary"), `ws2 = wb.create_sheet("Control Details")`.
- Each sheet: title row (large bold font) → blank row → section header row (section fill) → blank row → `_xl_header_row` → data rows with border + alignment + status colours.
- File: `wb.save(os.path.join(reports_dir, filename))`.

**All-frameworks Excel pattern** (lines 144–247):
- Per framework: two sheets named `"{short} Assets"` and `"{short} Controls"` plus an Overview sheet.
- Sheet name sanitisation: `re.sub(r'[\\/?*\[\]:]', '-', fw_name)[:24].strip()` — copy this exactly.

---

### 3. Report Endpoint Pattern

**Primary analog:** `backend/compliance_report_endpoints.py` (newer, has `_persist_report_meta`)
**Secondary analog:** `backend/compliance_reports_endpoints.py` (simpler, no DB persistence)

**Imports pattern** (lines 1–17 of `compliance_report_endpoints.py`):
```python
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse
from authentication_service import get_current_user
from auth_types import TokenData
from compliance_reporting_service import compliance_reporting_service
from database import get_database

router = APIRouter(prefix="/api/compliance/reports", tags=["Compliance Reports"])
_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "static", "reports")
```

**Generate endpoint pattern** (lines 29–44):
```python
@router.post("/generate")
async def generate_csv_report(
    framework_id: str = Form(...),
    current_user: TokenData = Depends(get_current_user),
):
    _ensure_reports_dir()
    tenant_id = getattr(current_user, "tenant_id", None)
    try:
        result = await compliance_reporting_service.generate_report(tenant_id, framework_id)
        await _persist_report_meta(result, framework_id, tenant_id, "csv", current_user)
        return result
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
```

**Download endpoint pattern** (`compliance_reports_endpoints.py` lines 86–110):
```python
@router.get("/download/{filename}")
async def download_compliance_report(filename: str, current_user=Depends(get_current_user)):
    file_path = os.path.join(_REPORTS_DIR, filename)
    # Path traversal guard:
    if not os.path.abspath(file_path).startswith(os.path.abspath(_REPORTS_DIR) + os.sep):
        raise HTTPException(status_code=404, detail="Report not found")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not found")

    media_type = {
        ".pdf":  "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv":  "text/csv",
    }.get(os.path.splitext(filename)[1], "application/octet-stream")

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
```

**Response type in use:** `FileResponse` (not `StreamingResponse`). Files are written to disk first (`static/reports/`), then served via `FileResponse`. The only place `StreamingResponse(io.BytesIO(...))` appears is in `compliance_automation_endpoints.py` — a different subsystem.

---

### 4. Tenant Isolation in Exports

**Current state — ANTI-PATTERN to fix:**

`compliance_reporting_data.py::_build_report_data` (lines 69–176) queries `asset_compliance` and `compliance_frameworks` **without any `tenant_id` filter**:
```python
# line 78 — no tenant filter:
framework = await db.compliance_frameworks.find_one({"id": framework_id})
# line 85 — no tenant filter:
ac_docs = await db.asset_compliance.find({"controlId": {"$in": control_ids}}).to_list(length=10000)
```

`tenant_id` is accepted by the service class methods (lines 127–139) but silently discarded — it is never passed down to `_build_report_data`.

The endpoint layer correctly extracts `tenant_id`:
```python
# compliance_report_endpoints.py line 36-37
tenant_id = getattr(current_user, "tenant_id", None)
```
...but it then passes it to a service that ignores it.

**Pattern to follow for Phase 3:** Thread `tenant_id` as a parameter into `_build_report_data` and add it to every DB query:
```python
# Add to asset_compliance query:
{"controlId": {"$in": control_ids}, "tenantId": tenant_id}
# Add to compliance_frameworks query:
{"id": framework_id, "tenantId": tenant_id}
```

The `compliance_evidence` collection already has a compound index on `(tenantId, controlId)` (`database.py` line 264) — use it.

---

### 5. Compliance Data Query Pattern

**Analog:** `backend/compliance_reporting_data.py::_build_report_data` (lines 69–176)

Collections queried:
| Collection | Query Key | Notes |
|---|---|---|
| `compliance_frameworks` | `{"id": framework_id}` | Missing tenant filter (anti-pattern) |
| `asset_compliance` | `{"controlId": {"$in": control_ids}}` | Missing tenant filter (anti-pattern) |
| `compliance_artifacts` | `{"control_ids": {"$in": control_ids}}` | Missing tenant filter |
| `assets` | `{"id": {"$in": asset_ids}}` | Lookup-only, projection `{id,hostname}` |

**Evidence merge logic** (lines 156–161):
```python
asset_ev = doc.get("evidence", [])
merged   = asset_ev + [
    a for a in standalone
    if not any(ae.get("id") == a.get("id") for ae in asset_ev)
]
ev = _flatten_evidence(merged)
```
Evidence comes from two sources per control/asset pair: inline `evidence` array on the `asset_compliance` doc, and standalone `compliance_artifacts` docs linked via `control_ids`. Both are merged via `_flatten_evidence` which deduplicates by `id/url/name`.

---

### 6. Evidence Data Inclusion

**Yes — existing exports already include evidence sub-documents.**

`_flatten_evidence` (lines 33–66 of `compliance_reporting_data.py`) extracts these fields from evidence records:
- `name` / `filename`
- `url`
- `description`
- `uploadedAt` / `uploaded_at` / `date` / `lastUpdated` (first 10 chars)
- `status`

Resulting columns in exported reports: `Evidence Count`, `Evidence Names`, `Evidence URLs`, `Evidence Dates`, `Evidence Desc`.

For Phase 3 audit export, copy this function as-is. If adding manual evidence from Phase 2 (`compliance_evidence` collection), extend `_build_report_data` to also query that collection and append to the merge list.

---

### 7. Frontend Export UI Pattern

**Analog:** `components/FrameworkDetail.tsx`

**ReportsModal component** (lines 65–136):
```tsx
const ReportsModal = ({ isOpen, onClose, frameworkId }) => {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading]  = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      setLoading(true);
      api.fetchComplianceReports(frameworkId).then(setReports).finally(() => setLoading(false));
    }
  }, [isOpen, frameworkId]);

  const handleDownload = async (report: any) => {
    setDownloading(report.filename);
    try {
      await api.downloadComplianceReport(report.filename);
    } catch (error) {
      showToast('Failed to download file. Please try again.', 'error');
    } finally {
      setDownloading(null);
    }
  };
  // ... table rendering with per-row Download button
};
```

**Generate + format selector UI** (lines 225, 270–291, 344–360):
```tsx
// State:
const [reportFormat, setReportFormat] = useState<'csv' | 'excel' | 'pdf'>('csv');

// Handler — selects API call by format:
const handleGenerateReport = async () => {
  let res;
  if (reportFormat === 'excel')     res = await api.generateExcelComplianceReport(framework.id);
  else if (reportFormat === 'pdf')  res = await api.generatePDFComplianceReport(framework.id);
  else                              res = await api.generateComplianceReport(framework.id);
  if (res?.filename) {
    showToast(`${reportFormat.toUpperCase()} report generated successfully!`, 'success');
    setIsReportsModalOpen(true);
  }
};

// JSX format picker:
<select value={reportFormat} onChange={(e) => setReportFormat(e.target.value as ...)}>
  <option value="csv">CSV</option>
  <option value="excel">Excel (.xlsx)</option>
  <option value="pdf">PDF</option>
</select>
<button onClick={handleGenerateReport}>Generate Report</button>
```

**Toast pattern:** `showToast(message, 'success' | 'error')` from `../utils/toast`.

---

### 8. API Service Pattern

**Analog:** `services/apiService.ts` lines 3306–3375

**POST to generate (FormData pattern)**:
```typescript
export const generateExcelComplianceReport = async (frameworkId: string) => {
    const formData = new FormData();
    formData.append('framework_id', frameworkId);
    const res = await authFetch(`${API_BASE}/compliance/reports/generate/excel`, { method: 'POST', body: formData });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Excel report generation failed' }));
        throw new Error(err.detail || 'Excel report generation failed');
    }
    return await res.json();
};
```

**GET to download (blob trigger pattern)**:
```typescript
export const downloadComplianceReport = async (filename: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/compliance/reports/download/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error('Failed to download report');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
};
```

---

## Shared Patterns

### Authentication / Tenant Extraction
**Source:** `backend/compliance_report_endpoints.py` lines 36–37
**Apply to:** All generate and download endpoints in Phase 3
```python
current_user: TokenData = Depends(get_current_user)
tenant_id = getattr(current_user, "tenant_id", None)
if not tenant_id:
    raise HTTPException(status_code=403, detail="Tenant context required")
```

### Path Traversal Guard
**Source:** `backend/compliance_reports_endpoints.py` lines 91–93
**Apply to:** Any download endpoint that takes a filename from the URL path
```python
if not os.path.abspath(file_path).startswith(os.path.abspath(_REPORTS_DIR) + os.sep):
    raise HTTPException(status_code=404, detail="Report not found")
```

### Error Handling in Endpoints
**Source:** `backend/compliance_report_endpoints.py` lines 41–44
```python
except ValueError:
    raise HTTPException(status_code=404, detail="Not found")
except Exception:
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Reports Directory
**Source:** `backend/compliance_report_endpoints.py` line 20 + `compliance_reporting_service.py` lines 122–125
```python
_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "static", "reports")
os.makedirs(_REPORTS_DIR, exist_ok=True)
```
Both endpoint files define `_REPORTS_DIR` the same way. Use the absolute `os.path.dirname(__file__)` form.

### File Naming Convention
**Source:** `compliance_reporting_service.py` lines 53–54, `compliance_reporting_excel.py` line 135
```python
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
filename  = f"compliance_report_{framework_id}_{timestamp}.{ext}"
# all-frameworks variant:
filename  = f"all_compliance_report_{timestamp}.{ext}"
```

### Return Shape from Generator Functions
```python
return {
    "filename": filename,
    "url": f"/static/reports/{filename}",
    "generatedAt": datetime.now().isoformat(),
    "rowCount": len(control_rows),   # or "frameworkCount" for all-frameworks
}
```
The frontend checks `res?.filename` to confirm success (`FrameworkDetail.tsx` line 282).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| Audit package ZIP bundling | utility | file-I/O | No ZIP archive generation exists anywhere in the codebase |
| Watermarking / classification labels on PDF | renderer | file-I/O | No precedent; reportlab supports it via `canvas.drawString` on `onFirstPage` callback |

---

## Key Inconsistencies / Anti-Patterns to Avoid

1. **Tenant isolation gap** — `_build_report_data` ignores the `tenant_id` passed to it. Every new Phase 3 query must include `{"tenantId": tenant_id}` in the MongoDB filter. The `compliance_evidence` compound index `(tenantId, controlId)` already exists and should be used.

2. **Duplicate endpoint files** — both `compliance_reports_endpoints.py` and `compliance_report_endpoints.py` exist with overlapping routes. `compliance_report_endpoints.py` is the newer, more complete version (has `_persist_report_meta`). Phase 3 endpoints should extend `compliance_report_endpoints.py`, not the older file.

3. **No streaming** — files are written to disk and served via `FileResponse`. Do not switch to `StreamingResponse`; the disk-file approach is consistent throughout the compliance reporting subsystem and allows the "View Reports" list to show previously generated files.

4. **`logger` not wired in `_generate_csv` / PDF / Excel renderers** — errors are silently swallowed. Phase 3 renderers should add `logger = logging.getLogger(__name__)` at module level and log before re-raising.

---

## Metadata

**Analog search scope:** `backend/compliance_reporting_*.py`, `backend/compliance_report*_endpoints.py`, `components/FrameworkDetail.tsx`, `services/apiService.ts`
**Files scanned:** 10
**Pattern extraction date:** 2026-06-17
