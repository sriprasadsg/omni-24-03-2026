import csv
import os
from datetime import datetime
from database import get_database
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table as PDFTable, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

class ComplianceReportingService:
    def __init__(self):
        self.reports_dir = "static/reports"
        os.makedirs(self.reports_dir, exist_ok=True)

    async def _get_evidence_for_control(self, db, control_id):
        pipeline = [
            {"$unwind": "$evidence"},
            {"$match": {"evidence.controlId": control_id}},
            {"$project": {"evidence.name": 1, "_id": 0}}
        ]
        cursor = db.asset_compliance.aggregate(pipeline)
        return [doc['evidence'] for doc in await cursor.to_list(length=100)]

    async def generate_report(self, tenant_id: str, framework_id: str) -> dict:
        """Generate CSV report"""
        db = get_database()
        
        # 1. Fetch Framework
        framework = await db.compliance_frameworks.find_one({"id": framework_id})
        if not framework:
            raise ValueError(f"Framework {framework_id} not found")
            
        # 2. Fetch Compliance Data
        controls = framework.get("controls", [])
        
        # Prepare CSV Data
        rows = []
        rows.append(["Control ID", "Name", "Category", "Status", "Evidence Count", "Collected Evidence", "Last Reviewed"])
        
        for control in controls:
            # Check if there is evidence for this control
            evidence_count = await db.asset_compliance.count_documents({
                "controlId": control["id"],
                "evidence": {"$exists": True, "$not": {"$size": 0}}
            })
            
            rows.append([
                control["id"],
                control["name"],
                control.get("category", ""),
                control.get("status", "Not Implemented"),
                str(evidence_count),
                # Fetch evidence names if count > 0
                ", ".join([e['name'] for e in await self._get_evidence_for_control(db, control["id"])]) if evidence_count > 0 else "None",
                control.get("lastReviewed", "")
            ])
            
        # 3. Write CSV
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"compliance_report_{framework_id}_{timestamp}.csv"
        filepath = os.path.join(self.reports_dir, filename)
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
            
        # 4. Return Metadata
        return {
            "filename": filename,
            "url": f"/static/reports/{filename}",
            "generatedAt": datetime.now().isoformat(),
            "rowCount": len(rows) - 1
        }

    async def generate_excel_report(self, tenant_id: str, framework_id: str) -> dict:
        """Generate Excel report with professional formatting"""
        db = get_database()
        
        # Fetch framework and controls
        framework = await db.compliance_frameworks.find_one({"id": framework_id})
        if not framework:
            raise ValueError(f"Framework {framework_id} not found")
        
        controls = framework.get("controls", [])
        
        # Create Excel workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"{framework_id} Report"
        
        # Add headers with formatting
        headers = ["Control ID", "Name", "Category", "Status", "Evidence Count", "Collected Evidence", "Last Reviewed"]
        ws.append(headers)
        
        # Style headers
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
        
        # Add data rows
        for control in controls:
            evidence_count = await db.asset_compliance.count_documents({
                "controlId": control["id"],
                "evidence": {"$exists": True, "$not": {"$size": 0}}
            })
            
            status = control.get("status", "Not Implemented")
            
            ws.append([
                control["id"],
                control["name"],
                control.get("category", ""),
                status,
                evidence_count,
                 ", ".join([e['name'] for e in await self._get_evidence_for_control(db, control["id"])]) if evidence_count > 0 else "None",
                control.get("lastReviewed", "")
            ])
            
            # Color code status cell
            current_row = ws.max_row
            status_cell = ws.cell(row=current_row, column=4)
            
            if status == "Implemented":
                status_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                status_cell.font = Font(color="006100")
            elif status == "Not Implemented":
                status_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                status_cell.font = Font(color="9C0006")
            else:  # Pending, In Progress, etc.
                status_cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
                status_cell.font = Font(color="9C5700")
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            adjusted_width = min(max_length + 2, 60)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Add borders to all cells
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=len(headers)):
            for cell in row:
                cell.border = thin_border
                if cell.row > 1:  # Data rows
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
        
        # Save file
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"compliance_report_{framework_id}_{timestamp}.xlsx"
        filepath = os.path.join(self.reports_dir, filename)
        wb.save(filepath)
        
        return {
            "filename": filename,
            "url": f"/static/reports/{filename}",
            "generatedAt": datetime.now().isoformat(),
            "rowCount": len(controls)
        }

    async def generate_pdf_report(self, tenant_id: str, framework_id: str) -> dict:
        """Generate PDF report with professional formatting"""
        try:
            db = get_database()
            
            framework = await db.compliance_frameworks.find_one({"id": framework_id})
            if not framework:
                raise ValueError(f"Framework {framework_id} not found")
            
            controls = framework.get("controls", [])
            print(f"[PDF] Generating report for {framework_id} with {len(controls)} controls")
            
            # Create PDF
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"compliance_report_{framework_id}_{timestamp}.pdf"
            filepath = os.path.join(self.reports_dir, filename)
            
            doc = SimpleDocTemplate(filepath, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
            elements = []
            
            # Title
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=20,
                textColor=colors.HexColor('#1a237e'),
                spaceAfter=20,
                alignment=1  # Center
            )
            
            framework_name = framework.get('name', framework_id).upper()
            title = Paragraph(f"{framework_name} Compliance Report", title_style)
            elements.append(title)
            elements.append(Spacer(1, 0.2*inch))
            
            # Metadata
            meta_style = ParagraphStyle(
                'MetaStyle',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#555555'),
                alignment=1
            )
            meta_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Total Controls: {len(controls)}"
            elements.append(Paragraph(meta_text, meta_style))
            elements.append(Spacer(1, 0.3*inch))
            
            # Table data
            data = [["Control ID", "Name", "Category", "Status", "Evidence", "Collected Evidence", "Last Reviewed"]]
            
            for control in controls:
                try:
                    evidence_count = await db.asset_compliance.count_documents({
                        "controlId": control["id"],
                        "evidence": {"$exists": True, "$not": {"$size": 0}}
                    })
                    evidence_list = await self._get_evidence_for_control(db, control["id"])
                    evidence_names = ", ".join([e['name'] for e in evidence_list])[:100] # Truncate for PDF
                    if len(evidence_names) == 100: evidence_names += "..."
                except Exception as e:
                    print(f"[PDF] Error counting evidence for {control.get('id', 'unknown')}: {e}")
                    evidence_count = 0
                    evidence_names = ""
                
                # Truncate long names for better table fit
                name = control["name"]
                if len(name) > 40:
                    name = name[:37] + "..."
                
                data.append([
                    control["id"],
                    name,
                    control.get("category", "")[:15],
                    control.get("status", "Not Implemented"),
                    str(evidence_count),
                    evidence_names if evidence_count > 0 else "None",
                    control.get("lastReviewed", "")
                ])
            
            print(f"[PDF] Created table with {len(data)} rows (including header)")
            
            # Create table
            # Adjusted widths to fit new column
            col_widths = [0.8*inch, 2.0*inch, 1.0*inch, 1.0*inch, 0.5*inch, 1.8*inch, 0.8*inch]
            table = PDFTable(data, colWidths=col_widths)
            
            # Table styling
            table_style = TableStyle([
                # Header styling
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#366092')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                
                # Data rows
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Control ID left
                ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Evidence count center
                ('ALIGN', (5, 1), (5, -1), 'LEFT'),    # Evidence names left
                ('VALIGN', (0, 1), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('LEFTPADDING', (0, 1), (-1, -1), 4),
                ('RIGHTPADDING', (0, 1), (-1, -1), 4),
                
                # Borders
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#366092')),
                
                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ])
            
            table.setStyle(table_style)
            elements.append(table)
            
            print(f"[PDF] Building PDF document with {len(elements)} elements at {filepath}")
            
            # Build PDF
            doc.build(elements)
            
            # Verify file was created and has content
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                print(f"[PDF] Successfully created PDF: {filename} ({file_size} bytes)")
            else:
                print(f"[PDF] ERROR: PDF file was not created at {filepath}")
            
            return {
                "filename": filename,
                "url": f"/static/reports/{filename}",
                "generatedAt": datetime.now().isoformat(),
                "rowCount": len(controls)
            }
        except Exception as e:
            print(f"[PDF] Error generating PDF report: {e}")
            import traceback
            traceback.print_exc()
            raise

compliance_reporting_service = ComplianceReportingService()

