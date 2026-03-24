from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid

class VendorAssessment(BaseModel):
    id: str
    vendor_id: str
    assessment_date: str
    reviewer: str
    risk_score: int # 0-100
    status: str # Pending, In Progress, Completed, Rejected
    questionnaire_responses: Dict[str, Any]
    findings: List[str]

class Vendor(BaseModel):
    id: str
    name: str
    website: str
    criticality: str  # Low, Medium, High, Critical
    category: str # SaaS, Hardware, Services, Software
    contact_name: str
    contact_email: str
    contract_start: str
    contract_end: str
    status: str # Active, Inactive, Pending Review
    assessments: List[VendorAssessment] = []
    linked_sboms: List[str] = [] # IDs of Sbom objects

class VendorService:
    def __init__(self):
        self.vendors: List[Vendor] = [
            Vendor(
                id="vendor-1",
                name="CloudServices Inc.",
                website="https://cloudservices.example.com",
                criticality="Critical",
                category="SaaS",
                contact_name="Jane Doe",
                contact_email="jane@cloudservices.example.com",
                contract_start="2025-01-01",
                contract_end="2026-01-01",
                status="Active",
                assessments=[],
                linked_sboms=["sbom-1"]
            ),
             Vendor(
                id="vendor-2",
                name="Legacy Hardware Corp",
                website="https://legacyhq.example.com",
                criticality="Medium",
                category="Hardware",
                contact_name="John Smith",
                contact_email="john@legacyhq.example.com",
                contract_start="2024-06-01",
                contract_end="2027-06-01",
                status="Active",
                 assessments=[],
                linked_sboms=[]
            )
        ]

    def get_all_vendors(self) -> List[Vendor]:
        return self.vendors

    def get_vendor(self, vendor_id: str) -> Optional[Vendor]:
        return next((v for v in self.vendors if v.id == vendor_id), None)

    def create_vendor(self, vendor_data: Dict[str, Any]) -> Vendor:
        new_vendor = Vendor(
            id=str(uuid.uuid4()),
            assessments=[],
            **vendor_data
        )
        self.vendors.append(new_vendor)
        return new_vendor

    def update_vendor(self, vendor_id: str, updates: Dict[str, Any]) -> Optional[Vendor]:
        vendor = self.get_vendor(vendor_id)
        if vendor:
            # Pydantic models are immutable by default in some versions, but here we can re-instantiate or use update logic
            # Simulating update
            vendor_dict = vendor.dict()
            vendor_dict.update(updates)
            new_vendor = Vendor(**vendor_dict)
            self.vendors = [v for v in self.vendors if v.id != vendor_id]
            self.vendors.append(new_vendor)
            return new_vendor
        return None
    
    def delete_vendor(self, vendor_id: str) -> bool:
        initial_len = len(self.vendors)
        self.vendors = [v for v in self.vendors if v.id != vendor_id]
        return len(self.vendors) < initial_len

    def add_assessment(self, vendor_id: str, assessment_data: Dict[str, Any]) -> Optional[VendorAssessment]:
        vendor = self.get_vendor(vendor_id)
        if vendor:
            new_assessment = VendorAssessment(
                id=str(uuid.uuid4()),
                vendor_id=vendor_id,
                status="Pending",
                **assessment_data
            )
            vendor.assessments.append(new_assessment)
            return new_assessment
        return None

vendor_service = VendorService()
