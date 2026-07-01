from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid

class TrustProfile(BaseModel):
    company_name: str
    description: str
    contact_email: str
    logo_url: str
    compliance_frameworks: List[str] # e.g., ["SOC2", "ISO27001"]
    public_documents: List[Dict[str, str]] # {"name": "Security Whitepaper", "url": "..."}
    private_documents: List[Dict[str, str]] # {"name": "SOC2 Type II Report", "url": "..."}

class AccessRequest(BaseModel):
    id: str
    requester_email: str
    company: str
    reason: str
    status: str # Pending, Approved, Denied
    requested_at: str
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None

class TrustService:
    def __init__(self):
        self.profile = TrustProfile(
            company_name="Omni-Agent Corp",
            description="Leading provider of AI-driven enterprise security solutions.",
            contact_email="security@omni-agent.com",
            logo_url="/logo.png",
            compliance_frameworks=["SOC2", "ISO 27001", "GDPR", "HIPAA"],
            public_documents=[
                {"name": "Security Whitepaper", "url": "/docs/whitepaper.pdf"},
                {"name": "Privacy Policy", "url": "/docs/privacy.pdf"}
            ],
            private_documents=[
                {"name": "SOC2 Type II Report (2025)", "url": "/docs/soc2-2025.pdf"},
                {"name": "Penetration Test Result (Q3 2025)", "url": "/docs/pentest-q3.pdf"}
            ]
        )
        self.requests: List[AccessRequest] = [
             AccessRequest(
                id="req-1",
                requester_email="auditor@bigfirm.com",
                company="Big Audit Firm",
                reason="Annual Audit",
                status="Pending",
                requested_at=datetime.now().isoformat()
            )
        ]

    def get_profile(self) -> TrustProfile:
        return self.profile

    def update_profile(self, updates: Dict[str, Any]) -> TrustProfile:
        current_data = self.profile.dict()
        current_data.update(updates)
        self.profile = TrustProfile(**current_data)
        return self.profile

    def get_requests(self) -> List[AccessRequest]:
        return self.requests

    def create_request(self, request_data: Dict[str, Any]) -> AccessRequest:
        new_request = AccessRequest(
            id=str(uuid.uuid4()),
            requested_at=datetime.now().isoformat(),
            status="Pending",
            **request_data
        )
        self.requests.append(new_request)
        return new_request

    def update_request_status(self, request_id: str, status: str, approved_by: str = None) -> Optional[AccessRequest]:
        for req in self.requests:
            if req.id == request_id:
                req.status = status
                if status == 'Approved':
                    req.approved_at = datetime.now().isoformat()
                    req.approved_by = approved_by
                return req
        return None

trust_service = TrustService()
