"""
Compliance Reporting Service aggregator.

Format renderers live in dedicated modules:
  compliance_reporting_data.py  — scoring helpers + DB fetch
  compliance_reporting_excel.py — Excel (single & all-frameworks)
  compliance_reporting_pdf.py   — PDF (single framework)

This module owns CSV generation and the backwards-compatible service class.
"""

import csv
import io
import os
import logging
from datetime import datetime

from database import get_database
from compliance_reporting_data import _build_report_data, _sanitize_cell
from compliance_reporting_excel import _generate_excel, _generate_all_excel
from compliance_reporting_pdf import _generate_pdf

logger = logging.getLogger(__name__)


# ── CSV ───────────────────────────────────────────────────────────────────────

async def _generate_csv(framework_id: str, reports_dir: str, tenant_id: str = None) -> dict:
    framework, asset_summary, control_rows = await _build_report_data(framework_id, tenant_id)
    fw_name = framework.get("name", framework_id)

    output = io.StringIO()
    w = csv.writer(output)
    w.writerow([f"Compliance Report: {fw_name}"])
    w.writerow([f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    w.writerow([])

    w.writerow(["ASSET COMPLIANCE SUMMARY"])
    if asset_summary:
        w.writerow(list(asset_summary[0].keys()))
        for row in asset_summary:
            w.writerow([_sanitize_cell(v) for v in row.values()])
    else:
        w.writerow(["No asset compliance data available"])
    w.writerow([])

    w.writerow(["CONTROL DETAILS WITH EVIDENCE"])
    if control_rows:
        w.writerow(list(control_rows[0].keys()))
        for row in control_rows:
            w.writerow([_sanitize_cell(v) for v in row.values()])

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"compliance_report_{framework_id}_{timestamp}.csv"
    with open(os.path.join(reports_dir, filename), "w", newline="", encoding="utf-8") as f:
        f.write(output.getvalue())
    return {
        "filename": filename, "url": f"/static/reports/{filename}",
        "generatedAt": datetime.now().isoformat(), "rowCount": len(control_rows),
    }


async def _generate_all_csv(reports_dir: str, tenant_id: str = None) -> dict:
    db = get_database()
    frameworks = await db.compliance_frameworks.find(
        {}, {"id": 1, "name": 1}
    ).to_list(length=100)
    if not frameworks:
        raise ValueError("No compliance frameworks found")

    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["All Compliance Frameworks — Combined Report"])
    w.writerow([f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    w.writerow([])

    total_done = 0
    for fw in frameworks:
        fw_id = fw.get("id", "")
        fw_name = fw.get("name", fw_id)
        try:
            _, asset_summary, control_rows = await _build_report_data(fw_id, tenant_id)
        except Exception as exc:
            logger.warning("Skipping framework %s in combined report: %s", fw_name, exc)
            continue
        total_done += 1

        w.writerow([f"=== FRAMEWORK: {fw_name} ==="])
        w.writerow(["ASSET COMPLIANCE SUMMARY"])
        if asset_summary:
            w.writerow(list(asset_summary[0].keys()))
            for row in asset_summary:
                w.writerow([_sanitize_cell(v) for v in row.values()])
        else:
            w.writerow(["No asset compliance data available"])
        w.writerow([])

        w.writerow(["CONTROL DETAILS WITH EVIDENCE"])
        if control_rows:
            w.writerow(list(control_rows[0].keys()))
            for row in control_rows:
                w.writerow([_sanitize_cell(v) for v in row.values()])
        else:
            w.writerow(["No control data available"])
        w.writerow([])
        w.writerow([])

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"all_compliance_report_{timestamp}.csv"
    with open(os.path.join(reports_dir, filename), "w", newline="", encoding="utf-8") as f:
        f.write(output.getvalue())
    return {
        "filename": filename, "url": f"/static/reports/{filename}",
        "generatedAt": datetime.now().isoformat(), "frameworkCount": total_done,
    }


# ── Report metadata persistence (enables tenant ownership check on download) ──

async def _store_report_meta(filename: str, tenant_id: str | None) -> None:
    db = get_database()
    await db.compliance_reports.update_one(
        {"filename": filename},
        {"$set": {"filename": filename, "tenantId": tenant_id,
                  "createdAt": datetime.now().isoformat()}},
        upsert=True,
    )


# ── Service class (backwards-compatible API) ──────────────────────────────────

class ComplianceReportingService:
    def __init__(self):
        self.reports_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static", "reports"
        )
        os.makedirs(self.reports_dir, exist_ok=True)

    async def generate_report(self, tenant_id: str, framework_id: str) -> dict:
        result = await _generate_csv(framework_id, self.reports_dir, tenant_id)
        await _store_report_meta(result["filename"], tenant_id)
        return result

    async def generate_excel_report(self, tenant_id: str, framework_id: str) -> dict:
        result = await _generate_excel(framework_id, self.reports_dir, tenant_id)
        await _store_report_meta(result["filename"], tenant_id)
        return result

    async def generate_pdf_report(self, tenant_id: str, framework_id: str) -> dict:
        result = await _generate_pdf(framework_id, self.reports_dir, tenant_id)
        await _store_report_meta(result["filename"], tenant_id)
        return result

    async def generate_all_csv_report(self, tenant_id: str) -> dict:
        result = await _generate_all_csv(self.reports_dir, tenant_id)
        await _store_report_meta(result["filename"], tenant_id)
        return result

    async def generate_all_excel_report(self, tenant_id: str) -> dict:
        result = await _generate_all_excel(self.reports_dir, tenant_id=tenant_id)
        await _store_report_meta(result["filename"], tenant_id)
        return result

    async def generate_all_frameworks_report(self, tenant_id: str, format: str) -> dict:
        if format == "excel":
            result = await _generate_all_excel(self.reports_dir, tenant_id=tenant_id)
        else:
            result = await _generate_all_csv(self.reports_dir, tenant_id)
        await _store_report_meta(result["filename"], tenant_id)
        return result


compliance_reporting_service = ComplianceReportingService()
