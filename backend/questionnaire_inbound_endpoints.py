from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from authentication_service import get_current_user
from models import User
from questionnaire_inbound_service import questionnaire_inbound_service, QuestionnaireInboundCreate

router = APIRouter(prefix="/api/questionnaires/inbound", tags=["Inbound Questionnaires"])

async def _tenant(user: User) -> str:
    """Helper to extract tenant_id from current_user, ensuring tenant isolation."""
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID not found for user")
    return user.tenant_id


@router.post("/", response_model=Dict[str, Any])
async def create_inbound_question_set(
    data: QuestionnaireInboundCreate,
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(_tenant),
) -> Dict[str, Any]:
    """Create a new inbound questionnaire set manually."""
    return await questionnaire_inbound_service.create_question_set(data, tenant_id, user.username)


@router.post("/{qid}/upload", response_model=Dict[str, Any])
async def upload_inbound_questions(
    qid: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(_tenant),
) -> Dict[str, Any]:
    """Upload questions from a CSV or XLSX file and append to an existing set."""
    question_set = await questionnaire_inbound_service.get_question_set(qid, tenant_id)
    if not question_set:
        raise HTTPException(status_code=404, detail="Questionnaire set not found")

    content_bytes = await file.read()
    new_questions = await questionnaire_inbound_service.parse_upload(file.filename, content_bytes)

    question_set["questions"].extend(new_questions)
    # Update the question set in the database (assuming partial update capability or full doc replacement)
    # This example replaces the questions array; a more robust solution might handle merge/dedup
    await questionnaire_inbound_service._db().questionnaire_inbound.update_one(
        {"id": qid, "tenantId": tenant_id},
        {"$set": {"questions": question_set["questions"], "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return question_set


@router.get("/", response_model=List[Dict[str, Any]])
async def list_inbound_question_sets(
    tenant_id: str = Depends(_tenant),
) -> List[Dict[str, Any]]:
    """List all inbound questionnaire sets for the current tenant."""
    return await questionnaire_inbound_service.list_question_sets(tenant_id)


@router.get("/{qid}", response_model=Dict[str, Any])
async def get_inbound_question_set(
    qid: str,
    tenant_id: str = Depends(_tenant),
) -> Dict[str, Any]:
    """Get a specific inbound questionnaire set by ID."""
    question_set = await questionnaire_inbound_service.get_question_set(qid, tenant_id)
    if not question_set:
        raise HTTPException(status_code=404, detail="Questionnaire set not found")
    return question_set
