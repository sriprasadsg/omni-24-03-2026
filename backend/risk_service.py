from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid

class Risk(BaseModel):
    id: str
    title: str
    description: str
    category: str  # Enterprise, AI, Compliance, Third-Party, Cyber
    status: str  # Open, Mitigated, Accepted, Transferred, Avoided
    likelihood: int  # 1-5
    impact: int  # 1-5
    risk_score: int  # likelihood * impact
    owner: str
    mitigation_plan: Optional[str] = None
    created_at: str
    updated_at: str

    # AI Specific
    ai_system_id: Optional[str] = None
    
    # Vendor Specific
    vendor_id: Optional[str] = None

class RiskService:
    def __init__(self):
        self.risks: List[Risk] = []  # Start with empty risk list, no mock data

    def get_all_risks(self) -> List[Risk]:
        return self.risks

    def create_risk(self, risk_data: Dict[str, Any]) -> Risk:
        new_risk = Risk(
            id=str(uuid.uuid4()),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            **risk_data
        )
        new_risk.risk_score = new_risk.likelihood * new_risk.impact
        self.risks.append(new_risk)
        return new_risk

    def update_risk(self, risk_id: str, updates: Dict[str, Any]) -> Optional[Risk]:
        for risk in self.risks:
            if risk.id == risk_id:
                updated_data = risk.dict()
                updated_data.update(updates)
                updated_data['updated_at'] = datetime.now().isoformat()
                
                # Recalculate score if likelihood or impact changed
                if 'likelihood' in updates or 'impact' in updates:
                     updated_data['risk_score'] = updated_data.get('likelihood', risk.likelihood) * updated_data.get('impact', risk.impact)

                new_risk = Risk(**updated_data)
                self.risks.remove(risk)
                self.risks.append(new_risk)
                return new_risk
        return None

    def delete_risk(self, risk_id: str) -> bool:
        initial_len = len(self.risks)
        self.risks = [r for r in self.risks if r.id != risk_id]
        return len(self.risks) < initial_len

# Singleton instance
risk_service = RiskService()
