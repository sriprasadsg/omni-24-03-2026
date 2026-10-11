"""
Security awareness training — modules, assignments and server-graded quizzes.

Stored in Mongo (training_modules, training_assignments) through the
tenant-isolated database handle from get_database(), so each tenant only sees
its own modules and assignments. Replaces an in-memory service that was seeded
with demo modules and let learners report their own quiz score.

Quiz answers never leave the server: learners get questions and options only,
and a score is recorded only by grading submitted answers here.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

PASS_MARK = 70  # percent needed to complete a module that has a quiz


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_quiz(questions: List[Dict[str, Any]]) -> Optional[str]:
    """Return an error message for a malformed quiz, else None."""
    for i, q in enumerate(questions, 1):
        options = q.get("options") or []
        if not str(q.get("question", "")).strip():
            return f"Question {i} has no text"
        if len(options) < 2:
            return f"Question {i} needs at least two options"
        if q.get("correct_answer") not in options:
            return f"Question {i}: the correct answer must be one of its options"
    return None


def public_module(module: Dict[str, Any]) -> Dict[str, Any]:
    """Module as a learner may see it: quiz questions without their answers."""
    view = {k: v for k, v in module.items() if k != "_id"}
    view["quiz_questions"] = [
        {"question": q.get("question"), "options": q.get("options", [])}
        for q in module.get("quiz_questions", [])
    ]
    return view


async def list_modules(db) -> List[Dict[str, Any]]:
    docs = await db.training_modules.find({"is_active": True}, {"_id": 0}).to_list(length=500)
    return [public_module(m) for m in docs]


async def get_module(db, module_id: str) -> Optional[Dict[str, Any]]:
    return await db.training_modules.find_one({"id": module_id}, {"_id": 0})


async def create_module(db, data: Dict[str, Any]) -> Dict[str, Any]:
    module = {
        "id": f"mod-{uuid.uuid4().hex[:12]}",
        "title": data["title"],
        "description": data.get("description", ""),
        "content_url": data.get("content_url", ""),
        "duration_minutes": int(data.get("duration_minutes") or 0),
        "quiz_questions": data.get("quiz_questions") or [],
        "created_at": _now_iso(),
        "is_active": True,
    }
    await db.training_modules.insert_one(dict(module))
    return public_module(module)


async def assign(db, user_email: str, module_id: str) -> Dict[str, Any]:
    assignment = {
        "id": f"asg-{uuid.uuid4().hex[:12]}",
        "user_email": user_email.strip().lower(),
        "module_id": module_id,
        "assigned_at": _now_iso(),
        "started_at": None,
        "completed_at": None,
        "status": "Assigned",
        "quiz_score": None,
        "attempts": 0,
    }
    await db.training_assignments.insert_one(dict(assignment))
    return assignment


async def get_assignment(db, assignment_id: str) -> Optional[Dict[str, Any]]:
    return await db.training_assignments.find_one({"id": assignment_id}, {"_id": 0})


async def _joined(db, assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    modules = {m["id"]: m for m in await db.training_modules.find({}, {"_id": 0}).to_list(length=500)}
    out = []
    for a in assignments:
        module = modules.get(a["module_id"])
        if not module:
            continue
        pm = public_module(module)
        out.append({
            **a,
            "module_title": pm["title"],
            "module_description": pm["description"],
            "duration_minutes": pm["duration_minutes"],
            "content_url": pm["content_url"],
            "quiz_questions": pm["quiz_questions"],
        })
    return out


async def user_training(db, user_email: str) -> List[Dict[str, Any]]:
    docs = await db.training_assignments.find(
        {"user_email": user_email.strip().lower()}, {"_id": 0}
    ).to_list(length=500)
    return await _joined(db, docs)


async def all_assignments(db) -> List[Dict[str, Any]]:
    docs = await db.training_assignments.find({}, {"_id": 0}).to_list(length=2000)
    return await _joined(db, docs)


async def _update(db, assignment_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    await db.training_assignments.update_one({"id": assignment_id}, {"$set": fields})
    return await get_assignment(db, assignment_id)


async def start(db, assignment: Dict[str, Any]) -> Dict[str, Any]:
    if assignment["status"] != "Assigned":
        return assignment
    return await _update(db, assignment["id"], {"status": "In Progress", "started_at": _now_iso()})


async def complete_without_quiz(db, assignment: Dict[str, Any]) -> Dict[str, Any]:
    fields = {"status": "Completed", "completed_at": _now_iso()}
    if not assignment.get("started_at"):
        fields["started_at"] = fields["completed_at"]
    return await _update(db, assignment["id"], fields)


def grade(module: Dict[str, Any], answers: List[str]) -> int:
    questions = module.get("quiz_questions", [])
    correct = sum(
        1 for i, q in enumerate(questions)
        if i < len(answers) and answers[i] == q.get("correct_answer")
    )
    return round(100 * correct / len(questions))


async def submit_quiz(db, assignment: Dict[str, Any], module: Dict[str, Any], answers: List[str]) -> Dict[str, Any]:
    score = grade(module, answers)
    now = _now_iso()
    fields: Dict[str, Any] = {"quiz_score": score, "attempts": int(assignment.get("attempts") or 0) + 1}
    if not assignment.get("started_at"):
        fields["started_at"] = now
    if score >= PASS_MARK:
        fields.update(status="Completed", completed_at=now)
    else:
        fields["status"] = "In Progress"
    updated = await _update(db, assignment["id"], fields)
    return {**updated, "passed": score >= PASS_MARK, "pass_mark": PASS_MARK}
