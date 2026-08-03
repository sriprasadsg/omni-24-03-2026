import pytest
import asyncio
from unittest.mock import patch, AsyncMock

from backend.soc_integration_service import push_ocsf_event
from backend.siem_engine import SiemEngine
from backend.ueba_service import _persist_alert
from backend.remediation_audit_service import write_audit

def _make_case_doc():
    return {
        "id": "CASE-123",
        "title": "Test Alert",
        "severity": "High",
        "description": "Sample investigation",
        "status": "Open",
        "createdAt": "2023-01-01T00:00:00Z"
    }


def test_soc_integration_basic_structure():
    # Test that push_ocsf_event builds OCSF payload with required UIDs
    async def main():
        sample_doc = _make_case_doc()
        event_type = "threat.correlation"

        with patch('backend.soc_integration_service._webhook_service') as svc:
            svc.trigger_webhook = AsyncMock()
            # Call push_ocsf_event — fire-and-forget via create_task
            await push_ocsf_event(event_type, sample_doc)

            # Let the background task finish
            await asyncio.sleep(0)

            # Assert trigger_webhook was called once with correct event_type
            svc.trigger_webhook.assert_awaited_once()
            args, kwargs = svc.trigger_webhook.call_args
            assert args[0] == event_type
            assert isinstance(args[1], dict)
            # Payload should contain class_uid 2004 and category_uid 2
            payload = args[1]
            assert payload['class_uid'] == 2004
            assert payload['category_uid'] == 2
            assert payload['type_uid'] == 200401

    asyncio.run(main())

def test_siem_engine_trigger_alert_calls_push_ocsf():
    # Setup a mock db and case_doc
    import backend.siem_engine
    import backend.siem_engine as siem_engine_mod

    async def main():
        with patch.object(siem_engine_mod.SiemEngine, '__init__', return_value=None):
            engine = siem_engine_mod.SiemEngine(None)
            engine.db = type('MockDB', (), {
                'security_cases': type('MockCol', (), {
                    'insert_one': AsyncMock()
                })()
            })()

            with patch('soc_integration_service.push_ocsf_event') as mock_push:
                mock_push.return_value = None
                # Mock rule and tenant_id
                rule = {'name': 'Test Rule', 'severity': 'Medium'}
                tenant_id = 'test_tenant'
                event = {'id': 'test-event', 'raw': 'test-raw', 'agent_id': 'agent-001'}

                # Call _trigger_alert
                await engine._trigger_alert(event, rule, tenant_id)

                assert mock_push.called
                args, kwargs = mock_push.call_args
                assert args[0] == 'threat.correlation'

    asyncio.run(main())

def test_delivery_failure_is_non_fatal_for_ueba_and_remediation():
    # Task 2 acceptance criterion: a failing push_ocsf_event must not stop
    # _persist_alert's or write_audit's own insert from completing.
    import backend.ueba_service as ueba_mod
    import backend.remediation_audit_service as audit_mod

    async def main():
        with patch('soc_integration_service.push_ocsf_event', side_effect=RuntimeError("SIEM down")):
            alerts_col = type('MockCol', (), {'insert_one': AsyncMock()})()
            blockchain_col = type('MockCol', (), {
                'find_one': AsyncMock(return_value=None),
                'insert_one': AsyncMock(),
            })()
            mock_db = type('MockDB', (), {
                'security_alerts': alerts_col,
                'blockchain_audit': blockchain_col,
            })()

            await ueba_mod._persist_alert(mock_db, "shadow_ai_detected", "High", "t", "d", {})
            await asyncio.sleep(0)
            alerts_col.insert_one.assert_awaited_once()

            audit_col = type('MockCol', (), {
                'insert_one': AsyncMock(return_value=type('Result', (), {'inserted_id': 'abc'})())
            })()
            audit_db = type('MockDB', (), {'remediation_audit': audit_col})()

            audit_id = await audit_mod.write_audit(audit_db, "tenant-1", {"stage": "selected"})
            await asyncio.sleep(0)
            assert audit_id == "abc"
            audit_col.insert_one.assert_awaited_once()

    asyncio.run(main())

def test_multiple_call_sites_exist():
    # Verify there are at least 3 call sites of push_ocsf_event across the three services
    import inspect
    import backend.siem_engine
    import backend.ueba_service
    import backend.remediation_audit_service

    # Count async function definitions that reference push_ocsf_event
    def has_push_call(obj_file, attr_name):
        src = inspect.getsource(obj_file)
        return 'push_ocsf_event' in src

    call_count = 0
    call_count += has_push_call(backend.siem_engine.SiemEngine._trigger_alert, 'push_ocsf_event')
    call_count += has_push_call(backend.ueba_service._persist_alert, 'push_ocsf_event')
    call_count += has_push_call(backend.remediation_audit_service.write_audit, 'push_ocsf_event')

    assert call_count >= 3, f'Expected at least 3 call sites, found {call_count}'

if __name__ == '__main__':
    pytest.main(['-q'])