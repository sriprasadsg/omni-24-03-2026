# Testing Patterns

**Analysis Date:** 2026-06-17

## Test Framework

**Runner:**
- Python: pytest (configured in `pytest.ini`)
- TypeScript: vitest (configured in `package.json` scripts)

**Config (Python):**
- File: `pytest.ini`
- Settings:
  ```ini
  [pytest]
  testpaths = . backend
  python_files = test_*.py
  python_classes = Test*
  python_functions = test_*
  addopts = -v --tb=short -p no:anyio
  asyncio_mode = auto
  filterwarnings =
      ignore::DeprecationWarning
      ignore::PendingDeprecationWarning
  ```
- Asyncio mode: `auto` — pytest-asyncio handles async tests automatically
- Plugins: `-p no:anyio` — disables anyio plugin to prevent conflicts

**Run Commands:**
```bash
# Run all Python tests
pytest

# Run all TypeScript tests
npm test                # Single run (vitest run)
npm run test:watch    # Watch mode (vitest)

# Run specific test file
pytest tests/test_ai_remediation.py
pytest agent/test_compliance.py
```

**Assertion Library:**
- Python: `unittest.mock` for mocking, `assert` statements for assertions
- TypeScript: vitest built-in (not yet in use; no test files in src/)

## Test File Organization

**Location:**
- Python: co-located or in `tests/` directory
- Pattern: `test_*.py` in project root or `tests/` subdirectory (e.g., `tests/test_ai_remediation.py`, `agent/test_compliance.py`)
- TypeScript: co-located with source (not yet used)

**Directory Structure:**
```
/tests/
  test_ai_remediation.py      # AI remediation engine tests
  test_network_discovery.py   # Network discovery tests

/agent/
  test_compliance.py          # Compliance capability tests
  test_comp.py               # Component tests
  test_self_healing.py       # Self-healing capability tests
  test_update_capability.py  # Update capability tests
  capabilities/
    test_linux_compliance_mock.py  # Linux compliance mock tests

/code-review-graph-main/tests/  # Third-party: code review tests
  test_wiki.py
  test_hints.py
  test_changes.py
  test_parser.py
  ...
```

**Naming:**
- Test files: `test_<feature>.py`
- Test functions: `test_<scenario>()` (e.g., `test_ai_remediation()`, `test_compliance()`)
- Test classes: Not commonly used; functions preferred

## Test Structure

**Suite Organization (Python):**
```python
# Example from test_ai_remediation.py
import logging
import sys
import os
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.autonomous_actions.remediation import AutonomousRemediationEngine

def test_ai_remediation():
    logging.basicConfig(level=logging.INFO)
    
    # Setup: Create mock objects
    mock_reasoning = MagicMock()
    mock_llm = MagicMock()
    mock_reasoning.llm = mock_llm
    
    # Setup: Configure mock return values
    mock_llm.plan_remediation.return_value = {
        "name": "Test Remediation Plan",
        "affected_services": ["test-service"],
        "steps": [...]
    }
    
    # Act: Initialize system under test with mocks
    engine = AutonomousRemediationEngine(mock_reasoning)
    success = engine.execute_remediation(issue)
    
    # Assert: Verify results
    if success:
        print("✅ AI-driven remediation test passed!")
    else:
        print("❌ AI-driven remediation test failed!")
```

**Patterns:**
- No class-based test structure (using plain functions)
- Path setup: `sys.path.append()` to import from parent directories
- Logging: `logging.basicConfig(level=logging.INFO)` in each test function
- Main guard: `if __name__ == "__main__": test_ai_remediation()`

## Mocking

**Framework:**
- Python: `unittest.mock.MagicMock` and `MagicMock()`
- TypeScript: Not yet implemented

**Patterns (Python):**
```python
# Basic mock creation
mock_obj = MagicMock()

# Configure return value for method
mock_obj.method_name.return_value = {
    "key": "value",
    "items": [...]
}

# Inject mock into system under test
system = SystemUnderTest(mock_obj)
result = system.do_something()

# Verify mock was called (optional)
mock_obj.method_name.assert_called_once()
```

**What to Mock:**
- External services (LLM providers, database connections, cloud APIs)
- I/O operations (file system, network requests)
- Non-deterministic operations (time-based logic, random values)

**What NOT to Mock:**
- Business logic under test (create real instances when possible)
- Utility functions (time helpers, parsers)
- Data validation logic

## Fixtures and Factories

**Test Data:**
```python
# Example: Mock remediation plan structure
mock_plan = {
    "name": "Test Remediation Plan",
    "affected_services": ["test-service"],
    "affected_files": ["C:\\temp\\test.txt"],
    "steps": [
        {
            "action": "restart_service",
            "target": "test-service",
            "description": "Restarting test service"
        },
        {
            "action": "run_command",
            "target": "echo 'Hello World'",
            "description": "Running test command"
        }
    ]
}
```

