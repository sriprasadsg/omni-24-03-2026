import csv
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from database import get_database

class ExportService:
    async def generate_report(self, report_type: str, fmt: str, tenant_id: str = None):
        data = await self._fetch_data(report_type, tenant_id)
        filename = f"{report_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"

        if fmt == 'csv':
            content = self._generate_csv(data)
            return content, f"{filename}.csv", "text/csv"
        elif fmt == 'pdf':
            content = self._generate_pdf(data, report_type)
            return content, f"{filename}.pdf", "application/pdf"
        else:
            raise ValueError("Unsupported format")

    async def _fetch_data(self, report_type, tenant_id=None):
        db = get_database()
        query = {}
        if tenant_id:
            query["tenantId"] = tenant_id

        if report_type == 'Asset Inventory':
            cursor = db.assets.find(query, {"_id": 0})
            return await cursor.to_list(length=1000)
        elif report_type == 'Patch Management':
            cursor = db.patches.find(query, {"_id": 0})
            return await cursor.to_list(length=1000)
        elif report_type == 'Security Events':
            cursor = db.alerts.find(query, {"_id": 0}).limit(100) # Last 100 alerts
            return await cursor.to_list(length=100)
        elif report_type == 'AI Risk Register':
             # Mock for now as we don't have a dedicated collection yet
            return [
                {"Risk ID": "R-101", "Description": "Model Hallucination in Finance", "Severity": "High", "Status": "Open"},
                {"Risk ID": "R-102", "Description": "Prompt Injection Vulnerability", "Severity": "Critical", "Status": "Mitigated"},
                {"Risk ID": "R-103", "Description": "Training Data Leakage", "Severity": "Medium", "Status": "Monitoring"}
            ]
        return []

    def _generate_csv(self, data):
        if not data:
            return ""
        
        output = io.StringIO()
        # Flatten dictionary if needed or just take top level keys
        if isinstance(data[0], dict):
            # Simple flattening for primary keys
            keys = data[0].keys()
            writer = csv.DictWriter(output, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        else:
            # List of lists
            writer = csv.writer(output)
            writer.writerows(data)
            
        return output.getvalue()

    def _generate_pdf(self, data, title):
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()

        # Title
        elements.append(Paragraph(f"{title} Report", styles['Title']))
        elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 20))

        if not data:
            elements.append(Paragraph("No data available.", styles['Normal']))
        else:
            # Table Data
            # limited columns for PDF to fit
            headers = list(data[0].keys())[:8] # Take first 8 cols max
            table_data = [headers]
            
            for row in data:
                row_data = []
                for h in headers:
                    val = str(row.get(h, ''))
                    # Truncate long text
                    if len(val) > 50: val = val[:47] + "..."
                    row_data.append(val)
                table_data.append(row_data)

            # Create Table
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(t)

        doc.build(elements)
        return output.getvalue()
