import asyncio
import sys
import os
# Add backend to path to allow imports like 'from database' to work
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
# Import directly since backend is in path now
from ai_governance_service import AiGovernanceService
from models import AiModel, AiPolicy

# Mock Database
mock_db = MagicMock()
# ai_models collection
mock_db.ai_models = MagicMock() 
mock_db.ai_models.find_one = AsyncMock()
mock_db.ai_models.insert_one = AsyncMock()
mock_db.ai_models.update_one = AsyncMock()
mock_db.ai_models.find = MagicMock()
mock_db.ai_models.find.return_value.to_list = AsyncMock()

# ai_policies collection
mock_db.ai_policies = MagicMock()
mock_db.ai_policies.find_one = AsyncMock()
mock_db.ai_policies.insert_one = AsyncMock()
mock_db.ai_policies.find = MagicMock()
mock_db.ai_policies.find.return_value.to_list = AsyncMock()

async def verify_ai_governance():
    print("Starting AI Governance Verification...")
    service = AiGovernanceService(mock_db)
    
    # 1. Register Model
    model_data = AiModel(
        id="test-model-1",
        tenantId="default",
        name="Test Model",
        description="A test model",
        framework="PyTorch",
        type="LLM",
        owner="admin",
        createdAt=datetime.now().isoformat(),
        updatedAt=datetime.now().isoformat()
    )
    
    mock_db.ai_models.find_one.return_value = None # No existing model
    await service.register_model(model_data)
    print("✅ Model Registration Verified")
    
    # 2. Create Policy
    policy_data = AiPolicy(
        id="policy-1",
        tenantId="default",
        name="PyTorch Only",
        description="Enforce PyTorch",
        rules=[{
            "id": "r1", 
            "name": "Framework Check",
            "description": "Must be PyTorch",
            "condition": "framework == PyTorch",
            "action": "flag",
            "severity": "High"
        }],
        createdAt=datetime.now().isoformat(),
        updatedAt=datetime.now().isoformat()
    )
    
    await service.create_policy(policy_data)
    print("✅ Policy Creation Verified")
    
    # 3. Evaluate Compliance
    # Mock find to return the policy we just created
    mock_db.ai_policies.find.return_value.to_list.return_value = [policy_data.dict()]
    # Mock get_model
    service.get_model = AsyncMock(return_value=model_data.dict())
    
    report = await service.evaluate_model_compliance("test-model-1", "default")
    
    if report['compliant']:
         print("✅ Compliance Check Passed (Model is PyTorch)")
    else:
         print(f"❌ Compliance Check Failed: {report}")
         
    # Test Violation
    violation_model = model_data.copy()
    violation_model.framework = "TensorFlow"
    service.get_model = AsyncMock(return_value=violation_model.dict())
    
    report_fail = await service.evaluate_model_compliance("test-model-1", "default")
    
    if not report_fail['compliant'] and "PyTorch" in report_fail['violations'][0]['message']:
        print("✅ Violation Detection Verified (TensorFlow flagged)")
    else:
         print(f"❌ Violation Detection Failed: {report_fail}")

if __name__ == "__main__":
    asyncio.run(verify_ai_governance())