**Location:**
- Fixtures embedded in test function (no pytest fixtures framework observed)
- Mock objects created inline with `MagicMock()`
- No separate fixture files or factories

**Patterns:**
- MagicMock objects with configured return values
- Inline setup within test function
- No parameterized tests or shared fixtures (yet)

## Coverage

**Requirements:**
- No explicit coverage target enforced
- Bandit security scanning enabled (see `backend/pyproject.toml`)

**View Coverage (TypeScript):**
```bash
npm test -- --coverage     # Generate coverage report (vitest)
```

**Coverage Config:**
- Not explicitly configured for Python or TypeScript
- Focus on security scanning (Bandit) rather than coverage metrics

## Test Types

**Unit Tests:**
- Scope: Individual functions/methods with mocked dependencies
- Approach: Mock external services, test business logic in isolation
- Example: `test_ai_remediation()` tests `AutonomousRemediationEngine.execute_remediation()` with mocked LLM and reasoning engine
- Pattern: Create mocks, inject into system, verify output

**Integration Tests:**
- Scope: Real database, real service interactions (limited)
- Approach: Use test fixtures or sandboxed services
- Example: `test_compliance.py` may interact with real compliance capabilities
- Not yet widespread; mostly unit tests with mocks observed

**E2E Tests:**
- Framework: Not yet implemented; no test files in src/
- Would require Playwright, Cypress, or similar for browser automation
- Vitest configured for potential unit/integration tests

**Async Testing:**
- Python: Pytest with `asyncio_mode = auto` handles async test discovery and execution
- Pattern: `async def test_function()` with `await` for async operations
- Async mock: `MagicMock()` supports async mocks via `.return_value` configuration
- Not yet observed in current tests; most use synchronous mocking

## Common Patterns

**Running Tests (Python):**
```bash
# From project root
pytest agent/test_compliance.py -v

# With logging
pytest tests/test_ai_remediation.py -v -s  # -s shows print statements

# Run all tests in directory
pytest tests/ -v
```

**Error Testing:**
```python
# Capture and assert exceptions
try:
    result = system.do_something_invalid()
    assert False, "Should have raised exception"
except ValueError as e:
    assert "expected error message" in str(e)
```

**Async Testing (Future Pattern):**
```python
# Expected pytest-asyncio pattern for async code
async def test_async_operation():
    result = await async_function()
    assert result is not None
```

**Mock Verification:**
```python
# Verify mock was called correctly
mock_obj.method.assert_called_once()
mock_obj.method.assert_called_with(expected_arg)
mock_obj.method.assert_not_called()
```

## TypeScript Testing Setup

**Config:**
- File: `package.json` (no vitest.config.ts found)
- Test script: `"test": "vitest run"`
- Watch script: `"test:watch": "vitest"`

**Planned Structure:**
- Test files: `src/**/*.test.ts` or `src/**/*.spec.ts`
- Testing library: `@testing-library/react` (in devDependencies)
- Framework: vitest (lightweight, Vite-native)

**Example Test (Planned):**
```typescript
// components/AgentList.test.tsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentList } from './AgentList';

describe('AgentList', () => {
  let mockProps: AgentListProps;

  beforeEach(() => {
    mockProps = {
      agents: [],
      selectedAgentIds: new Set(),
      onToggleSelection: vi.fn(),
      // ... other handlers
    };
  });

  it('renders empty state when no agents', () => {
    render(<AgentList {...mockProps} />);
    // assertions
  });

  it('calls onToggleSelection when checkbox clicked', async () => {
    const { user } = render(<AgentList {...mockProps} />);
    // test interaction
  });
});
```

## Test Execution Flow

**Python Test Execution:**
1. Pytest discovers files matching `test_*.py` pattern
2. Each test function runs independently (no class coupling)
3. Setup: Initialize mocks and test data
4. Act: Call system under test
5. Assert: Verify output and side effects
6. Teardown: MagicMock objects cleaned up automatically

**Output:**
```
tests/test_ai_remediation.py::test_ai_remediation PASSED
agent/test_compliance.py::test_compliance PASSED
```

**Failure Handling:**
- Failed assertions raise `AssertionError`
- Uncaught exceptions fail the test
- Pytest captures and displays stack trace with `--tb=short` format

## Known Gaps

**TypeScript Testing:**
- No test files in src/ directory (vitest configured but not yet used)
- React component tests not yet implemented
- Service tests (apiService.ts, socketService.ts) untested

**Python Testing:**
- Compliance capability tests call actual implementations (see `test_compliance.py`: no mocking of OS-level operations)
- Network tests may require real network setup (see `test_network_discovery.py`)
- Limited async testing patterns observed

**Missing Coverage Areas:**
- Database layer: No `test_database.py` for TenantIsolatedCollection
- Authentication: No comprehensive JWT validation tests
- Error handling: Limited exception scenario testing
- WebSocket: No tests for socketio event handlers

---

*Testing analysis: 2026-06-17*
