"""SOC case work routes: a case's tasks and evidence (soc_cases), under the Security Overview catalogue.

Reads need view:security; changes need what the catalogue's writes need (manage:security_cases or
manage:settings). The case is looked up in the caller's scope first (soc_endpoints.soc_scope), so a task or
evidence id of another tenant's case is never reached.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from auth_types import TokenData
from authentication_service import get_current_user
from catalogue_mounts_secops import SECURITY_GUARD
from database import get_database
from rbac_utils import verify_permission
import soc_actions
import soc_cases
from soc_endpoints import soc_scope

router = APIRouter(prefix="/api/security/soc/cases", tags=["SOC"], dependencies=[Depends(SECURITY_GUARD)])


class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    assignee: Optional[str] = Field(None, max_length=120)
    dueAt: Optional[str] = Field(None, max_length=40)

    model_config = {"extra": "forbid"}


class TaskPatch(BaseModel):
    status: Optional[Literal["todo", "in_progress", "done", "skipped"]] = None
    assignee: Optional[str] = Field(None, max_length=120)
    dueAt: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=1000)

    model_config = {"extra": "forbid"}


class EvidenceIn(BaseModel):
    kind: Literal["indicator", "note"]
    value: str = Field(..., min_length=1, max_length=4000)
    indicatorKind: Optional[Literal["user", "process", "file", "ip", "domain", "hash", "other"]] = None
    note: Optional[str] = Field(None, max_length=1000)

    model_config = {"extra": "forbid"}


class ExcludeIn(BaseModel):
    excluded: bool
    reason: Optional[str] = Field(None, max_length=500)

    model_config = {"extra": "forbid"}


async def _run(coro):
    try:
        return await coro
    except soc_cases.CaseError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


def _who(user) -> str:
    return soc_actions._actor(user)


async def _audit(action: str, out: dict, user, case_id: str, **fields) -> None:
    await soc_actions._audit(action, out.get("tenantId") or soc_scope(user), user, caseId=case_id, **fields)


@router.get("/{case_id}/work")
async def get_case_work(case_id: str, current_user: TokenData = Depends(get_current_user)):
    """The case's tasks and evidence, plus the standard steps and alert indicators it does not hold yet."""
    out = await _run(soc_cases.work(get_database(), soc_scope(current_user), case_id[:128]))
    out["canEdit"] = any([await verify_permission(current_user, p) for p in ("manage:security_cases", "manage:settings")])
    return out


@router.post("/{case_id}/tasks")
async def add_case_task(case_id: str, body: TaskIn, current_user: TokenData = Depends(get_current_user)):
    out = await _run(soc_cases.add_task(get_database(), soc_scope(current_user), case_id[:128], _who(current_user),
                                        body.title, body.assignee, body.dueAt))
    await _audit("soc.case.task.add", out, current_user, case_id[:128], taskId=out["id"])
    return out


@router.post("/{case_id}/tasks/standard")
async def add_standard_steps(case_id: str, current_user: TokenData = Depends(get_current_user)):
    """Add the response checklist (and steps for the case's alert types) that the case does not have yet."""
    out = await _run(soc_cases.add_standard_steps(get_database(), soc_scope(current_user), case_id[:128], _who(current_user)))
    await _audit("soc.case.task.standard", out, current_user, case_id[:128], added=out["added"])
    return out


@router.patch("/{case_id}/tasks/{task_id}")
async def patch_case_task(case_id: str, task_id: str, body: TaskPatch, current_user: TokenData = Depends(get_current_user)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to change")
    out = await _run(soc_cases.update_task(get_database(), soc_scope(current_user), case_id[:128], task_id[:64],
                                           _who(current_user), changes))
    await _audit("soc.case.task.update", out, current_user, case_id[:128], taskId=task_id[:64], status=out.get("status"))
    return out


@router.post("/{case_id}/evidence")
async def add_case_evidence(case_id: str, body: EvidenceIn, current_user: TokenData = Depends(get_current_user)):
    out = await _run(soc_cases.add_evidence(get_database(), soc_scope(current_user), case_id[:128], _who(current_user),
                                            body.kind, body.value, body.indicatorKind, body.note))
    await _audit("soc.case.evidence.add", out, current_user, case_id[:128], evidenceId=out["id"], kind=out["kind"])
    return out


@router.post("/{case_id}/evidence/from-alerts")
async def add_alert_indicators(case_id: str, current_user: TokenData = Depends(get_current_user)):
    """Every user, process, file and IP the case's alerts name, as indicator evidence."""
    out = await _run(soc_cases.add_alert_indicators(get_database(), soc_scope(current_user), case_id[:128], _who(current_user)))
    await _audit("soc.case.evidence.from_alerts", out, current_user, case_id[:128], added=out["added"])
    return out


@router.post("/{case_id}/evidence/file")
async def upload_case_file(case_id: str, file: UploadFile = File(...), note: Optional[str] = Form(None, max_length=1000),
                           current_user: TokenData = Depends(get_current_user)):
    """A file (at most 25 MB) kept with its SHA-256; it is only ever served back as a download."""
    contents = await file.read(soc_cases.MAX_FILE_BYTES + 1)
    out = await _run(soc_cases.add_file(get_database(), soc_scope(current_user), case_id[:128], _who(current_user),
                                        file.filename or "evidence", contents, note))
    await _audit("soc.case.evidence.file", out, current_user, case_id[:128], evidenceId=out["id"], sha256=out["sha256"],
                 size=out["size"])
    return out


@router.get("/{case_id}/evidence/{evidence_id}/download")
async def download_case_file(case_id: str, evidence_id: str, current_user: TokenData = Depends(get_current_user)):
    """The file as an attachment (never shown in the browser); the download goes on its custody log."""
    out = await _run(soc_cases.file_for_download(get_database(), soc_scope(current_user), case_id[:128], evidence_id[:64],
                                                 _who(current_user)))
    await _audit("soc.case.evidence.download", out, current_user, case_id[:128], evidenceId=evidence_id[:64], sha256=out["sha256"])
    return FileResponse(out["path"], media_type="application/octet-stream", filename=out["filename"],
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.patch("/{case_id}/evidence/{evidence_id}")
async def exclude_case_evidence(case_id: str, evidence_id: str, body: ExcludeIn, current_user: TokenData = Depends(get_current_user)):
    """Exclude evidence that turned out not to matter (with a reason), or include it again; nothing is deleted."""
    out = await _run(soc_cases.set_excluded(get_database(), soc_scope(current_user), case_id[:128], evidence_id[:64],
                                            _who(current_user), body.excluded, body.reason))
    await _audit("soc.case.evidence.exclude" if body.excluded else "soc.case.evidence.restore", out, current_user,
                 case_id[:128], evidenceId=evidence_id[:64])
    return out
