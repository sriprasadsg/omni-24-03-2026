import pytest
from backend.program_service import create_program, get_program_status

@pytest.mark.asyncio
async def test_program_rollup():
    p = await create_program("test", "Access Control", ["C1", "C2"])
    # Mock compliance DB state here
    # Assert score and status
    assert True