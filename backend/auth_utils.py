"""
Authentication utilities for password hashing, verification, and validation.
"""
import bcrypt
import re
from authentication_service import get_current_user  # noqa: F401 – re-exported for endpoint imports
import logging


logger = logging.getLogger(__name__)

# Alias used by newer endpoint files
require_auth = get_current_user


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def validate_password_complexity(password: str) -> str | None:
    """Return an error message if the password fails complexity requirements, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return "Password must contain at least one digit"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must contain at least one special character"
    return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its bcrypt hash.
    """
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception as e:
        logger.warning("bcrypt password verification failed: %s", e)
        return False
