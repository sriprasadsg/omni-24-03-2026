from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.itam import Base

SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class User:
    def __init__(self, id: int, tenant_id: int, is_approver: bool, email: str, slack_id: str = None):
        self.id = id
        self.tenant_id = tenant_id
        self.is_approver = is_approver
        self.email = email
        self.slack_id = slack_id

def get_current_user():
    return User(id=1, tenant_id=1, is_approver=True, email="user@example.com", slack_id="U1234567890")

Base.metadata.create_all(bind=engine)