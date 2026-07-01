"""Questionnaire Engine endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr
from authentication_service import get_current_user
from auth_types import TokenData
from questionnaire_service import questionnaire_service

router = APIRouter(prefix="/api/questionnaires", tags=["Questionnaires"])


def _tenant(user: TokenData) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


def _role(user: TokenData) -> str:
    return getattr(user, "role", "")


class QuestionCreate(BaseModel):
    text: str
    type: str = "text"
    required: bool = False
    options: Optional[List[str]] = None
    scale_min: Optional[int] = None
    scale_max: Optional[int] = None


class QuestionnaireCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: Optional[str] = "Internal"
    questions: Optional[List[Dict[str, Any]]] = None


class QuestionnaireUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    questions: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = None


class SendPayload(BaseModel):
    emails: List[str]


class ResponseSubmit(BaseModel):
    token: str
    answers: Dict[str, Any]


@router.get("")
async def list_questionnaires(current_user: TokenData = Depends(get_current_user)):
    return await questionnaire_service.list_questionnaires(_tenant(current_user), _role(current_user))


@router.post("")
async def create_questionnaire(payload: QuestionnaireCreate, current_user: TokenData = Depends(get_current_user)):
    created_by = getattr(current_user, "username", getattr(current_user, "email", "unknown"))
    return await questionnaire_service.create_questionnaire(
        payload.model_dump(exclude_none=True), _tenant(current_user), created_by
    )


@router.get("/{qid}")
async def get_questionnaire(qid: str, current_user: TokenData = Depends(get_current_user)):
    q = await questionnaire_service.get_questionnaire(qid, _tenant(current_user), _role(current_user))
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    return q


@router.put("/{qid}")
async def update_questionnaire(qid: str, payload: QuestionnaireUpdate, current_user: TokenData = Depends(get_current_user)):
    q = await questionnaire_service.update_questionnaire(
        qid, payload.model_dump(exclude_none=True), _tenant(current_user), _role(current_user)
    )
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    return q


@router.delete("/{qid}")
async def delete_questionnaire(qid: str, current_user: TokenData = Depends(get_current_user)):
    deleted = await questionnaire_service.delete_questionnaire(qid, _tenant(current_user), _role(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    return {"success": True}


@router.post("/{qid}/send")
async def send_questionnaire(qid: str, payload: SendPayload, current_user: TokenData = Depends(get_current_user)):
    if not payload.emails:
        raise HTTPException(status_code=400, detail="At least one email required")
    return await questionnaire_service.send_questionnaire(
        qid, payload.emails, _tenant(current_user), _role(current_user)
    )


@router.get("/{qid}/responses")
async def get_responses(qid: str, current_user: TokenData = Depends(get_current_user)):
    return await questionnaire_service.get_responses(qid, _tenant(current_user), _role(current_user))


@router.get("/{qid}/stats")
async def get_questionnaire_stats(qid: str, current_user: TokenData = Depends(get_current_user)):
    return await questionnaire_service.get_stats(qid, _tenant(current_user), _role(current_user))


@router.post("/{qid}/responses")
async def submit_response(qid: str, payload: ResponseSubmit):
    """Public endpoint — respondents submit answers via their unique token."""
    result = await questionnaire_service.submit_response(qid, payload.token, payload.answers)
    if not result:
        raise HTTPException(status_code=404, detail="Invalid token or already submitted")
    return {"success": True, "responseId": result.get("id")}
