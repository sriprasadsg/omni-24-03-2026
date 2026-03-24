import asyncio
import logging
import json
import re
from datetime import datetime
from database import get_database
import uuid

logger = logging.getLogger(__name__)

# Basic CEF Parser (Common Event Format)
# Example: CEF:0|Vendor|Product|Version|SignatureID|Name|Severity|Extension
CEF_REGEX = re.compile(r"^CEF:(\d+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|(.*)$")

class SyslogProtocol(asyncio.DatagramProtocol):
    def __init__(self, tenant_id="default"):
        super().__init__()
        self.tenant_id = tenant_id

    def connection_made(self, transport):
        self.transport = transport
        logger.info(f"Syslog UDP server started for tenant {self.tenant_id}")

    def datagram_received(self, data, addr):
        message = data.decode('utf-8', errors='ignore').strip()
        asyncio.create_task(self.process_syslog_message(message, addr))

    async def process_syslog_message(self, message, addr):
        parsed_doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": self.tenant_id,
            "timestamp": datetime.utcnow().isoformat(),
            "source_ip": addr[0],
            "raw_message": message,
            "log_type": "syslog",
            "device_vendor": "Unknown",
            "device_product": "Unknown",
            "severity": "Low"
        }

        # Try mapping CEF format if applicable
        cef_match = CEF_REGEX.match(message)
        if cef_match:
            parsed_doc.update({
                "log_type": "cef",
                "cef_version": cef_match.group(1),
                "device_vendor": cef_match.group(2).strip(),
                "device_product": cef_match.group(3).strip(),
                "device_version": cef_match.group(4).strip(),
                "signature_id": cef_match.group(5).strip(),
                "name": cef_match.group(6).strip(),
                "severity": cef_match.group(7).strip(),
                "extension": cef_match.group(8)
            })
            # Naive K=V parsing for extensions could go here

        try:
            db = get_database()
            # Store in the logs collection
            await db.siem_logs.insert_one(parsed_doc)
        except Exception as e:
            logger.error(f"Error saving syslog message to DB: {e}")

async def start_syslog_server(host="0.0.0.0", port=5140, tenant_id="default"):
    loop = asyncio.get_running_loop()
    logger.info(f"Starting UDP Syslog Server on {host}:{port}")
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: SyslogProtocol(tenant_id=tenant_id),
        local_addr=(host, port)
    )
    return transport
