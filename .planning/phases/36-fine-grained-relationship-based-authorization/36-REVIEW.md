---
phase: 36-fine-grained-relationship-based-authorization
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - backend/rebac_service.py
  - backend/compliance_framework_mgmt_endpoints.py
  - backend/tests/test_rebac.py
findings:
  critical: 1
  warning: 1
  info: 1
  total: 3
status: issues_found
---

# Phase 36: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 36 integrates OpenFGA for Relationship-Based Access Control (ReBAC).
`ReBACService` class wraps the OpenFGA client. The `add_compliance_control`
endpoint is the pilot: it now gates writes behind `rebac.check_permission`.
Tests mock the ReBAC service to verify allow/deny paths. The design is sound, but
the implementation has a critical error-handling vulnerability and one minor
issue.

## Critical Issues

### CR-01: Generic `except Exception` in `check_permission` causes fail-open/fail-closed ambiguity

**File:** `backend/rebac_service.py:64-66`
**Issue:** `check_permission` catches ANY exception from the OpenFGA client (network
error, config error, SDK bug) and returns `False`.
This conflates a definitive "access denied" (`False`) with a catastrophic failure
("can't tell"). A caller that expects `True` to grant access will fail securely,
but a caller that expects `False` to *deny* access will fail open. The `add_compliance_control`
endpoint happens to fail closed (403 on `False`), but the service method itself
is unsafe. An auth check must be decisive.
**Fix:** Let exceptions propagate, or wrap them in a specific `ReBACError`. The
caller must handle auth-system unavailability distinctly from a `False` result.

```python
# In backend/rebac_service.py

# Add a custom exception
class ReBACError(Exception):
    """Indicates a failure to communicate with the ReBAC service."""
    pass

# ... in ReBACService.check_permission
        try:
            response = await self.client.check(request)
            return response.allowed
        except Exception as e:
            # Re-raise as a specific, catchable error so callers can distinguish
            # "denied" from "auth system is down".
            raise ReBACError(f"ReBAC check failed: {e}") from e

# In backend/compliance_framework_mgmt_endpoints.py
# The caller must now handle the exception.
    try:
        is_authorized = await rebac.check_permission(user_fga, "add_control", "framework", framework_id)
        if not is_authorized:
            raise HTTPException(status_code=403, detail="Not authorized to add controls to this framework via ReBAC")
    except ReBACError as e:
        logger.error("ReBAC service unavailable: %s", e)
        # Fail closed: if the auth system is down, deny access and alert.
        raise HTTPException(status_code=503, detail="Authorization service is currently unavailable. Please try again later.")
```

## Warnings

### WR-01: Hardcoded OpenFGA user prefix in endpoint

**File:** `backend/compliance_framework_mgmt_endpoints.py:209`
**Issue:** The `add_compliance_control` endpoint hardcodes the FGA user string as `f"user:{current_user.username}"`. The user type/prefix (`user:`) is an authorization model detail that belongs in the `rebac_service`, not its callers. If the model changes to `principal:` or `employee:`, all callers would need to be updated.
**Fix:** The ReBAC service should be responsible for formatting the user object string. Pass the `TokenData` object to the service.

```python
# In backend/rebac_service.py
# Modify check_permission to accept the user object
    async def check_permission(
        self,
        user: Any,  # Expects TokenData or similar object with a username
        relation: str,
        object_type: str,
        object_id: str,
    ) -> bool:
        user_fga = f"user:{getattr(user, 'username', '')}" # Service formats the string
        request = CheckRequest(
            user=user_fga,
            #...
        )
        #...

# In backend/compliance_framework_mgmt_endpoints.py
# Pass the user object directly
    if not await rebac.check_permission(current_user, "add_control", "framework", framework_id):
        raise HTTPException(...)
```

## Info

### IN-01: Global singleton pattern for service

**File:** `backend/rebac_service.py:150-158`
**Issue:** The `get_reback_service` function uses a global variable for the service singleton. This pattern works but makes testing and dependency management more difficult than using FastAPI's dependency injection system. The tests already use `app.dependency_overrides` for other services.
**Fix:** Refactor to use FastAPI's `Depends` system for the `ReBACService` as well. This is a quality/maintainability suggestion, not a bug.

```python
# In backend/rebac_service.py (at the end)
reback_service_instance = ReBACService()
def get_reback_service() -> ReBACService:
    return reback_service_instance

# In backend/compliance_framework_mgmt_endpoints.py
@router.post(...)
async def add_compliance_control(
    #...
    rebac: ReBACService = Depends(get_reback_service),
    current_user=Depends(get_current_user),
):
    # use 'rebac' directly
```

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
