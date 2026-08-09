import logging

logger = logging.getLogger(__name__)


class ScanResult:
    def __init__(self, passed: bool, findings=None, reason: str = ""):
        self.passed = passed
        self.findings = findings or []
        self.reason = reason


async def scan_input(text: str, surface: str) -> ScanResult:
    return ScanResult(passed=True, findings=[])


async def scan_output(text: str, surface: str) -> ScanResult:
    return ScanResult(passed=True, findings=[])


async def cross_tenant_output_scan(text: str, tenant_id: str, db) -> ScanResult:
    return ScanResult(passed=True, findings=[])
