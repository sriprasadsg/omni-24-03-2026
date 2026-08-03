import pytest
import asyncio
from unittest.mock import patch, AsyncMock

from backend.siam_integration_service import push_ocsf_event
from backend.siem_engine import SIEMEngine
from backend.ueba_service import UEBAService
from backend.remediation_audit_service import RemediationAuditService

def _make_sample_case_doc():
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
    sample_doc = _make_sample_case_doc()
    event_type = "threat.correlation"

    # Mock WebhookService to capture dispatch
    with patch('backend.ocsf_endpoints.WebhookService') as mock_webhook_service:
        mock_instance = AsyncMock()
        mock_webhook_service.return_value = mock_instance

        # Call push_ocsf_event
        asyncio.run(push_ocsf_event(event_type, sample_doc))

        # Assert WebhookService was called once with correct event_type
        mock_instance.trigger_webhook.assert_awaited_once()
        args, kwargs = mock_instance.trigger_webhook.call_args
        assert args[0] == event_type
        assert isinstance(args[1], dict)
        # Payload should contain class_uid 2004 and category_uid 2
        payload = args[1]
        assert payload['class_uid'] == 2004
        assert payload['category_uid'] == 2
        assert payload['type_uid'] == 200401

def test_siem_engine_trigger_alert_calls_push_ocsf():
    # Setup a mock db and case_doc
    import backend.siem_engine
    import backend.siem_engine as siem_engine_mod

    with patch.object(siem_engine_mod.SiemEngine, '__init__', return_value=None):
        engine = siem_engine_mod.SiemEngine(None)
        engine.db = type('MockDB', (), {
            'security_cases': type('MockCol', (), {
                'insert_one': AsyncMock()
            })()
        })()

        # Mock the push_ocsf_event function
        with patch('backend.siem_engine.push_ocsf_event') as mock_push:
            # Mock rule and tenant_id
            rule = {'name': 'Test Rule', 'severity': 'Medium'}
            tenant_id = 'test_tenant'
            event = {'id': 'test-event', 'raw': 'test-raw'}

            # Call _trigger_alert
            asyncio.run(engine._trigger_alert(event, rule, tenant_id))

            # Verify push_ocsf_event was called with correct event_type
            assert mock_push.called
            mock_push.assert_awaited_once_with('threat.correlation', event)

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