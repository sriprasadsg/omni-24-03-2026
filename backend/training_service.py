from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid

class TrainingModule(BaseModel):
    id: str
    title: str
    description: str
    content_url: str # Video or slide deck URL
    duration_minutes: int
    quiz_questions: List[Dict[str, Any]] # [{"question": "...", "options": [], "correct_answer": "..."}]
    created_at: str
    is_active: bool

class UserTrainingProgress(BaseModel):
    id: str
    user_email: str
    module_id: str
    assigned_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: str # Assigned, In Progress, Completed
    quiz_score: Optional[int] = None

class TrainingService:
    def __init__(self):
        self.modules: List[TrainingModule] = [
             TrainingModule(
                id="mod-1",
                title="Phishing Fundamentals 2025",
                description="Learn how to spot advanced AI-driven phishing attacks.",
                content_url="https://example.com/videos/phishing-101.mp4",
                duration_minutes=15,
                quiz_questions=[
                    {"question": "What is a red flag in an email?", "options": ["Urgency", "Generic Greeting", "Both"], "correct_answer": "Both"}
                ],
                created_at=datetime.now().isoformat(),
                is_active=True
            ),
             TrainingModule(
                id="mod-2",
                title="Data Privacy & GDPR",
                description="Understanding your role in protecting customer data.",
                content_url="https://example.com/slides/gdpr-basics",
                duration_minutes=30,
                quiz_questions=[],
                created_at=datetime.now().isoformat(),
                is_active=True
            )
        ]
        self.assignments: List[UserTrainingProgress] = [
            UserTrainingProgress(
                id="prog-1",
                user_email="employee@omni-agent.com",
                module_id="mod-1",
                assigned_at=datetime.now().isoformat(),
                status="Assigned"
            )
        ]

    def get_modules(self) -> List[TrainingModule]:
        return self.modules

    def create_module(self, module_data: Dict[str, Any]) -> TrainingModule:
        new_module = TrainingModule(
            id=str(uuid.uuid4()),
            created_at=datetime.now().isoformat(),
            is_active=True,
            **module_data
        )
        self.modules.append(new_module)
        return new_module

    def assign_training(self, user_email: str, module_id: str) -> UserTrainingProgress:
        new_assignment = UserTrainingProgress(
            id=str(uuid.uuid4()),
            user_email=user_email,
            module_id=module_id,
            assigned_at=datetime.now().isoformat(),
            status="Assigned"
        )
        self.assignments.append(new_assignment)
        return new_assignment

    def get_user_training(self, user_email: str) -> List[Dict[str, Any]]:
        # Join assignments with module details
        result = []
        for assignment in self.assignments:
            if assignment.user_email == user_email:
                module = next((m for m in self.modules if m.id == assignment.module_id), None)
                if module:
                    data = assignment.dict()
                    data['module_title'] = module.title
                    data['module_description'] = module.description
                    data['duration_minutes'] = module.duration_minutes
                    result.append(data)
        return result

    def update_progress(self, assignment_id: str, updates: Dict[str, Any]) -> Optional[UserTrainingProgress]:
        for assignment in self.assignments:
            if assignment.id == assignment_id:
                if 'status' in updates:
                    assignment.status = updates['status']
                    if updates['status'] == 'Completed':
                        assignment.completed_at = datetime.now().isoformat()
                    elif updates['status'] == 'In Progress' and not assignment.started_at:
                        assignment.started_at = datetime.now().isoformat()
                
                if 'quiz_score' in updates:
                    assignment.quiz_score = updates['quiz_score']
                
                return assignment
        return None

training_service = TrainingService()
